"""Tests for debug tools."""

import os
from unittest.mock import patch

from council.tools.debug import (
    DebugWriter,
    _escape_markdown,
    get_debug_dir,
    is_debug_enabled,
)


class TestEscapeMarkdown:
    """Test markdown escaping function."""

    def test_escape_code_blocks(self):
        """Test escaping code blocks."""
        text = "Here is some ```code```"
        result = _escape_markdown(text)
        assert "\\`\\`\\`" in result
        assert "```" not in result

    def test_escape_headers(self):
        """Test escaping headers."""
        text = "Here is a # header"
        result = _escape_markdown(text)
        assert "\\#" in result
        # The escaped version should be present
        assert result.count("#") == 1  # Only the escaped one

    def test_escape_multiple(self):
        """Test escaping multiple special characters."""
        text = "```code``` and # header"
        result = _escape_markdown(text)
        assert "\\`\\`\\`" in result
        assert "\\#" in result


class TestGetDebugDir:
    """Test get_debug_dir function."""

    def test_get_debug_dir_creates_directory(self):
        """Test that get_debug_dir creates the directory."""
        debug_dir = get_debug_dir()
        assert debug_dir.exists()
        assert debug_dir.is_dir()
        assert debug_dir.name == "debug"
        assert debug_dir.parent.name == ".council"


class TestIsDebugEnabled:
    """Test is_debug_enabled function."""

    def test_debug_disabled_by_default(self):
        """Test that debug is disabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            assert not is_debug_enabled()

    def test_debug_enabled_with_env_var(self):
        """Test that debug can be enabled via environment variable."""
        with patch.dict(os.environ, {"COUNCIL_DEBUG": "true"}):
            assert is_debug_enabled()

        with patch.dict(os.environ, {"COUNCIL_DEBUG": "1"}):
            assert is_debug_enabled()

        with patch.dict(os.environ, {"COUNCIL_DEBUG": "yes"}):
            assert is_debug_enabled()

        with patch.dict(os.environ, {"COUNCIL_DEBUG": "on"}):
            assert is_debug_enabled()

    def test_debug_disabled_with_false(self):
        """Test that debug is disabled with false values."""
        with patch.dict(os.environ, {"COUNCIL_DEBUG": "false"}):
            assert not is_debug_enabled()

        with patch.dict(os.environ, {"COUNCIL_DEBUG": "0"}):
            assert not is_debug_enabled()

        with patch.dict(os.environ, {"COUNCIL_DEBUG": "no"}):
            assert not is_debug_enabled()


class TestDebugWriter:
    """Test DebugWriter class."""

    def test_debug_writer_disabled(self):
        """Test DebugWriter when debug is disabled."""
        with patch("council.tools.debug.is_debug_enabled", return_value=False):
            writer = DebugWriter(review_id="test123", file_path="test.py")
            assert not writer.enabled
            assert writer.debug_file is None
            # Should not raise when writing
            writer.write_entry("test", {"data": "value"})

    def test_debug_writer_enabled(self):
        """Test DebugWriter when debug is enabled."""
        with patch("council.tools.debug.is_debug_enabled", return_value=True):
            writer = DebugWriter(review_id="test123", file_path="test.py")
            assert writer.enabled
            assert writer.debug_file is not None
            assert writer.debug_file.exists()

    def test_debug_writer_write_entry(self):
        """Test writing debug entries."""
        with patch("council.tools.debug.is_debug_enabled", return_value=True):
            writer = DebugWriter(review_id="test123", file_path="test.py")

            writer.write_entry("system_prompt", {"prompt": "test prompt"})
            writer.write_entry("tool_call", {"tool": "read_file", "args": {"path": "test.py"}})
            writer.write_entry("tool_output", {"result": "file content"})

            # Verify file was written
            assert writer.debug_file.exists()
            content = writer.debug_file.read_text()
            assert "test123" in content
            assert "test.py" in content
            assert "System Prompt" in content or "system_prompt" in content
            assert "Tool Call" in content or "tool_call" in content

    def test_debug_writer_large_entry_truncation(self):
        """Test that large entries are truncated."""
        with patch("council.tools.debug.is_debug_enabled", return_value=True):
            writer = DebugWriter(review_id="test123", file_path="test.py")

            # Create a very large entry
            large_data = {"content": "x" * (15 * 1024 * 1024)}  # 15MB
            writer.write_entry("large_entry", large_data)

            # File should exist but entry should be truncated
            assert writer.debug_file.exists()
            content = writer.debug_file.read_text()
            # Should contain truncation notice
            assert "truncated" in content.lower() or len(content) < len(large_data["content"])

    def test_debug_writer_defaults(self):
        """Test DebugWriter with default parameters."""
        with patch("council.tools.debug.is_debug_enabled", return_value=True):
            writer = DebugWriter()
            assert writer.review_id == "unknown"
            assert writer.file_path == "unknown"

    def test_debug_writer_sanitizes_file_path(self):
        """Test that file paths are sanitized in debug filenames."""
        with patch("council.tools.debug.is_debug_enabled", return_value=True):
            writer = DebugWriter(review_id="test123", file_path="src/council/test.py")
            assert writer.debug_file is not None
            # Filename should not contain slashes
            assert "/" not in writer.debug_file.name
            assert "\\" not in writer.debug_file.name
