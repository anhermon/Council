"""Path resolution and file collection utilities."""

from pathlib import Path

import click


def resolve_path(path: Path) -> Path:
    """
    Resolve a path, handling @ prefix as shorthand for src/council/.

    Args:
        path: Path that may start with @

    Returns:
        Resolved Path

    Raises:
        ValueError: If path contains traversal attempts or is invalid
    """
    path_str = str(path)

    # Validate path doesn't contain traversal attempts
    if ".." in Path(path_str).parts:
        raise ValueError("Path traversal detected: '..' not allowed in path")

    if path_str.startswith("@"):
        # Remove @ prefix and resolve relative to src/council/
        # e.g., @agents -> src/council/agents
        # e.g., @council or @ -> src/council
        folder_name = path_str[1:]

        # Validate folder_name doesn't contain path separators or traversal
        if "/" in folder_name or "\\" in folder_name or ".." in folder_name:
            raise ValueError("Invalid folder name in @ path")

        # Try to resolve relative to current directory first
        base_path = Path.cwd()
        # Check if src/council exists
        if (base_path / "src" / "council").exists():
            # If folder_name is empty or matches "council", resolve to src/council itself
            if not folder_name or folder_name == "council":
                resolved = base_path / "src" / "council"
            else:
                resolved = base_path / "src" / "council" / folder_name
        else:
            # Fall back to treating @folder as just folder
            resolved = base_path / folder_name if folder_name else base_path

        resolved_path = resolved.resolve() if resolved.exists() else path.resolve()

        # Ensure resolved path is within allowed directories
        allowed_roots = [base_path.resolve(), (base_path / "src").resolve()]
        for root in allowed_roots:
            try:
                if hasattr(resolved_path, "is_relative_to"):
                    if resolved_path.is_relative_to(root):
                        return resolved_path
                else:
                    # Python < 3.9 fallback
                    resolved_path.relative_to(root)
                    return resolved_path
            except (ValueError, AttributeError):
                continue

        # If path doesn't exist yet, still validate it would be safe
        for root in allowed_roots:
            try:
                if hasattr(resolved_path, "is_relative_to") and resolved_path.is_relative_to(root):
                    return resolved_path
            except (ValueError, AttributeError):
                continue

        raise ValueError("Resolved path would be outside allowed directories")

    resolved = path.resolve()

    # Validate non-@ paths are within current directory or project
    allowed_roots = [Path.cwd().resolve()]
    for root in allowed_roots:
        try:
            if hasattr(resolved, "is_relative_to"):
                if resolved.is_relative_to(root):
                    return resolved
            else:
                # Python < 3.9 fallback
                resolved.relative_to(root)
                return resolved
        except (ValueError, AttributeError):
            continue

    # If absolute path, allow it but log a warning
    if resolved.is_absolute():
        return resolved

    return resolved


def collect_files(paths: list[Path]) -> list[Path]:
    """
    Collect all files to review from given paths.

    For directories, finds all code files recursively.
    For files, includes them directly.

    Args:
        paths: List of file or directory paths

    Returns:
        List of file paths to review
    """
    # Common code file extensions
    CODE_EXTENSIONS = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".java",
        ".go",
        ".rs",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".cc",
        ".cxx",
        ".cs",
        ".php",
        ".rb",
        ".swift",
        ".kt",
        ".scala",
        ".r",
        ".m",
        ".mm",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".ps1",
        ".bat",
        ".cmd",
        ".sql",
        ".html",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".vue",
        ".svelte",
        ".elm",
        ".clj",
        ".cljs",
        ".edn",
        ".lua",
        ".pl",
        ".pm",
        ".rkt",
        ".dart",
        ".ex",
        ".exs",
        ".jl",
        ".nim",
        ".cr",
        ".d",
        ".pas",
        ".f",
        ".f90",
        ".f95",
        ".ml",
        ".mli",
        ".fs",
        ".fsi",
        ".fsx",
        ".vb",
        ".vbs",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".xml",
        ".xsd",
        ".xsl",
        ".xslt",
        ".makefile",
        ".mk",
        ".dockerfile",
        ".cmake",
        ".proto",
        ".thrift",
        ".graphql",
        ".gql",
        ".tf",
        ".tfvars",
        ".hcl",
        ".groovy",
        ".gradle",
        ".jinja",
        ".jinja2",
        ".j2",
        ".mustache",
        ".handlebars",
        ".hbs",
        ".ejs",
        ".pug",
        ".jade",
        ".njk",
    }

    # Common lock files to exclude
    LOCK_FILES = {
        "uv.lock",
        "package-lock.json",
        "poetry.lock",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Gemfile.lock",
        "composer.lock",
        "mix.lock",
        "go.sum",
        "Cargo.lock",
    }

    files_to_review: list[Path] = []

    for path in paths:
        resolved_path = resolve_path(path)

        if not resolved_path.exists():
            click.echo(f"⚠️  Path does not exist, skipping: {path}", err=True)
            continue

        if resolved_path.is_file():
            if resolved_path.name in LOCK_FILES:
                click.echo(f"⚠️  Skipping lock file: {resolved_path.name}", err=True)
                continue
            files_to_review.append(resolved_path)
        elif resolved_path.is_dir():
            # Find all code files in directory recursively
            dir_files = [
                file_path
                for file_path in resolved_path.rglob("*")
                if file_path.is_file()
                and file_path.suffix.lower() in CODE_EXTENSIONS
                and file_path.name not in LOCK_FILES
            ]

            if not dir_files:
                click.echo(f"⚠️  No code files found in directory: {path}", err=True)
            else:
                files_to_review.extend(dir_files)
        else:
            click.echo(f"⚠️  Path is neither file nor directory, skipping: {path}", err=True)

    return files_to_review
