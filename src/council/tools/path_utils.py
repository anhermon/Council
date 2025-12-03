"""Shared path resolution utilities for tools."""

import logging
import os
from pathlib import Path
from typing import Set

from ..config import settings

logger = logging.getLogger(__name__)

MAX_PATH_LENGTH = 4096
MAX_SEARCH_DEPTH = 10  # Limit recursive search depth


def _is_safe_path(path: Path, allowed_roots: Set[Path]) -> bool:
    """
    Safely check if a path is within allowed directories.

    This function validates paths without following symlinks initially,
    then checks resolved paths to prevent directory traversal attacks.

    Args:
        path: Path to validate
        allowed_roots: Set of allowed root directories

    Returns:
        True if path is safe, False otherwise
    """
    try:
        # First check: ensure the path doesn't contain obvious traversal attempts
        if ".." in path.parts:
            return False

        # Resolve the path to handle symlinks
        resolved_path = path.resolve()

        # Check against each allowed root
        for root in allowed_roots:
            try:
                # Use is_relative_to if available (Python 3.9+)
                if hasattr(resolved_path, "is_relative_to"):
                    if resolved_path.is_relative_to(root):
                        return True
                else:
                    # Safer fallback for Python < 3.9
                    try:
                        resolved_path.relative_to(root)
                        return True
                    except ValueError:
                        continue
            except (OSError, ValueError):
                continue

        return False
    except (OSError, ValueError) as e:
        logger.warning(f"Path validation failed for {path}: {e}")
        return False


def resolve_file_path(file_path: str, base_path: str | None = None) -> Path:
    """
    Resolve file path intelligently, handling relative paths and filenames.

    This function tries multiple strategies to resolve a file path:
    1. If absolute, validate and use as-is
    2. If base_path provided, resolve relative to it
    3. Try relative to project root
    4. Try relative to current working directory
    5. Search recursively in project root (for just filenames, with depth limit)

    Args:
        file_path: Path to resolve (can be absolute, relative, or just filename)
        base_path: Optional base path to resolve relative paths from

    Returns:
        Resolved Path object

    Raises:
        ValueError: If path is invalid or outside allowed directories
        TypeError: If file_path is not a string
    """
    if not isinstance(file_path, str):
        raise TypeError("file_path must be a string")

    if not file_path or not file_path.strip():
        raise ValueError("file_path cannot be empty")

    if len(file_path) > MAX_PATH_LENGTH:
        raise ValueError(f"Path exceeds maximum length of {MAX_PATH_LENGTH}")

    # Prepare allowed roots
    allowed_roots = {settings.project_root.resolve(), Path.cwd().resolve()}

    path_obj = Path(file_path)

    # If absolute path, validate and use as-is
    if path_obj.is_absolute():
        if not _is_safe_path(path_obj, allowed_roots):
            raise ValueError("Absolute path outside allowed directories")
        return path_obj.resolve()

    # Try multiple resolution strategies
    candidates = []

    # Strategy 1: If base_path provided, resolve relative to it
    if base_path:
        try:
            base = Path(base_path).resolve()
            if base.is_file():
                base = base.parent
            candidate = base / file_path
            if _is_safe_path(candidate, allowed_roots) and candidate.exists():
                candidates.append(candidate.resolve())
        except (OSError, ValueError) as e:
            logger.debug(f"Base path resolution failed: {e}")

    # Strategy 2: Try relative to project root
    try:
        candidate = settings.project_root / file_path
        if _is_safe_path(candidate, allowed_roots) and candidate.exists():
            candidates.append(candidate.resolve())
    except (OSError, ValueError) as e:
        logger.debug(f"Project root resolution failed: {e}")

    # Strategy 3: Try relative to current working directory
    try:
        candidate = Path.cwd() / file_path
        if _is_safe_path(candidate, allowed_roots) and candidate.exists():
            candidates.append(candidate.resolve())
    except (OSError, ValueError) as e:
        logger.debug(f"CWD resolution failed: {e}")

    # Strategy 4: Search in project root recursively (for just filename)
    if (
        not candidates
        and os.sep not in file_path
        and (os.altsep is None or os.altsep not in file_path)
    ):
        try:
            # Limit search to reasonable depth to prevent performance issues
            matches = []
            for depth in range(MAX_SEARCH_DEPTH):
                pattern = "/".join(["*"] * depth + [file_path])
                current_matches = list(settings.project_root.glob(pattern))
                if current_matches:
                    matches.extend(current_matches)
                    break

            # Filter safe matches and sort by proximity to root
            safe_matches = [
                match.resolve() for match in matches if _is_safe_path(match, allowed_roots)
            ]
            if safe_matches:
                safe_matches.sort(key=lambda p: len(p.parts))
                candidates.append(safe_matches[0])
        except (OSError, ValueError) as e:
            logger.debug(f"Recursive search failed: {e}")

    # Return the best candidate if found
    if candidates:
        # Prefer the first valid candidate (they're ordered by preference)
        return candidates[0]

    # If still not resolved, try to create a safe path (may not exist yet)
    if base_path:
        try:
            base = Path(base_path).resolve()
            if base.is_file():
                base = base.parent
            candidate = base / file_path
        except (OSError, ValueError):
            candidate = settings.project_root / file_path
    else:
        candidate = settings.project_root / file_path

    if not _is_safe_path(candidate, allowed_roots):
        raise ValueError("Resolved path would be outside allowed directories")

    return candidate.resolve()
