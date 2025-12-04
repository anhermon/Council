"""Architecture analysis tools for design patterns and coupling."""

import ast
import re
from typing import Any

import logfire
from tree_sitter import Query, QueryCursor

from ..core.parser import LANGUAGE_MAP, get_code_parser
from .path_utils import resolve_file_path


def _analyze_architecture_treesitter(
    content: str, extension: str, parser_instance: Any, file_name: str
) -> dict[str, Any]:
    """
    Analyze architecture using Tree Sitter for non-Python languages.

    Args:
        content: File content
        extension: File extension
        parser_instance: CodeParser instance
        file_name: Name of the file for reporting

    Returns:
        Dictionary with architecture analysis
    """
    tree, language_name = parser_instance.parse(content, extension)
    if not tree:
        return {}

    language = parser_instance.get_language(language_name)
    if not language:
        return {}

    design_patterns = []
    anti_patterns = []
    coupling_issues = []
    recommendations = []

    # regex for simple pattern detection (fallback/supplement)
    if re.search(r"Singleton|instance", content, re.IGNORECASE):
        design_patterns.append("Singleton (potential)")
    if re.search(r"Factory", content, re.IGNORECASE):
        design_patterns.append("Factory")
    if re.search(r"Observer|subscribe", content, re.IGNORECASE):
        design_patterns.append("Observer")

    # Tree Sitter Queries
    method_count = 0
    import_count = 0

    try:
        # Count imports for coupling
        query_imports = ""
        if language_name == "javascript":
            query_imports = "(import_statement) @import"
        elif language_name in ["typescript", "tsx"]:
            query_imports = "(import_statement) @import"  # import_require removed
        elif language_name == "java":
            query_imports = "(import_declaration) @import"
        elif language_name == "go":
            query_imports = "(import_spec) @import"

        if query_imports:
            query = Query(language, query_imports)
            cursor = QueryCursor(query)
            captures = cursor.captures(tree.root_node)
            # captures is dict, sum lengths of lists
            import_count = sum(len(nodes) for nodes in captures.values())

        # Count methods/functions for God Object detection
        query_methods = ""
        if language_name in ["javascript", "typescript", "tsx"]:
            query_methods = """
            (class_declaration
              body: (class_body
                (method_definition) @method
              )
            )
            """
        elif language_name == "java":
            query_methods = "(class_declaration body: (class_body (method_declaration) @method))"
        # Go doesn't have classes in the same way, skip for now

        if query_methods:
            query = Query(language, query_methods)
            cursor = QueryCursor(query)
            captures = cursor.captures(tree.root_node)
            method_count = sum(len(nodes) for nodes in captures.values())

            if method_count > 20:
                anti_patterns.append(f"God Object: File contains {method_count} methods in classes")
                recommendations.append("Consider splitting classes into smaller components")

    except Exception as e:
        logfire.warning(f"Tree Sitter architecture query failed for {language_name}", error=str(e))

    # Coupling checks
    if import_count > 15:
        coupling_issues.append(f"High Coupling: {import_count} imports in {file_name}")
        recommendations.append(f"Reduce dependencies in {file_name}")

    return {
        "design_patterns": design_patterns,
        "anti_patterns": anti_patterns,
        "coupling_analysis": {
            "issues": coupling_issues,
            "import_count": import_count,
        },
        "recommendations": recommendations,
    }


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

        # Collect files to analyze
        files_to_analyze = []
        if resolved_path.is_file():
            files_to_analyze = [resolved_path]
        else:
            # Analyze supported files in directory
            for ext in LANGUAGE_MAP:
                files_to_analyze.extend(list(resolved_path.rglob(f"*{ext}")))
            files_to_analyze = files_to_analyze[:50]  # Limit to 50 files

        design_patterns: list[str] = []
        anti_patterns: list[str] = []
        coupling_issues: list[str] = []
        recommendations: list[str] = []
        analyzed_count = 0  # Track how many files were actually analyzed

        parser_instance = get_code_parser()

        # Analyze each file
        for file_path_obj in files_to_analyze:
            try:
                content = file_path_obj.read_text(encoding="utf-8", errors="replace")
                extension = file_path_obj.suffix.lower()

                if extension == ".py":
                    # Use existing Python AST logic
                    try:
                        tree = ast.parse(content, filename=str(file_path_obj))
                        analyzed_count += 1
                    except SyntaxError:
                        continue

                    # (Original Python logic preserved)
                    if re.search(r"__instance\s*=|_instance\s*=", content):
                        design_patterns.append("Singleton")
                    if re.search(
                        r"def\s+\w*factory\w*\(|class\s+\w*Factory\w*", content, re.IGNORECASE
                    ):
                        design_patterns.append("Factory")
                    if re.search(r"notify|observer|subscribe|publish", content, re.IGNORECASE):
                        design_patterns.append("Observer")
                    if re.search(r"strategy|algorithm", content, re.IGNORECASE):
                        design_patterns.append("Strategy")

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

                    # Detect deep nesting
                    def get_max_depth(node: ast.AST, depth: int = 0) -> int:
                        """Calculate maximum nesting depth in a node."""
                        max_depth = depth
                        for child in ast.iter_child_nodes(node):
                            if isinstance(
                                child,
                                ast.If
                                | ast.For
                                | ast.While
                                | ast.With
                                | ast.Try
                                | ast.FunctionDef
                                | ast.AsyncFunctionDef,
                            ):
                                child_depth = get_max_depth(child, depth + 1)
                                max_depth = max(max_depth, child_depth)
                        return max_depth

                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                            max_depth = get_max_depth(node)
                            if max_depth > 5:  # More than 5 levels of nesting
                                anti_patterns.append(
                                    f"Deep Nesting: {node.name} has {max_depth} levels of nesting"
                                )
                                recommendations.append(
                                    f"Consider refactoring {node.name} to reduce nesting depth"
                                )
                                break  # Only report once per function

                    imports = []
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            imports.extend([alias.name for alias in node.names])
                        elif isinstance(node, ast.ImportFrom) and node.module:
                            imports.append(node.module)

                    if len(imports) > 15:
                        coupling_issues.append(
                            f"High Coupling: {len(imports)} imports in {file_path_obj.name}"
                        )
                        recommendations.append(
                            f"Consider reducing dependencies in {file_path_obj.name} to improve modularity"
                        )

                    internal_imports = [
                        imp for imp in imports if not imp.startswith(("http", "json", "os", "sys"))
                    ]
                    if len(internal_imports) > 10:
                        coupling_issues.append(
                            f"Potential Circular Dependencies: Many internal imports in {file_path_obj.name}"
                        )

                elif extension in LANGUAGE_MAP:
                    # Use Tree Sitter for other languages
                    analyzed_count += 1
                    ts_result = _analyze_architecture_treesitter(
                        content, extension, parser_instance, file_path_obj.name
                    )
                    if ts_result:
                        design_patterns.extend(ts_result.get("design_patterns", []))
                        anti_patterns.extend(ts_result.get("anti_patterns", []))
                        if "coupling_analysis" in ts_result:
                            coupling_issues.extend(ts_result["coupling_analysis"].get("issues", []))
                        recommendations.extend(ts_result.get("recommendations", []))
                else:
                    # Non-supported file type
                    recommendations.append(
                        f"Architecture analysis is only supported for Python files and other supported languages. {file_path_obj.name} is not supported."
                    )

            except Exception as e:
                logfire.warning("Failed to analyze file", file=str(file_path_obj), error=str(e))
                continue

        # Calculate cohesion score (simplified)
        if analyzed_count == 0:
            # No files were actually analyzed (all unsupported or syntax errors)
            cohesion_score = 0
        else:
            cohesion_score = 100
            cohesion_score -= len(anti_patterns) * 5
            cohesion_score -= len(coupling_issues) * 3
            cohesion_score = max(0, min(100, cohesion_score))

        design_patterns = list(set(design_patterns))
        anti_patterns = list(set(anti_patterns))
        coupling_issues = list(set(coupling_issues))
        recommendations = list(set(recommendations))

        result = {
            "design_patterns": design_patterns,
            "anti_patterns": anti_patterns,
            "coupling_analysis": {
                "issues": coupling_issues,
                "import_count": 0,  # Aggregate count not easily available for mix
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
