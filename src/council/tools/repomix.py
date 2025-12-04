"""Repomix execution module for context extraction."""

import hashlib
import re
import tempfile
import threading
import time
from pathlib import Path

import logfire

from ..config import get_settings
from .exceptions import (
    PathValidationError,
    RepomixError,
    RepomixTimeoutError,
    SecurityError,
    SubprocessError,
)
from .utils import run_command_safely
from .validation import check_xml_security, validate_file_path, validate_include_pattern

settings = get_settings()

__all__ = ["get_packed_context", "get_packed_diff", "extract_code_from_xml"]

# Cache TTL for Repomix results (1 hour in seconds)
REPOMIX_CACHE_TTL = 3600.0

# In-memory cache for Repomix results: cache_key -> (content, timestamp)
_repomix_cache: dict[str, tuple[str, float]] = {}

# Lock for thread-safe cache operations
_cache_lock = threading.Lock()


def _get_file_hash(file_path: Path) -> str:
    """
    Generate a cache key hash for a file based on path, modification time, and size.

    Args:
        file_path: Path to the file

    Returns:
        Hexadecimal hash string
    """
    try:
        stat = file_path.stat()
        # Include path, modification time, and size in hash (use separator to prevent collisions)
        hash_input = f"{file_path}|{stat.st_mtime}|{stat.st_size}"
        return hashlib.sha256(hash_input.encode()).hexdigest()
    except (OSError, ValueError) as e:
        logfire.warning("Failed to generate file hash", file=str(file_path), error=str(e))
        # Fallback: use path only
        return hashlib.sha256(str(file_path).encode()).hexdigest()


async def _execute_repomix(
    target_dir: Path,
    output_path: Path,
    include_pattern: str | None = None,
    additional_patterns: list[str] | None = None,
) -> str:
    """
    Execute Repomix command and return XML content.

    Args:
        target_dir: Directory to analyze
        output_path: Path to output file
        include_pattern: Optional file pattern to include
        additional_patterns: Optional list of additional file patterns to include

    Returns:
        XML content from Repomix

    Raises:
        RepomixTimeoutError: If execution times out
        RepomixError: If execution fails
    """
    cmd = [
        "uvx",
        "repomix",
        str(target_dir),
        "--style",
        "xml",
        "--output",
        str(output_path),
        "--no-security-check",  # Disable security checks to avoid false positives
    ]

    # IMPORTANT: Repomix only uses the LAST --include pattern
    # So we must ensure the main file pattern comes LAST

    # Add SQL file patterns first (they'll be ignored, but we parse them separately)
    if additional_patterns:
        for pattern in additional_patterns:
            validated_pattern = validate_include_pattern(pattern)
            cmd.extend(["--include", validated_pattern])
        logfire.debug(
            "Added SQL file patterns (will be parsed separately)", count=len(additional_patterns)
        )

    # Add main file pattern LAST (this is what Repomix will actually use)
    if include_pattern:
        validated_pattern = validate_include_pattern(include_pattern)
        cmd.extend(["--include", validated_pattern])
        logfire.debug("Main file pattern (last, will be used by Repomix)", pattern=include_pattern)

    logfire.debug("Running repomix", command=" ".join(cmd))

    try:
        stdout, stderr, return_code = await run_command_safely(
            cmd,
            cwd=str(target_dir),
            timeout=settings.subprocess_timeout,
            check=False,  # We'll handle return code ourselves
        )

        if return_code != 0:
            error_msg = stderr or "Unknown error"
            logfire.error("Repomix execution failed", error=error_msg, return_code=return_code)
            raise RepomixError(
                f"Repomix failed with return code {return_code}: {error_msg}",
                original_error=SubprocessError(
                    "Repomix command failed",
                    command=cmd,
                    return_code=return_code,
                    stderr=stderr,
                ),
            )

        # Read the output file
        if output_path.exists():
            content = output_path.read_text(encoding="utf-8")
            # Check XML content for security issues (defense in depth)
            check_xml_security(content)
            return content
        else:
            # If output file doesn't exist, try reading from stdout
            if stdout:
                # Check XML content for security issues
                check_xml_security(stdout)
                logfire.warning("Output file not found, using stdout")
                return stdout
            raise RepomixError("Repomix did not generate output file and stdout is empty")

    except TimeoutError as e:
        raise RepomixTimeoutError(
            f"Repomix execution timed out after {settings.subprocess_timeout} seconds",
            original_error=e,
        ) from e
    except (RepomixError, SecurityError):
        # Re-raise Repomix and security errors as-is
        raise
    except Exception as e:
        # Wrap unexpected errors
        raise RepomixError(
            f"Unexpected error during Repomix execution: {str(e)}",
            original_error=e,
        ) from e


async def get_packed_context(file_path: str) -> str:
    """
    Extract packed context using Repomix.

    Args:
        file_path: Path to the file or directory to analyze

    Returns:
        XML content from Repomix output

    Raises:
        PathValidationError: If the file path is invalid or contains security issues
        FileNotFoundError: If the file path doesn't exist
        RepomixTimeoutError: If Repomix execution times out
        RepomixError: If Repomix execution fails
        SecurityError: If XML content contains security issues
    """
    logfire.info("Extracting context", file_path=file_path)

    # Validate and resolve the file path (prevents path traversal and injection)
    # Use resolve_file_path for more flexible path resolution (supports base_path)
    from .path_utils import resolve_file_path

    try:
        resolved_path = resolve_file_path(file_path)
    except (PathValidationError, ValueError) as e:
        # Re-raise validation errors as-is
        raise PathValidationError(str(e)) from e

    if not resolved_path.exists():
        raise FileNotFoundError(f"File or directory not found: {file_path}")

    # Check cache first
    cache_key = _get_file_hash(resolved_path)
    current_time = time.time()

    # Check if we have a valid cached result (thread-safe)
    # Optimize lock usage: read cache entry, release lock, then check TTL
    with _cache_lock:
        cached_result = _repomix_cache.get(cache_key)

    # Check TTL outside lock to minimize lock contention
    if cached_result:
        cached_content, cache_timestamp = cached_result
        # Verify cache is still valid (within TTL)
        if (current_time - cache_timestamp) < REPOMIX_CACHE_TTL:
            logfire.info("Using cached Repomix context", file_path=file_path)
            return cached_content

    # Repomix works with directories, so if a file is provided, use its parent
    # and include only that file
    if resolved_path.is_file():
        target_dir = resolved_path.parent
        include_pattern = resolved_path.name

        # Discover SQL files related to this code file
        from ..config import get_settings
        from .db_file_discovery import discover_sql_files

        settings_instance = get_settings()
        sql_files = discover_sql_files(resolved_path, settings_instance.project_root)

        # Convert SQL file paths to relative patterns for Repomix
        # Use project root as base for Repomix to ensure we can find files in sibling directories
        additional_patterns: list[str] = []
        for sql_file in sql_files:
            try:
                # Try relative to project root first (most reliable)
                rel_path = sql_file.relative_to(settings_instance.project_root)
                additional_patterns.append(str(rel_path))
            except ValueError:
                # If not relative to project root, try relative to target_dir
                try:
                    rel_path = sql_file.relative_to(target_dir)
                    additional_patterns.append(str(rel_path))
                except ValueError:
                    # Skip if we can't make it relative
                    logfire.warning(
                        "Could not make SQL file relative for Repomix",
                        sql_file=str(sql_file),
                        target_dir=str(target_dir),
                        project_root=str(settings_instance.project_root),
                    )

        # If we found SQL files, we need to run Repomix from project root
        # to be able to include files from different directories
        if additional_patterns:
            # Switch to project root and make include_pattern relative to it
            original_target_dir = target_dir
            target_dir = settings_instance.project_root
            try:
                include_pattern = str(resolved_path.relative_to(settings_instance.project_root))
            except ValueError:
                # If not relative, try to construct relative path
                # Fallback: use original pattern and hope it works
                logfire.warning(
                    "Could not make file path relative to project root",
                    file_path=str(resolved_path),
                    project_root=str(settings_instance.project_root),
                )
                # Keep original target_dir and pattern
                target_dir = original_target_dir
    else:
        target_dir = resolved_path
        include_pattern = None
        additional_patterns = None

    # Create a temporary file for output
    output_path = None
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".xml", delete=False) as tmp_file:
        output_path = Path(tmp_file.name)

    try:
        content = await _execute_repomix(
            target_dir, output_path, include_pattern, additional_patterns
        )

        # Cache the result (thread-safe)
        with _cache_lock:
            _repomix_cache[cache_key] = (content, current_time)

            # Clean up old cache entries (keep cache size reasonable)
            if len(_repomix_cache) > 100:
                # Remove entries older than TTL
                cutoff_time = current_time - REPOMIX_CACHE_TTL
                expired_keys = [k for k, v in _repomix_cache.items() if v[1] <= cutoff_time]
                for key in expired_keys:
                    del _repomix_cache[key]

        logfire.info("Context extracted successfully", size=len(content))
        return content

    finally:
        # Clean up temporary file with proper error handling
        if output_path:
            try:
                output_path.unlink(missing_ok=True)
            except OSError as e:
                # Log cleanup failures but don't fail the operation
                logfire.warning(
                    "Failed to clean up temporary file", file=str(output_path), error=str(e)
                )
            except PermissionError as e:
                logfire.warning(
                    "Permission denied cleaning up temporary file",
                    file=str(output_path),
                    error=str(e),
                )


def extract_code_from_xml(xml_content: str) -> str:
    """
    Extract code content from Repomix XML output.

    This function extracts the actual code from the XML structure, presenting
    it in a cleaner format for the agent to review. The XML structure is:
    <repository>
      <repository_files>
        <file>
          <path>...</path>
          <content>...</content>
        </file>
      </repository_files>
    </repository>

    Args:
        xml_content: The full XML content from Repomix

    Returns:
        Extracted code content with file paths as headers
    """
    if not xml_content or not xml_content.strip():
        return ""

    # Use regex to extract file content from XML
    # Pattern matches <content>...</content> tags and extracts the content
    # Also captures the file path for context
    code_sections = []

    # Pattern to match file blocks with path and content
    file_pattern = r"<file>.*?<path>(.*?)</path>.*?<content>(.*?)</content>.*?</file>"
    matches = re.findall(file_pattern, xml_content, re.DOTALL)

    for file_path, content in matches:
        # Decode XML entities in file path
        file_path = (
            file_path.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&apos;", "'")
        )

        # Decode XML entities in content
        content = (
            content.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&apos;", "'")
        )

        # Add file header and content
        code_sections.append(f"=== File: {file_path} ===\n{content}")

    if code_sections:
        return "\n\n".join(code_sections)

    # Fallback: if no matches found, try simpler pattern for just content
    content_pattern = r"<content>(.*?)</content>"
    content_matches = re.findall(content_pattern, xml_content, re.DOTALL)

    if content_matches:
        # Decode XML entities
        decoded_contents = [
            content.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&apos;", "'")
            for content in content_matches
        ]
        return "\n\n".join(decoded_contents)

    # If no content found, return original (might be malformed XML)
    logfire.warning("Could not extract code from XML, returning original content")
    return xml_content


async def get_packed_diff(file_path: str, base_ref: str = "HEAD") -> str:
    """
    Extract packed context for only changed code using git diff and Repomix.

    This function gets the git diff for changed files and uses Repomix to
    extract context only for the modified files, enabling incremental reviews.

    Args:
        file_path: Path to the file or directory to analyze
        base_ref: Git reference to compare against (default: "HEAD")

    Returns:
        XML content from Repomix output for changed files only

    Raises:
        PathValidationError: If the file path is invalid or contains security issues
        FileNotFoundError: If the file path doesn't exist
        RepomixTimeoutError: If Repomix execution times out
        RepomixError: If git or Repomix execution fails
    """
    logfire.info("Extracting diff context", file_path=file_path, base_ref=base_ref)

    # Validate and resolve the file path
    try:
        resolved_path = validate_file_path(file_path)
    except PathValidationError:
        # Re-raise validation errors as-is
        raise

    if not resolved_path.exists():
        raise FileNotFoundError(f"File or directory not found: {file_path}")

    project_root = settings.project_root.resolve()

    # Get list of changed files from git diff
    # If git diff fails or times out, fallback to full context extraction
    try:
        # Get relative path
        try:
            if resolved_path.is_relative_to(project_root):
                rel_path = str(resolved_path.relative_to(project_root))
            else:
                rel_path = str(resolved_path)
        except AttributeError:
            rel_path = str(resolved_path).replace(str(project_root) + "/", "")

        # Run git diff to get changed files
        try:
            stdout, stderr, return_code = await run_command_safely(
                [
                    "git",
                    "diff",
                    "--name-only",
                    base_ref,
                    "--",
                    rel_path,
                ],
                cwd=project_root,
                timeout=60.0,
                check=False,
            )

            if return_code != 0:
                error_msg = stderr or "Unknown error"
                logfire.warning(
                    "Git diff failed, falling back to full context extraction",
                    error=error_msg,
                    return_code=return_code,
                )
                # Fallback to full context extraction
                return await get_packed_context(file_path)

            changed_files = stdout.strip().split("\n")
        except TimeoutError:
            logfire.warning(
                "Git diff timed out, falling back to full context extraction", timeout=60.0
            )
            # Fallback to full context extraction
            return await get_packed_context(file_path)

        changed_files = [f for f in changed_files if f.strip()]

        if not changed_files:
            # No changes, return empty or indicate no changes
            logfire.info("No changes detected", file_path=file_path, base_ref=base_ref)
            return f"<!-- No changes in {rel_path} compared to {base_ref} -->"

        # Filter changed files to only include those that exist and are within allowed paths
        valid_changed_files: list[str] = []
        for changed_file in changed_files:
            if not changed_file.strip():
                continue
            try:
                changed_path = (project_root / changed_file).resolve()
                # Validate path is within project root
                try:
                    if changed_path.is_relative_to(project_root) and changed_path.exists():
                        valid_changed_files.append(changed_file)
                except AttributeError:
                    if str(changed_path).startswith(str(project_root)) and changed_path.exists():
                        valid_changed_files.append(changed_file)
            except (OSError, ValueError, AttributeError):
                # Skip invalid paths and continue processing
                continue

        if not valid_changed_files:
            logfire.warning("No valid changed files found after filtering", file_path=file_path)
            # Return empty result rather than falling back - user requested diff, got no changes
            return f"<!-- No valid changed files in {rel_path} compared to {base_ref} -->"

        # Use Repomix with include pattern for changed files only
        # If multiple files, we'll need to run repomix on the directory with includes
        target_dir = project_root
        include_patterns = valid_changed_files

        # Create a temporary file for output
        output_path = None
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".xml", delete=False) as tmp_file:
            output_path = Path(tmp_file.name)

        try:
            # Run repomix with include patterns for changed files
            # Note: Repomix may need multiple --include flags or a pattern
            # For now, we'll include all changed files
            cmd = [
                "uvx",
                "repomix",
                str(target_dir),
                "--style",
                "xml",
                "--output",
                str(output_path),
                "--no-security-check",
            ]

            # Add include patterns (repomix may support multiple --include flags)
            # If not, we might need to run repomix multiple times or use a different approach
            for pattern in include_patterns[:10]:  # Limit to 10 files to avoid command line issues
                # Validate each pattern
                try:
                    validated_pattern = validate_include_pattern(pattern)
                    cmd.extend(["--include", validated_pattern])
                except PathValidationError:
                    # Skip invalid patterns
                    logfire.warning("Skipping invalid include pattern", pattern=pattern)
                    continue

            logfire.debug("Running repomix with diff", command=" ".join(cmd))

            try:
                stdout, stderr, return_code = await run_command_safely(
                    cmd,
                    cwd=str(target_dir),
                    timeout=settings.subprocess_timeout,
                    check=False,
                )

                if return_code != 0:
                    error_msg = stderr or "Unknown error"
                    logfire.error(
                        "Repomix diff extraction failed",
                        error=error_msg,
                        return_code=return_code,
                    )
                    raise RepomixError(
                        f"Repomix diff extraction failed with return code {return_code}: {error_msg}",
                        original_error=SubprocessError(
                            "Repomix diff command failed",
                            command=cmd,
                            return_code=return_code,
                            stderr=stderr,
                        ),
                    )

                # Read the output file
                if output_path.exists():
                    content = output_path.read_text(encoding="utf-8")
                    # Check XML content for security issues
                    check_xml_security(content)
                    logfire.info(
                        "Diff context extracted successfully",
                        size=len(content),
                        files=len(valid_changed_files),
                    )
                    return content
                else:
                    # If output file doesn't exist, try reading from stdout
                    if stdout:
                        stdout_text = stdout
                        check_xml_security(stdout_text)
                        logfire.warning("Output file not found, using stdout")
                        return stdout_text
                    # No output available - raise error instead of silently falling back
                    raise RepomixError(
                        "Repomix diff extraction produced no output file and stdout is empty"
                    )

            except TimeoutError as e:
                logfire.error("Repomix diff timed out", timeout=settings.subprocess_timeout)
                raise RepomixTimeoutError(
                    f"Repomix diff extraction timed out after {settings.subprocess_timeout} seconds",
                    original_error=e,
                ) from e

        finally:
            # Clean up temporary file
            if output_path:
                import contextlib

                with contextlib.suppress(Exception):
                    output_path.unlink(missing_ok=True)

    except (PathValidationError, FileNotFoundError):
        # Re-raise validation and file not found errors
        raise
    except (RepomixError, RepomixTimeoutError) as e:
        # If Repomix itself fails, fallback to full context extraction
        logfire.warning(
            "Repomix diff extraction failed, falling back to full context", error=str(e)
        )
        return await get_packed_context(file_path)
    except Exception as e:
        # For other unexpected errors, try fallback before giving up
        logfire.warning("Unexpected error during diff extraction, falling back", error=str(e))
        try:
            return await get_packed_context(file_path)
        except Exception as fallback_error:
            # If fallback also fails, raise original error
            logfire.error("Fallback to full context also failed", error=str(fallback_error))
            raise RepomixError(
                f"Diff extraction failed and fallback failed: {str(e)}",
                original_error=e,
            ) from e
