"""Tests for custom exception classes."""

from council.tools.exceptions import (
    PathValidationError,
    RepomixError,
    RepomixTimeoutError,
    SecurityError,
    SubprocessError,
    SubprocessTimeoutError,
    ToolError,
    ValidationError,
)


class TestToolError:
    """Test ToolError base class."""

    def test_tool_error_basic(self):
        """Test basic ToolError creation."""
        error = ToolError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.original_error is None

    def test_tool_error_with_original(self):
        """Test ToolError with original error."""
        original = ValueError("Original error")
        error = ToolError("Wrapper error", original_error=original)
        assert str(error) == "Wrapper error"
        assert error.original_error == original


class TestValidationError:
    """Test ValidationError class."""

    def test_validation_error(self):
        """Test ValidationError creation."""
        error = ValidationError("Validation failed")
        assert isinstance(error, ToolError)
        assert str(error) == "Validation failed"


class TestPathValidationError:
    """Test PathValidationError class."""

    def test_path_validation_error(self):
        """Test PathValidationError creation."""
        error = PathValidationError("Path validation failed")
        assert isinstance(error, ValidationError)
        assert isinstance(error, ToolError)
        assert str(error) == "Path validation failed"


class TestSecurityError:
    """Test SecurityError class."""

    def test_security_error(self):
        """Test SecurityError creation."""
        error = SecurityError("Security check failed")
        assert isinstance(error, ToolError)
        assert str(error) == "Security check failed"


class TestRepomixError:
    """Test RepomixError class."""

    def test_repomix_error(self):
        """Test RepomixError creation."""
        error = RepomixError("Repomix failed")
        assert isinstance(error, ToolError)
        assert str(error) == "Repomix failed"

    def test_repomix_error_with_original(self):
        """Test RepomixError with original error."""
        original = RuntimeError("Original")
        error = RepomixError("Repomix failed", original_error=original)
        assert error.original_error == original


class TestRepomixTimeoutError:
    """Test RepomixTimeoutError class."""

    def test_repomix_timeout_error(self):
        """Test RepomixTimeoutError creation."""
        error = RepomixTimeoutError("Repomix timed out")
        assert isinstance(error, RepomixError)
        assert isinstance(error, TimeoutError)
        assert isinstance(error, ToolError)
        assert str(error) == "Repomix timed out"


class TestSubprocessError:
    """Test SubprocessError class."""

    def test_subprocess_error_basic(self):
        """Test basic SubprocessError creation."""
        error = SubprocessError("Command failed")
        assert isinstance(error, ToolError)
        assert str(error) == "Command failed"
        assert error.command is None
        assert error.return_code is None
        assert error.stderr is None

    def test_subprocess_error_with_details(self):
        """Test SubprocessError with all details."""
        error = SubprocessError(
            "Command failed",
            command=["git", "status"],
            return_code=1,
            stderr="Error message",
        )
        assert error.command == ["git", "status"]
        assert error.return_code == 1
        assert error.stderr == "Error message"

    def test_subprocess_error_with_original(self):
        """Test SubprocessError with original error."""
        original = ValueError("Original")
        error = SubprocessError("Command failed", original_error=original)
        assert error.original_error == original


class TestSubprocessTimeoutError:
    """Test SubprocessTimeoutError class."""

    def test_subprocess_timeout_error(self):
        """Test SubprocessTimeoutError creation."""
        error = SubprocessTimeoutError("Command timed out")
        assert isinstance(error, SubprocessError)
        assert isinstance(error, TimeoutError)
        assert isinstance(error, ToolError)
        assert str(error) == "Command timed out"

    def test_subprocess_timeout_error_with_details(self):
        """Test SubprocessTimeoutError with details."""
        error = SubprocessTimeoutError(
            "Command timed out",
            command=["long", "running", "command"],
            return_code=None,
        )
        assert error.command == ["long", "running", "command"]
        assert isinstance(error, TimeoutError)
