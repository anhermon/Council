"""Static analysis tool integration for code quality checks."""

import asyncio
import json
from pathlib import Path
from typing import Any

import logfire

from ..config import settings
from .path_utils import resolve_file_path

# Maximum output size (10MB)
MAX_OUTPUT_SIZE = 10 * 1024 * 1024

# Timeout for static analysis tools (5 minutes)
STATIC_ANALYSIS_TIMEOUT = 300.0


async def _run_tool_command(
    cmd: list[str], cwd: Path | None = None, timeout: float = STATIC_ANALYSIS_TIMEOUT
) -> tuple[str, str, int]:
    """
    Run a static analysis tool command.

    Args:
        cmd: Command as list of strings
        cwd: Working directory
        timeout: Command timeout

    Returns:
        Tuple of (stdout, stderr, return_code)
    """
    if cwd is None:
        cwd = settings.project_root.resolve()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        # Check output size
        if len(stdout_text) > MAX_OUTPUT_SIZE:
            logfire.warning("Tool output too large, truncating", size=len(stdout_text))
            stdout_text = stdout_text[:MAX_OUTPUT_SIZE]

        return stdout_text, stderr_text, proc.returncode

    except TimeoutError as e:
        raise TimeoutError(f"Static analysis command timed out after {timeout} seconds") from e
    except Exception as e:
        logfire.error("Static analysis command failed", cmd=cmd, error=str(e))
        raise


async def run_static_analysis(file_path: str, base_path: str | None = None) -> dict[str, Any]:
    """
    Run static analysis tools (ruff, mypy, pylint) on a file.

    This tool runs common static analysis tools and returns their findings,
    which can be correlated with the AI review for more comprehensive analysis.

    Args:
        file_path: Path to the file to analyze

    Returns:
        Dictionary with analysis results from each tool:
        - ruff: Ruff linting results
        - mypy: MyPy type checking results (Python only)
        - pylint: Pylint results (Python only)
        - available_tools: List of tools that were available

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist
    """
    logfire.info("Running static analysis", file_path=file_path, base_path=base_path)

    try:
        resolved_path = resolve_file_path(file_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not resolved_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        project_root = settings.project_root.resolve()
        results: dict[str, Any] = {
            "ruff": None,
            "mypy": None,
            "pylint": None,
            "available_tools": [],
        }

        # Only run Python-specific tools for .py files
        is_python = resolved_path.suffix == ".py"

        if is_python:
            # Helper functions to run each tool
            async def run_ruff() -> tuple[str, dict[str, Any] | None]:
                """Run Ruff analysis."""
                try:
                    # Check if ruff is available
                    check_proc = await asyncio.create_subprocess_exec(
                        "ruff",
                        "--version",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await check_proc.wait()
                    if check_proc.returncode != 0:
                        return "ruff", None

                    # Run ruff
                    stdout, stderr, return_code = await _run_tool_command(
                        ["ruff", "check", "--output-format", "json", str(resolved_path)],
                        cwd=project_root,
                        timeout=60.0,
                    )
                    # Parse JSON output
                    try:
                        ruff_results = json.loads(stdout) if stdout.strip() else []
                        return "ruff", {
                            "issues": ruff_results,
                            "return_code": return_code,
                            "stderr": stderr,
                        }
                    except json.JSONDecodeError:
                        # Fallback to text output
                        return "ruff", {
                            "output": stdout,
                            "stderr": stderr,
                            "return_code": return_code,
                        }
                except Exception as e:
                    logfire.warning("Ruff analysis failed", error=str(e))
                    return "ruff", {"error": str(e)}

            async def run_mypy() -> tuple[str, dict[str, Any] | None]:
                """Run MyPy analysis."""
                try:
                    # Check if mypy is available
                    check_proc = await asyncio.create_subprocess_exec(
                        "mypy",
                        "--version",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await check_proc.wait()
                    if check_proc.returncode != 0:
                        return "mypy", None

                    # Run mypy
                    stdout, stderr, return_code = await _run_tool_command(
                        [
                            "mypy",
                            "--no-error-summary",
                            "--show-error-codes",
                            str(resolved_path),
                        ],
                        cwd=project_root,
                        timeout=120.0,
                    )
                    return "mypy", {
                        "output": stdout,
                        "stderr": stderr,
                        "return_code": return_code,
                    }
                except Exception as e:
                    logfire.warning("MyPy analysis failed", error=str(e))
                    return "mypy", {"error": str(e)}

            async def run_pylint() -> tuple[str, dict[str, Any] | None]:
                """Run Pylint analysis."""
                try:
                    # Check if pylint is available
                    check_proc = await asyncio.create_subprocess_exec(
                        "pylint",
                        "--version",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await check_proc.wait()
                    if check_proc.returncode != 0:
                        return "pylint", None

                    # Run pylint
                    stdout, stderr, return_code = await _run_tool_command(
                        [
                            "pylint",
                            "--output-format=json",
                            "--disable=all",
                            "--enable=C,R,W",
                            str(resolved_path),
                        ],
                        cwd=project_root,
                        timeout=120.0,
                    )
                    # Parse JSON output
                    try:
                        pylint_results = json.loads(stdout) if stdout.strip() else []
                        return "pylint", {
                            "issues": pylint_results,
                            "return_code": return_code,
                            "stderr": stderr,
                        }
                    except json.JSONDecodeError:
                        # Fallback to text output
                        return "pylint", {
                            "output": stdout,
                            "stderr": stderr,
                            "return_code": return_code,
                        }
                except Exception as e:
                    logfire.warning("Pylint analysis failed", error=str(e))
                    return "pylint", {"error": str(e)}

            # Run all tools in parallel
            tool_results = await asyncio.gather(
                run_ruff(), run_mypy(), run_pylint(), return_exceptions=True
            )

            # Process results
            for result in tool_results:
                if isinstance(result, Exception):
                    logfire.warning("Tool execution raised exception", error=str(result))
                    continue

                tool_name, tool_data = result
                if tool_data is not None:
                    results["available_tools"].append(tool_name)
                    results[tool_name] = tool_data

        logfire.info(
            "Static analysis completed",
            file_path=file_path,
            tools=results["available_tools"],
        )
        return results

    except Exception as e:
        logfire.error("Static analysis failed", file_path=file_path, error=str(e))
        raise
