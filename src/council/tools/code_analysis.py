"""Code analysis tools for cross-file dependency analysis."""

import ast
import re
from typing import Any

import logfire
from tree_sitter import Query, QueryCursor

from ..config import get_settings
from ..core.parser import LANGUAGE_MAP, get_code_parser
from .path_utils import resolve_file_path

settings = get_settings()

# Maximum number of files to search
MAX_SEARCH_RESULTS = 50


async def read_file(file_path: str, base_path: str | None = None) -> str:
    """
    Read a file to understand dependencies and imports.

    This tool allows the agent to read related files for cross-file analysis,
    understanding how code interacts with other modules.

    Args:
        file_path: Path to the file to read. Can be:
            - Full path: "src/council/config.py"
            - Relative path: "config.py" (will search from project root)
            - Just filename: "config.py" (will search recursively in project)
        base_path: Optional base path (usually not needed, tool resolves automatically)

    Returns:
        File contents as string or error message if file cannot be read

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist
        IOError: If file cannot be read
    """
    logfire.info("Reading file", file_path=file_path, base_path=base_path)

    try:
        try:
            resolved_path = resolve_file_path(file_path, base_path)
        except FileNotFoundError:
            # Try creating a path relative to src/council if it fails
            # This handles cases where agent uses short paths like "tools/foo.py"
            # instead of "src/council/tools/foo.py"
            project_root = settings.project_root.resolve()
            src_council_path = project_root / "src" / "council" / file_path
            if src_council_path.exists():
                resolved_path = src_council_path
            else:
                raise

        if not resolved_path.exists():
            return f"Error: File not found: {file_path}"

        if not resolved_path.is_file():
            return f"Error: Path is not a file: {file_path}"

        # Check file size
        file_size = resolved_path.stat().st_size
        if file_size > settings.max_file_size:
            return f"Error: File too large: {file_size} bytes (max: {settings.max_file_size})"

        # Read file content
        content = resolved_path.read_text(encoding="utf-8", errors="replace")

        logfire.info("File read successfully", file_path=file_path, size=len(content))
        return content

    except Exception as e:
        logfire.error("Failed to read file", file_path=file_path, error=str(e))
        return f"Error reading file {file_path}: {str(e)}"


async def search_codebase(query: str, file_pattern: str | None = None) -> list[str]:
    """
    Search codebase for patterns, functions, classes, etc.

    This tool helps find related code across the codebase by searching for
    specific patterns, function names, class names, or other code elements.

    Args:
        query: Search query (can be regex pattern or plain text)
        file_pattern: Optional file pattern to limit search (e.g., "*.py", "src/**/*.ts")

    Returns:
        List of file paths containing matches (limited to MAX_SEARCH_RESULTS)

    Raises:
        ValueError: If query is invalid
    """
    logfire.info("Searching codebase", query=query, file_pattern=file_pattern)

    if not query or not query.strip():
        raise ValueError("Search query cannot be empty")

    if len(query) > 1000:
        raise ValueError("Search query too long (max 1000 characters)")

    try:
        # Validate file pattern if provided
        if file_pattern:
            if len(file_pattern) > 255:
                raise ValueError("File pattern too long")
            if ".." in file_pattern:
                raise ValueError("File pattern cannot contain '..'")

        # Determine search root
        search_root = settings.project_root.resolve()

        # Collect matching files
        matches: list[str] = []
        query_lower = query.lower()

        # Compile regex if query looks like a pattern
        try:
            pattern = re.compile(query, re.IGNORECASE)
            use_regex = True
        except re.error:
            # Not a valid regex, use plain text search
            pattern = None
            use_regex = False

        # Search files
        if file_pattern:
            # Use glob pattern
            if "**" in file_pattern:
                # Recursive search
                for file_path in search_root.rglob(file_pattern.replace("**", "*")):
                    if file_path.is_file() and len(matches) < MAX_SEARCH_RESULTS:
                        try:
                            content = file_path.read_text(encoding="utf-8", errors="replace")
                            if use_regex:
                                if pattern.search(content):
                                    matches.append(str(file_path.relative_to(search_root)))
                            else:
                                if query_lower in content.lower():
                                    matches.append(str(file_path.relative_to(search_root)))
                        except Exception:
                            # Skip files that can't be read
                            continue
            else:
                # Non-recursive search
                for file_path in search_root.glob(file_pattern):
                    if file_path.is_file() and len(matches) < MAX_SEARCH_RESULTS:
                        try:
                            content = file_path.read_text(encoding="utf-8", errors="replace")
                            if use_regex:
                                if pattern.search(content):
                                    matches.append(str(file_path.relative_to(search_root)))
                            else:
                                if query_lower in content.lower():
                                    matches.append(str(file_path.relative_to(search_root)))
                        except Exception:
                            continue
        else:
            # Search all code files and template files
            code_extensions = {
                ".py",
                ".js",
                ".ts",
                ".tsx",
                ".jsx",
                ".java",
                ".go",
                ".rs",
                ".j2",
                ".jinja",
                ".jinja2",  # Template files
            }
            for file_path in search_root.rglob("*"):
                if (
                    file_path.is_file()
                    and file_path.suffix in code_extensions
                    and len(matches) < MAX_SEARCH_RESULTS
                ):
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                        if use_regex:
                            if pattern.search(content):
                                matches.append(str(file_path.relative_to(search_root)))
                        else:
                            if query_lower in content.lower():
                                matches.append(str(file_path.relative_to(search_root)))
                    except Exception:
                        continue

        logfire.info("Search completed", query=query, matches=len(matches))
        return matches[:MAX_SEARCH_RESULTS]

    except Exception as e:
        logfire.error("Codebase search failed", query=query, error=str(e))
        raise


def _analyze_imports_treesitter(
    content: str,
    extension: str,
    parser_instance: Any,
) -> dict[str, Any]:
    """
    Analyze imports using Tree Sitter for non-Python languages.

    Args:
        content: File content
        extension: File extension
        parser_instance: CodeParser instance

    Returns:
        Dictionary with import analysis
    """
    tree, language_name = parser_instance.parse(content, extension)
    if not tree:
        return {
            "imports": [],
            "from_imports": [],
            "local_imports": [],
            "external_imports": [],
            "note": f"Could not parse {extension} file (language: {language_name})",
        }

    language = parser_instance.get_language(language_name)
    if not language:
        return {
            "imports": [],
            "from_imports": [],
            "local_imports": [],
            "external_imports": [],
            "note": f"Language {language_name} not initialized",
        }

    imports = []
    local_imports = []
    external_imports = []

    # Define queries based on language
    query_scm = ""
    if language_name == "javascript":
        query_scm = """
        (import_statement source: (string) @source)
        (export_statement source: (string) @source)
        (call_expression
          function: (identifier) @func
          arguments: (arguments (string) @source)
          (#eq? @func "require"))
        """
    elif language_name in ["typescript", "tsx"]:
        # Removed import_require as it may not be present in all grammars
        query_scm = """
        (import_statement source: (string) @source)
        (export_statement source: (string) @source)
        """
    elif language_name == "java":
        query_scm = """
        (import_declaration (scoped_identifier) @import)
        """
    elif language_name == "go":
        query_scm = """
        (import_spec path: (interpreted_string_literal) @path)
        """

    if query_scm:
        try:
            # New 0.23+ API: Query(language, source) -> QueryCursor(query)
            query = Query(language, query_scm)
            cursor = QueryCursor(query)
            captures = cursor.captures(tree.root_node)

            # captures is a dict: {'capture_name': [Node, Node, ...]})
            # Only process source/path/import captures, not function identifiers
            source_captures = []
            for capture_name, nodes_list in captures.items():
                # Skip function identifier captures (like @func for require)
                if capture_name in ("source", "path", "import"):
                    source_captures.extend(nodes_list)

            for node in source_captures:
                text = content[node.start_byte : node.end_byte]
                # Clean up quotes
                clean_text = text.strip("'\"")
                imports.append(clean_text)

                # Simple heuristic for local vs external
                if language_name in ["javascript", "typescript", "tsx"]:
                    if clean_text.startswith((".", "/")):
                        local_imports.append(clean_text)
                    else:
                        external_imports.append(clean_text)
                else:
                    # For Java/Go, assume everything is external/package level for now
                    external_imports.append(clean_text)

        except Exception as e:
            logfire.warning(f"Tree Sitter query failed for {language_name}", error=str(e))

    return {
        "imports": imports,
        "from_imports": [],  # Simplified for non-Python
        "local_imports": list(set(local_imports)),
        "external_imports": list(set(external_imports)),
    }


async def analyze_imports(file_path: str, base_path: str | None = None) -> dict[str, Any]:
    """
    Analyze imports and dependencies of a file.

    Supports Python, JavaScript, TypeScript, Java, and Go.

    Args:
        file_path: Path to the file to analyze.
        base_path: Optional base path (usually not needed, tool resolves automatically)

    Returns:
        Dictionary with import analysis including:
        - imports: List of imported modules/functions
        - from_imports: List of from-import statements (Python only)
        - local_imports: List of local/relative imports
        - external_imports: List of external package imports
        - note: Warning message if file type not supported

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist
    """
    logfire.info("Analyzing imports", file_path=file_path, base_path=base_path)

    try:
        resolved_path = resolve_file_path(file_path, base_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not resolved_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # Read file content
        content = resolved_path.read_text(encoding="utf-8", errors="replace")
        extension = resolved_path.suffix.lower()

        # Use Python AST for Python files (legacy robust support)
        if extension == ".py":
            try:
                tree = ast.parse(content, filename=str(resolved_path))
            except SyntaxError:
                return {
                    "imports": [],
                    "from_imports": [],
                    "local_imports": [],
                    "external_imports": [],
                    "note": "File contains syntax errors, cannot parse imports",
                }

            imports: list[str] = []
            from_imports: list[dict[str, str]] = []
            local_imports: list[str] = []
            external_imports: list[str] = []

            # Determine if this is a local package (has __init__.py nearby)
            project_root = settings.project_root.resolve()
            is_local_package = False
            try:
                if resolved_path.is_relative_to(project_root):
                    is_local_package = True
            except AttributeError:
                is_local_package = str(resolved_path).startswith(str(project_root))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        import_name = alias.name
                        imports.append(import_name)
                        # Determine if local or external
                        if is_local_package and any(
                            (project_root / part).exists() for part in import_name.split(".")[:1]
                        ):
                            local_imports.append(import_name)
                        else:
                            external_imports.append(import_name)

                elif isinstance(node, ast.ImportFrom) and node.module:
                    module_name = node.module
                    imported_items = [alias.name for alias in node.names]
                    from_imports.append({"module": module_name, "items": imported_items})
                    # Determine if local or external
                    if is_local_package and any(
                        (project_root / part).exists() for part in module_name.split(".")[:1]
                    ):
                        local_imports.append(module_name)
                    else:
                        external_imports.append(module_name)

            result = {
                "imports": imports,
                "from_imports": from_imports,
                "local_imports": list(set(local_imports)),
                "external_imports": list(set(external_imports)),
            }

            logfire.info("Import analysis completed", file_path=file_path, imports=len(imports))
            return result

        # Use Tree Sitter for other supported languages
        elif extension in LANGUAGE_MAP:
            parser_instance = get_code_parser()
            result = _analyze_imports_treesitter(content, extension, parser_instance)
            logfire.info(
                "Import analysis completed (Tree Sitter)",
                file_path=file_path,
                imports=len(result["imports"]),
            )
            return result

        else:
            return {
                "imports": [],
                "from_imports": [],
                "local_imports": [],
                "external_imports": [],
                "note": f"Import analysis is only supported for Python files and other supported languages. {extension} files are not supported.",
            }

    except Exception as e:
        logfire.error("Import analysis failed", file_path=file_path, error=str(e))
        raise


async def write_file(file_path: str, content: str, base_path: str | None = None) -> str:
    """
    Write content to a file, creating it if it doesn't exist.

    This tool allows the agent to modify files, add docstrings, remove dead code,
    and make other intelligent edits during housekeeping operations.

    For large files (>100KB), consider using write_file_chunk instead to avoid
    tool call serialization issues.

    Args:
        file_path: Path to the file to write. Can be:
            - Full path: "src/council/config.py"
            - Relative path: "config.py" (will resolve from project root)
        content: Content to write to the file
        base_path: Optional base path (usually not needed, tool resolves automatically)

    Returns:
        Success message with file path

    Raises:
        ValueError: If path is invalid or outside project root
        PermissionError: If file cannot be written
    """
    logfire.info("Writing file", file_path=file_path, base_path=base_path)

    try:
        # resolve_file_path already validates the path is within allowed directories
        resolved_path = resolve_file_path(file_path, base_path)
        project_root = settings.project_root.resolve()

        # Check content size
        if len(content) > settings.max_file_size:
            raise ValueError(
                f"Content too large: {len(content)} bytes (max: {settings.max_file_size})"
            )

        # Create parent directories if needed
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        resolved_path.write_text(content, encoding="utf-8")

        logfire.info("File written successfully", file_path=file_path, size=len(content))
        # Try to get relative path, fallback to absolute if not within project_root
        try:
            rel_path = resolved_path.relative_to(project_root)
            return f"Successfully wrote {rel_path}"
        except ValueError:
            return f"Successfully wrote {resolved_path}"

    except Exception as e:
        logfire.error("Failed to write file", file_path=file_path, error=str(e))
        raise


async def write_file_chunk(
    file_path: str,
    content: str,
    chunk_index: int,
    total_chunks: int,
    base_path: str | None = None,
) -> str:
    """
    Write a chunk of content to a file, supporting chunked writes for large files.

    This tool allows writing large files in chunks to avoid tool call serialization
    issues with providers like Bedrock. Use this for files larger than ~100KB.

    The tool will:
    - Create the file if it doesn't exist (chunk_index 0)
    - Append chunks in order (chunk_index 1, 2, 3, ...)
    - Replace the entire file if chunk_index is 0 and total_chunks is 1

    Args:
        file_path: Path to the file to write. Can be:
            - Full path: "src/council/config.py"
            - Relative path: "config.py" (will resolve from project root)
        content: Content chunk to write
        chunk_index: Zero-based index of this chunk (0 = first chunk)
        total_chunks: Total number of chunks that will be written
        base_path: Optional base path (usually not needed, tool resolves automatically)

    Returns:
        Success message with file path and chunk info

    Raises:
        ValueError: If path is invalid, outside project root, or chunk_index is invalid
        PermissionError: If file cannot be written
    """
    logfire.info(
        "Writing file chunk",
        file_path=file_path,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        chunk_size=len(content),
        base_path=base_path,
    )

    try:
        # resolve_file_path already validates the path is within allowed directories
        resolved_path = resolve_file_path(file_path, base_path)
        project_root = settings.project_root.resolve()

        # Validate chunk parameters
        if chunk_index < 0:
            raise ValueError(f"chunk_index must be >= 0, got {chunk_index}")
        if total_chunks < 1:
            raise ValueError(f"total_chunks must be >= 1, got {total_chunks}")
        if chunk_index >= total_chunks:
            raise ValueError(f"chunk_index ({chunk_index}) must be < total_chunks ({total_chunks})")

        # Check chunk size
        if len(content) > settings.max_file_size:
            raise ValueError(
                f"Chunk too large: {len(content)} bytes (max: {settings.max_file_size})"
            )

        # Create parent directories if needed
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

        # Write chunk
        if chunk_index == 0:
            # First chunk: create/overwrite file
            resolved_path.write_text(content, encoding="utf-8")
        else:
            # Subsequent chunks: append to file
            with resolved_path.open("a", encoding="utf-8") as f:
                f.write(content)

        logfire.info(
            "File chunk written successfully",
            file_path=file_path,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
        )

        # Try to get relative path, fallback to absolute if not within project_root
        try:
            rel_path = resolved_path.relative_to(project_root)
            path_str = str(rel_path)
        except ValueError:
            path_str = str(resolved_path)

        if chunk_index == total_chunks - 1:
            # Last chunk
            return (
                f"Successfully wrote chunk {chunk_index + 1}/{total_chunks} (final) to {path_str}"
            )
        else:
            return f"Successfully wrote chunk {chunk_index + 1}/{total_chunks} to {path_str}"

    except Exception as e:
        logfire.error("Failed to write file chunk", file_path=file_path, error=str(e))
        raise
