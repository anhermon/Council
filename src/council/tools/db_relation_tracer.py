"""Database relation tracing utilities."""

import ast
import re
from pathlib import Path
from typing import Any

import logfire

from .sql_parser import parse_schema_file, parse_sql_query


def extract_queries_from_code(code_content: str) -> list[dict[str, Any]]:
    """
    Extract SQL queries from code content.

    Args:
        code_content: Source code content

    Returns:
        List of query dictionaries with method context
    """
    queries: list[dict[str, Any]] = []

    # Try to parse as Python AST to find method definitions
    try:
        tree = ast.parse(code_content)
        # Use a visitor to properly track method context
        visitor = _QueryExtractorVisitor()
        visitor.visit(tree)
        queries.extend(visitor.queries)

    except SyntaxError:
        # If AST parsing fails, fall back to regex-based extraction
        logfire.debug("AST parsing failed, using regex-based extraction")
        queries.extend(_extract_queries_regex(code_content))

    # Also use regex as fallback/supplement for queries not found by AST
    # (e.g., queries in execute() calls, complex string formatting)
    regex_queries = _extract_queries_regex(code_content)
    # Merge with AST-extracted queries, avoiding duplicates
    existing_queries = {q["query"][:100] for q in queries}
    for regex_query in regex_queries:
        if regex_query["query"][:100] not in existing_queries:
            queries.append(regex_query)

    return queries


class _QueryExtractorVisitor(ast.NodeVisitor):
    """AST visitor to extract SQL queries with proper method context."""

    def __init__(self) -> None:
        """Initialize the visitor."""
        self.queries: list[dict[str, Any]] = []
        self._method_stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definitions and track method name."""
        self._method_stack.append(node.name)
        self.generic_visit(node)
        self._method_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definitions and track method name."""
        self._method_stack.append(node.name)
        self.generic_visit(node)
        self._method_stack.pop()

    def visit_Constant(self, node: ast.Constant) -> None:
        """Visit constant nodes (string literals in Python 3.8+)."""
        if isinstance(node.value, str):
            self._process_string_literal(node.value)

    def visit_Str(self, node: ast.Str) -> None:  # type: ignore[deprecated]  # noqa: ARG002
        """
        Visit string nodes (for Python < 3.8 compatibility).

        Note: ast.Str is deprecated in Python 3.8+ but we keep this method
        for backward compatibility with older Python versions.
        """
        self._process_string_literal(node.s)

    def _process_string_literal(self, query_str: str) -> None:
        """Process a string literal that might contain SQL."""
        if _is_sql_query(query_str):
            parsed = parse_sql_query(query_str)
            current_method = self._method_stack[-1] if self._method_stack else None
            self.queries.append(
                {
                    "method": current_method,
                    "query": query_str[:200] + "..." if len(query_str) > 200 else query_str,
                    "tables": parsed["tables"],
                    "columns": parsed["columns"],
                    "joins": parsed["joins"],
                }
            )


def _is_sql_query(text: str) -> bool:
    """Check if a string looks like a SQL query."""
    sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP"]
    text_upper = text.upper().strip()
    return any(text_upper.startswith(keyword) for keyword in sql_keywords) and len(text) > 10


def _extract_queries_regex(code_content: str) -> list[dict[str, Any]]:
    """Extract SQL queries using regex patterns."""
    queries: list[dict[str, Any]] = []

    # Pattern for triple-quoted strings (common for SQL queries)
    triple_quote_pattern = r'"""(.*?)"""|\'\'\'(.*?)\'\'\''
    for match in re.finditer(triple_quote_pattern, code_content, re.DOTALL):
        query_str = match.group(1) or match.group(2)
        if _is_sql_query(query_str):
            parsed = parse_sql_query(query_str)
            queries.append(
                {
                    "method": None,
                    "query": query_str[:200] + "..." if len(query_str) > 200 else query_str,
                    "tables": parsed["tables"],
                    "columns": parsed["columns"],
                    "joins": parsed["joins"],
                }
            )

    # Pattern for execute() calls with SQL strings
    execute_pattern = (
        r'(?:cur\.execute|cursor\.execute|db\.execute|conn\.execute)\s*\(\s*["\'](.*?)["\']'
    )
    for match in re.finditer(execute_pattern, code_content, re.DOTALL):
        query_str = match.group(1)
        if _is_sql_query(query_str):
            parsed = parse_sql_query(query_str)
            queries.append(
                {
                    "method": None,
                    "query": query_str[:200] + "..." if len(query_str) > 200 else query_str,
                    "tables": parsed["tables"],
                    "columns": parsed["columns"],
                    "joins": parsed["joins"],
                }
            )

    return queries


def build_relation_map(code_content: str, sql_files: list[Path]) -> dict[str, Any]:
    """
    Build a relation map between code, queries, and schema.

    Args:
        code_content: Source code content
        sql_files: List of SQL file paths

    Returns:
        Dictionary with relation mapping information
    """
    if not code_content:
        code_content = ""

    relation_map: dict[str, Any] = {
        "tables_referenced": set(),
        "queries_in_code": [],
        "queries_in_files": [],
        "schema_tables": {},
        "relationships": [],
    }

    # Extract queries from code
    code_queries = extract_queries_from_code(code_content)
    relation_map["queries_in_code"] = code_queries

    # Collect all tables referenced in code queries
    for query_info in code_queries:
        if query_info.get("tables"):
            relation_map["tables_referenced"].update(query_info["tables"])

    # Parse SQL files
    for sql_file in sql_files:
        if not sql_file or not sql_file.exists():
            continue

        try:
            content = sql_file.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue
        except Exception as e:
            logfire.warning("Failed to read SQL file", file=str(sql_file), error=str(e))
            continue

        # Determine if it's a schema file or query file
        content_upper = content.upper()
        if "CREATE TABLE" in content_upper:
            # Parse schema
            try:
                schema_info = parse_schema_file(content)
                relation_map["schema_tables"].update(schema_info["tables"])
                relation_map["relationships"].extend(schema_info["relationships"])

                # Collect tables from schema
                relation_map["tables_referenced"].update(schema_info["tables"].keys())
            except Exception as e:
                logfire.warning("Failed to parse schema file", file=str(sql_file), error=str(e))
                continue
        else:
            # Parse queries from query file
            # Split by semicolon or comment blocks
            query_blocks = re.split(r";\s*\n|--.*?\n", content, flags=re.MULTILINE)
            for block in query_blocks:
                block = block.strip()
                if block and _is_sql_query(block):
                    try:
                        parsed = parse_sql_query(block)
                        relation_map["queries_in_files"].append(
                            {
                                "file": str(sql_file),
                                "query": block[:200] + "..." if len(block) > 200 else block,
                                "tables": parsed["tables"],
                                "columns": parsed["columns"],
                                "used_in_code": False,
                                "used_in_methods": [],
                            }
                        )
                        if parsed.get("tables"):
                            relation_map["tables_referenced"].update(parsed["tables"])
                    except Exception as e:
                        logfire.debug(
                            "Failed to parse query block", file=str(sql_file), error=str(e)
                        )
                        continue

    # Match queries in files to queries in code
    for file_query in relation_map["queries_in_files"]:
        file_query_normalized = _normalize_query(file_query["query"])
        for code_query in code_queries:
            code_query_normalized = _normalize_query(code_query["query"])
            if _queries_similar(file_query_normalized, code_query_normalized):
                file_query["used_in_code"] = True
                method = code_query.get("method")
                if method and method not in file_query["used_in_methods"]:
                    file_query["used_in_methods"].append(method)

    # Convert sets to lists for JSON serialization
    relation_map["tables_referenced"] = sorted(relation_map["tables_referenced"])

    return relation_map


def _normalize_query(query: str) -> str:
    """Normalize a SQL query for comparison."""
    # Remove whitespace and convert to uppercase
    normalized = re.sub(r"\s+", " ", query.upper().strip())
    # Remove parameter placeholders
    normalized = re.sub(r"[%:]\w+", "?", normalized)
    return normalized


def _queries_similar(query1: str, query2: str) -> bool:
    """Check if two queries are similar."""
    if not query1 or not query2:
        return False

    # Normalize both queries for comparison
    norm1 = _normalize_query(query1)
    norm2 = _normalize_query(query2)

    # Extract table names and compare
    tables1 = set(re.findall(r"FROM\s+(\w+)|JOIN\s+(\w+)", norm1, re.IGNORECASE))
    tables2 = set(re.findall(r"FROM\s+(\w+)|JOIN\s+(\w+)", norm2, re.IGNORECASE))
    tables1_flat = {t[0] or t[1] for t in tables1 if t[0] or t[1]}
    tables2_flat = {t[0] or t[1] for t in tables2 if t[0] or t[1]}

    # If both queries reference tables, check for overlap
    if tables1_flat and tables2_flat:
        # Require at least 50% table overlap or exact match
        overlap = tables1_flat & tables2_flat
        if overlap:
            # Check if they have the same query type (SELECT, INSERT, etc.)
            q1_type = norm1.split()[0] if norm1 else ""
            q2_type = norm2.split()[0] if norm2 else ""
            if q1_type == q2_type:
                return True
            # Even if types differ, if tables overlap significantly, consider similar
            return len(overlap) >= min(len(tables1_flat), len(tables2_flat)) * 0.5

    # Fallback: check if normalized queries are similar (substring match)
    # Use longer prefix for better accuracy
    min_len = min(len(norm1), len(norm2))
    if min_len > 0:
        prefix_len = min(100, min_len // 2)
        return norm1[:prefix_len] in norm2 or norm2[:prefix_len] in norm1

    return False
