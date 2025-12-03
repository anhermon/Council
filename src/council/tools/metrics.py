"""Code metrics tools for complexity and maintainability analysis."""

import ast
from typing import Any

import logfire

from .path_utils import resolve_file_path

# Maximum file size to read (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


class ComplexityVisitor(ast.NodeVisitor):
    """AST visitor to calculate cyclomatic complexity."""

    def __init__(self) -> None:
        """Initialize complexity visitor."""
        self.complexity = 1  # Base complexity
        self.functions: list[dict[str, Any]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Visit function definition and calculate complexity."""
        complexity = 1  # Base complexity for function
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1

        self.functions.append(
            {
                "name": node.name,
                "complexity": complexity,
                "lines": node.end_lineno - node.lineno + 1 if node.end_lineno else 0,
            }
        )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition."""
        self.generic_visit(node)


async def calculate_complexity(file_path: str, base_path: str | None = None) -> dict[str, Any]:
    """
    Calculate code complexity and maintainability metrics.

    This tool calculates cyclomatic complexity, maintainability index,
    and other code quality metrics to help assess code maintainability.

    Args:
        file_path: Path to the file to analyze

    Returns:
        Dictionary with complexity metrics:
        - cyclomatic_complexity: Overall cyclomatic complexity
        - maintainability_index: Maintainability index (0-100)
        - function_complexities: List of function-level complexities
        - lines_of_code: Total lines of code
        - comment_ratio: Ratio of comments to code

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist
    """
    logfire.info("Calculating code complexity", file_path=file_path, base_path=base_path)

    try:
        resolved_path = resolve_file_path(file_path, base_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not resolved_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # Only support Python files for now
        if resolved_path.suffix != ".py":
            return {
                "cyclomatic_complexity": 0,
                "maintainability_index": 0,
                "function_complexities": [],
                "lines_of_code": 0,
                "comment_ratio": 0.0,
                "note": "Complexity calculation only supported for Python files",
            }

        # Read file
        content = resolved_path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")

        # Parse AST
        try:
            tree = ast.parse(content, filename=str(resolved_path))
        except SyntaxError:
            return {
                "cyclomatic_complexity": 0,
                "maintainability_index": 0,
                "function_complexities": [],
                "lines_of_code": len(lines),
                "comment_ratio": 0.0,
                "note": "File contains syntax errors, cannot calculate complexity",
            }

        # Calculate complexity using visitor
        visitor = ComplexityVisitor()
        visitor.visit(tree)

        # Calculate overall complexity (sum of function complexities)
        total_complexity = sum(func["complexity"] for func in visitor.functions)
        if total_complexity == 0:
            total_complexity = 1  # At least 1 for the file itself

        # Count lines of code (excluding comments and blank lines)
        code_lines = 0
        comment_lines = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                comment_lines += 1
            else:
                code_lines += 1

        # Calculate comment ratio
        comment_ratio = (comment_lines / code_lines * 100) if code_lines > 0 else 0.0

        # Calculate maintainability index (simplified formula)
        # MI = 171 - 5.2 * ln(avg_complexity) - 0.23 * ln(avg_lines) - 16.2 * ln(avg_halstead_volume)
        # Simplified version: MI = 171 - 5.2 * ln(complexity) - 0.23 * ln(lines)
        import math

        avg_complexity = total_complexity / len(visitor.functions) if visitor.functions else 1
        avg_lines = (
            sum(func["lines"] for func in visitor.functions) / len(visitor.functions)
            if visitor.functions
            else len(lines)
        )

        # Simplified maintainability index calculation
        if avg_complexity > 0 and avg_lines > 0:
            mi = 171 - 5.2 * math.log(avg_complexity) - 0.23 * math.log(avg_lines)
            # Clamp to 0-100 range
            maintainability_index = max(0, min(100, mi))
        else:
            maintainability_index = 100  # Perfect if no complexity

        result = {
            "cyclomatic_complexity": total_complexity,
            "maintainability_index": round(maintainability_index, 2),
            "function_complexities": visitor.functions,
            "lines_of_code": code_lines,
            "comment_ratio": round(comment_ratio, 2),
            "total_lines": len(lines),
            "function_count": len(visitor.functions),
        }

        logfire.info(
            "Complexity calculation completed",
            file_path=file_path,
            complexity=total_complexity,
            maintainability=maintainability_index,
        )
        return result

    except Exception as e:
        logfire.error("Complexity calculation failed", file_path=file_path, error=str(e))
        raise
