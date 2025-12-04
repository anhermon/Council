"""Security scanning tools for vulnerability detection."""

import json
from pathlib import Path
from typing import Any

import logfire

from ..config import get_settings
from .exceptions import SubprocessError, SubprocessTimeoutError
from .path_utils import resolve_file_path
from .utils import resolve_tool_command, run_command_safely

settings = get_settings()

# Maximum output size (10MB)
MAX_OUTPUT_SIZE = 10 * 1024 * 1024

# Timeout for security scanning tools (5 minutes)
SECURITY_SCAN_TIMEOUT = 300.0


async def _run_security_tool(
    cmd: list[str], cwd: Path | None = None, timeout: float = SECURITY_SCAN_TIMEOUT
) -> tuple[str, str, int]:
    """
    Run a security scanning tool command.

    Uses run_command_safely for proper timeout handling and process cleanup.

    Args:
        cmd: Command as list of strings
        cwd: Working directory
        timeout: Command timeout

    Returns:
        Tuple of (stdout, stderr, return_code)

    Raises:
        SubprocessTimeoutError: If command times out
        SubprocessError: If command execution fails
    """
    if cwd is None:
        cwd = settings.project_root.resolve()

    try:
        stdout, stderr, return_code = await run_command_safely(
            cmd,
            cwd=cwd,
            timeout=timeout,
            max_output_size=MAX_OUTPUT_SIZE,
            check=False,  # Don't raise on non-zero return codes
        )
        return stdout, stderr, return_code
    except SubprocessTimeoutError as e:
        raise SubprocessTimeoutError(
            f"Security scan command timed out after {timeout} seconds: {' '.join(cmd)}",
            command=cmd,
            original_error=e.original_error if hasattr(e, "original_error") else e,
        ) from e
    except SubprocessError:
        # Re-raise subprocess errors as-is
        raise
    except Exception as e:
        logfire.error("Security scan command failed unexpectedly", cmd=cmd, error=str(e))
        raise SubprocessError(
            f"Security scan command failed: {' '.join(cmd)} - {str(e)}",
            command=cmd,
            original_error=e,
        ) from e


async def scan_security_vulnerabilities(
    file_path: str, base_path: str | None = None
) -> dict[str, Any]:
    """
    Scan code for security vulnerabilities using bandit and semgrep.

    This tool runs security scanners to detect common vulnerabilities and
    security issues. Results are included in the review context.

    Args:
        file_path: Path to the file or directory to scan

    Returns:
        Dictionary with security scan results:
        - bandit: Bandit results (Python only)
        - semgrep: Semgrep results (multi-language)
        - available_tools: List of tools that were available

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist
    """
    logfire.info("Scanning for security vulnerabilities", file_path=file_path, base_path=base_path)

    try:
        resolved_path = resolve_file_path(file_path, base_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"File or directory not found: {file_path}")

        project_root = settings.project_root.resolve()
        results: dict[str, Any] = {
            "bandit": None,
            "semgrep": None,
            "available_tools": [],
        }

        # Determine if this is a Python file or directory
        is_python = False
        if resolved_path.is_file():
            is_python = resolved_path.suffix == ".py"
        elif resolved_path.is_dir():
            # Check if directory contains Python files
            py_files = list(resolved_path.rglob("*.py"))
            is_python = len(py_files) > 0

        # Run Bandit (Python security scanner)
        if is_python:
            try:
                # Resolve tool command (use uv run if available)
                bandit_cmd = resolve_tool_command("bandit")

                # Check if bandit is available
                try:
                    await run_command_safely(
                        bandit_cmd + ["--version"],
                        cwd=project_root,
                        timeout=settings.tool_check_timeout,
                        check=False,
                    )
                except (SubprocessError, SubprocessTimeoutError):
                    # Bandit not available
                    pass
                else:
                    results["available_tools"].append("bandit")
                    try:
                        # Run bandit with JSON output
                        target = str(resolved_path)
                        stdout, stderr, return_code = await _run_security_tool(
                            bandit_cmd
                            + [
                                "-r",
                                target,
                                "-f",
                                "json",
                                "-ll",  # Low confidence, low severity (show all)
                            ],
                            cwd=project_root,
                            timeout=180.0,
                        )
                        # Parse JSON output
                        try:
                            bandit_results = json.loads(stdout) if stdout.strip() else {}
                            results["bandit"] = {
                                "results": bandit_results,
                                "return_code": return_code,
                                "stderr": stderr,
                            }
                        except json.JSONDecodeError:
                            # Fallback to text output
                            results["bandit"] = {
                                "output": stdout,
                                "stderr": stderr,
                                "return_code": return_code,
                            }
                    except (SubprocessError, SubprocessTimeoutError) as e:
                        logfire.warning("Bandit scan failed", error=str(e))
                        results["bandit"] = {"error": str(e)}
            except Exception as e:
                # Unexpected error checking bandit availability
                logfire.debug("Bandit availability check failed", error=str(e))
                pass

        # Run Semgrep (multi-language security scanner)
        try:
            # Resolve tool command (use uv run if available)
            semgrep_cmd = resolve_tool_command("semgrep")

            # Check if semgrep is available
            try:
                await run_command_safely(
                    semgrep_cmd + ["--version"],
                    cwd=project_root,
                    timeout=settings.tool_check_timeout,
                    check=False,
                )
            except (SubprocessError, SubprocessTimeoutError):
                # Semgrep not available
                pass
            else:
                results["available_tools"].append("semgrep")
                try:
                    target = str(resolved_path)
                    stdout, stderr, return_code = await _run_security_tool(
                        semgrep_cmd
                        + [
                            "--json",
                            "--quiet",
                            "--config=auto",  # Use auto config for security rules
                            target,
                        ],
                        cwd=project_root,
                        timeout=180.0,
                    )
                    # Parse JSON output
                    try:
                        semgrep_results = json.loads(stdout) if stdout.strip() else {}
                        results["semgrep"] = {
                            "results": semgrep_results,
                            "return_code": return_code,
                            "stderr": stderr,
                        }
                    except json.JSONDecodeError:
                        # Fallback to text output
                        results["semgrep"] = {
                            "output": stdout,
                            "stderr": stderr,
                            "return_code": return_code,
                        }
                except (SubprocessError, SubprocessTimeoutError) as e:
                    logfire.warning("Semgrep scan failed", error=str(e))
                    results["semgrep"] = {"error": str(e)}
        except Exception as e:
            # Unexpected error checking semgrep availability
            logfire.debug("Semgrep availability check failed", error=str(e))
            pass

        logfire.info(
            "Security scan completed",
            file_path=file_path,
            tools=results["available_tools"],
        )
        return results

    except Exception as e:
        logfire.error("Security scan failed", file_path=file_path, error=str(e))
        raise
