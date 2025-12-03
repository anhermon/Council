"""Static analysis tool integration for code quality checks."""

import asyncio
import json
from typing import Any

import logfire

from ..config import settings
from .path_utils import resolve_file_path
from .utils import run_command_safely


async def run_static_analysis(file_path: str, base_path: str | None = None) -> dict[str, Any]:
    """
    Run static analysis tools (ruff, mypy, pylint) on a file.

    This tool runs common static analysis tools and returns their findings,
    which can be correlated with the AI review for more comprehensive analysis.

    Args:
        file_path: Path to the file to analyze
        base_path: Optional base path to resolve relative paths from

    Returns:
        Dictionary with analysis results from each tool:
        - ruff: Ruff linting results
        - mypy: MyPy type checking results (Python only)
        - pylint: Pylint results (Python only)
        - available_tools: List of tools that were available

    Raises:
        ValueError: If path is invalid or empty
        FileNotFoundError: If file doesn't exist
        TypeError: If file_path is not a string
    """
    # Input validation
    if not isinstance(file_path, str):
        raise TypeError("file_path must be a string")

    if not file_path or not file_path.strip():
        raise ValueError("file_path cannot be empty or None")

    logfire.info("Running static analysis", file_path=file_path, base_path=base_path)

    try:
        resolved_path = resolve_file_path(file_path, base_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not resolved_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        project_root = settings.project_root.resolve()
        results: dict[str, Any] = {
            settings.ruff_tool_name: None,
            settings.mypy_tool_name: None,
            settings.pylint_tool_name: None,
            "available_tools": [],
        }

        # Only run Python-specific tools for .py files
        is_python = resolved_path.suffix == ".py"

        if is_python:
            # Helper functions to run each tool
            async def run_ruff() -> tuple[str, dict[str, Any] | None]:
                """Run Ruff analysis."""
                tool_name = settings.ruff_tool_name
                try:
                    # Check if ruff is available
                    try:
                        await run_command_safely(
                            [tool_name, "--version"],
                            cwd=project_root,
                            timeout=settings.tool_check_timeout,
                            check=False,
                        )
                    except (RuntimeError, TimeoutError):
                        return tool_name, None

                    # Run ruff
                    stdout, stderr, return_code = await run_command_safely(
                        [tool_name, "check", "--output-format", "json", str(resolved_path)],
                        cwd=project_root,
                        timeout=60.0,  # Ruff-specific timeout
                        max_output_size=settings.max_output_size,
                        check=False,
                    )
                    # Parse JSON output
                    try:
                        ruff_results = json.loads(stdout) if stdout.strip() else []
                        return tool_name, {
                            "issues": ruff_results,
                            "return_code": return_code,
                            "stderr": stderr,
                        }
                    except json.JSONDecodeError:
                        # Fallback to text output
                        return tool_name, {
                            "output": stdout,
                            "stderr": stderr,
                            "return_code": return_code,
                        }
                except (TimeoutError, RuntimeError, OSError) as e:
                    logfire.warning("Ruff analysis failed", error=str(e))
                    return tool_name, {"error": str(e)}

            async def run_mypy() -> tuple[str, dict[str, Any] | None]:
                """Run MyPy analysis."""
                tool_name = settings.mypy_tool_name
                try:
                    # Check if mypy is available
                    try:
                        await run_command_safely(
                            [tool_name, "--version"],
                            cwd=project_root,
                            timeout=settings.tool_check_timeout,
                            check=False,
                        )
                    except (RuntimeError, TimeoutError):
                        return tool_name, None

                    # Run mypy
                    stdout, stderr, return_code = await run_command_safely(
                        [
                            tool_name,
                            "--no-error-summary",
                            "--show-error-codes",
                            str(resolved_path),
                        ],
                        cwd=project_root,
                        timeout=120.0,  # MyPy-specific timeout
                        max_output_size=settings.max_output_size,
                        check=False,
                    )
                    return tool_name, {
                        "output": stdout,
                        "stderr": stderr,
                        "return_code": return_code,
                    }
                except (TimeoutError, RuntimeError, OSError) as e:
                    logfire.warning("MyPy analysis failed", error=str(e))
                    return tool_name, {"error": str(e)}

            async def run_pylint() -> tuple[str, dict[str, Any] | None]:
                """Run Pylint analysis."""
                tool_name = settings.pylint_tool_name
                try:
                    # Check if pylint is available
                    try:
                        await run_command_safely(
                            [tool_name, "--version"],
                            cwd=project_root,
                            timeout=settings.tool_check_timeout,
                            check=False,
                        )
                    except (RuntimeError, TimeoutError):
                        return tool_name, None

                    # Run pylint
                    stdout, stderr, return_code = await run_command_safely(
                        [
                            tool_name,
                            "--output-format=json",
                            "--disable=all",
                            "--enable=C,R,W",
                            str(resolved_path),
                        ],
                        cwd=project_root,
                        timeout=120.0,  # Pylint-specific timeout
                        max_output_size=settings.max_output_size,
                        check=False,
                    )
                    # Parse JSON output
                    try:
                        pylint_results = json.loads(stdout) if stdout.strip() else []
                        return tool_name, {
                            "issues": pylint_results,
                            "return_code": return_code,
                            "stderr": stderr,
                        }
                    except json.JSONDecodeError:
                        # Fallback to text output
                        return tool_name, {
                            "output": stdout,
                            "stderr": stderr,
                            "return_code": return_code,
                        }
                except (TimeoutError, RuntimeError, OSError) as e:
                    logfire.warning("Pylint analysis failed", error=str(e))
                    return tool_name, {"error": str(e)}

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
                    # Use the tool name as key (already set in results dict)
                    if tool_name in results:
                        results[tool_name] = tool_data

        logfire.info(
            "Static analysis completed",
            file_path=file_path,
            tools=results["available_tools"],
        )
        return results

    except (ValueError, TypeError, FileNotFoundError) as e:
        # Re-raise specific exceptions as-is
        logfire.error("Static analysis failed", file_path=file_path, error=str(e))
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logfire.error("Static analysis failed unexpectedly", file_path=file_path, error=str(e))
        raise RuntimeError(f"Static analysis failed: {str(e)}") from e
