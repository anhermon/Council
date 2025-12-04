"""Review execution logic."""

import asyncio
import time
from typing import Any

import click
import logfire

from ...agents import CouncilDeps, ReviewResult, get_councilor_agent
from ...tools.debug import DebugWriter
from ...tools.metrics_collector import get_metrics_collector
from ...tools.repomix import extract_code_from_xml
from ..ui.spinner import Spinner
from ..ui.streaming import cleanup_spinner_task, create_event_stream_handler


async def run_agent_review(
    packed_xml: str, deps: CouncilDeps, spinner: Spinner, review_id: str | None = None
) -> ReviewResult:
    """
    Run the councilor agent and get review results.

    Args:
        packed_xml: Packed XML context from Repomix
        deps: Council dependencies
        spinner: Spinner instance for status updates
        review_id: Optional review ID for metrics tracking

    Returns:
        ReviewResult from the agent
    """
    agent = get_councilor_agent()

    # Create debug writer if enabled
    debug_writer = DebugWriter(review_id=review_id, file_path=deps.file_path)

    # Extract code from XML for cleaner presentation to the agent
    extracted_code = extract_code_from_xml(packed_xml)

    # Write extracted code to debug file (this is what's actually sent to the agent)
    if debug_writer.enabled:
        debug_writer.write_entry(
            "xml_context",
            {
                "extracted_code": extracted_code,
                "extracted_code_length": len(extracted_code),
                "xml_length": len(packed_xml),  # Keep for reference, but don't duplicate content
            },
        )

    # Use extracted code for the user prompt (cleaner for agent)
    user_prompt = f"Please review the following code:\n\n{extracted_code}"
    debug_writer.write_user_prompt(user_prompt)

    # Store debug writer in thread-safe storage for access in system prompt function
    from ...agents import councilor

    with councilor._debug_writers_lock:
        councilor._debug_writers[deps.file_path] = debug_writer

    event_handler = create_event_stream_handler(spinner, debug_writer)
    metrics_collector = get_metrics_collector()

    # Retry logic for rate limit errors
    max_retries = 3
    base_delay = 5.0  # seconds

    for attempt in range(max_retries):
        spinner_task = None
        agent_start = time.time()
        try:
            # Start spinner task (only if enabled)
            if spinner.enabled:
                spinner_task = asyncio.create_task(spinner.run())

            # Run the councilor agent with streaming
            async with agent.run_stream(
                user_prompt,
                deps=deps,
                event_stream_handler=event_handler,
            ) as agent_run:
                # Stream structured output as it's being generated
                results_received = False
                async for partial_result in agent_run.stream_output():
                    # Update status when we start receiving results
                    if partial_result and not results_received:
                        results_received = True
                        if spinner_task and not spinner_task.done():
                            spinner_task.cancel()
                            spinner_task = None
                        spinner.stop()
                        if spinner.enabled:
                            spinner.show_status("Receiving review results...")

                # Extract the structured result from the streamed run
                review_result: ReviewResult = await agent_run.get_output()

                # Capture tool results from the run history for debug output
                # Note: Pydantic AI stores tool results in assistant messages as tool result parts
                if debug_writer:
                    try:
                        run_obj = getattr(agent_run, "run", None)
                        if run_obj and hasattr(run_obj, "messages"):
                            tool_calls_tracked: dict[
                                str, dict[str, Any]
                            ] = {}  # Track tool calls by call_id

                            for message in run_obj.messages:
                                getattr(message, "role", None)
                                parts = getattr(message, "parts", [])

                                for part in parts:
                                    part_type = type(part).__name__

                                    # Track tool calls (from assistant messages)
                                    if hasattr(part, "tool_name") and hasattr(part, "call_id"):
                                        call_id = part.call_id
                                        tool_calls_tracked[call_id] = {
                                            "tool_name": part.tool_name,
                                            "arguments": getattr(part, "arguments", None),
                                        }

                                    # Capture tool results (from assistant messages after tool execution)
                                    # Tool results are typically FunctionToolResultPart objects
                                    # Check if this part has result-related attributes
                                    has_result_attr = (
                                        hasattr(part, "result")
                                        or hasattr(part, "output")
                                        or hasattr(part, "content")
                                        or hasattr(part, "data")
                                    )
                                    has_tool_attrs = hasattr(part, "tool_name") or hasattr(
                                        part, "call_id"
                                    )

                                    # This is likely a tool result part if it has result attributes
                                    # or if it's a tool-related part type
                                    if has_result_attr or (
                                        has_tool_attrs and "result" in part_type.lower()
                                    ):
                                        # Try to get tool call ID to match with tool call
                                        call_id = (
                                            getattr(part, "call_id", None)
                                            or getattr(part, "tool_call_id", None)
                                            or getattr(part, "id", None)
                                        )

                                        # Get result data - try multiple attributes
                                        result = None
                                        for attr in ["result", "output", "content", "data"]:
                                            if hasattr(part, attr):
                                                val = getattr(part, attr)
                                                if val is not None:
                                                    result = val
                                                    break

                                        # Get tool name from tracked calls or from part
                                        tool_name = None
                                        if call_id and call_id in tool_calls_tracked:
                                            tool_name = tool_calls_tracked[call_id]["tool_name"]
                                        else:
                                            tool_name = getattr(part, "tool_name", None)

                                        error = getattr(part, "error", None)

                                        # Only write if we have a tool name and (result or error)
                                        if tool_name and (result is not None or error is not None):
                                            debug_writer.write_tool_output(
                                                tool_name,
                                                result,
                                                call_id,
                                                error,
                                            )
                    except Exception as e:
                        # Log but don't fail if we can't capture tool results
                        logfire.debug(
                            "Could not capture tool results for debug", error=str(e), exc_info=True
                        )

                agent_duration = time.time() - agent_start

                # Write agent response to debug file
                debug_writer.write_agent_response(
                    review_result,
                    metadata={
                        "duration_seconds": agent_duration,
                        "issues_found": len(review_result.issues),
                        "severity": review_result.severity,
                    },
                )

                # Clean up debug writer from storage
                with councilor._debug_writers_lock:
                    councilor._debug_writers.pop(deps.file_path, None)

                if review_id:
                    metrics_collector.record_tool_execution(
                        "councilor_agent", agent_duration, success=True
                    )
                return review_result
        except asyncio.CancelledError:
            # Don't catch cancellation - let it propagate
            raise
        except Exception as e:
            # Check if this is a rate limit error (429)
            error_str = str(e).lower()
            is_rate_limit = (
                "429" in error_str
                or "rate limit" in error_str
                or "ratelimiterror" in error_str
                or "throttling" in error_str
                or "too many tokens" in error_str
            )

            # Ensure spinner is always cleaned up on error
            await cleanup_spinner_task(spinner_task, spinner)

            # Retry on rate limit errors
            if is_rate_limit and attempt < max_retries - 1:
                delay = base_delay * (2**attempt)  # Exponential backoff
                if spinner.enabled:
                    click.echo(
                        f"\n⚠️  Rate limit hit, retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})...",
                        err=True,
                    )
                await asyncio.sleep(delay)
                continue
            else:
                # Write error to debug file
                debug_writer.write_error(str(e), error_type=type(e).__name__)
                # Clean up debug writer from storage
                with councilor._debug_writers_lock:
                    councilor._debug_writers.pop(deps.file_path, None)
                # Re-raise if not a rate limit error or out of retries
                raise
        finally:
            # Clean up spinner
            await cleanup_spinner_task(spinner_task, spinner)

    # Should never reach here, but just in case
    raise RuntimeError("Failed to get review result after retries")
