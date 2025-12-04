"""Event stream handling for agent operations."""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterable, Callable
from typing import Any

from pydantic_ai.messages import (
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPartDelta,
)

from ...tools.debug import DebugWriter
from ..ui.spinner import Spinner


def create_event_stream_handler(
    spinner: Spinner, debug_writer: DebugWriter | None = None
) -> Callable:
    """
    Create an event stream handler for agent streaming events.

    Args:
        spinner: Spinner instance to update with status
        debug_writer: Optional debug writer for capturing tool calls and outputs

    Returns:
        Event stream handler function
    """
    last_status = ""  # Track last status to avoid duplicate updates
    tool_calls_tracked: dict[str, str] = {}  # Track tool calls by call_id -> tool_name

    async def event_stream_handler(
        _ctx: Any,
        event_stream: AsyncIterable[
            PartStartEvent
            | PartDeltaEvent
            | FunctionToolCallEvent
            | FunctionToolResultEvent
            | FinalResultEvent
        ],
    ) -> None:
        """Handle streaming events to show progress."""
        nonlocal last_status, tool_calls_tracked
        async for event in event_stream:
            if isinstance(event, PartStartEvent):
                if hasattr(event.part, "tool_name"):
                    new_status = f"Calling tool: {event.part.tool_name}..."
                    # Capture tool call for debug
                    if debug_writer and hasattr(event.part, "tool_name"):
                        tool_name = event.part.tool_name
                        call_id = getattr(event.part, "call_id", None)
                        arguments = getattr(event.part, "arguments", None)
                        # Always try to parse arguments, even if None (to ensure they're logged)
                        if arguments:
                            try:
                                # Try to parse arguments if they're a string
                                if isinstance(arguments, str):
                                    arguments = json.loads(arguments)
                            except Exception:
                                # If parsing fails, keep as string
                                pass
                        # Log tool call with arguments (even if empty/None)
                        debug_writer.write_tool_call(tool_name, arguments or {}, call_id)
                else:
                    new_status = "Generating review..."
                if new_status != last_status:
                    spinner.show_status(new_status)
                    last_status = new_status
            elif isinstance(event, PartDeltaEvent):
                # Text is being generated - only update if spinner is not active
                # to avoid conflicts with the spinner loop
                if isinstance(event.delta, TextPartDelta) and not spinner.active:
                    new_status = "Writing review..."
                    if new_status != last_status:
                        spinner.show_status(new_status)
                        last_status = new_status
            elif isinstance(event, FunctionToolCallEvent):
                new_status = f"Executing: {event.part.tool_name}..."
                # Track tool call for later result matching
                tool_call_id = getattr(event.part, "tool_call_id", None)
                if tool_call_id:
                    tool_calls_tracked[tool_call_id] = event.part.tool_name
                # Note: Tool results are captured via FunctionToolResultEvent, not here
                # FunctionToolCallEvent fires when tool is called, not when it completes
                if new_status != last_status:
                    spinner.show_status(new_status)
                    last_status = new_status
            elif isinstance(event, FunctionToolResultEvent):
                # Capture tool output for debug - this event fires when tool completes
                if debug_writer:
                    tool_call_id = event.tool_call_id
                    # Get the result content from the ToolReturnPart
                    result_content = getattr(event.result, "content", None)
                    # Get tool name from tracked calls
                    tool_name = tool_calls_tracked.get(tool_call_id, "unknown_tool")

                    error = getattr(event.result, "error", None)
                    debug_writer.write_tool_output(
                        tool_name,
                        result_content,
                        tool_call_id,
                        error,
                    )
            elif isinstance(event, FinalResultEvent):
                new_status = "Finalizing review..."
                if new_status != last_status:
                    spinner.show_status(new_status)
                    last_status = new_status

    return event_stream_handler


async def cleanup_spinner_task(task: asyncio.Task | None, spinner: Spinner) -> None:
    """Safely cleanup spinner task."""
    spinner.stop()
    if task and not task.done():
        task.cancel()
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=Spinner.SPINNER_CLEANUP_TIMEOUT)
