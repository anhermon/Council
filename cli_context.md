# Code Review Context

**Generated:** 2025-12-04 13:37:28 UTC

## File: /Users/angelhermon/workspace/council/src/council/cli

**Language:** unknown

## System Prompt

```

You are a Senior Code Reviewer with expertise in software engineering best practices, code quality, security, performance, and maintainability.

Your task is to analyze the provided code and provide a comprehensive review.

CRITICAL: Before reporting any issue, VERIFY that it actually exists in the ACTUAL CODE. Do NOT report:
- Issues that don't exist in the actual code
- Problems that are already correctly implemented
- Style preferences that are subjective and don't represent actual bugs
- Non-existent syntax errors

Only report REAL issues that:
- Actually exist in the actual code
- Represent genuine bugs, security vulnerabilities, or code quality problems
- Can be verified by examining the actual code logic

Analyze the code for:
- Code quality and best practices
- Security vulnerabilities
- Performance issues
- Maintainability concerns
- Style and consistency (only report if it causes actual problems)
- Potential bugs or edge cases
- Documentation quality

Provide specific, actionable feedback with severity levels (low, medium, high, critical).
Include accurate line numbers and exact code snippets when relevant.
Suggest concrete fixes when possible.

IMPORTANT: When calling tools that require file paths (read_file, analyze_imports, run_static_analysis, etc.):
- If you see a filename in the code (e.g., "config.py", "main.py"), you can pass just the filename - the tool will automatically search for it in the project
- For better results, use the full relative path from the project root (e.g., "src/council/config.py")
- The tools will intelligently resolve paths relative to the project root or search recursively if needed

Report issues comprehensively - aim to identify all significant issues in a single review to minimize iterations. Prioritize higher severity issues but don't skip lower severity ones if they're legitimate concerns.

```

## Knowledge Base

*No relevant knowledge base content loaded.*

## Code to Review

```unknown

=== File: ui/__init__.py ===
"""UI components for CLI."""

from .output import print_markdown, print_pretty
from .spinner import Spinner
from .streaming import cleanup_spinner_task, create_event_stream_handler

__all__ = [
    "Spinner",
    "create_event_stream_handler",
    "cleanup_spinner_task",
    "print_pretty",
    "print_markdown",
]

=== File: ui/streaming.py ===
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

=== File: ui/spinner.py ===
"""Terminal spinner for async operations."""

import asyncio
import shutil
import sys


class Spinner:
    """Manages spinner display for async operations."""

    SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    DEFAULT_TERMINAL_WIDTH = 80
    SPINNER_REFRESH_RATE = 0.15  # seconds between spinner updates
    SPINNER_CLEANUP_TIMEOUT = 1.0  # seconds to wait for spinner task cleanup

    def __init__(self, enabled: bool | None = None) -> None:
        """
        Initialize the spinner.

        Args:
            enabled: Whether spinner is enabled. If None, auto-detect based on TTY.
        """
        self.current_status = "Analyzing code structure..."
        self.spinner_idx = 0
        self.active = False
        # Auto-detect if enabled is None: only enable if stderr is a TTY
        if enabled is None:
            self.enabled = self._is_tty()
        else:
            self.enabled = enabled

    @staticmethod
    def _is_tty() -> bool:
        """Check if stderr is a TTY (interactive terminal)."""
        try:
            return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
        except Exception:
            return False

    def show_status(self, message: str | None = None) -> None:
        """Show current status with spinner (only if enabled)."""
        if not self.enabled:
            return
        if message:
            self.current_status = message
        status_msg = (
            f"\r🤖 {self.current_status} "
            f"{self.SPINNER_CHARS[self.spinner_idx % len(self.SPINNER_CHARS)]}"
        )
        self._safe_stderr_write(status_msg)
        self.spinner_idx += 1

    @staticmethod
    def _safe_stderr_write(message: str) -> None:
        """Safely write to stderr with fallback."""
        try:
            if hasattr(sys.stderr, "write") and sys.stderr.writable():
                sys.stderr.write(message)
                sys.stderr.flush()
        except OSError:
            # Specific I/O errors - try stdout as fallback
            try:
                sys.stdout.write(message)
                sys.stdout.flush()
            except OSError:
                # Both stderr and stdout failed, silently ignore
                pass
        except AttributeError as e:
            # Handle missing methods gracefully
            # Log to stderr if possible, but don't fail
            try:
                if hasattr(sys.stderr, "write"):
                    sys.stderr.write(f"Warning: stderr attribute error: {e}\n")
            except Exception:
                pass  # If even logging fails, silently ignore

    async def run(self) -> None:
        """Run the spinner loop (only if enabled)."""
        if not self.enabled:
            return
        self.active = True
        try:
            while self.active:
                self.show_status()
                await asyncio.sleep(self.SPINNER_REFRESH_RATE)
        except asyncio.CancelledError:
            # Expected when cancelling the task
            pass
        except OSError as e:
            # Handle OS-level errors (e.g., terminal issues)
            if self.enabled:
                Spinner._safe_stderr_write(f"\nSpinner OS error: {e}\n")
        except Exception as e:
            # Log unexpected errors but don't crash
            if self.enabled:
                Spinner._safe_stderr_write(f"\nUnexpected spinner error: {e}\n")
        finally:
            self.active = False

    def stop(self) -> None:
        """Stop the spinner and clear the line."""
        self.active = False
        if not self.enabled:
            return
        # Get terminal width or use default
        try:
            width = shutil.get_terminal_size().columns
        except Exception:
            width = self.DEFAULT_TERMINAL_WIDTH
        self._safe_stderr_write("\r" + " " * width + "\r")

=== File: ui/output.py ===
"""Output formatting for review results."""

import click

from ...agents import ReviewResult


def print_pretty(review_result: ReviewResult) -> None:
    """Print review results in a pretty format."""
    click.echo("\n" + "=" * 80)
    click.echo("📋 REVIEW SUMMARY")
    click.echo("=" * 80)
    click.echo(f"\n{review_result.summary}\n")
    click.echo(f"Overall Severity: {review_result.severity.upper()}\n")

    if review_result.issues:
        click.echo("=" * 80)
        click.echo("🔍 ISSUES FOUND")
        click.echo("=" * 80)
        for i, issue in enumerate(review_result.issues, 1):
            click.echo(f"\n{i}. [{issue.severity.upper()}] {issue.description}")
            if issue.line_number:
                click.echo(f"   Line: {issue.line_number}")
            if issue.code_snippet:
                click.echo(f"   Code: {click.style(issue.code_snippet, dim=True)}")
    else:
        click.echo("✅ No issues found!")

    if review_result.code_fix:
        click.echo("\n" + "=" * 80)
        click.echo("💡 SUGGESTED FIX")
        click.echo("=" * 80)
        click.echo(f"\n{review_result.code_fix}\n")


def print_markdown(review_result: ReviewResult) -> None:
    """Print review results in markdown format."""
    click.echo("# Code Review Results\n")
    click.echo(f"## Summary\n\n{review_result.summary}\n")
    click.echo(f"**Overall Severity:** {review_result.severity.upper()}\n")

    if review_result.issues:
        click.echo("## Issues Found\n")
        for i, issue in enumerate(review_result.issues, 1):
            click.echo(f"### {i}. {issue.description}\n")
            click.echo(f"- **Severity:** {issue.severity.upper()}")
            click.echo(f"- **Category:** {issue.category.upper()}")
            if issue.line_number:
                click.echo(f"- **Line:** {issue.line_number}")
            if issue.code_snippet:
                click.echo(f"- **Code:**\n  ```\n  {issue.code_snippet}\n  ```")
            if issue.related_files:
                click.echo(f"- **Related Files:** {', '.join(issue.related_files)}")
            if issue.suggested_priority:
                click.echo(f"- **Priority:** {issue.suggested_priority}/10")
            if issue.references:
                click.echo(f"- **References:** {', '.join(issue.references)}")
            if issue.auto_fixable:
                click.echo("- **Auto-fixable:** Yes")
            click.echo()

    if review_result.code_fix:
        click.echo("## Suggested Fix\n")
        click.echo(f"```\n{review_result.code_fix}\n```\n")

=== File: core/context_builder.py ===
"""Context builder for review context command."""

from ...agents import CouncilDeps
from ...agents.councilor import detect_language, get_relevant_knowledge
from ...config import get_settings
from ...tools.repomix import extract_code_from_xml

settings = get_settings()


async def build_review_context(
    packed_xml: str,
    deps: CouncilDeps,
) -> dict[str, str | dict]:
    """
    Build review context for external agents.

    Args:
        packed_xml: Packed XML context from Repomix
        deps: Council dependencies

    Returns:
        Dictionary containing extracted_code, system_prompt, knowledge_base, file_path, language, and review_checklist
    """
    # Extract code from XML
    extracted_code = extract_code_from_xml(packed_xml)

    # Load relevant knowledge
    knowledge_base, loaded_filenames = await get_relevant_knowledge([deps.file_path])

    # Detect language
    language = detect_language(deps.file_path)

    # Build system prompt using template logic
    system_prompt = await _build_system_prompt(deps, knowledge_base, language, loaded_filenames)

    # Create review checklist/prompt
    review_checklist = _create_review_checklist(language, deps.review_phases)

    return {
        "extracted_code": extracted_code,
        "system_prompt": system_prompt,
        "knowledge_base": knowledge_base,
        "file_path": deps.file_path,
        "language": language,
        "metadata": {
            "extra_instructions": deps.extra_instructions,
            "review_phases": deps.review_phases,
            "loaded_knowledge_files": list(loaded_filenames),
        },
        "review_checklist": review_checklist,
    }


async def _build_system_prompt(
    deps: CouncilDeps,
    domain_rules: str,
    language: str,
    _loaded_filenames: set[str],  # Unused but kept for API consistency
) -> str:
    """Build system prompt using template logic."""
    from ...agents.councilor import _get_jinja_env, _validate_extra_instructions

    knowledge_dir = settings.knowledge_dir

    # Load and render the Jinja2 template
    jinja_env = _get_jinja_env()
    template = jinja_env.get_template("system_prompt.j2")

    # Validate extra instructions
    validated_extra_instructions = _validate_extra_instructions(deps.extra_instructions)

    # Check for language-specific files
    language_specific_files: list[str] = []
    if language != "unknown" and knowledge_dir.exists():
        language_patterns = [
            f"{language}_best_practices.md",
            f"{language}_patterns.md",
            f"{language}_guidelines.md",
            f"{language}_standards.md",
            f"{language}_rules.md",
        ]

        for pattern in language_patterns:
            lang_file = knowledge_dir / pattern
            if lang_file.exists():
                language_specific_files.append(pattern)

    # Add phase-specific instructions if phases are specified
    phase_instructions = ""
    if deps.review_phases:
        phase_instructions = f"\n\nREVIEW PHASES: Focus on {', '.join(deps.review_phases)}. "

        if "security" in deps.review_phases:
            phase_instructions += (
                "Prioritize security vulnerabilities and security best practices. "
            )

        if "performance" in deps.review_phases:
            phase_instructions += (
                "Focus on performance bottlenecks, optimization opportunities, and efficiency. "
            )

        if "maintainability" in deps.review_phases:
            phase_instructions += (
                "Emphasize code maintainability, readability, and long-term sustainability. "
            )

        if "best_practices" in deps.review_phases:
            phase_instructions += "Apply general best practices and coding standards. "

    prompt = template.render(
        domain_rules=domain_rules,
        extra_instructions=validated_extra_instructions,
        language=language,
        language_specific_files=language_specific_files,
    )

    return prompt + phase_instructions


def _create_review_checklist(language: str, review_phases: list[str] | None) -> str:
    """
    Create a review checklist/prompt for external agents.

    Args:
        language: Detected programming language
        review_phases: Optional list of review phases

    Returns:
        Review checklist as a string
    """
    checklist = """# Code Review Checklist

You are performing a comprehensive code review. Follow this checklist to ensure a thorough review.

## Review Process

1. **Read and Understand**: Carefully read through all the provided code
2. **Analyze**: Check for issues across all categories below
3. **Document**: Report all findings with accurate line numbers and code snippets
4. **Prioritize**: Focus on higher severity issues first, but report all legitimate issues

## What to Check

### Security
- [ ] SQL injection vulnerabilities
- [ ] XSS (Cross-Site Scripting) vulnerabilities
- [ ] Authentication and authorization issues
- [ ] Sensitive data exposure
- [ ] Insecure random number generation
- [ ] Hardcoded secrets or credentials
- [ ] Insecure deserialization
- [ ] Missing input validation
- [ ] Path traversal vulnerabilities
- [ ] CSRF protection

### Performance
- [ ] N+1 query problems
- [ ] Inefficient algorithms or data structures
- [ ] Memory leaks or excessive memory usage
- [ ] Unnecessary database queries
- [ ] Missing indexes
- [ ] Inefficient loops or iterations
- [ ] Blocking operations in async code
- [ ] Large file operations without streaming

### Code Quality & Maintainability
- [ ] Code duplication (DRY violations)
- [ ] Complex functions (high cyclomatic complexity)
- [ ] Poor naming conventions
- [ ] Missing or inadequate error handling
- [ ] Inconsistent code style
- [ ] Magic numbers without constants
- [ ] Long parameter lists
- [ ] God objects or classes with too many responsibilities

### Best Practices
- [ ] Proper use of design patterns
- [ ] SOLID principles adherence
- [ ] Proper separation of concerns
- [ ] Appropriate use of abstractions
- [ ] Testability concerns
- [ ] Documentation quality
- [ ] Logging and monitoring

### Bugs & Edge Cases
- [ ] Null pointer exceptions
- [ ] Off-by-one errors
- [ ] Race conditions
- [ ] Unhandled edge cases
- [ ] Incorrect logic
- [ ] Type mismatches
- [ ] Boundary condition errors

## Expected Output Format

You must return a structured review result with the following format:

```json
{
  "summary": "Overall summary of the code review (2-3 sentences)",
  "issues": [
    {
      "description": "Clear description of the issue",
      "severity": "low|medium|high|critical",
      "category": "security|performance|maintainability|bug|style|documentation",
      "line_number": 42,
      "code_snippet": "exact code showing the issue",
      "related_files": [],
      "suggested_priority": 8,
      "references": [],
      "auto_fixable": false
    }
  ],
  "severity": "low|medium|high|critical",
  "code_fix": "Optional suggested code fix",
  "cross_file_issues": [],
  "dependency_analysis": {
    "external_dependencies": [],
    "internal_dependencies": [],
    "circular_dependencies": [],
    "unused_imports": []
  }
}
```

## Severity Guidelines

- **critical**: Security vulnerabilities, data loss risks, system crashes
- **high**: Serious bugs, significant performance issues, major security concerns
- **medium**: Code quality issues, moderate bugs, maintainability concerns
- **low**: Style issues, minor improvements, documentation gaps

## Important Notes

- **VERIFY BEFORE REPORTING**: Only report issues that actually exist in the code
- **Be Accurate**: Line numbers and code snippets must be exact
- **Be Comprehensive**: Aim to find all significant issues in a single review
- **Be Specific**: Provide clear, actionable feedback
- **Prioritize**: Focus on higher severity issues but don't skip lower severity ones
"""

    if language != "unknown":
        checklist += "\n## Language-Specific Guidelines\n\n"
        checklist += f"You are reviewing **{language}** code. Apply {language}-specific best practices and conventions.\n"

    if review_phases:
        checklist += "\n## Review Focus\n\n"
        checklist += f"Focus on these phases: {', '.join(review_phases)}\n"

    return checklist

=== File: core/review_executor.py ===
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

=== File: core/__init__.py ===
"""Core review execution logic."""

from .review_executor import run_agent_review

__all__ = ["run_agent_review"]

=== File: __init__.py ===
"""CLI package for The Council."""

from .core.review_executor import run_agent_review
from .main import main
from .ui.output import print_markdown, print_pretty
from .ui.spinner import Spinner
from .ui.streaming import cleanup_spinner_task, create_event_stream_handler
from .utils.errors import handle_common_errors
from .utils.paths import collect_files, resolve_path

__all__ = [
    "main",
    "Spinner",
    "cleanup_spinner_task",
    "collect_files",
    "resolve_path",
    "create_event_stream_handler",
    "run_agent_review",
    "handle_common_errors",
    "print_pretty",
    "print_markdown",
]

=== File: utils/paths.py ===
"""Path resolution and file collection utilities."""

from pathlib import Path

import click


def resolve_path(path: Path) -> Path:
    """
    Resolve a path, handling @ prefix as shorthand for src/council/.

    Args:
        path: Path that may start with @

    Returns:
        Resolved Path

    Raises:
        ValueError: If path contains traversal attempts or is invalid
    """
    path_str = str(path)

    # Validate path doesn't contain traversal attempts
    if ".." in Path(path_str).parts:
        raise ValueError("Path traversal detected: '..' not allowed in path")

    if path_str.startswith("@"):
        # Remove @ prefix and resolve relative to src/council/
        # e.g., @agents -> src/council/agents
        # e.g., @council or @ -> src/council
        folder_name = path_str[1:]

        # Validate folder_name doesn't contain path separators or traversal
        if "/" in folder_name or "\\" in folder_name or ".." in folder_name:
            raise ValueError("Invalid folder name in @ path")

        # Try to resolve relative to current directory first
        base_path = Path.cwd()
        # Check if src/council exists
        if (base_path / "src" / "council").exists():
            # If folder_name is empty or matches "council", resolve to src/council itself
            if not folder_name or folder_name == "council":
                resolved = base_path / "src" / "council"
            else:
                resolved = base_path / "src" / "council" / folder_name
        else:
            # Fall back to treating @folder as just folder
            resolved = base_path / folder_name if folder_name else base_path

        resolved_path = resolved.resolve() if resolved.exists() else path.resolve()

        # Ensure resolved path is within allowed directories
        allowed_roots = [base_path.resolve(), (base_path / "src").resolve()]
        for root in allowed_roots:
            try:
                if hasattr(resolved_path, "is_relative_to"):
                    if resolved_path.is_relative_to(root):
                        return resolved_path
                else:
                    # Python < 3.9 fallback
                    resolved_path.relative_to(root)
                    return resolved_path
            except (ValueError, AttributeError):
                continue

        # If path doesn't exist yet, still validate it would be safe
        for root in allowed_roots:
            try:
                if hasattr(resolved_path, "is_relative_to") and resolved_path.is_relative_to(root):
                    return resolved_path
            except (ValueError, AttributeError):
                continue

        raise ValueError("Resolved path would be outside allowed directories")

    resolved = path.resolve()

    # Validate non-@ paths are within current directory or project
    allowed_roots = [Path.cwd().resolve()]
    for root in allowed_roots:
        try:
            if hasattr(resolved, "is_relative_to"):
                if resolved.is_relative_to(root):
                    return resolved
            else:
                # Python < 3.9 fallback
                resolved.relative_to(root)
                return resolved
        except (ValueError, AttributeError):
            continue

    # If absolute path, allow it but log a warning
    if resolved.is_absolute():
        return resolved

    return resolved


def collect_files(paths: list[Path]) -> list[Path]:
    """
    Collect all files to review from given paths.

    For directories, finds all code files recursively.
    For files, includes them directly.

    Args:
        paths: List of file or directory paths

    Returns:
        List of file paths to review
    """
    # Common code file extensions
    CODE_EXTENSIONS = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".java",
        ".go",
        ".rs",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".cc",
        ".cxx",
        ".cs",
        ".php",
        ".rb",
        ".swift",
        ".kt",
        ".scala",
        ".r",
        ".m",
        ".mm",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".ps1",
        ".bat",
        ".cmd",
        ".sql",
        ".html",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".vue",
        ".svelte",
        ".elm",
        ".clj",
        ".cljs",
        ".edn",
        ".lua",
        ".pl",
        ".pm",
        ".rkt",
        ".dart",
        ".ex",
        ".exs",
        ".jl",
        ".nim",
        ".cr",
        ".d",
        ".pas",
        ".f",
        ".f90",
        ".f95",
        ".ml",
        ".mli",
        ".fs",
        ".fsi",
        ".fsx",
        ".vb",
        ".vbs",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".xml",
        ".xsd",
        ".xsl",
        ".xslt",
        ".makefile",
        ".mk",
        ".dockerfile",
        ".cmake",
        ".proto",
        ".thrift",
        ".graphql",
        ".gql",
        ".tf",
        ".tfvars",
        ".hcl",
        ".groovy",
        ".gradle",
        ".jinja",
        ".jinja2",
        ".j2",
        ".mustache",
        ".handlebars",
        ".hbs",
        ".ejs",
        ".pug",
        ".jade",
        ".njk",
    }

    # Common lock files to exclude
    LOCK_FILES = {
        "uv.lock",
        "package-lock.json",
        "poetry.lock",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Gemfile.lock",
        "composer.lock",
        "mix.lock",
        "go.sum",
        "Cargo.lock",
    }

    files_to_review: list[Path] = []

    for path in paths:
        resolved_path = resolve_path(path)

        if not resolved_path.exists():
            click.echo(f"⚠️  Path does not exist, skipping: {path}", err=True)
            continue

        if resolved_path.is_file():
            if resolved_path.name in LOCK_FILES:
                click.echo(f"⚠️  Skipping lock file: {resolved_path.name}", err=True)
                continue
            files_to_review.append(resolved_path)
        elif resolved_path.is_dir():
            # Find all code files in directory recursively
            dir_files = [
                file_path
                for file_path in resolved_path.rglob("*")
                if file_path.is_file()
                and file_path.suffix.lower() in CODE_EXTENSIONS
                and file_path.name not in LOCK_FILES
            ]

            if not dir_files:
                click.echo(f"⚠️  No code files found in directory: {path}", err=True)
            else:
                files_to_review.extend(dir_files)
        else:
            click.echo(f"⚠️  Path is neither file nor directory, skipping: {path}", err=True)

    return files_to_review

=== File: utils/__init__.py ===
"""Utility functions for CLI."""

from .errors import handle_common_errors
from .paths import collect_files, resolve_path

__all__ = ["resolve_path", "collect_files", "handle_common_errors"]

=== File: utils/errors.py ===
"""Error handling utilities."""

import sys

import click


def handle_common_errors(e: Exception) -> None:
    """
    Handle common CLI errors consistently.

    Args:
        e: The exception to handle. Will be categorized and appropriate
           error message will be displayed before exiting.
    """
    if isinstance(e, ValueError | TypeError | KeyError):
        click.echo(f"❌ Configuration error: {e}", err=True)
        sys.exit(1)
    elif isinstance(e, FileNotFoundError):
        click.echo(f"❌ File not found: {e}", err=True)
        sys.exit(1)
    else:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        sys.exit(1)

=== File: commands/commit.py ===
"""Git commit command with LibreChat-style commit messages."""

import asyncio
import subprocess
import sys

import click

from ...tools.git_tools import get_uncommitted_files

# Emoji mapping for commit types
COMMIT_EMOJIS: dict[str, str] = {
    "feat": "🚀",
    "fix": "🐛",
    "docs": "📚",
    "style": "💄",
    "refactor": "♻️",
    "test": "🧪",
    "chore": "📦",
    "perf": "⚡",
    "ci": "👷",
    "build": "🔧",
    "revert": "⏪",
    "security": "🔐",
    "i18n": "🌍",
    "config": "⚙️",
    "deps": "📦",
    "ui": "🎨",
    "ux": "✨",
    "api": "🔌",
    "db": "🗃️",
    "docker": "🐳",
    "k8s": "☸️",
    "helm": "🪣",
    "merge": "🔀",
    "hotfix": "🚨",
    "wip": "🚧",
    "cleanup": "🧹",
    "init": "🎉",
    "deploy": "🚀",
    "release": "🏷️",
}


def get_commit_type_choices() -> list[str]:
    """Get available commit type choices."""
    return list(COMMIT_EMOJIS.keys())


def format_commit_message(commit_type: str, message: str, body: str | None = None) -> str:
    """Format commit message with emoji and type."""
    emoji = COMMIT_EMOJIS.get(commit_type, "📝")
    formatted_message = f"{emoji} {commit_type}: {message}"

    if body:
        formatted_message += f"\n\n{body}"

    return formatted_message


async def get_staged_files() -> list[str]:
    """Get list of staged files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get staged files: {e}") from e


async def stage_files(files: list[str]) -> None:
    """Stage specified files."""
    try:
        subprocess.run(["git", "add"] + files, check=True)
        click.echo(f"✅ Staged {len(files)} file(s)", err=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to stage files: {e}") from e


async def create_commit(message: str) -> None:
    """Create git commit with formatted message."""
    try:
        subprocess.run(["git", "commit", "-m", message], check=True)
        click.echo("✅ Commit created successfully", err=True)
    except subprocess.CalledProcessError as e:
        if e.returncode == 1:
            # No changes to commit
            click.echo("⚠️ Nothing to commit, working tree clean", err=True)
        else:
            raise RuntimeError(f"Failed to create commit: {e}") from e


@click.command()
@click.option(
    "--type",
    "-t",
    "commit_type",
    type=click.Choice(get_commit_type_choices(), case_sensitive=False),
    required=True,
    help="Type of commit (determines emoji prefix)",
)
@click.option(
    "--message",
    "-m",
    required=True,
    help="Commit message description",
)
@click.option(
    "--body",
    "-b",
    help="Optional commit message body (additional details)",
)
@click.option(
    "--add",
    "-a",
    "add_files",
    multiple=True,
    help="Files to stage before committing (can be used multiple times)",
)
@click.option(
    "--all",
    "-A",
    "add_all",
    is_flag=True,
    help="Stage all modified files before committing",
)
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    help="Show what would be committed without actually creating the commit",
)
def commit(
    commit_type: str,
    message: str,
    body: str | None,
    add_files: tuple[str, ...],
    add_all: bool,
    dry_run: bool,
) -> None:
    """Create a git commit with LibreChat-style formatting.

    This command creates commits with emoji prefixes and consistent formatting
    following the LibreChat project style.

    Examples:
        council commit --type feat --message "Add user authentication"
        council commit -t fix -m "Fix login validation bug" -b "Resolves issue with empty password validation"
        council commit -t chore -m "Update dependencies" --add package.json --add package-lock.json
        council commit -t refactor -m "Restructure auth module" --all
    """

    async def _commit():
        try:
            # Check if we're in a git repository
            try:
                subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, check=True)
            except subprocess.CalledProcessError:
                click.echo("❌ Not in a git repository", err=True)
                sys.exit(1)

            # Stage files if requested
            if add_all:
                try:
                    uncommitted_files = await get_uncommitted_files()
                    if uncommitted_files:
                        await stage_files(uncommitted_files)
                    else:
                        click.echo("⚠️ No uncommitted files to stage", err=True)
                except Exception as e:
                    click.echo(f"❌ Failed to get uncommitted files: {e}", err=True)
                    sys.exit(1)
            elif add_files:
                await stage_files(list(add_files))

            # Get staged files to show what will be committed
            staged_files = await get_staged_files()

            if not staged_files:
                click.echo("❌ No staged changes to commit", err=True)
                click.echo(
                    "   Use --add to stage specific files or --all to stage all changes", err=True
                )
                sys.exit(1)

            # Format the commit message
            formatted_message = format_commit_message(commit_type, message, body)

            if dry_run:
                click.echo("🔍 Dry run - would commit the following:", err=True)
                click.echo(f"\nCommit message:\n{formatted_message}\n", err=True)
                click.echo("Staged files:", err=True)
                for file in staged_files:
                    click.echo(f"  📄 {file}", err=True)
                return

            # Show what will be committed
            click.echo("📝 Creating commit with:", err=True)
            click.echo(
                f"   Message: {formatted_message.split(chr(10))[0]}", err=True
            )  # First line only
            click.echo(f"   Files: {len(staged_files)} staged", err=True)

            # Create the commit
            await create_commit(formatted_message)

        except RuntimeError as e:
            click.echo(f"❌ {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Unexpected error: {e}", err=True)
            sys.exit(1)

    asyncio.run(_commit())

=== File: commands/__init__.py ===
"""CLI commands for The Council."""

from .commit import commit

__all__ = ["commit"]

=== File: commands/review.py ===
"""Review command - perform code reviews."""

import asyncio
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import click
import logfire

from ...agents import CouncilDeps, ReviewResult
from ...config import get_settings
from ...tools.cache import cache_review, get_cached_review
from ...tools.git_tools import get_uncommitted_files
from ...tools.metrics_collector import get_metrics_collector
from ...tools.persistence import ReviewRecord, get_review_history
from ...tools.repomix import get_packed_context, get_packed_diff
from ..core.review_executor import run_agent_review
from ..ui.output import print_markdown, print_pretty
from ..ui.spinner import Spinner
from ..utils.paths import collect_files

settings = get_settings()

# Configuration constants
MAX_EXTRA_INSTRUCTIONS_LENGTH = 10000


@click.command()
@click.argument("paths", nargs=-1, required=False, type=click.Path(path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "markdown", "pretty"], case_sensitive=False),
    default="pretty",
    help="Output format for the review results (json, markdown, or pretty)",
)
@click.option(
    "--extra-instructions",
    "-i",
    help="Additional instructions for the review",
)
@click.option(
    "--diff",
    "-d",
    "base_ref",
    help="Review only changed code compared to git reference (e.g., HEAD, main). "
    "If provided, only modified files will be reviewed.",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Disable caching of review results",
)
@click.option(
    "--phases",
    help="Comma-separated list of review phases to run (security,performance,maintainability,best_practices). "
    "If not specified, runs all phases in a single pass.",
)
@click.option(
    "--uncommitted",
    "-u",
    is_flag=True,
    default=False,
    help="Review only uncommitted changes. If specified without paths, reviews all uncommitted files.",
)
def review(
    paths: tuple[Path, ...] | None,
    output: str,
    extra_instructions: str | None,
    base_ref: str | None,
    no_cache: bool,
    phases: str | None,
    uncommitted: bool,
) -> None:
    """Review code at the given file path(s) or directory/ies.

    You can specify multiple files and/or directories:

    \b
    Examples:
        council review file1.py file2.py
        council review @agents
        council review src/ tests/ file.py
        council review --uncommitted  # Review all uncommitted files
    """
    # Validate and sanitize extra_instructions
    if extra_instructions:
        # Check length to prevent API limit issues
        if len(extra_instructions) > MAX_EXTRA_INSTRUCTIONS_LENGTH:
            click.echo(
                f"❌ Extra instructions too long (max {MAX_EXTRA_INSTRUCTIONS_LENGTH} characters)",
                err=True,
            )
            sys.exit(1)

        # Basic sanitization: remove null bytes and control characters that could cause issues
        # Keep newlines and tabs as they might be intentional
        sanitized = "".join(
            char for char in extra_instructions if ord(char) >= 32 or char in "\n\t"
        )
        if sanitized != extra_instructions:
            click.echo(
                "⚠️  Warning: Removed invalid control characters from extra instructions",
                err=True,
            )
        extra_instructions = sanitized

    # Handle --uncommitted without paths: use project root
    if uncommitted and (not paths or len(paths) == 0):
        paths = (settings.project_root,)

    # Validate that paths are provided (unless --uncommitted was used, which we handled above)
    if not paths or len(paths) == 0:
        click.echo("❌ No paths specified. Provide file(s) or directory/ies to review.", err=True)
        click.echo("   Use --uncommitted to review all uncommitted files.", err=True)
        sys.exit(1)

    # Collect all files to review
    files_to_review = collect_files(list(paths))

    # Filter to uncommitted files if --uncommitted flag is set
    if uncommitted:

        async def _filter_uncommitted():
            try:
                uncommitted_file_paths = await get_uncommitted_files()
                if not uncommitted_file_paths:
                    click.echo("⚠️  No uncommitted changes found", err=True)
                    sys.exit(0)

                # Convert to Path objects relative to project root
                project_root = settings.project_root.resolve()
                uncommitted_paths = {
                    (project_root / path).resolve() for path in uncommitted_file_paths
                }

                # If no specific paths were provided, use all uncommitted files
                if not paths or len(paths) == 0 or paths == (settings.project_root,):
                    # Use all uncommitted files directly, but filter out deleted files
                    filtered_files = [
                        (project_root / path).resolve()
                        for path in uncommitted_file_paths
                        if (project_root / path).exists()
                    ]
                else:
                    # Filter files_to_review to only include uncommitted files that exist
                    filtered_files = [
                        f
                        for f in files_to_review
                        if f.resolve() in uncommitted_paths and f.exists()
                    ]

                if not filtered_files:
                    click.echo(
                        "⚠️  None of the specified files have uncommitted changes",
                        err=True,
                    )
                    sys.exit(0)

                return filtered_files
            except Exception as e:
                click.echo(f"❌ Failed to get uncommitted files: {e}", err=True)
                sys.exit(1)

        files_to_review = asyncio.run(_filter_uncommitted())
        click.echo(
            f"📝 Filtered to {len(files_to_review)} uncommitted file(s) to review",
            err=True,
        )
        # When reviewing uncommitted changes, use HEAD as base reference for diff context
        if not base_ref:
            base_ref = "HEAD"

    if not files_to_review:
        click.echo("❌ No files found to review", err=True)
        sys.exit(1)

    click.echo(f"🔍 Found {len(files_to_review)} file(s) to review", err=True)

    async def _review_single_file(
        file_path: Path,
        idx: int,
        total: int,
        semaphore: asyncio.Semaphore,
    ) -> tuple[Path, ReviewResult] | None:
        """
        Review a single file.

        Args:
            file_path: Path to the file to review
            idx: Index of this file (1-based)
            total: Total number of files
            semaphore: Semaphore to limit concurrency

        Returns:
            Tuple of (file_path, ReviewResult) or None if review failed
        """
        async with semaphore:
            # Initialize metrics and persistence
            review_id = str(uuid.uuid4())[:8]
            metrics_collector = get_metrics_collector()
            review_history = get_review_history()
            review_metrics = metrics_collector.start_review(review_id, str(file_path))

            try:
                click.echo(f"\n[{idx}/{total}] 🔍 Reviewing: {file_path}", err=True)
                if base_ref:
                    click.echo(f"📦 Extracting diff context (base: {base_ref})...", err=True)
                else:
                    click.echo("📦 Extracting context with Repomix...", err=True)

                # Get packed context using Repomix (with diff if base_ref provided)
                context_start = time.time()
                try:
                    if base_ref:
                        packed_xml = await get_packed_diff(str(file_path), base_ref)
                    else:
                        packed_xml = await get_packed_context(str(file_path))
                    context_duration = time.time() - context_start
                    metrics_collector.record_tool_execution(
                        "repomix", context_duration, success=True
                    )
                except Exception as e:
                    context_duration = time.time() - context_start
                    metrics_collector.record_tool_execution(
                        "repomix", context_duration, success=False, error_type=type(e).__name__
                    )
                    raise

                # Parse review phases if provided
                review_phases = None
                if phases:
                    review_phases = [p.strip() for p in phases.split(",") if p.strip()]
                    valid_phases = {"security", "performance", "maintainability", "best_practices"}
                    review_phases = [p for p in review_phases if p in valid_phases]
                    if not review_phases:
                        click.echo(
                            f"⚠️  No valid phases specified, using all phases. Valid phases: {', '.join(valid_phases)}",
                            err=True,
                        )
                        review_phases = None

                # Create dependencies for the agent
                deps = CouncilDeps(
                    file_path=str(file_path),
                    extra_instructions=extra_instructions,
                    review_phases=review_phases,
                )

                # Check cache if enabled
                cached_result = None
                if not no_cache and settings.enable_cache:
                    model_name = os.getenv("COUNCIL_MODEL") or "unknown"
                    cached_data = await get_cached_review(str(file_path), model_name)
                    if cached_data:
                        # Reconstruct ReviewResult from cached data
                        cached_result = ReviewResult(**cached_data)
                        click.echo("✅ Using cached review result", err=True)

                if cached_result:
                    review_result = cached_result
                else:
                    # Run the agent review
                    click.echo("🤖 Running AI review...", err=True)
                    spinner = Spinner()
                    review_result = await run_agent_review(
                        packed_xml, deps, spinner, review_id=review_id
                    )

                    # Cache result if enabled
                    if not no_cache and settings.enable_cache:
                        model_name = os.getenv("COUNCIL_MODEL") or "unknown"
                        await cache_review(
                            str(file_path),
                            review_result.model_dump(),
                            model_name,
                        )

                # Finish metrics collection
                metrics_collector.finish_review(
                    review_id,
                    success=True,
                    issues_found=len(review_result.issues),
                    severity=review_result.severity,
                    context_size_bytes=len(packed_xml),
                )

                # Save review to history
                try:
                    review_record = ReviewRecord(
                        review_id=review_id,
                        file_path=str(file_path),
                        timestamp=datetime.now().isoformat(),
                        duration_seconds=review_metrics.duration_seconds or 0.0,
                        success=True,
                        error_type=None,
                        issues_found=len(review_result.issues),
                        severity=review_result.severity,
                        context_size_bytes=len(packed_xml),
                        token_usage={},  # Token usage not available in streaming mode
                        summary=review_result.summary,
                        metadata={
                            "base_ref": base_ref,
                            "extra_instructions": extra_instructions is not None,
                            "review_phases": deps.review_phases,
                        }
                        if base_ref or extra_instructions or deps.review_phases
                        else None,
                    )
                    review_history.save_review(review_record)
                except Exception as e:
                    # Don't fail the review if persistence fails
                    logfire.warning("Failed to save review history", error=str(e))

                return (file_path, review_result)

            except FileNotFoundError as e:
                click.echo(f"❌ File not found: {e}", err=True)
                metrics_collector.finish_review(
                    review_id, success=False, error_type="FileNotFoundError"
                )
                return None
            except RuntimeError as e:
                error_msg = str(e)
                error_type = "RuntimeError"
                if "No API keys configured" in error_msg or "API key" in error_msg.lower():
                    click.echo(f"❌ Configuration error: {e}", err=True)
                    click.echo(
                        "\n💡 Set environment variables:\n"
                        "  - OPENAI_API_KEY for direct provider access, or\n"
                        "  - LITELLM_BASE_URL and LITELLM_API_KEY for LiteLLM proxy",
                        err=True,
                    )
                    metrics_collector.finish_review(
                        review_id, success=False, error_type="ConfigurationError"
                    )
                    sys.exit(1)
                else:
                    click.echo(f"❌ Review failed for {file_path}: {e}", err=True)
                    metrics_collector.finish_review(review_id, success=False, error_type=error_type)
                    return None
            except Exception as e:
                error_str = str(e).lower()
                error_type = type(e).__name__
                metrics_collector.finish_review(review_id, success=False, error_type=error_type)
                # Check if this is a rate limit error
                is_rate_limit = (
                    "429" in error_str
                    or "rate limit" in error_str
                    or "ratelimiterror" in error_str
                    or "throttling" in error_str
                    or "too many tokens" in error_str
                )

                if is_rate_limit:
                    # Extract model name if available
                    model_match = None
                    if hasattr(e, "body") and isinstance(e.body, dict):
                        model_match = e.body.get("model_name", "unknown")
                    elif "model" in error_str:
                        # Try to extract model name from error message
                        model_match = re.search(
                            r"model[_\s]*[=:]?\s*([^\s,]+)", error_str, re.IGNORECASE
                        )
                        if model_match:
                            model_match = model_match.group(1)

                    click.echo(
                        f"❌ Review failed for {file_path}: Rate limit exceeded",
                        err=True,
                    )
                    if model_match:
                        click.echo(
                            f"   Model: {model_match}",
                            err=True,
                        )
                    click.echo(
                        "   💡 Consider:\n"
                        "   - Waiting a few minutes before retrying\n"
                        "   - Using a different model via COUNCIL_MODEL env var\n"
                        "   - Reducing the number of files reviewed at once",
                        err=True,
                    )
                else:
                    click.echo(f"❌ Unexpected error reviewing {file_path}: {e}", err=True)
                return None
            except (ValueError, TypeError, KeyError) as e:
                click.echo(f"❌ Error reviewing {file_path}: {e}", err=True)
                return None

    async def _review():
        all_results: list[tuple[Path, ReviewResult]] = []

        # Calculate concurrency limit based on number of files
        # More aggressive scaling: use at least 3, scale up to max_concurrent_reviews
        # For small batches, use higher concurrency
        if len(files_to_review) <= 5:
            concurrency_limit = len(files_to_review)
        else:
            concurrency_limit = min(
                settings.max_concurrent_reviews, max(3, len(files_to_review) // 2)
            )
        semaphore = asyncio.Semaphore(concurrency_limit)
        click.echo(
            f"⚡ Processing {len(files_to_review)} files with concurrency limit: {concurrency_limit}",
            err=True,
        )

        # Create tasks for all files
        tasks = [
            _review_single_file(file_path, idx + 1, len(files_to_review), semaphore)
            for idx, file_path in enumerate(files_to_review)
        ]

        # Run all reviews in parallel (with concurrency limit)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and filter out None values
        for result in results:
            if isinstance(result, Exception):
                logfire.error("Review task raised exception", error=str(result))
                continue
            if result is not None:
                all_results.append(result)

        # Output results
        if output == "json":
            # For JSON output, create a structured format with file paths
            results_dict = {
                "files": [
                    {
                        "file_path": str(file_path),
                        "summary": review_result.summary,
                        "issues": [
                            {
                                "description": issue.description,
                                "severity": issue.severity,
                                "category": issue.category,
                                "line_number": issue.line_number,
                                "code_snippet": issue.code_snippet,
                                "related_files": issue.related_files,
                                "suggested_priority": issue.suggested_priority,
                                "references": issue.references,
                                "auto_fixable": issue.auto_fixable,
                            }
                            for issue in review_result.issues
                        ],
                        "severity": review_result.severity,
                        "code_fix": review_result.code_fix,
                        "cross_file_issues": [
                            {
                                "description": issue.description,
                                "severity": issue.severity,
                                "files": issue.files,
                                "category": issue.category,
                            }
                            for issue in review_result.cross_file_issues
                        ],
                        "dependency_analysis": (
                            {
                                "external_dependencies": review_result.dependency_analysis.external_dependencies,
                                "internal_dependencies": review_result.dependency_analysis.internal_dependencies,
                                "circular_dependencies": review_result.dependency_analysis.circular_dependencies,
                                "unused_imports": review_result.dependency_analysis.unused_imports,
                            }
                            if review_result.dependency_analysis
                            else None
                        ),
                    }
                    for file_path, review_result in all_results
                ]
            }
            click.echo(json.dumps(results_dict, indent=2))
        else:
            # For markdown and pretty output, show each file's results separately
            for file_path, review_result in all_results:
                click.echo(f"\n{'=' * 80}", err=True)
                click.echo(f"📄 FILE: {file_path}", err=True)
                click.echo(f"{'=' * 80}\n", err=True)

                if output == "markdown":
                    print_markdown(review_result)
                else:  # pretty
                    print_pretty(review_result)

    asyncio.run(_review())

=== File: commands/housekeeping.py ===
"""Housekeeping command - comprehensive codebase maintenance."""

import ast
import asyncio
import re
import subprocess
from pathlib import Path

import click

from ...agents import CouncilDeps, get_councilor_agent
from ...config import settings
from ..ui.spinner import Spinner
from ..ui.streaming import create_event_stream_handler


async def _agent_edit_file(file_path: Path, instruction: str, spinner: Spinner) -> tuple[bool, str]:
    """
    Use the agent to edit a file based on instructions.

    Args:
        file_path: Path to the file to edit
        instruction: Instruction for what the agent should do
        spinner: Spinner instance for status updates

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        agent = get_councilor_agent()
        event_handler = create_event_stream_handler(spinner)

        # Read current file content
        current_content = file_path.read_text(encoding="utf-8")

        # For very large files, truncate content in prompt to avoid token limits
        # The agent can use read_file tool to get full content if needed
        MAX_PROMPT_CONTENT = 50000  # ~50k chars to leave room for tool calls
        content_preview = (
            current_content[:MAX_PROMPT_CONTENT]
            if len(current_content) > MAX_PROMPT_CONTENT
            else current_content
        )
        content_truncated = len(current_content) > MAX_PROMPT_CONTENT

        # Create prompt for the agent
        truncation_note = (
            "\n\nNote: File content is truncated in this prompt. Use the read_file tool to get the full content before making changes."
            if content_truncated
            else ""
        )

        # Determine if file is large enough to need chunked writes
        file_size = len(current_content)
        use_chunked_writes = file_size > 100000  # 100KB threshold

        chunked_write_note = (
            "\n\nIMPORTANT: This file is large. Use write_file_chunk tool instead of write_file to write it in chunks. "
            "Split the modified content into chunks of ~50KB each and write them sequentially using write_file_chunk "
            "with chunk_index (0-based) and total_chunks parameters."
            if use_chunked_writes
            else ""
        )

        prompt = f"""You are performing housekeeping on this file. {instruction}

Current file content:
```python
{content_preview}
```{truncation_note}{chunked_write_note}

Please read the file using read_file tool first (to get full content if truncated), make the requested changes, and write the updated content back to the file.
{"Use write_file_chunk tool for large files (split into ~50KB chunks)." if use_chunked_writes else "Use write_file tool for small files."}
Only make the changes requested - do not make other modifications unless they are clearly necessary for the requested change."""

        deps = CouncilDeps(file_path=str(file_path), extra_instructions=instruction)

        async with agent.run_stream(
            prompt, deps=deps, event_stream_handler=event_handler
        ) as agent_run:
            async for _ in agent_run.stream_output():
                pass
            await agent_run.get_output()

        return True, f"Successfully edited {file_path.name}"

    except Exception as e:
        error_str = str(e).lower()
        # Check if this is a Bedrock tool call serialization error
        is_bedrock_error = (
            "bedrock" in error_str
            or "tool call" in error_str
            or "jsondecodeerror" in error_str
            or "expecting" in error_str
            or "unable to convert" in error_str
        )

        if is_bedrock_error:
            # Fallback: Use text-based approach - ask agent to provide modified content in response
            click.echo(
                "    ⚠️  Bedrock tool call issue detected, using text fallback method...",
                err=True,
            )
            try:
                agent = get_councilor_agent()
                event_handler = create_event_stream_handler(spinner)

                # Read current file content
                current_content = file_path.read_text(encoding="utf-8")
                MAX_PROMPT_CONTENT = 50000
                content_preview = (
                    current_content[:MAX_PROMPT_CONTENT]
                    if len(current_content) > MAX_PROMPT_CONTENT
                    else current_content
                )
                content_truncated = len(current_content) > MAX_PROMPT_CONTENT

                truncation_note = (
                    "\n\nNote: File content is truncated. Please use read_file tool to get full content first."
                    if content_truncated
                    else ""
                )

                prompt = f"""You are performing housekeeping on this file. {instruction}

Current file content:
```python
{content_preview}
```{truncation_note}

IMPORTANT: Due to technical limitations with tool calls, please provide the COMPLETE modified file content in a code block in your response.
Read the file using read_file tool first if needed to get the full content, then provide the entire modified file in a ```python code block.
Only make the changes requested - do not make other modifications unless clearly necessary."""

                deps = CouncilDeps(file_path=str(file_path), extra_instructions=instruction)

                async with agent.run_stream(
                    prompt, deps=deps, event_stream_handler=event_handler
                ) as agent_run:
                    # Collect text parts from stream
                    text_parts = []
                    async for part in agent_run.stream_output():
                        if hasattr(part, "text") and part.text:
                            text_parts.append(part.text)

                    result = await agent_run.get_output()

                # Extract code block from response
                full_response = "".join(text_parts)

                # Try to get text from result if available
                if (
                    hasattr(result, "data")
                    and isinstance(result.data, dict)
                    and "text" in result.data
                ):
                    full_response += result.data["text"]

                # Extract Python code block
                code_block_pattern = r"```python\s*\n(.*?)```"
                matches = re.findall(code_block_pattern, full_response, re.DOTALL)
                if not matches:
                    # Try without language tag
                    code_block_pattern = r"```\s*\n(.*?)```"
                    matches = re.findall(code_block_pattern, full_response, re.DOTALL)

                if matches:
                    # Use the largest code block (likely the full file)
                    modified_content = max(matches, key=len).strip()
                    # Write the modified content
                    file_path.write_text(modified_content, encoding="utf-8")
                    return True, f"Successfully edited {file_path.name} (using text fallback)"
                else:
                    return (
                        False,
                        "Could not extract code block from agent response - no code blocks found",
                    )

            except Exception as fallback_error:
                return False, f"Fallback also failed: {str(fallback_error)[:200]}"
        else:
            return False, f"Failed to edit {file_path.name}: {str(e)[:200]}"


@click.command()
def housekeeping() -> None:
    """Execute comprehensive codebase maintenance and cleanup following a structured 4-phase protocol."""
    project_root = settings.project_root.resolve()
    gitignore_path = project_root / ".gitignore"

    # Get project name early (used in multiple phases)
    pyproject_path = project_root / "pyproject.toml"
    project_name = "The Council"
    python_version = "3.12+"
    if pyproject_path.exists():
        try:
            # Try standard library tomllib first (Python 3.11+)
            try:
                import tomllib  # noqa: F401
            except ImportError:
                # Fall back to tomli if available
                try:
                    import tomli as tomllib  # type: ignore[no-redef]
                except ImportError:
                    tomllib = None

            if tomllib:
                with pyproject_path.open("rb") as f:
                    pyproject_data = tomllib.load(f)
                    if "project" in pyproject_data:
                        project_name = pyproject_data["project"].get("name", project_name)
                        if "requires-python" in pyproject_data["project"]:
                            python_version = pyproject_data["project"]["requires-python"]
        except Exception:
            pass  # Use defaults if parsing fails

    click.echo("🧹 Starting Agent Housekeeping Protocol...\n", err=True)
    click.echo("=" * 80, err=True)
    click.echo("Phase 1: Hygiene & Safety (The 'Sweep')", err=True)
    click.echo("=" * 80 + "\n", err=True)

    # Phase 1.1: Gitignore Audit
    click.echo("📋 Phase 1.1: Gitignore Audit", err=True)
    gitignore_additions: list[str] = []
    gitignore_content = gitignore_path.read_text() if gitignore_path.exists() else ""

    # Scan for common untracked files that should be ignored
    patterns_to_check = {
        ".env.local": ".env.local",
        ".env.*.local": ".env.*.local",
        "*.swp": "*.swp",
        "*.swo": "*.swo",
        "*~": "*~",
        ".DS_Store": ".DS_Store",
        "Thumbs.db": "Thumbs.db",
        "*.log": "*.log",
        "*.tmp": "*.tmp",
        "*.temp": "*.temp",
        "__pycache__": "__pycache__/",
        ".pytest_cache": ".pytest_cache/",
        ".mypy_cache": ".mypy_cache/",
        ".ruff_cache": ".ruff_cache/",
        "node_modules": "node_modules/",
        ".next": ".next/",
        "dist": "dist/",
        "build": "build/",
    }

    for _pattern, addition in patterns_to_check.items():
        if addition not in gitignore_content:
            gitignore_additions.append(addition)

    if gitignore_additions:
        click.echo(f"  ➕ Adding {len(gitignore_additions)} patterns to .gitignore", err=True)
        with gitignore_path.open("a") as f:
            f.write("\n# Added by housekeeping\n")
            for addition in gitignore_additions:
                f.write(f"{addition}\n")
                click.echo(f"    ✓ {addition}", err=True)
    else:
        click.echo("  ✅ .gitignore is up to date", err=True)

    # Phase 1.2: Root Directory Cleanup
    click.echo("\n📁 Phase 1.2: Root Directory Cleanup", err=True)
    root_files_to_delete: list[Path] = []
    standard_files = {
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "docker-compose.yml",
        "Dockerfile",
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        ".eslintrc",
        ".eslintrc.json",
        ".eslintrc.js",
        ".prettierrc",
        "tsconfig.json",
        ".gitignore",
        ".env",
        ".env.example",
        "uv.lock",
    }

    for item in project_root.iterdir():
        if (
            item.is_file()
            and item.name not in standard_files
            and item.suffix in (".tmp", ".temp", ".log", ".bak")
        ):
            root_files_to_delete.append(item)
            click.echo(f"  🗑️  Will delete: {item.name}", err=True)

    if root_files_to_delete:
        for file_path in root_files_to_delete:
            try:
                file_path.unlink()
                click.echo(f"    ✓ Deleted {file_path.name}", err=True)
            except Exception as e:
                click.echo(f"    ⚠️  Failed to delete {file_path.name}: {e}", err=True)
    else:
        click.echo("  ✅ No temporary files found in root", err=True)

    # Phase 1.3: Dead Code Removal
    click.echo("\n🔍 Phase 1.3: Dead Code Removal", err=True)
    source_files = list((project_root / "src").rglob("*.py"))
    files_with_commented_code: list[Path] = []

    for file_path in source_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")

            # Check for large commented-out code blocks (not docstrings)
            in_multiline_string = False
            multiline_string_char = None
            found_commented_block = False

            for i, line in enumerate(lines):
                stripped = line.strip()
                # Skip docstrings
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    if not in_multiline_string:
                        in_multiline_string = True
                        multiline_string_char = stripped[:3]
                    elif stripped.startswith(multiline_string_char):
                        in_multiline_string = False
                        multiline_string_char = None
                    continue

                if in_multiline_string:
                    continue

                # Look for commented-out code blocks (3+ consecutive commented lines)
                if stripped.startswith("#") and len(stripped) > 1 and i + 2 < len(lines):
                    # Check if next 2 lines are also comments
                    next_two_comments = all(
                        line.strip().startswith("#") and len(line.strip()) > 1
                        for line in lines[i + 1 : i + 3]
                    )
                    if next_two_comments:
                        found_commented_block = True
                        break

            if found_commented_block:
                files_with_commented_code.append(file_path)

        except Exception as e:
            click.echo(
                f"    ⚠️  Error analyzing {file_path.relative_to(project_root)}: {e}", err=True
            )

    if files_with_commented_code:
        click.echo(
            f"  🔧 Found {len(files_with_commented_code)} file(s) with commented code blocks",
            err=True,
        )
        click.echo("  🤖 Using AI agent to remove commented code...", err=True)

        spinner = Spinner()
        spinner_task = None
        if spinner.enabled:
            spinner_task = asyncio.create_task(spinner.run())

        async def _remove_commented_code():
            edited_count = 0
            for file_path in files_with_commented_code:
                rel_path = file_path.relative_to(project_root)
                click.echo(f"    📝 Processing {rel_path}...", err=True)
                success, message = await _agent_edit_file(
                    file_path,
                    "Remove all commented-out code blocks (3+ consecutive commented lines). Keep docstrings and single-line explanatory comments. Only remove actual commented code.",
                    spinner,
                )
                if success:
                    edited_count += 1
                    click.echo(f"      ✓ {message}", err=True)
                else:
                    click.echo(f"      ⚠️  {message}", err=True)
            return edited_count

        try:
            edited_count = asyncio.run(_remove_commented_code())
            if spinner_task:
                spinner.stop()
                if not spinner_task.done():
                    spinner_task.cancel()
            click.echo(f"  ✅ Removed commented code from {edited_count} file(s)", err=True)
        except Exception as e:
            if spinner_task:
                spinner.stop()
                if not spinner_task.done():
                    spinner_task.cancel()
            click.echo(f"  ⚠️  Error during commented code removal: {e}", err=True)
    else:
        click.echo("  ✅ No commented code blocks found", err=True)

    click.echo("\n" + "=" * 80, err=True)
    click.echo("✅ Phase 1 Complete", err=True)
    click.echo("=" * 80 + "\n", err=True)

    # Phase 2: Standardization & Quality
    click.echo("=" * 80, err=True)
    click.echo("Phase 2: Standardization & Quality", err=True)
    click.echo("=" * 80 + "\n", err=True)

    # Phase 2.1: Linting & Formatting
    click.echo("🔧 Phase 2.1: Linting & Formatting", err=True)

    # Check for Ruff (Python linter/formatter)
    try:
        result = subprocess.run(
            ["uv", "run", "ruff", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            click.echo("  ✓ Ruff detected", err=True)
            # Run ruff check --fix
            click.echo("  🔧 Running ruff check --fix...", err=True)
            result = subprocess.run(
                ["uv", "run", "ruff", "check", "--fix", "src/"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                click.echo("    ✅ Ruff check completed", err=True)
            else:
                click.echo(f"    ⚠️  Ruff found issues: {result.stdout[:200]}", err=True)

            # Run ruff format
            click.echo("  🎨 Running ruff format...", err=True)
            result = subprocess.run(
                ["uv", "run", "ruff", "format", "src/"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                click.echo("    ✅ Ruff format completed", err=True)
            else:
                click.echo(f"    ⚠️  Ruff format issues: {result.stdout[:200]}", err=True)
        else:
            click.echo("  ⚠️  Ruff not available", err=True)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        click.echo(f"  ⚠️  Could not run Ruff: {e}", err=True)

    # Phase 2.2: DRY Scan (simplified - just report potential duplicates)
    click.echo("\n🔄 Phase 2.2: DRY Scan", err=True)
    click.echo("  ℹ️  DRY analysis requires manual review", err=True)
    click.echo("  💡 Consider using tools like jscpd or pydup for detailed analysis", err=True)

    click.echo("\n" + "=" * 80, err=True)
    click.echo("✅ Phase 2 Complete", err=True)
    click.echo("=" * 80 + "\n", err=True)

    # Phase 3: Documentation Alignment
    click.echo("=" * 80, err=True)
    click.echo("Phase 3: Documentation Alignment", err=True)
    click.echo("=" * 80 + "\n", err=True)

    # Phase 3.1: Docstring Audit
    click.echo("📝 Phase 3.1: Docstring Audit", err=True)
    files_needing_docstrings: list[Path] = []
    functions_without_docs = 0

    for file_path in source_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))
            file_needs_docs = False
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                    and not ast.get_docstring(node)
                    and not node.name.startswith("_")
                ):
                    # Public function without docstring
                    functions_without_docs += 1
                    file_needs_docs = True
            if file_needs_docs and file_path not in files_needing_docstrings:
                files_needing_docstrings.append(file_path)
        except Exception:
            pass  # Skip files that can't be parsed

    if files_needing_docstrings:
        click.echo(
            f"  🔧 Found {functions_without_docs} public functions without docstrings in {len(files_needing_docstrings)} file(s)",
            err=True,
        )
        click.echo("  🤖 Using AI agent to add docstrings...", err=True)

        spinner = Spinner()
        spinner_task = None
        if spinner.enabled:
            spinner_task = asyncio.create_task(spinner.run())

        async def _add_docstrings():
            edited_count = 0
            for file_path in files_needing_docstrings:
                rel_path = file_path.relative_to(project_root)
                click.echo(f"    📝 Processing {rel_path}...", err=True)
                success, message = await _agent_edit_file(
                    file_path,
                    "Add docstrings to all public functions and classes that are missing them. Docstrings should follow Google-style format and describe what the function/class does, its parameters, and return values.",
                    spinner,
                )
                if success:
                    edited_count += 1
                    click.echo(f"      ✓ {message}", err=True)
                else:
                    click.echo(f"      ⚠️  {message}", err=True)
            return edited_count

        try:
            edited_count = asyncio.run(_add_docstrings())
            if spinner_task:
                spinner.stop()
                if not spinner_task.done():
                    spinner_task.cancel()
            click.echo(f"  ✅ Added docstrings to {edited_count} file(s)", err=True)
        except Exception as e:
            if spinner_task:
                spinner.stop()
                if not spinner_task.done():
                    spinner_task.cancel()
            click.echo(f"  ⚠️  Error during docstring addition: {e}", err=True)
    else:
        click.echo("  ✅ All public functions have docstrings", err=True)

    # Phase 3.2: README Reality Check
    click.echo("\n📖 Phase 3.2: README Reality Check", err=True)
    readme_path = project_root / "README.md"

    if readme_path.exists():
        readme_content = readme_path.read_text()
        # Check if README mentions the correct commands
        has_cli_commands = "uv run council" in readme_content or "council review" in readme_content
        has_uv_sync = "uv sync" in readme_content
        has_housekeeping = "housekeeping" in readme_content.lower()
        has_context = "context" in readme_content.lower()

        if not has_cli_commands or not has_uv_sync or not has_housekeeping or not has_context:
            click.echo("  🔧 README needs updates", err=True)
            if not has_cli_commands:
                click.echo("    - Missing CLI command examples", err=True)
            if not has_uv_sync:
                click.echo("    - Missing uv sync in setup instructions", err=True)
            if not has_housekeeping:
                click.echo("    - Missing housekeeping command documentation", err=True)
            if not has_context:
                click.echo("    - Missing context command documentation", err=True)

            click.echo("  🤖 Using AI agent to update README...", err=True)

            spinner = Spinner()
            spinner_task = None
            if spinner.enabled:
                spinner_task = asyncio.create_task(spinner.run())

            async def _update_readme():
                success, message = await _agent_edit_file(
                    readme_path,
                    "Update the README to ensure it includes: 1) All CLI commands (review, learn, context, housekeeping) with examples, 2) uv sync in setup instructions, 3) Housekeeping command documentation, 4) Context command documentation. Verify all commands and setup steps are accurate and match the actual implementation.",
                    spinner,
                )
                return success, message

            try:
                success, message = asyncio.run(_update_readme())
                if spinner_task:
                    spinner.stop()
                    if not spinner_task.done():
                        spinner_task.cancel()
                if success:
                    click.echo(f"  ✅ {message}", err=True)
                else:
                    click.echo(f"  ⚠️  {message}", err=True)
            except Exception as e:
                if spinner_task:
                    spinner.stop()
                    if not spinner_task.done():
                        spinner_task.cancel()
                click.echo(f"  ⚠️  Error updating README: {e}", err=True)
        else:
            click.echo("  ✅ README is up to date", err=True)
    else:
        click.echo("  ⚠️  README.md not found - creating it...", err=True)
        # Create a basic README using the agent
        spinner = Spinner()
        spinner_task = None
        if spinner.enabled:
            spinner_task = asyncio.create_task(spinner.run())

        async def _create_readme():
            # Read project context to understand the project
            context_path = project_root / "ai_docs" / "project_context.md"
            context_content = ""
            if context_path.exists():
                context_content = context_path.read_text()

            initial_readme = f"""# {project_name}

AI-powered code review agent.

## Setup

1. Install dependencies: `uv sync`
2. Configure API keys in `.env` file
3. Run: `uv run council review <file_path>`

## Commands

- `uv run council review <file_path>` - Review code
- `uv run council learn <url> <topic>` - Learn from documentation
- `uv run council context <file_path>` - Get review context for external agents
- `uv run council housekeeping` - Run maintenance protocol
"""

            readme_path.write_text(initial_readme, encoding="utf-8")
            success, message = await _agent_edit_file(
                readme_path,
                f"Create a comprehensive README.md based on this project context: {context_content[:2000]}. Include setup instructions, all CLI commands with examples, and project overview.",
                spinner,
            )
            return success, message

        try:
            success, message = asyncio.run(_create_readme())
            if spinner_task:
                spinner.stop()
                if not spinner_task.done():
                    spinner_task.cancel()
            if success:
                click.echo(f"  ✅ {message}", err=True)
            else:
                click.echo(f"  ⚠️  {message}", err=True)
        except Exception as e:
            if spinner_task:
                spinner.stop()
                if not spinner_task.done():
                    spinner_task.cancel()
            click.echo(f"  ⚠️  Error creating README: {e}", err=True)

    click.echo("\n" + "=" * 80, err=True)
    click.echo("✅ Phase 3 Complete", err=True)
    click.echo("=" * 80 + "\n", err=True)

    # Phase 4: The "Mental Map"
    click.echo("=" * 80, err=True)
    click.echo("Phase 4: The 'Mental Map'", err=True)
    click.echo("=" * 80 + "\n", err=True)

    click.echo("🗺️  Phase 4.1: Creating Project Mental Map", err=True)

    # Ensure ai_docs directory exists
    ai_docs_dir = project_root / "ai_docs"
    ai_docs_dir.mkdir(exist_ok=True)

    # Generate project context
    context_content = f"""# Project Mental Map

## 1. Purpose & Core Logic

The Council is an AI-powered code review agent. It uses Repomix to extract comprehensive code context, Pydantic-AI for structured AI outputs, and Jina Reader to learn from documentation. The agent performs automated code reviews with severity assessments, issue detection, and suggested fixes. It can dynamically learn coding standards from documentation URLs and apply them to future reviews.

## 2. Tech Stack & Key Libraries

- Language: Python {python_version}
- Frameworks:
  - Pydantic-AI (type-safe AI agent framework)
  - Click (CLI framework)
- Key DB/Services: None (file-based knowledge storage)
- Critical Libs:
  - `repomix` (via uvx) - Code context extraction
  - `httpx` - HTTP client for Jina Reader API
  - `logfire` - Structured logging
  - `jinja2` - Template engine for system prompts
  - `python-dotenv` - Environment variable management

## 3. Architecture & Key Patterns

- **Architecture:** CLI-based agent review system
  - CLI Layer: Click commands (review, learn, context, housekeeping)
  - Logic Layer: Pydantic-AI agent (`councilor.py`) performs reviews
  - Context Layer: Repomix wrapper extracts code context as XML
  - Knowledge Layer: Jina Reader fetches docs, stored in `knowledge/` directory
- **State Management:** Stateless agent with lazy initialization (thread-safe singleton pattern)
- **Auth Pattern:** API keys via environment variables (OpenAI, LiteLLM proxy, or direct providers)

## 4. Operational Context

- **Run Locally:**
  - CLI Review: `uv run council review <file_path> [options]`
  - Learn Rules: `uv run council learn <url> <topic>`
  - Get Context: `uv run council context <file_path>` - Output review context for external agents
  - Housekeeping: `uv run council housekeeping`
- **Run Tests:** (Not yet implemented - placeholder in README)
- **Build/Deploy:**
  - Install: `uv sync`
  - Package: Standard Python packaging via `pyproject.toml` (hatchling backend)

## 5. File Structure Map

```
council/
├── pyproject.toml          # Project config, dependencies, Ruff linting config
├── README.md               # User-facing documentation
├── .gitignore              # Git ignore patterns
├── knowledge/              # Dynamic knowledge base (markdown files loaded into prompts)
│   └── .keep
├── ai_docs/                # AI agent context documentation
│   └── project_context.md  # This file
└── src/
    └── council/
        ├── __init__.py     # Package init, version
        ├── cli/
        │   ├── main.py     # Main CLI entry point
        │   ├── commands/   # CLI commands (review, learn, context, housekeeping)
        │   ├── core/       # Core review execution and context building
        │   ├── ui/         # UI components (spinner, streaming, output)
        │   └── utils/      # Utility functions (paths, errors)
        ├── config.py       # Settings management, path resolution, env vars
        ├── templates/
        │   └── system_prompt.j2  # Jinja2 template for agent system prompt
        ├── agents/
        │   ├── __init__.py        # Agent exports
        │   └── councilor.py       # Core Pydantic-AI agent, model creation, knowledge loading
        └── tools/
            ├── __init__.py        # Tool exports
            ├── context.py         # Repomix wrapper, path validation, XML security checks
            ├── git_tools.py       # Git integration (diff, history, uncommitted files)
            └── scribe.py          # Jina Reader wrapper, URL validation, SSRF protection
```

## 6. Known Gotchas & Debugging

- **API Key Configuration:** Must set either `OPENAI_API_KEY` for direct providers OR `LITELLM_BASE_URL` + `LITELLM_API_KEY` for proxy. The `COUNCIL_MODEL` environment variable is required and must be set to specify which model to use. No hardcoded defaults - all configuration must come from environment variables.
- **Path Resolution:** Project root is auto-detected from `config.py` location. Can override with `COUNCIL_PROJECT_ROOT` env var if needed. Paths are validated for security (no path traversal, must be within project root or CWD).
- **Knowledge Base:** Markdown files in `knowledge/` are loaded alphabetically and injected into system prompt as "RULESET" sections. Files are loaded dynamically on each agent run.
- **Repomix Integration:** Runs via `uvx repomix` subprocess. Uses temporary XML files for output. Timeout is configurable via `COUNCIL_SUBPROCESS_TIMEOUT` (default 300s).
- **Template Loading:** Templates directory is resolved via `__file__` path or `importlib.resources` fallback. Must exist or runtime error occurs.
- **Security:** Extensive validation for path traversal, SSRF (URL validation), XXE (XML security checks), and command injection prevention in all user inputs.
- **Code Quality:** Project uses Ruff for linting and formatting. Run `uv run ruff check --fix src/` and `uv run ruff format src/` to maintain code quality. All linting issues should be resolved before committing.
- **Configuration Separation:** No user-specific configuration values should be hardcoded in the repository. All model names, API endpoints, and other user-specific settings must come from environment variables.
- **Uncommitted Reviews:** Use `--uncommitted` flag to review only files with uncommitted changes. This is useful for pre-commit reviews.
- **Context Command:** Use `council context <file_path>` to get review context (code, prompt, knowledge) for external agents to perform reviews without Council's LLM.
"""

    context_file = ai_docs_dir / "project_context.md"
    context_file.write_text(context_content, encoding="utf-8")
    click.echo(f"  ✅ Updated {context_file.relative_to(project_root)}", err=True)

    click.echo("\n" + "=" * 80, err=True)
    click.echo("✅ Phase 4 Complete", err=True)
    click.echo("=" * 80 + "\n", err=True)

    click.echo("🎉 Housekeeping protocol complete!", err=True)
    click.echo("\n💡 Next steps:", err=True)
    click.echo("  - Review the changes made in Phase 1", err=True)
    click.echo("  - Check linting/formatting results from Phase 2", err=True)
    click.echo("  - Verify documentation updates from Phase 3", err=True)
    click.echo("  - Review the updated project context in ai_docs/project_context.md", err=True)

=== File: commands/context.py ===
"""Context command - output review context for external agents."""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import click
import logfire

from ...agents import CouncilDeps
from ...tools.repomix import get_packed_context, get_packed_diff
from ..core.context_builder import build_review_context
from ..utils.paths import resolve_path

# Configuration constants
MAX_EXTRA_INSTRUCTIONS_LENGTH = 10000
OUTPUT_FORMAT_JSON = "json"
OUTPUT_FORMAT_MARKDOWN = "markdown"


@click.command()
@click.argument("file_path", type=str)
@click.option(
    "--output",
    "-o",
    type=click.Choice([OUTPUT_FORMAT_JSON, OUTPUT_FORMAT_MARKDOWN], case_sensitive=False),
    default=OUTPUT_FORMAT_JSON,
    help="Output format for the context (json or markdown)",
)
@click.option(
    "--diff",
    "-d",
    "base_ref",
    help="Extract context for diff-based review (e.g., HEAD, main). "
    "If provided, only changed code will be included.",
)
@click.option(
    "--extra-instructions",
    "-i",
    help="Additional instructions for the review",
)
@click.option(
    "--phases",
    help="Comma-separated list of review phases to focus on (security,performance,maintainability,best_practices).",
)
def context(
    file_path: str,
    output: str,
    base_ref: str | None,
    extra_instructions: str | None,
    phases: str | None,
) -> None:
    """Output review context for a file path.

    This command extracts code context, loads relevant knowledge base content,
    and generates a review checklist. The output can be used by external agents
    (like Gemini, Claude, Codex, etc.) to perform code reviews.

    Examples:
        council context src/council/main.py
        council context src/council/main.py --output markdown
        council context src/council/main.py --diff HEAD
    """
    # Validate and sanitize extra_instructions
    if extra_instructions:
        if len(extra_instructions) > MAX_EXTRA_INSTRUCTIONS_LENGTH:
            click.echo(
                f"❌ Extra instructions too long (max {MAX_EXTRA_INSTRUCTIONS_LENGTH} characters)",
                err=True,
            )
            sys.exit(1)

        # Basic sanitization
        sanitized = "".join(
            char for char in extra_instructions if ord(char) >= 32 or char in "\n\t"
        )
        if sanitized != extra_instructions:
            click.echo(
                "⚠️  Warning: Removed invalid control characters from extra instructions",
                err=True,
            )
        extra_instructions = sanitized

    # Validate file path
    try:
        resolved_path = resolve_path(Path(file_path))
        if not resolved_path.exists():
            click.echo(f"❌ File not found: {file_path}", err=True)
            sys.exit(1)
        file_path = str(resolved_path)
    except ValueError as e:
        click.echo(f"❌ Invalid path: {e}", err=True)
        sys.exit(1)

    # Parse review phases if provided
    review_phases = None
    if phases:
        review_phases = [p.strip() for p in phases.split(",") if p.strip()]
        valid_phases = {"security", "performance", "maintainability", "best_practices"}
        review_phases = [p for p in review_phases if p in valid_phases]
        if not review_phases:
            click.echo(
                f"⚠️  No valid phases specified. Valid phases: {', '.join(valid_phases)}",
                err=True,
            )
            review_phases = None

    async def _get_context() -> None:
        # Suppress logfire output for both JSON and markdown to ensure clean output
        # Configure before any operations that might use logfire
        logfire.configure(send_to_logfire=False, console=False)
        logging.getLogger("logfire").setLevel(logging.CRITICAL)  # Only show critical errors
        # Also suppress other logfire loggers
        logging.getLogger("logfire.instrumentation").setLevel(logging.CRITICAL)
        logging.getLogger("logfire.otel").setLevel(logging.CRITICAL)

        try:
            if output != OUTPUT_FORMAT_JSON:  # Only show status messages for markdown output
                click.echo("📦 Extracting context...", err=True)

            # Get packed context using Repomix
            if base_ref:
                packed_xml = await get_packed_diff(file_path, base_ref)
            else:
                packed_xml = await get_packed_context(file_path)

            # Create dependencies
            deps = CouncilDeps(
                file_path=file_path,
                extra_instructions=extra_instructions,
                review_phases=review_phases,
            )

            # Build review context
            context_data = await build_review_context(packed_xml, deps)

            # Output based on format
            if output == OUTPUT_FORMAT_MARKDOWN:
                _output_markdown(context_data)
            else:
                _output_json(context_data)

        except ValueError as e:
            click.echo(f"❌ Invalid input: {e}", err=True)
            sys.exit(1)
        except FileNotFoundError as e:
            click.echo(f"❌ File not found: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Unexpected error: {e}", err=True)
            sys.exit(1)

    asyncio.run(_get_context())


def _output_json(context_data: dict) -> None:
    """Output context as JSON."""
    # Use sys.stdout directly to avoid any click formatting that might interfere
    print(json.dumps(context_data, indent=2), file=sys.stdout)


def _output_markdown(context_data: dict) -> None:
    """Output context as Markdown."""
    # Calculate approximate output size for warning
    output_size = len(str(context_data))
    if output_size > 100 * 1024:  # 100KB
        click.echo(
            f"⚠️  Warning: Large context file ({output_size / 1024:.1f}KB). "
            "Consider using --phases to focus on specific review areas.\n",
            err=True,
        )

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    click.echo("# Code Review Context\n")
    click.echo(f"**Generated:** {timestamp}\n")
    click.echo(f"## File: {context_data['file_path']}\n")
    click.echo(f"**Language:** {context_data['language']}\n")

    if context_data["metadata"]["extra_instructions"]:
        click.echo(f"**Extra Instructions:** {context_data['metadata']['extra_instructions']}\n")

    if context_data["metadata"]["review_phases"]:
        click.echo(f"**Review Phases:** {', '.join(context_data['metadata']['review_phases'])}\n")

    click.echo("## System Prompt\n")
    click.echo("```\n")
    click.echo(context_data["system_prompt"])
    click.echo("\n```\n")

    # Always show knowledge base section, even if empty
    click.echo("## Knowledge Base\n")
    knowledge_content = context_data.get("knowledge_base", "").strip()
    if knowledge_content:
        click.echo("```\n")
        click.echo(knowledge_content)
        click.echo("\n```\n")
    else:
        click.echo("*No relevant knowledge base content loaded.*\n")

    click.echo("## Code to Review\n")
    # Add language identifier for syntax highlighting
    language = context_data.get("language", "text")
    click.echo(f"```{language}\n")
    click.echo(context_data["extracted_code"])
    click.echo("\n```\n")

    click.echo("## Review Checklist\n")
    click.echo(context_data["review_checklist"])

=== File: commands/learn.py ===
"""Learn command - learn rules from documentation."""

import asyncio
import sys

import click

from ...tools.scribe import fetch_and_summarize, validate_topic, validate_url


@click.command()
@click.argument("url")
@click.argument("topic")
def learn(url: str, topic: str) -> None:
    """Learn rules from a documentation URL and add to knowledge base."""
    # Validate URL format and security using scribe.validate_url
    try:
        validate_url(url)
    except ValueError as e:
        click.echo(f"❌ Invalid URL: {e}", err=True)
        sys.exit(1)

    # Validate topic using scribe.validate_topic
    try:
        validated_topic = validate_topic(topic)
        topic = validated_topic  # Use validated topic
    except ValueError as e:
        click.echo(f"❌ Invalid topic: {e}", err=True)
        sys.exit(1)

    click.echo(f"📚 Learning from: {url}", err=True)
    click.echo(f"📝 Topic: {topic}", err=True)

    async def _learn() -> None:
        try:
            result = await fetch_and_summarize(url, topic)
            click.echo(f"✅ {result}")
        except (ValueError, TypeError, KeyError) as e:
            click.echo(f"❌ Configuration error: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Failed to learn rules: {e}", err=True)
            sys.exit(1)

    asyncio.run(_learn())

=== File: main.py ===
"""Main CLI entry point for The Council."""

import click
import logfire

from .commands.commit import commit
from .commands.context import context
from .commands.housekeeping import housekeeping
from .commands.learn import learn
from .commands.review import review

# Initialize logfire
logfire.configure(send_to_logfire=False)


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """The Council - AI Code Review Agent main CLI entry point."""
    pass


# Register all commands
main.add_command(commit)
main.add_command(context)
main.add_command(housekeeping)
main.add_command(learn)
main.add_command(review)

__all__ = ["main"]

```

## Review Checklist

# Code Review Checklist

You are performing a comprehensive code review. Follow this checklist to ensure a thorough review.

## Review Process

1. **Read and Understand**: Carefully read through all the provided code
2. **Analyze**: Check for issues across all categories below
3. **Document**: Report all findings with accurate line numbers and code snippets
4. **Prioritize**: Focus on higher severity issues first, but report all legitimate issues

## What to Check

### Security
- [ ] SQL injection vulnerabilities
- [ ] XSS (Cross-Site Scripting) vulnerabilities
- [ ] Authentication and authorization issues
- [ ] Sensitive data exposure
- [ ] Insecure random number generation
- [ ] Hardcoded secrets or credentials
- [ ] Insecure deserialization
- [ ] Missing input validation
- [ ] Path traversal vulnerabilities
- [ ] CSRF protection

### Performance
- [ ] N+1 query problems
- [ ] Inefficient algorithms or data structures
- [ ] Memory leaks or excessive memory usage
- [ ] Unnecessary database queries
- [ ] Missing indexes
- [ ] Inefficient loops or iterations
- [ ] Blocking operations in async code
- [ ] Large file operations without streaming

### Code Quality & Maintainability
- [ ] Code duplication (DRY violations)
- [ ] Complex functions (high cyclomatic complexity)
- [ ] Poor naming conventions
- [ ] Missing or inadequate error handling
- [ ] Inconsistent code style
- [ ] Magic numbers without constants
- [ ] Long parameter lists
- [ ] God objects or classes with too many responsibilities

### Best Practices
- [ ] Proper use of design patterns
- [ ] SOLID principles adherence
- [ ] Proper separation of concerns
- [ ] Appropriate use of abstractions
- [ ] Testability concerns
- [ ] Documentation quality
- [ ] Logging and monitoring

### Bugs & Edge Cases
- [ ] Null pointer exceptions
- [ ] Off-by-one errors
- [ ] Race conditions
- [ ] Unhandled edge cases
- [ ] Incorrect logic
- [ ] Type mismatches
- [ ] Boundary condition errors

## Expected Output Format

You must return a structured review result with the following format:

```json
{
  "summary": "Overall summary of the code review (2-3 sentences)",
  "issues": [
    {
      "description": "Clear description of the issue",
      "severity": "low|medium|high|critical",
      "category": "security|performance|maintainability|bug|style|documentation",
      "line_number": 42,
      "code_snippet": "exact code showing the issue",
      "related_files": [],
      "suggested_priority": 8,
      "references": [],
      "auto_fixable": false
    }
  ],
  "severity": "low|medium|high|critical",
  "code_fix": "Optional suggested code fix",
  "cross_file_issues": [],
  "dependency_analysis": {
    "external_dependencies": [],
    "internal_dependencies": [],
    "circular_dependencies": [],
    "unused_imports": []
  }
}
```

## Severity Guidelines

- **critical**: Security vulnerabilities, data loss risks, system crashes
- **high**: Serious bugs, significant performance issues, major security concerns
- **medium**: Code quality issues, moderate bugs, maintainability concerns
- **low**: Style issues, minor improvements, documentation gaps

## Important Notes

- **VERIFY BEFORE REPORTING**: Only report issues that actually exist in the code
- **Be Accurate**: Line numbers and code snippets must be exact
- **Be Comprehensive**: Aim to find all significant issues in a single review
- **Be Specific**: Provide clear, actionable feedback
- **Prioritize**: Focus on higher severity issues but don't skip lower severity ones
