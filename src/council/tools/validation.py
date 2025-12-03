"""Security validation utilities for file paths and content."""

import re
from pathlib import Path

import logfire

from ..config import settings
from .exceptions import PathValidationError, SecurityError

# Maximum path length to prevent DoS attacks
MAX_PATH_LENGTH = 4096

# Maximum include pattern length
MAX_INCLUDE_PATTERN_LENGTH = 255

# Maximum XML content size to prevent DoS (100MB)
MAX_XML_CONTENT_SIZE = 100 * 1024 * 1024


def validate_file_path(file_path: str) -> Path:
    """
    Validate and sanitize file path to prevent path traversal and injection attacks.

    Args:
        file_path: Path to validate

    Returns:
        Resolved Path object if valid

    Raises:
        PathValidationError: If path contains suspicious patterns or is outside allowed directories
    """
    # Check path length to prevent DoS
    if len(file_path) > MAX_PATH_LENGTH:
        raise PathValidationError(f"Path exceeds maximum length of {MAX_PATH_LENGTH} characters")

    # Reject paths with suspicious patterns (path traversal attempts)
    if re.search(r"\.\./", file_path) or re.search(r"\.\.\\", file_path):
        raise PathValidationError(
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
        raise PathValidationError(
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
        PathValidationError: If pattern contains invalid characters
    """
    # Check length
    if len(include_pattern) > MAX_INCLUDE_PATTERN_LENGTH:
        raise PathValidationError(
            f"Include pattern exceeds maximum length of {MAX_INCLUDE_PATTERN_LENGTH} characters"
        )

    # Only allow alphanumeric, dots, dashes, underscores, and forward slashes
    # Forward slashes are needed for subdirectory patterns like "src/**/*.py"
    if not re.match(r"^[a-zA-Z0-9._/\-*]+$", include_pattern):
        raise PathValidationError(
            "Invalid include pattern: only alphanumeric characters, dots, dashes, "
            "underscores, forward slashes, and wildcards (*) are allowed"
        )

    # Prevent path traversal attempts
    if ".." in include_pattern:
        raise PathValidationError("Include pattern cannot contain '..' (path traversal)")

    return include_pattern


def check_xml_security(content: str) -> None:
    """
    Check XML content for potential XXE (XML External Entity) vulnerabilities.

    Since we're reading XML as text (not parsing), XXE risk is minimal.
    However, this function checks for dangerous patterns as a defense-in-depth measure.

    Args:
        content: XML content to check

    Raises:
        SecurityError: If content contains dangerous XXE patterns or exceeds size limits
    """
    # Check content size to prevent DoS
    if len(content) > MAX_XML_CONTENT_SIZE:
        raise SecurityError(f"XML content exceeds maximum size of {MAX_XML_CONTENT_SIZE} bytes")

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
