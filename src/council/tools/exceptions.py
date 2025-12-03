"""Custom exceptions for tools module to preserve error context."""

from __future__ import annotations


class ToolError(Exception):
    """Base exception for tool-related errors."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        """Initialize tool error with optional original error context."""
        super().__init__(message)
        self.original_error = original_error
        self.message = message


class ValidationError(ToolError):
    """Raised when input validation fails."""

    pass


class PathValidationError(ValidationError):
    """Raised when file path validation fails."""

    pass


class SecurityError(ToolError):
    """Raised when security checks fail."""

    pass


class RepomixError(ToolError):
    """Raised when Repomix execution fails."""

    pass


class RepomixTimeoutError(RepomixError, TimeoutError):
    """Raised when Repomix execution times out."""

    pass


class SubprocessError(ToolError):
    """Raised when subprocess execution fails."""

    def __init__(
        self,
        message: str,
        command: list[str] | None = None,
        return_code: int | None = None,
        stderr: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """Initialize subprocess error with execution details."""
        super().__init__(message, original_error)
        self.command = command
        self.return_code = return_code
        self.stderr = stderr


class SubprocessTimeoutError(SubprocessError, TimeoutError):
    """Raised when subprocess execution times out."""

    pass
