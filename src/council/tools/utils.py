"""Shared utility functions for tools."""

import asyncio
import logging
import shutil
from pathlib import Path

import logfire

from ..config import get_settings
from .exceptions import SubprocessError, SubprocessTimeoutError

settings = get_settings()

logger = logging.getLogger(__name__)

# Cache for uv availability check
_uv_available: bool | None = None


def _is_uv_available() -> bool:
    """Check if uv is available in PATH."""
    global _uv_available
    if _uv_available is None:
        _uv_available = shutil.which("uv") is not None
    return _uv_available


def resolve_tool_command(tool_name: str) -> list[str]:
    """
    Resolve a tool command, using 'uv run' if uv is available.

    This ensures tools from project dependencies are executed in the correct
    virtual environment context.

    Args:
        tool_name: Name of the tool (e.g., "ruff", "coverage")

    Returns:
        Command as list of strings, prefixed with "uv run" if uv is available
    """
    if _is_uv_available():
        return ["uv", "run", tool_name]
    return [tool_name]


async def run_command_safely(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: float | None = None,
    max_output_size: int | None = None,
    check: bool = True,
) -> tuple[str, str, int]:
    """
    Run a command safely with proper timeout handling and process cleanup.

    This utility ensures that processes are properly killed on timeout to prevent
    zombie processes and resource leaks. It standardizes error handling and
    output size limits across all subprocess calls.

    Args:
        cmd: Command as list of strings (e.g., ["git", "diff", "HEAD"])
        cwd: Working directory for the command. Defaults to project root.
        timeout: Command timeout in seconds. Defaults to settings.subprocess_timeout.
        max_output_size: Maximum output size in bytes. If exceeded, output is truncated.
            Defaults to 10MB.
        check: If True, raise SubprocessError on non-zero return code. Defaults to True.

    Returns:
        Tuple of (stdout_text, stderr_text, return_code)

    Raises:
        SubprocessTimeoutError: If command times out
        SubprocessError: If check=True and command returns non-zero exit code
        ValueError: If output exceeds max_output_size
    """
    if cwd is None:
        cwd = settings.project_root.resolve()

    if timeout is None:
        timeout = settings.subprocess_timeout

    if max_output_size is None:
        max_output_size = 10 * 1024 * 1024  # 10MB default

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError as err:
            # Kill the process if it times out
            if proc:
                proc.kill()
                await proc.wait()
            raise SubprocessTimeoutError(
                f"Command timed out after {timeout} seconds: {' '.join(cmd)}",
                command=cmd,
                original_error=err,
            ) from err

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        # Check output size
        if len(stdout_text) > max_output_size:
            logfire.warning(
                "Command output too large, truncating",
                cmd=" ".join(cmd),
                size=len(stdout_text),
                max_size=max_output_size,
            )
            stdout_text = stdout_text[:max_output_size]

        if check and proc.returncode != 0:
            error_msg = stderr_text or f"Command failed with return code {proc.returncode}"
            raise SubprocessError(
                f"Command failed: {' '.join(cmd)} - {error_msg}",
                command=cmd,
                return_code=proc.returncode,
                stderr=stderr_text,
            )

        return stdout_text, stderr_text, proc.returncode

    except (SubprocessError, SubprocessTimeoutError):
        # Re-raise subprocess errors as-is
        raise
    except FileNotFoundError as e:
        # Command not found - this is expected when checking tool availability
        # Don't log as error, just raise SubprocessError with clear message
        raise SubprocessError(
            f"Command not found: {' '.join(cmd)} - {str(e)}",
            command=cmd,
            original_error=e,
        ) from e
    except OSError as e:
        # Other OS-level errors (permission denied, etc.)
        logfire.warning("Command execution failed (OS error)", cmd=cmd, error=str(e))
        raise SubprocessError(
            f"Command execution failed: {' '.join(cmd)} - {str(e)}",
            command=cmd,
            original_error=e,
        ) from e
    except Exception as e:
        # Unexpected errors
        logfire.error("Command execution failed (unexpected error)", cmd=cmd, error=str(e))
        raise SubprocessError(
            f"Command execution failed: {' '.join(cmd)} - {str(e)}",
            command=cmd,
            original_error=e,
        ) from e
    finally:
        # Ensure process is cleaned up even if there was an error
        if proc and proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except Exception as e:
                logger.warning(f"Failed to cleanup process: {e}")
