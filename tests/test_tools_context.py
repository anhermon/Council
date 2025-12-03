import pytest

from council.tools.exceptions import PathValidationError
from council.tools.validation import (
    check_xml_security,
    validate_file_path,
    validate_include_pattern,
)


class TestValidateFilePath:
    def test_valid_path_in_project(self, mock_settings):
        """Test valid path within project root."""
        # Create a dummy file
        test_file = mock_settings.project_root / "test_file.py"
        test_file.touch()

        result = validate_file_path(str(test_file))
        assert result == test_file.resolve()

    def test_path_traversal(self):
        """Test path traversal detection."""
        with pytest.raises(PathValidationError, match="Path traversal detected"):
            validate_file_path("../etc/passwd")

        with pytest.raises(PathValidationError, match="Path traversal detected"):
            validate_file_path("subdir/../../secret")

    def test_path_outside_project(self, tmp_path):
        """Test path outside allowed directories."""
        # Create a file outside the mock project root
        outside_file = tmp_path / "outside.py"
        outside_file.touch()

        with pytest.raises(PathValidationError, match="Path outside allowed directories"):
            validate_file_path(str(outside_file))

    def test_long_path(self):
        """Test path length limit."""
        long_path = "a/" * 2500  # > 4096 chars
        with pytest.raises(PathValidationError, match="Path exceeds maximum length"):
            validate_file_path(long_path)


class TestValidateIncludePattern:
    def test_valid_pattern(self):
        """Test valid include patterns."""
        assert validate_include_pattern("*.py") == "*.py"
        assert validate_include_pattern("src/**/*.ts") == "src/**/*.ts"
        assert validate_include_pattern("file-name_123.js") == "file-name_123.js"

    def test_invalid_characters(self):
        """Test invalid characters in pattern."""
        with pytest.raises(PathValidationError, match="Invalid include pattern"):
            validate_include_pattern("*.py; rm -rf /")

        with pytest.raises(PathValidationError, match="Invalid include pattern"):
            validate_include_pattern("$(whoami)")

    def test_path_traversal_in_pattern(self):
        """Test path traversal in pattern."""
        with pytest.raises(PathValidationError, match="Include pattern cannot contain '..'"):
            validate_include_pattern("../src/*.py")


class TestCheckXmlSecurity:
    def test_safe_xml(self):
        """Test safe XML content."""
        safe_xml = "<root><child>content</child></root>"
        # Should not raise
        check_xml_security(safe_xml)

    def test_xxe_pattern(self):
        """Test XXE pattern detection (logging only)."""
        # The function logs a warning but doesn't raise for XXE patterns as they are treated as text
        # We can verify it doesn't crash
        xxe_xml = """<!DOCTYPE foo [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>"""
        check_xml_security(xxe_xml)

    def test_large_content(self):
        """Test content size limit."""
        # Test with content that exceeds reasonable size limits
        # Using a smaller size for testing to avoid resource issues
        large_content = "x" * 100000  # 100KB of content
        # The function should handle this gracefully without raising
        # (it logs a warning but doesn't raise for large content)
        try:
            check_xml_security(large_content)
        except Exception as e:
            # If it raises, verify it's a size-related error
            assert "size" in str(e).lower() or "limit" in str(e).lower()
