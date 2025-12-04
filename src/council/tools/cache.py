"""Caching layer for review results."""

import hashlib
import json
from pathlib import Path
from typing import Any

import logfire

from ..config import get_settings
from .path_utils import resolve_file_path

settings = get_settings()

# Cache directory name
CACHE_DIR_NAME = ".council"
CACHE_SUBDIR = "cache"

# Cache version (increment when cache format changes)
CACHE_VERSION = 1


def get_cache_dir() -> Path:
    """
    Get the cache directory path.

    Returns:
        Path to cache directory
    """
    cache_dir = settings.project_root / CACHE_DIR_NAME / CACHE_SUBDIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def calculate_file_hash(file_path: Path) -> str:
    """
    Calculate SHA256 hash of file contents.

    Args:
        file_path: Path to file

    Returns:
        Hexadecimal hash string
    """
    sha256 = hashlib.sha256()
    try:
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        logfire.warning("Failed to calculate file hash", file=str(file_path), error=str(e))
        # Fallback: use file path and modification time
        return hashlib.sha256(f"{file_path}{file_path.stat().st_mtime}".encode()).hexdigest()


def get_cache_key(file_path: str, model_name: str | None = None) -> str:
    """
    Generate cache key for a file review.

    Args:
        file_path: Path to file being reviewed
        model_name: Optional model name/version

    Returns:
        Cache key string
    """
    resolved_path = Path(file_path).resolve()
    file_hash = calculate_file_hash(resolved_path)
    key_parts = [str(resolved_path), file_hash]
    if model_name:
        key_parts.append(model_name)
    key_string = "|".join(key_parts)
    return hashlib.sha256(key_string.encode()).hexdigest()


def get_cache_path(cache_key: str) -> Path:
    """
    Get cache file path for a cache key.

    Args:
        cache_key: Cache key

    Returns:
        Path to cache file
    """
    cache_dir = get_cache_dir()
    # Use first 2 chars of hash for subdirectory to avoid too many files in one dir
    subdir = cache_dir / cache_key[:2]
    subdir.mkdir(parents=True, exist_ok=True)
    return subdir / f"{cache_key}.json"


async def get_cached_review(file_path: str, model_name: str | None = None) -> dict[str, Any] | None:
    """
    Get cached review result if available.

    Args:
        file_path: Path to file
        model_name: Optional model name/version

    Returns:
        Cached review result or None if not found/invalid

    Raises:
        ValueError: If file_path is invalid or outside allowed directories
    """
    try:
        # Validate file path to prevent path traversal attacks
        resolved_path = resolve_file_path(file_path)
        if not resolved_path.exists():
            return None

        cache_key = get_cache_key(file_path, model_name)
        cache_path = get_cache_path(cache_key)

        if not cache_path.exists():
            return None

        # Read cache file
        cache_data = json.loads(cache_path.read_text(encoding="utf-8"))

        # Validate cache version
        if cache_data.get("version") != CACHE_VERSION:
            logfire.debug("Cache version mismatch, invalidating", cache_key=cache_key)
            cache_path.unlink(missing_ok=True)
            return None

        # Verify file hash still matches
        resolved_path = Path(file_path).resolve()
        current_hash = calculate_file_hash(resolved_path)
        if cache_data.get("file_hash") != current_hash:
            logfire.debug("File hash mismatch, invalidating cache", cache_key=cache_key)
            cache_path.unlink(missing_ok=True)
            return None

        logfire.info("Cache hit", file_path=file_path, cache_key=cache_key)
        return cache_data.get("result")

    except Exception as e:
        logfire.warning("Cache read failed", file_path=file_path, error=str(e))
        return None


async def cache_review(
    file_path: str, result: dict[str, Any], model_name: str | None = None
) -> None:
    """
    Cache a review result.

    Args:
        file_path: Path to file
        result: Review result to cache
        model_name: Optional model name/version

    Raises:
        ValueError: If file_path is invalid or outside allowed directories
    """
    try:
        # Validate file path to prevent path traversal attacks
        resolved_path = resolve_file_path(file_path)
        if not resolved_path.exists():
            logfire.warning("Cannot cache review for non-existent file", file_path=file_path)
            return

        cache_key = get_cache_key(file_path, model_name)
        cache_path = get_cache_path(cache_key)

        file_hash = calculate_file_hash(resolved_path)

        cache_data = {
            "version": CACHE_VERSION,
            "file_path": str(resolved_path),
            "file_hash": file_hash,
            "model_name": model_name,
            "result": result,
        }

        # Write cache file atomically
        temp_path = cache_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
        temp_path.replace(cache_path)

        logfire.info("Cached review result", file_path=file_path, cache_key=cache_key)

    except Exception as e:
        logfire.warning("Cache write failed", file_path=file_path, error=str(e))


async def clear_cache(file_path: str | None = None) -> int:
    """
    Clear cache entries.

    Args:
        file_path: Optional specific file path to clear. If None, clears all cache.

    Returns:
        Number of cache entries cleared

    Raises:
        ValueError: If file_path is invalid or outside allowed directories
    """
    try:
        cache_dir = get_cache_dir()
        cleared = 0

        if file_path:
            # Validate file path to prevent path traversal attacks
            resolve_file_path(file_path)  # Validates path, raises if invalid

            # Clear specific file cache
            cache_key = get_cache_key(file_path)
            cache_path = get_cache_path(cache_key)
            if cache_path.exists():
                cache_path.unlink()
                cleared = 1
        else:
            # Clear all cache
            for cache_file in cache_dir.rglob("*.json"):
                cache_file.unlink()
                cleared += 1

        logfire.info("Cache cleared", file_path=file_path, entries=cleared)
        return cleared

    except Exception as e:
        logfire.warning("Cache clear failed", error=str(e))
        return 0
