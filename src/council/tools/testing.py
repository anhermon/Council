"""Testing tools for test coverage and quality analysis."""

import json
import re
from typing import Any

import logfire

from ..config import get_settings
from .exceptions import SubprocessError
from .path_utils import resolve_file_path
from .utils import resolve_tool_command, run_command_safely

settings = get_settings()


async def find_related_tests(file_path: str, base_path: str | None = None) -> list[str]:
    """
    Find test files related to a given code file.

    This tool searches for test files that might test the given file,
    using common naming conventions (test_*.py, *_test.py, etc.).
    The search includes checking imports in test files to find files that
    import the target module.

    Args:
        file_path: Path to the code file
        base_path: Optional base path to resolve relative paths from

    Returns:
        List of paths to related test files (limited to 20 results)

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist
        RuntimeError: If an unexpected error occurs during search

    Note:
        This function does not have explicit timeout handling as it primarily
        performs file system operations which are typically fast. File reading
        operations may take longer for large test files but are not expected to
        exceed reasonable limits.
    """
    logfire.info("Finding related tests", file_path=file_path, base_path=base_path)

    try:
        resolved_path = resolve_file_path(file_path, base_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not resolved_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        project_root = settings.project_root.resolve()

        # Get file name without extension
        file_stem = resolved_path.stem
        file_name = resolved_path.name

        # Common test file patterns
        test_patterns = [
            f"test_{file_name}",
            f"test_{file_stem}.py",
            f"{file_stem}_test.py",
            f"tests/test_{file_name}",
            f"tests/test_{file_stem}.py",
            f"tests/{file_stem}_test.py",
        ]

        # Also check for test directories
        test_dirs = ["tests", "test", "__tests__", "spec"]

        found_tests: list[str] = []

        # Search in same directory
        for pattern in test_patterns:
            test_path = resolved_path.parent / pattern
            if test_path.exists() and test_path.is_file():
                try:
                    rel_path = str(test_path.relative_to(project_root))
                    found_tests.append(rel_path)
                except (ValueError, AttributeError):
                    found_tests.append(str(test_path))

        # Search in test directories
        for test_dir_name in test_dirs:
            test_dir = project_root / test_dir_name
            if test_dir.exists() and test_dir.is_dir():
                for pattern in test_patterns:
                    test_path = test_dir / pattern.split("/")[-1]  # Get just filename
                    if test_path.exists() and test_path.is_file():
                        try:
                            rel_path = str(test_path.relative_to(project_root))
                            if rel_path not in found_tests:
                                found_tests.append(rel_path)
                        except (ValueError, AttributeError):
                            if str(test_path) not in found_tests:
                                found_tests.append(str(test_path))

        # Also search for files that import the module
        module_name = file_stem
        if resolved_path.parent.name:
            # Try to construct module path
            parts = []
            current = resolved_path.parent
            while current != project_root and current != project_root.parent:
                parts.insert(0, current.name)
                current = current.parent
            if parts:
                module_name = ".".join(parts) + "." + file_stem

        # Search for test files that might import this module
        for test_dir_name in test_dirs:
            test_dir = project_root / test_dir_name
            if test_dir.exists() and test_dir.is_dir():
                for test_file in test_dir.rglob("test_*.py"):
                    try:
                        content = test_file.read_text(encoding="utf-8", errors="replace")
                        # Check if file imports the module
                        if (
                            f"import {file_stem}" in content
                            or f"from {module_name}" in content
                            or f"import {module_name}" in content
                        ):
                            try:
                                rel_path = str(test_file.relative_to(project_root))
                                if rel_path not in found_tests:
                                    found_tests.append(rel_path)
                            except (ValueError, AttributeError):
                                if str(test_file) not in found_tests:
                                    found_tests.append(str(test_file))
                    except Exception:
                        continue

        logfire.info("Found related tests", file_path=file_path, count=len(found_tests))
        return found_tests[:20]  # Limit to 20 results

    except (ValueError, FileNotFoundError) as e:
        # Re-raise specific exceptions as-is
        logfire.error("Failed to find related tests", file_path=file_path, error=str(e))
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logfire.error(
            "Failed to find related tests unexpectedly", file_path=file_path, error=str(e)
        )
        raise RuntimeError(f"Failed to find related tests: {str(e)}") from e


async def check_test_coverage(file_path: str, base_path: str | None = None) -> dict[str, Any]:
    """
    Check test coverage for a file using coverage.py.

    This tool runs coverage analysis to determine how much of the code
    is covered by tests. It requires that tests have been run with coverage.py
    first to generate coverage data.

    Args:
        file_path: Path to the file to check coverage for
        base_path: Optional base path to resolve relative paths from

    Returns:
        Dictionary with coverage information:
        - covered: Whether coverage data is available
        - coverage_percent: Coverage percentage (0-100)
        - lines_covered: Number of lines covered
        - lines_total: Total number of lines
        - missing_lines: List of line numbers not covered (limited to 100)
        - note: Optional note explaining why coverage data is unavailable

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist
        RuntimeError: If an unexpected error occurs

    Timeout Behavior:
        - Tool availability check: Uses settings.tool_check_timeout (default 10 seconds)
        - Coverage report generation: Uses settings.test_timeout (default 60 seconds)
        - If timeout occurs, returns a result indicating coverage data is unavailable
        - Processes are properly cleaned up on timeout to prevent resource leaks

    Note:
        Only supports Python files (.py extension). For other file types,
        returns a result indicating coverage checking is not supported.
    """
    logfire.info("Checking test coverage", file_path=file_path, base_path=base_path)

    try:
        resolved_path = resolve_file_path(file_path, base_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not resolved_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # Only support Python files for now
        if resolved_path.suffix != ".py":
            return {
                "covered": False,
                "coverage_percent": 0,
                "lines_covered": 0,
                "lines_total": 0,
                "missing_lines": [],
                "note": "Coverage checking only supported for Python files",
            }

        project_root = settings.project_root.resolve()

        # Check if coverage.py is available
        # Resolve tool command (use uv run if available)
        coverage_cmd = resolve_tool_command(settings.coverage_tool_name)
        try:
            await run_command_safely(
                coverage_cmd + ["--version"],
                cwd=project_root,
                timeout=settings.tool_check_timeout,
                check=False,
            )
        except (RuntimeError, TimeoutError, OSError, SubprocessError):
            return {
                "covered": False,
                "coverage_percent": 0,
                "lines_covered": 0,
                "lines_total": 0,
                "missing_lines": [],
                "note": "coverage.py not available",
            }

        # Try to get coverage data
        try:
            # Get relative path
            try:
                if resolved_path.is_relative_to(project_root):
                    rel_path = str(resolved_path.relative_to(project_root))
                else:
                    rel_path = str(resolved_path)
            except AttributeError:
                rel_path = str(resolved_path).replace(str(project_root) + "/", "")

            # Run coverage report
            stdout, stderr, return_code = await run_command_safely(
                coverage_cmd
                + [
                    "report",
                    "--include",
                    rel_path,
                    "--format=json",
                ],
                cwd=project_root,
                timeout=settings.test_timeout,
                check=False,
            )

            if return_code == 0 and stdout:
                try:
                    coverage_data = json.loads(stdout)
                    files = coverage_data.get("files", {})
                    file_data = files.get(rel_path, {})

                    if file_data:
                        summary = file_data.get("summary", {})
                        covered = summary.get("covered_lines", 0)
                        total = summary.get("num_statements", 0)
                        missing = file_data.get("missing_lines", [])

                        coverage_percent = (covered / total * 100) if total > 0 else 0

                        return {
                            "covered": True,
                            "coverage_percent": round(coverage_percent, 2),
                            "lines_covered": covered,
                            "lines_total": total,
                            "missing_lines": missing[:100],  # Limit to 100 lines
                        }
                except (json.JSONDecodeError, KeyError):
                    pass

            # If JSON parsing failed, try text output
            return {
                "covered": False,
                "coverage_percent": 0,
                "lines_covered": 0,
                "lines_total": 0,
                "missing_lines": [],
                "note": "Coverage data not available. Run tests with coverage first.",
            }

        except (TimeoutError, RuntimeError, OSError, SubprocessError) as e:
            logfire.warning("Coverage check failed", error=str(e))
            return {
                "covered": False,
                "coverage_percent": 0,
                "lines_covered": 0,
                "lines_total": 0,
                "missing_lines": [],
                "note": f"Coverage check failed: {str(e)}",
            }

    except (ValueError, FileNotFoundError) as e:
        # Re-raise specific exceptions as-is
        logfire.error("Test coverage check failed", file_path=file_path, error=str(e))
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logfire.error("Test coverage check failed unexpectedly", file_path=file_path, error=str(e))
        raise RuntimeError(f"Test coverage check failed: {str(e)}") from e


async def check_test_quality(test_file: str) -> dict[str, Any]:
    """
    Analyze test quality and structure.

    This tool analyzes a test file to assess test quality, including
    test structure, assertions, and best practices. It performs static
    analysis of the test file content to identify quality issues.

    Args:
        test_file: Path to the test file

    Returns:
        Dictionary with test quality metrics:
        - test_count: Number of test functions/methods found
        - assertion_count: Number of assertions found
        - quality_score: Quality score (0-100), where 100 is perfect
        - issues: List of quality issues found (e.g., missing docstrings,
          low assertion ratio, use of global variables)

    Raises:
        ValueError: If path is invalid or not a file
        FileNotFoundError: If file doesn't exist
        RuntimeError: If an unexpected error occurs during analysis

    Timeout Behavior:
        This function performs file I/O operations only (reading test file content).
        No explicit timeout is needed as file reading operations are typically
        fast and bounded by file size limits. Large files may take longer but
        are expected to complete within reasonable time.

    Note:
        Only analyzes Python test files (.py extension). For other file types,
        returns a result indicating test quality analysis is not supported.
        The quality score is calculated based on:
        - Presence of docstrings (-10 if missing)
        - Use of setUp methods (-5 if missing for >3 tests)
        - Assertion ratio (-15 if <1 per test, -5 if >5 per test)
        - Use of global variables (-10 if present)
        - Proper test naming (-20 if no test functions found)
    """
    logfire.info("Checking test quality", test_file=test_file)

    try:
        resolved_path = resolve_file_path(test_file)

        if not resolved_path.exists():
            raise FileNotFoundError(f"Test file not found: {test_file}")

        if not resolved_path.is_file():
            raise ValueError(f"Path is not a file: {test_file}")

        # Only analyze Python test files for now
        if resolved_path.suffix != ".py":
            return {
                "test_count": 0,
                "assertion_count": 0,
                "quality_score": 0,
                "issues": ["Test quality analysis only supported for Python files"],
            }

        # Read test file
        content = resolved_path.read_text(encoding="utf-8", errors="replace")

        # Count test functions - look for functions starting with test_ or classes starting with Test
        test_pattern = re.compile(
            r"^\s*(def|async def)\s+test_\w+|^\s*class\s+Test\w+", re.MULTILINE
        )
        test_count = len(test_pattern.findall(content))

        # Count assertions
        assertion_pattern = re.compile(
            r"\bassert\s+|assertEqual|assertNotEqual|assertTrue|assertFalse|"
            r"assertIn|assertNotIn|assertIs|assertIsNot|assertIsNone|assertIsNotNone|"
            r"assertRaises|assertAlmostEqual|assertNotAlmostEqual"
        )
        assertion_count = len(assertion_pattern.findall(content))

        # Basic quality checks
        issues: list[str] = []
        quality_score = 100

        # Check for test docstrings
        if "def test_" in content and '"""' not in content and "'''" not in content:
            issues.append("Test functions lack docstrings")
            quality_score -= 10

        # Check for setup/teardown methods
        if ("def setUp" not in content and "def setup" not in content) and test_count > 3:
            issues.append("Consider using setUp methods for test fixtures")
            quality_score -= 5

        # Check assertion ratio
        if test_count > 0:
            assertion_ratio = assertion_count / test_count
            if assertion_ratio < 1:
                issues.append(f"Low assertion ratio: {assertion_ratio:.2f} assertions per test")
                quality_score -= 15
            elif assertion_ratio > 5:
                issues.append("Tests may be too complex, consider splitting")
                quality_score -= 5

        # Check for test isolation (no shared state)
        if "global " in content and "def test_" in content:
            issues.append("Tests use global variables, may not be isolated")
            quality_score -= 10

        # Check for proper test naming
        if "def test" not in content.lower() and "class test" not in content.lower():
            issues.append("File may not contain proper test functions")
            quality_score -= 20

        quality_score = max(0, quality_score)

        result = {
            "test_count": test_count,
            "assertion_count": assertion_count,
            "quality_score": quality_score,
            "issues": issues,
        }

        logfire.info(
            "Test quality analysis completed",
            test_file=test_file,
            test_count=test_count,
            quality_score=quality_score,
        )
        return result

    except (ValueError, FileNotFoundError) as e:
        # Re-raise specific exceptions as-is
        logfire.error("Test quality check failed", test_file=test_file, error=str(e))
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logfire.error("Test quality check failed unexpectedly", test_file=test_file, error=str(e))
        raise RuntimeError(f"Test quality check failed: {str(e)}") from e
