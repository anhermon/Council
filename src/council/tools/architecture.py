"""Architecture analysis tools for design patterns and coupling."""

import ast
import re
from typing import Any

import logfire

from .path_utils import resolve_file_path


async def analyze_architecture(file_path: str, base_path: str | None = None) -> dict[str, Any]:
    """
    Analyze code architecture, design patterns, and coupling.

    This tool analyzes code structure to identify design patterns,
    anti-patterns, coupling issues, and architectural concerns.

    Args:
        file_path: Path to the file or directory to analyze
        base_path: Optional base path to resolve relative paths from

    Returns:
        Dictionary with architectural analysis:
        - design_patterns: List of detected design patterns
        - anti_patterns: List of detected anti-patterns
        - coupling_analysis: Analysis of code coupling
        - cohesion_score: Cohesion score (0-100)
        - recommendations: List of architectural recommendations

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist
    """
    logfire.info("Analyzing architecture", file_path=file_path, base_path=base_path)

    try:
        resolved_path = resolve_file_path(file_path, base_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"File or directory not found: {file_path}")

        # Only support Python files for now
        if resolved_path.is_file() and resolved_path.suffix != ".py":
            return {
                "design_patterns": [],
                "anti_patterns": [],
                "coupling_analysis": {},
                "cohesion_score": 0,
                "recommendations": ["Architecture analysis only supported for Python files"],
            }

        # Analyze single file or directory
        if resolved_path.is_file():
            files_to_analyze = [resolved_path]
        else:
            # Analyze all Python files in directory
            files_to_analyze = list(resolved_path.rglob("*.py"))[:50]  # Limit to 50 files

        design_patterns: list[str] = []
        anti_patterns: list[str] = []
        coupling_issues: list[str] = []
        recommendations: list[str] = []

        # Analyze each file
        for file_path_obj in files_to_analyze:
            try:
                content = file_path_obj.read_text(encoding="utf-8", errors="replace")

                # Parse AST
                try:
                    tree = ast.parse(content, filename=str(file_path_obj))
                except SyntaxError:
                    continue

                # Detect design patterns
                # Singleton pattern
                if re.search(r"__instance\s*=|_instance\s*=", content):
                    design_patterns.append("Singleton")

                # Factory pattern
                if re.search(
                    r"def\s+\w*factory\w*\(|class\s+\w*Factory\w*", content, re.IGNORECASE
                ):
                    design_patterns.append("Factory")

                # Observer pattern
                if re.search(r"notify|observer|subscribe|publish", content, re.IGNORECASE):
                    design_patterns.append("Observer")

                # Strategy pattern
                if re.search(r"strategy|algorithm", content, re.IGNORECASE):
                    design_patterns.append("Strategy")

                # Detect anti-patterns
                # God object (too many methods/attributes)
                class_count = len(
                    [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
                )
                if class_count > 0:
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            methods = [
                                n
                                for n in node.body
                                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                            ]
                            if len(methods) > 20:
                                anti_patterns.append(
                                    f"God Object: {node.name} has {len(methods)} methods"
                                )
                                recommendations.append(
                                    f"Consider splitting {node.name} class into smaller, focused classes"
                                )

                # Long parameter list
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                        and len(node.args.args) > 7
                    ):
                        anti_patterns.append(
                            f"Long Parameter List: {node.name} has {len(node.args.args)} parameters"
                        )
                        recommendations.append(
                            f"Consider using a configuration object for {node.name} parameters"
                        )

                # Deep nesting
                max_depth = 0

                def check_depth(node: ast.AST, depth: int = 0) -> None:
                    """
                    Recursively check the maximum nesting depth of control structures.

                    Args:
                        node: AST node to analyze
                        depth: Current depth level
                    """
                    nonlocal max_depth
                    max_depth = max(max_depth, depth)
                    for child in ast.iter_child_nodes(node):
                        if isinstance(child, ast.If | ast.For | ast.While | ast.Try | ast.With):
                            check_depth(child, depth + 1)

                check_depth(tree)
                if max_depth > 4:
                    anti_patterns.append(f"Deep Nesting: Maximum nesting depth is {max_depth}")
                    recommendations.append("Consider refactoring to reduce nesting depth")

                # Analyze coupling
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend([alias.name for alias in node.names])
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imports.append(node.module)

                # High coupling (many imports)
                if len(imports) > 15:
                    coupling_issues.append(
                        f"High Coupling: {len(imports)} imports in {file_path_obj.name}"
                    )
                    recommendations.append(
                        f"Consider reducing dependencies in {file_path_obj.name} to improve modularity"
                    )

                # Circular dependency detection (simplified)
                internal_imports = [
                    imp for imp in imports if not imp.startswith(("http", "json", "os", "sys"))
                ]
                if len(internal_imports) > 10:
                    coupling_issues.append(
                        f"Potential Circular Dependencies: Many internal imports in {file_path_obj.name}"
                    )

            except Exception as e:
                logfire.warning("Failed to analyze file", file=str(file_path_obj), error=str(e))
                continue

        # Calculate cohesion score (simplified)
        # Higher cohesion = fewer unrelated functions/classes in same file
        cohesion_score = 100
        if len(files_to_analyze) > 0:
            # Penalize for anti-patterns
            cohesion_score -= len(anti_patterns) * 5
            cohesion_score -= len(coupling_issues) * 3
            cohesion_score = max(0, min(100, cohesion_score))

        # Remove duplicates
        design_patterns = list(set(design_patterns))
        anti_patterns = list(set(anti_patterns))
        coupling_issues = list(set(coupling_issues))
        recommendations = list(set(recommendations))

        result = {
            "design_patterns": design_patterns,
            "anti_patterns": anti_patterns,
            "coupling_analysis": {
                "issues": coupling_issues,
                "import_count": len(imports) if "imports" in locals() else 0,
            },
            "cohesion_score": cohesion_score,
            "recommendations": recommendations,
        }

        logfire.info(
            "Architecture analysis completed",
            file_path=file_path,
            patterns=len(design_patterns),
            anti_patterns=len(anti_patterns),
        )
        return result

    except Exception as e:
        logfire.error("Architecture analysis failed", file_path=file_path, error=str(e))
        raise
