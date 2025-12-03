"""Testing tools for test coverage and quality analysis."""

import asyncio
import re
from typing import Any

import logfire

from ..config import settings
from .path_utils import resolve_file_path

# Maximum file size to read (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


async def find_related_tests(file_path: str, base_path: str | None = None) -> list[str]:
    """
    Find test files related to a given code file.

    This tool searches for test files that might test the given file,
    using common naming conventions (test_*.py, *_test.py, etc.).

    Args:
        file_path: Path to the code file

    Returns:
        List of paths to related test files

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist
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

    except Exception as e:
        logfire.error("Failed to find related tests", file_path=file_path, error=str(e))
        raise


async def check_test_coverage(file_path: str, base_path: str | None = None) -> dict[str, Any]:
    """
    Check test coverage for a file using coverage.py.

    This tool runs coverage analysis to determine how much of the code
    is covered by tests.

    Args:
        file_path: Path to the file to check coverage for

    Returns:
        Dictionary with coverage information:
        - covered: Whether coverage data is available
        - coverage_percent: Coverage percentage (0-100)
        - lines_covered: Number of lines covered
        - lines_total: Total number of lines
        - missing_lines: List of line numbers not covered

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist
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
        try:
            check_proc = await asyncio.create_subprocess_exec(
                "coverage",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await check_proc.wait()
            if check_proc.returncode != 0:
                return {
                    "covered": False,
                    "coverage_percent": 0,
                    "lines_covered": 0,
                    "lines_total": 0,
                    "missing_lines": [],
                    "note": "coverage.py not available",
                }
        except Exception:
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
            proc = await asyncio.create_subprocess_exec(
                "coverage",
                "report",
                "--include",
                rel_path,
                "--format=json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_root),
            )

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)

            if proc.returncode == 0 and stdout:
                import json

                try:
                    coverage_data = json.loads(stdout.decode("utf-8", errors="replace"))
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

        except Exception as e:
            logfire.warning("Coverage check failed", error=str(e))
            return {
                "covered": False,
                "coverage_percent": 0,
                "lines_covered": 0,
                "lines_total": 0,
                "missing_lines": [],
                "note": f"Coverage check failed: {str(e)}",
            }

    except Exception as e:
        logfire.error("Test coverage check failed", file_path=file_path, error=str(e))
        raise


async def check_test_quality(test_file: str) -> dict[str, Any]:
    """
    Analyze test quality and structure.

    This tool analyzes a test file to assess test quality, including
    test structure, assertions, and best practices.

    Args:
        test_file: Path to the test file

    Returns:
        Dictionary with test quality metrics:
        - test_count: Number of test functions/methods
        - assertion_count: Number of assertions
        - test_coverage: Estimated coverage (if available)
        - quality_score: Quality score (0-100)
        - issues: List of quality issues found

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist
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

        # Count test functions
        test_pattern = re.compile(
            r"^\s*(def|async def)\s+test_|^\s*def\s+.*test.*\(|^\s*class\s+Test"
        )
        test_count = len(test_pattern.findall(content, re.MULTILINE))

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

    except Exception as e:
        logfire.error("Test quality check failed", test_file=test_file, error=str(e))
        raise
