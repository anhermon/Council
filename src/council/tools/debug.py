"""Debug output for agent context, prompts, and tool calls."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import logfire

from ..config import get_settings

settings = get_settings()

# Debug directory name
DEBUG_DIR_NAME = ".council"
DEBUG_SUBDIR = "debug"

# Maximum size for individual debug entries (to prevent huge files)
MAX_DEBUG_ENTRY_SIZE = 10 * 1024 * 1024  # 10MB per entry


def _escape_markdown(text: str) -> str:
    """Escape special Markdown characters."""
    # Escape code blocks, headers, and other special characters
    return text.replace("```", "\\`\\`\\`").replace("#", "\\#")


def get_debug_dir() -> Path:
    """
    Get the debug directory path.

    Returns:
        Path to debug directory
    """
    debug_dir = settings.project_root / DEBUG_DIR_NAME / DEBUG_SUBDIR
    debug_dir.mkdir(parents=True, exist_ok=True)
    return debug_dir


def is_debug_enabled() -> bool:
    """
    Check if debug output is enabled via environment variable.

    Returns:
        True if COUNCIL_DEBUG is set to a truthy value
    """
    return os.getenv("COUNCIL_DEBUG", "false").lower() in ("true", "1", "yes", "on")


class DebugWriter:
    """Writes debug information about agent execution to files."""

    def __init__(self, review_id: str | None = None, file_path: str | None = None) -> None:
        """
        Initialize debug writer.

        Args:
            review_id: Optional review ID for correlation
            file_path: Optional file path being reviewed
        """
        self.enabled = is_debug_enabled()
        self.review_id = review_id or "unknown"
        self.file_path = file_path or "unknown"
        self.debug_file: Path | None = None
        self.entries: list[dict[str, Any]] = []

        if self.enabled:
            debug_dir = get_debug_dir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Sanitize file path for filename
            safe_file_path = (
                self.file_path.replace("/", "_").replace("\\", "_").replace(" ", "_")[:50]
            )
            self.debug_file = debug_dir / f"debug_{timestamp}_{self.review_id}_{safe_file_path}.md"
            logfire.info("Debug output enabled", debug_file=str(self.debug_file))

            # Write Markdown header
            with self.debug_file.open("w", encoding="utf-8") as f:
                f.write("# Debug Output\n\n")
                f.write(f"**Review ID:** `{self.review_id}`\n")
                f.write(f"**File Path:** `{self.file_path}`\n")
                f.write(f"**Started:** {datetime.now().isoformat()}\n\n")
                f.write("---\n\n")

    def write_entry(self, entry_type: str, data: dict[str, Any]) -> None:
        """
        Write a debug entry to the file in Markdown format.

        Args:
            entry_type: Type of entry (e.g., "system_prompt", "user_prompt", "tool_call", "tool_output")
            data: Entry data
        """
        if not self.enabled or not self.debug_file:
            return

        try:
            timestamp = datetime.now().isoformat()

            # Truncate large entries to prevent huge files
            data_str = json.dumps(data, default=str)
            if len(data_str) > MAX_DEBUG_ENTRY_SIZE:
                logfire.warning(
                    "Debug entry too large, truncating",
                    entry_type=entry_type,
                    size=len(data_str),
                    max_size=MAX_DEBUG_ENTRY_SIZE,
                )
                # Keep metadata but truncate content
                if "content" in data:
                    data["content"] = (
                        data["content"][: MAX_DEBUG_ENTRY_SIZE // 2] + "\n... [TRUNCATED]"
                    )
                elif "output" in data:
                    data["output"] = (
                        str(data["output"])[: MAX_DEBUG_ENTRY_SIZE // 2] + "\n... [TRUNCATED]"
                    )
                elif "prompt" in data:
                    data["prompt"] = (
                        data["prompt"][: MAX_DEBUG_ENTRY_SIZE // 2] + "\n... [TRUNCATED]"
                    )

            # Write as Markdown
            with self.debug_file.open("a", encoding="utf-8") as f:
                f.write(f"## {entry_type.replace('_', ' ').title()}\n\n")
                f.write(f"**Timestamp:** {timestamp}\n\n")

                # Format data based on entry type
                if entry_type == "system_prompt":
                    f.write(f"**Prompt Length:** {data.get('prompt_length', 0):,} characters\n\n")
                    if "metadata" in data:
                        f.write("**Metadata:**\n\n")
                        for key, value in data["metadata"].items():
                            if isinstance(value, list):
                                f.write(
                                    f"- **{key}:** {', '.join(str(v) for v in value) if value else 'None'}\n"
                                )
                            else:
                                f.write(f"- **{key}:** `{value}`\n")
                        f.write("\n")
                    f.write("**Prompt:**\n\n```\n")
                    f.write(data.get("prompt", ""))
                    f.write("\n```\n\n")

                elif entry_type == "user_prompt":
                    f.write(f"**Prompt Length:** {data.get('prompt_length', 0):,} characters\n\n")
                    f.write("**Prompt:**\n\n```xml\n")
                    f.write(data.get("prompt", ""))
                    f.write("\n```\n\n")

                elif entry_type == "tool_call":
                    f.write(f"**Tool:** `{data.get('tool_name', 'unknown')}`\n\n")
                    if data.get("call_id"):
                        f.write(f"**Call ID:** `{data['call_id']}`\n\n")
                    if data.get("arguments"):
                        f.write("**Arguments:**\n\n```json\n")
                        f.write(json.dumps(data["arguments"], indent=2, default=str))
                        f.write("\n```\n\n")

                elif entry_type == "tool_output":
                    f.write(f"**Tool:** `{data.get('tool_name', 'unknown')}`\n\n")
                    if data.get("call_id"):
                        f.write(f"**Call ID:** `{data['call_id']}`\n\n")
                    if data.get("error"):
                        f.write(f"**Error:** `{data['error']}`\n\n")
                    if data.get("output") is not None:
                        f.write("**Output:**\n\n```json\n")
                        output_str = json.dumps(data["output"], indent=2, default=str)
                        f.write(output_str)
                        f.write("\n```\n\n")

                elif entry_type == "agent_response":
                    f.write("**Response:**\n\n```json\n")
                    response_str = json.dumps(data.get("response", {}), indent=2, default=str)
                    f.write(response_str)
                    f.write("\n```\n\n")
                    if "metadata" in data:
                        f.write("**Metadata:**\n\n")
                        for key, value in data["metadata"].items():
                            f.write(f"- **{key}:** `{value}`\n")
                        f.write("\n")

                elif entry_type == "error":
                    f.write(f"**Error Type:** `{data.get('error_type', 'Unknown')}`\n\n")
                    f.write("**Error Message:**\n\n```\n")
                    f.write(data.get("error", ""))
                    f.write("\n```\n\n")
                else:
                    # Generic format for unknown types
                    f.write("**Data:**\n\n```json\n")
                    f.write(json.dumps(data, indent=2, default=str))
                    f.write("\n```\n\n")

                f.write("---\n\n")

            self.entries.append({"timestamp": timestamp, "type": entry_type, "data": data})

        except Exception as e:
            logfire.warning("Failed to write debug entry", entry_type=entry_type, error=str(e))

    def write_system_prompt(self, prompt: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Write system prompt to debug file.

        Args:
            prompt: The system prompt content
            metadata: Optional metadata (e.g., loaded knowledge files, language, etc.)
        """
        self.write_entry(
            "system_prompt",
            {
                "prompt": prompt,
                "prompt_length": len(prompt),
                "metadata": metadata or {},
            },
        )

    def write_user_prompt(self, prompt: str) -> None:
        """
        Write user prompt to debug file.

        Args:
            prompt: The user prompt content
        """
        self.write_entry(
            "user_prompt",
            {
                "prompt": prompt,
                "prompt_length": len(prompt),
            },
        )

    def write_tool_call(
        self, tool_name: str, arguments: dict[str, Any] | None = None, call_id: str | None = None
    ) -> None:
        """
        Write tool call to debug file.

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments
            call_id: Optional call ID for correlation with output
        """
        self.write_entry(
            "tool_call",
            {
                "tool_name": tool_name,
                "arguments": arguments or {},
                "call_id": call_id,
            },
        )

    def write_tool_output(
        self,
        tool_name: str,
        output: Any,
        call_id: str | None = None,
        error: str | None = None,
    ) -> None:
        """
        Write tool output to debug file.

        Args:
            tool_name: Name of the tool
            output: Tool output (will be serialized to JSON)
            call_id: Optional call ID for correlation with call
            error: Optional error message
        """
        # Convert output to JSON-serializable format
        try:
            if hasattr(output, "model_dump"):
                output_data = output.model_dump()
            elif hasattr(output, "__dict__"):
                output_data = {k: str(v) for k, v in output.__dict__.items()}
            else:
                output_data = str(output)
        except Exception:
            output_data = str(output)

        self.write_entry(
            "tool_output",
            {
                "tool_name": tool_name,
                "output": output_data,
                "call_id": call_id,
                "error": error,
            },
        )

    def write_agent_response(self, response: Any, metadata: dict[str, Any] | None = None) -> None:
        """
        Write agent response to debug file.

        Args:
            response: The agent response
            metadata: Optional metadata (e.g., token usage, duration, etc.)
        """
        # Convert response to JSON-serializable format
        try:
            if hasattr(response, "model_dump"):
                response_data = response.model_dump()
            elif hasattr(response, "__dict__"):
                response_data = {k: str(v) for k, v in response.__dict__.items()}
            else:
                response_data = str(response)
        except Exception:
            response_data = str(response)

        self.write_entry(
            "agent_response",
            {
                "response": response_data,
                "metadata": metadata or {},
            },
        )

    def write_error(self, error: str, error_type: str | None = None) -> None:
        """
        Write error to debug file.

        Args:
            error: Error message
            error_type: Optional error type
        """
        self.write_entry(
            "error",
            {
                "error": error,
                "error_type": error_type,
            },
        )
