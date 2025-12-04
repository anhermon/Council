"""Database file discovery utilities for finding SQL files related to code."""

import re
from pathlib import Path

import logfire

# Common database-related imports/patterns
DB_IMPORT_PATTERNS = [
    r"import\s+(psycopg2|sqlalchemy|asyncpg|aiosqlite|sqlite3|mysql|pymongo)",
    r"from\s+(psycopg2|sqlalchemy|asyncpg|aiosqlite|sqlite3|mysql|pymongo)",
    r"from\s+django\.db",
    r"from\s+sqlalchemy",
]

# SQL query patterns
SQL_QUERY_PATTERNS = [
    r"SELECT\s+.*?\s+FROM",
    r"INSERT\s+INTO",
    r"UPDATE\s+\w+\s+SET",
    r"DELETE\s+FROM",
    r"CREATE\s+TABLE",
    r"ALTER\s+TABLE",
]

# Common SQL file locations and patterns
SQL_DIR_PATTERNS = ["db", "database", "sql", "migrations", "schema"]
SQL_FILE_PATTERNS = [
    "schema.sql",
    "queries.sql",
    "*.schema.sql",
    "*.queries.sql",
    "*.sql",
]


def has_database_code(file_path: Path) -> bool:
    """
    Check if a file contains database-related code.

    Args:
        file_path: Path to the file to check

    Returns:
        True if file contains database code patterns, False otherwise
    """
    if not file_path.exists() or not file_path.is_file():
        return False

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logfire.warning(
            "Failed to read file for database detection", file=str(file_path), error=str(e)
        )
        return False

    # Check for database imports
    for pattern in DB_IMPORT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
            return True

    # Check for SQL query strings
    for pattern in SQL_QUERY_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
            return True

    return False


def discover_sql_files(file_path: Path, project_root: Path) -> list[Path]:
    """
    Discover SQL files related to a code file.

    Searches for SQL files in common database directories and patterns.
    Only searches if the file contains database-related code.

    Args:
        file_path: Path to the code file being analyzed
        project_root: Root directory of the project

    Returns:
        List of discovered SQL file paths
    """
    discovered_files: list[Path] = []

    # First check if the file has database code
    if not has_database_code(file_path):
        logfire.debug("No database code detected, skipping SQL file discovery", file=str(file_path))
        return discovered_files

    logfire.debug("Database code detected, discovering SQL files", file=str(file_path))

    # Determine search root (use file's directory or project root)
    search_root = file_path.parent if file_path.is_file() else file_path

    # Ensure we don't go outside project root
    try:
        if not search_root.is_relative_to(project_root):
            search_root = project_root
    except AttributeError:
        # Python < 3.9 compatibility
        if not str(search_root).startswith(str(project_root)):
            search_root = project_root

    # Search in common database directories
    for dir_pattern in SQL_DIR_PATTERNS:
        db_dir = search_root / dir_pattern
        if db_dir.exists() and db_dir.is_dir():
            # Look for SQL files in this directory
            for sql_file in db_dir.glob("*.sql"):
                if sql_file.is_file():
                    discovered_files.append(sql_file)

        # Also check parent directories (up to project root)
        current = search_root
        while current != project_root and current != current.parent:
            db_dir = current / dir_pattern
            if db_dir.exists() and db_dir.is_dir():
                for sql_file in db_dir.glob("*.sql"):
                    if sql_file.is_file():
                        discovered_files.append(sql_file)
            current = current.parent

    # Search for specific SQL file patterns in the same directory and parent directories
    for pattern in SQL_FILE_PATTERNS:
        # Search in file's directory
        for sql_file in search_root.glob(pattern):
            if sql_file.is_file() and sql_file.suffix == ".sql":
                discovered_files.append(sql_file)

        # Search in parent directories up to project root
        current = search_root
        while current != project_root and current != current.parent:
            for sql_file in current.glob(pattern):
                if sql_file.is_file() and sql_file.suffix == ".sql":
                    discovered_files.append(sql_file)
            current = current.parent

    # Remove duplicates and sort
    discovered_files = sorted(set(discovered_files), key=lambda p: str(p))

    logfire.info(
        "Discovered SQL files",
        file=str(file_path),
        sql_files=[str(f) for f in discovered_files],
        count=len(discovered_files),
    )

    return discovered_files
