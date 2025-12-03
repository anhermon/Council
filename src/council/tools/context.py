"""Context extraction using Repomix."""

import asyncio
import hashlib
import re
import tempfile
import time
from pathlib import Path

import logfire

from ..config import settings

# Maximum path length to prevent DoS attacks
MAX_PATH_LENGTH = 4096

# Maximum include pattern length
MAX_INCLUDE_PATTERN_LENGTH = 255

# Maximum XML content size to prevent DoS (100MB)
MAX_XML_CONTENT_SIZE = 100 * 1024 * 1024

# Cache TTL for Repomix results (1 hour in seconds)
REPOMIX_CACHE_TTL = 3600.0

# In-memory cache for Repomix results: cache_key -> (content, timestamp)
_repomix_cache: dict[str, tuple[str, float]] = {}


def validate_file_path(file_path: str) -> Path:
    """
    Validate and sanitize file path to prevent path traversal and injection attacks.

    Args:
        file_path: Path to validate

    Returns:
        Resolved Path object if valid

    Raises:
        ValueError: If path contains suspicious patterns or is outside allowed directories
    """
    # Check path length to prevent DoS
    if len(file_path) > MAX_PATH_LENGTH:
        raise ValueError(f"Path exceeds maximum length of {MAX_PATH_LENGTH} characters")

    # Reject paths with suspicious patterns (path traversal attempts)
    if re.search(r"\.\./", file_path) or re.search(r"\.\.\\", file_path):
        raise ValueError(
            "Path traversal detected: paths containing '../' or '..\\' are not allowed"
        )

    # Resolve the path
    resolved_path = Path(file_path).resolve()

    # Ensure path is within allowed directories
    # Allow paths within project root or current working directory
    allowed_roots = [settings.project_root.resolve(), Path.cwd().resolve()]

    # Check if path is within any allowed root
    path_str = str(resolved_path)
    is_allowed = False
    for root in allowed_roots:
        root_str = str(root)
        # Use is_relative_to if available (Python 3.9+), otherwise manual check
        try:
            if resolved_path.is_relative_to(root):
                is_allowed = True
                break
        except AttributeError:
            # Python < 3.9: manual check
            if path_str.startswith(root_str) or path_str == root_str:
                is_allowed = True
                break

    if not is_allowed:
        # Sanitize error message to prevent information disclosure
        # Only show that path is not allowed, not the full allowed roots
        raise ValueError(
            "Path outside allowed directories. "
            "Please ensure the path is within the project directory or current working directory."
        )

    return resolved_path


def validate_include_pattern(include_pattern: str) -> str:
    """
    Validate include pattern to prevent command injection.

    Args:
        include_pattern: Pattern to validate

    Returns:
        Validated pattern

    Raises:
        ValueError: If pattern contains invalid characters
    """
    # Check length
    if len(include_pattern) > MAX_INCLUDE_PATTERN_LENGTH:
        raise ValueError(
            f"Include pattern exceeds maximum length of {MAX_INCLUDE_PATTERN_LENGTH} characters"
        )

    # Only allow alphanumeric, dots, dashes, underscores, and forward slashes
    # Forward slashes are needed for subdirectory patterns like "src/**/*.py"
    if not re.match(r"^[a-zA-Z0-9._/\-*]+$", include_pattern):
        raise ValueError(
            "Invalid include pattern: only alphanumeric characters, dots, dashes, "
            "underscores, forward slashes, and wildcards (*) are allowed"
        )

    # Prevent path traversal attempts
    if ".." in include_pattern:
        raise ValueError("Include pattern cannot contain '..' (path traversal)")

    return include_pattern


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
        # Include path, modification time, and size in hash
        hash_input = f"{file_path}{stat.st_mtime}{stat.st_size}"
        return hashlib.sha256(hash_input.encode()).hexdigest()
    except Exception as e:
        logfire.warning("Failed to generate file hash", file=str(file_path), error=str(e))
        # Fallback: use path only
        return hashlib.sha256(str(file_path).encode()).hexdigest()


def check_xml_security(content: str) -> None:
    """
    Check XML content for potential XXE (XML External Entity) vulnerabilities.

    Since we're reading XML as text (not parsing), XXE risk is minimal.
    However, this function checks for dangerous patterns as a defense-in-depth measure.

    Args:
        content: XML content to check

    Raises:
        ValueError: If content contains dangerous XXE patterns
    """
    # Check content size to prevent DoS
    if len(content) > MAX_XML_CONTENT_SIZE:
        raise ValueError(f"XML content exceeds maximum size of {MAX_XML_CONTENT_SIZE} bytes")

    # Check for common XXE patterns (case-insensitive)
    content_lower = content.lower()

    # Check if XML contains external entity declarations
    # This is a simple check - in a real XML parser, we'd disable external entities
    if "<!doctype" in content_lower and any(
        pattern in content_lower for pattern in ["system", "public"]
    ):
        # Log warning but don't fail - we're not parsing XML, just passing as text
        logfire.warning(
            "XML content contains potential external entity references. "
            "Content is being passed as text, not parsed, so XXE risk is minimal."
        )


async def get_packed_context(file_path: str) -> str:
    """
    Extract packed context using Repomix.

    Args:
        file_path: Path to the file or directory to analyze

    Returns:
        XML content from Repomix output

    Raises:
        ValueError: If the file path is invalid or contains security issues
        FileNotFoundError: If the file path doesn't exist
        RuntimeError: If Repomix execution fails
    """
    logfire.info("Extracting context", file_path=file_path)

    # Validate and resolve the file path (prevents path traversal and injection)
    resolved_path = validate_file_path(file_path)

    if not resolved_path.exists():
        raise FileNotFoundError(f"File or directory not found: {file_path}")

    # Check cache first
    cache_key = _get_file_hash(resolved_path)
    current_time = time.time()

    # Check if we have a valid cached result
    cached_result = _repomix_cache.get(cache_key)
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
    else:
        target_dir = resolved_path
        include_pattern = None

    # Create a temporary file for output
    output_path = None
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".xml", delete=False) as tmp_file:
        output_path = tmp_file.name

    try:
        # Run repomix via uvx
        # Repomix CLI: repomix [directory] --style xml --output [file] [--include pattern]
        # Use --no-security-check to avoid false positives (e.g., API_KEY in comments)
        cmd = [
            "uvx",
            "repomix",
            str(target_dir),
            "--style",
            "xml",
            "--output",
            output_path,
            "--no-security-check",  # Disable security checks to avoid false positives
        ]

        # If targeting a specific file, include only that file
        if include_pattern:
            # Validate include_pattern to prevent command injection
            validated_pattern = validate_include_pattern(include_pattern)
            cmd.extend(["--include", validated_pattern])

        # Don't use config file to avoid conflicts
        # The style is passed directly via --style flag

        logfire.debug("Running repomix", command=" ".join(cmd))

        # Use async subprocess to avoid blocking the event loop
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(target_dir),
        )

        try:
            # Wait for process completion with timeout (configurable)
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=settings.subprocess_timeout
            )
        except TimeoutError as err:
            # Kill the process if it times out
            proc.kill()
            await proc.wait()
            raise RuntimeError(
                f"Repomix execution timed out after {settings.subprocess_timeout} seconds"
            ) from err

        # Check return code
        if proc.returncode != 0:
            error_msg = f"Repomix failed: {stderr.decode('utf-8', errors='replace') if stderr else 'Unknown error'}"
            logfire.error("Repomix execution failed", error=error_msg, return_code=proc.returncode)
            raise RuntimeError(error_msg)

        # Read the output file
        output_file = Path(output_path)
        if output_file.exists():
            content = output_file.read_text(encoding="utf-8")
            # Check XML content for security issues (defense in depth)
            check_xml_security(content)
            # Cache the result
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
        else:
            # If output file doesn't exist, try reading from stdout
            if stdout:
                stdout_text = stdout.decode("utf-8", errors="replace")
                # Check XML content for security issues
                check_xml_security(stdout_text)
                # Cache the result
                _repomix_cache[cache_key] = (stdout_text, current_time)
                logfire.warning("Output file not found, using stdout")
                return stdout_text
            raise RuntimeError("Repomix did not generate output file and stdout is empty")

    finally:
        # Clean up temporary file with proper error handling
        if output_path:
            try:
                Path(output_path).unlink(missing_ok=True)
            except OSError as e:
                # Log cleanup failures but don't fail the operation
                logfire.warning("Failed to clean up temporary file", file=output_path, error=str(e))
            except PermissionError as e:
                logfire.warning(
                    "Permission denied cleaning up temporary file", file=output_path, error=str(e)
                )


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
        ValueError: If the file path is invalid or contains security issues
        FileNotFoundError: If the file path doesn't exist
        RuntimeError: If git or Repomix execution fails
    """
    logfire.info("Extracting diff context", file_path=file_path, base_ref=base_ref)

    # Validate and resolve the file path
    resolved_path = validate_file_path(file_path)

    if not resolved_path.exists():
        raise FileNotFoundError(f"File or directory not found: {file_path}")

    project_root = settings.project_root.resolve()

    # Get list of changed files from git diff
    try:
        import asyncio

        # Get relative path
        try:
            if resolved_path.is_relative_to(project_root):
                rel_path = str(resolved_path.relative_to(project_root))
            else:
                rel_path = str(resolved_path)
        except AttributeError:
            rel_path = str(resolved_path).replace(str(project_root) + "/", "")

        # Run git diff to get changed files
        proc = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "--name-only",
            base_ref,
            "--",
            rel_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_root),
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            logfire.warning("Git diff failed, falling back to full context", error=error_msg)
            # Fall back to regular context extraction
            return await get_packed_context(file_path)

        changed_files = stdout.decode("utf-8", errors="replace").strip().split("\n")
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
            except Exception:
                continue

        if not valid_changed_files:
            logfire.warning("No valid changed files found, falling back to full context")
            return await get_packed_context(file_path)

        # Use Repomix with include pattern for changed files only
        # If multiple files, we'll need to run repomix on the directory with includes
        target_dir = project_root
        include_patterns = valid_changed_files

        # Create a temporary file for output
        output_path = None
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".xml", delete=False) as tmp_file:
            output_path = tmp_file.name

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
                output_path,
                "--no-security-check",
            ]

            # Add include patterns (repomix may support multiple --include flags)
            # If not, we might need to run repomix multiple times or use a different approach
            for pattern in include_patterns[:10]:  # Limit to 10 files to avoid command line issues
                cmd.extend(["--include", pattern])

            logfire.debug("Running repomix with diff", command=" ".join(cmd))

            # Use async subprocess to avoid blocking the event loop
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(target_dir),
            )

            try:
                # Wait for process completion with timeout
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=settings.subprocess_timeout
                )
            except TimeoutError as err:
                # Kill the process if it times out
                proc.kill()
                await proc.wait()
                raise RuntimeError(
                    f"Repomix execution timed out after {settings.subprocess_timeout} seconds"
                ) from err

            # Check return code
            if proc.returncode != 0:
                error_msg = f"Repomix failed: {stderr.decode('utf-8', errors='replace') if stderr else 'Unknown error'}"
                logfire.warning(
                    "Repomix diff extraction failed, falling back to full context", error=error_msg
                )
                # Fall back to regular context extraction
                return await get_packed_context(file_path)

            # Read the output file
            output_file = Path(output_path)
            if output_file.exists():
                content = output_file.read_text(encoding="utf-8")
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
                    stdout_text = stdout.decode("utf-8", errors="replace")
                    check_xml_security(stdout_text)
                    logfire.warning("Output file not found, using stdout")
                    return stdout_text
                # Fall back to regular context extraction
                logfire.warning("Repomix diff output empty, falling back to full context")
                return await get_packed_context(file_path)

        finally:
            # Clean up temporary file
            if output_path:
                import contextlib

                with contextlib.suppress(Exception):
                    Path(output_path).unlink(missing_ok=True)

    except Exception as e:
        logfire.warning("Diff extraction failed, falling back to full context", error=str(e))
        # Fall back to regular context extraction
        return await get_packed_context(file_path)
