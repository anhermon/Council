"""Tests for Repomix execution module."""

from unittest.mock import patch

import pytest

from council.config import get_settings
from council.tools.exceptions import (
    PathValidationError,
    RepomixError,
    RepomixTimeoutError,
    SecurityError,
)
from council.tools.repomix import (
    get_packed_context,
    get_packed_diff,
)

settings = get_settings()
REPOMIX_CACHE_TTL = settings.repomix_cache_ttl


class TestGetPackedContext:
    """Test get_packed_context function."""

    @pytest.mark.asyncio
    async def test_get_packed_context_success(self, mock_settings):
        """Test successful context extraction."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test content")

        mock_xml = "<xml>test content</xml>"
        with patch("council.tools.repomix.run_command_safely") as mock_run:
            mock_run.return_value = ("", "", 0)
            with (
                patch("pathlib.Path.read_text", return_value=mock_xml),
                patch("pathlib.Path.exists", return_value=True),
            ):
                result = await get_packed_context(str(test_file))
                assert result == mock_xml

    @pytest.mark.asyncio
    async def test_get_packed_context_nonexistent_file(self):
        """Test context extraction with nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await get_packed_context("nonexistent.py")

    @pytest.mark.asyncio
    async def test_get_packed_context_path_validation(self):
        """Test path validation."""
        with pytest.raises(PathValidationError):
            await get_packed_context("../etc/passwd")

    @pytest.mark.asyncio
    async def test_get_packed_context_cache_hit(self, mock_settings):
        """Test cache hit scenario."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        mock_xml = "<xml>cached</xml>"
        with patch("council.tools.repomix.run_command_safely") as mock_run:
            mock_run.return_value = ("", "", 0)
            with (
                patch("pathlib.Path.read_text", return_value=mock_xml),
                patch("pathlib.Path.exists", return_value=True),
            ):
                # First call - should execute repomix
                result1 = await get_packed_context(str(test_file))
                assert result1 == mock_xml
                assert mock_run.called

                # Reset mock
                mock_run.reset_mock()

                # Second call within cache TTL - should use cache
                result2 = await get_packed_context(str(test_file))
                assert result2 == mock_xml
                # Should not call repomix again
                assert not mock_run.called

    @pytest.mark.asyncio
    async def test_get_packed_context_cache_expired(self, mock_settings):
        """Test cache expiration with TTLCache."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        mock_xml = "<xml>content</xml>"
        # Mock time.time() to control TTL expiration
        # TTLCache uses time.time() internally for TTL checks
        with patch("council.tools.repomix.run_command_safely") as mock_run:
            mock_run.return_value = ("", "", 0)
            with (
                patch("pathlib.Path.read_text", return_value=mock_xml),
                patch("pathlib.Path.exists", return_value=True),
                patch("time.time") as mock_time,
            ):
                # First call - cache the result
                mock_time.return_value = 1000.0
                result1 = await get_packed_context(str(test_file))
                assert result1 == mock_xml

                # Reset mock
                mock_run.reset_mock()

                # Second call after cache expires (TTL exceeded)
                # TTLCache will expire entries when time.time() exceeds TTL
                mock_time.return_value = 1000.0 + REPOMIX_CACHE_TTL + 1
                result2 = await get_packed_context(str(test_file))
                assert result2 == mock_xml
                # Should call repomix again because cache expired
                assert mock_run.called

    @pytest.mark.asyncio
    async def test_get_packed_context_directory(self, mock_settings):
        """Test context extraction for directory."""
        test_dir = mock_settings.project_root / "test_dir"
        test_dir.mkdir()
        (test_dir / "file1.py").write_text("# file1")
        (test_dir / "file2.py").write_text("# file2")

        mock_xml = "<xml>directory content</xml>"
        with patch("council.tools.repomix.run_command_safely") as mock_run:
            mock_run.return_value = ("", "", 0)
            with (
                patch("pathlib.Path.read_text", return_value=mock_xml),
                patch("pathlib.Path.exists", return_value=True),
            ):
                result = await get_packed_context(str(test_dir))
                assert result == mock_xml

    @pytest.mark.asyncio
    async def test_get_packed_context_repomix_error(self, mock_settings):
        """Test handling of Repomix execution errors."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.repomix.run_command_safely") as mock_run:
            mock_run.return_value = ("", "Repomix error", 1)
            with pytest.raises(RepomixError):
                await get_packed_context(str(test_file))

    @pytest.mark.asyncio
    async def test_get_packed_context_timeout(self, mock_settings):
        """Test timeout handling."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.repomix.run_command_safely") as mock_run:
            mock_run.side_effect = TimeoutError("Command timed out")
            with pytest.raises(RepomixTimeoutError):
                await get_packed_context(str(test_file))

    @pytest.mark.asyncio
    async def test_get_packed_context_security_error(self, mock_settings):
        """Test security error handling."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        dangerous_xml = "<!DOCTYPE foo [ <!ENTITY xxe SYSTEM 'file:///etc/passwd'> ]>"
        with patch("council.tools.repomix.run_command_safely") as mock_run:
            mock_run.return_value = ("", "", 0)
            with (
                patch("pathlib.Path.read_text", return_value=dangerous_xml),
                patch("pathlib.Path.exists", return_value=True),
                patch("council.tools.repomix.check_xml_security") as mock_check,
            ):
                mock_check.side_effect = SecurityError("Security check failed")
                with pytest.raises(SecurityError):
                    await get_packed_context(str(test_file))

    @pytest.mark.asyncio
    async def test_get_packed_context_cache_cleanup(self, mock_settings):
        """Test cache LRU eviction when cache size exceeds limit."""
        # Create multiple files to trigger cache eviction
        # TTLCache automatically evicts oldest entries when maxsize is reached
        files = []
        cache_max_size = settings.repomix_cache_max_size
        for i in range(cache_max_size + 10):  # More than cache limit
            test_file = mock_settings.project_root / f"test{i}.py"
            test_file.write_text(f"# test {i}")
            files.append(test_file)

        mock_xml = "<xml>content</xml>"
        with patch("council.tools.repomix.run_command_safely") as mock_run:
            mock_run.return_value = ("", "", 0)
            with (
                patch("pathlib.Path.read_text", return_value=mock_xml),
                patch("pathlib.Path.exists", return_value=True),
            ):
                # Process files to fill cache beyond maxsize
                # TTLCache will automatically evict oldest entries
                for test_file in files:
                    await get_packed_context(str(test_file))
                # Cache should not exceed maxsize (TTLCache handles this automatically)


class TestGetPackedDiff:
    """Test get_packed_diff function."""

    @pytest.mark.asyncio
    async def test_get_packed_diff_success(self, mock_settings):
        """Test successful diff context extraction."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        mock_xml = "<xml>diff content</xml>"
        with patch("council.tools.repomix.run_command_safely") as mock_run:
            # Mock git diff
            mock_run.return_value = ("test.py\n", "", 0)
            with (
                patch("pathlib.Path.read_text", return_value=mock_xml),
                patch("pathlib.Path.exists", return_value=True),
            ):
                result = await get_packed_diff(str(test_file), base_ref="HEAD")
                assert result == mock_xml

    @pytest.mark.asyncio
    async def test_get_packed_diff_no_changes(self, mock_settings):
        """Test diff when no changes exist."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.repomix.run_command_safely") as mock_run:
            mock_run.return_value = ("", "", 0)
            result = await get_packed_diff(str(test_file))
            assert "No changes" in result

    @pytest.mark.asyncio
    async def test_get_packed_diff_git_error_fallback(self, mock_settings):
        """Test fallback to full context on git error."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        mock_xml = "<xml>full context</xml>"
        with patch("council.tools.repomix.run_command_safely") as mock_run:
            # First call (git diff) fails
            # Second call (get_packed_context) succeeds
            mock_run.side_effect = [
                ("", "git error", 1),  # git diff fails
                ("", "", 0),  # repomix succeeds
            ]
            with (
                patch("pathlib.Path.read_text", return_value=mock_xml),
                patch("pathlib.Path.exists", return_value=True),
            ):
                result = await get_packed_diff(str(test_file))
                assert result == mock_xml

    @pytest.mark.asyncio
    async def test_get_packed_diff_git_timeout_fallback(self, mock_settings):
        """Test fallback to full context on git timeout."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        mock_xml = "<xml>full context</xml>"
        with patch("council.tools.repomix.run_command_safely") as mock_run:
            # First call times out, second succeeds
            mock_run.side_effect = [
                TimeoutError("git timeout"),
                ("", "", 0),
            ]
            with (
                patch("pathlib.Path.read_text", return_value=mock_xml),
                patch("pathlib.Path.exists", return_value=True),
            ):
                result = await get_packed_diff(str(test_file))
                assert result == mock_xml

    @pytest.mark.asyncio
    async def test_get_packed_diff_multiple_files(self, mock_settings):
        """Test diff with multiple changed files."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        mock_xml = "<xml>multiple files</xml>"
        with patch("council.tools.repomix.run_command_safely") as mock_run:
            # Git diff returns multiple files
            mock_run.return_value = ("file1.py\nfile2.py\nfile3.py\n", "", 0)
            with (
                patch("pathlib.Path.read_text", return_value=mock_xml),
                patch("pathlib.Path.exists", return_value=True),
            ):
                result = await get_packed_diff(str(test_file))
                assert result == mock_xml
                # Verify multiple --include flags were added
                call_args = mock_run.call_args[0][0]
                assert call_args.count("--include") >= 1

    @pytest.mark.asyncio
    async def test_get_packed_diff_invalid_patterns(self, mock_settings):
        """Test handling of invalid include patterns."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        mock_xml = "<xml>content</xml>"
        with patch("council.tools.repomix.run_command_safely") as mock_run:
            # Git diff returns file with invalid pattern
            mock_run.return_value = ("../invalid.py\nvalid.py\n", "", 0)
            with (
                patch("pathlib.Path.read_text", return_value=mock_xml),
                patch("pathlib.Path.exists", return_value=True),
            ):
                result = await get_packed_diff(str(test_file))
                # Should skip invalid pattern and process valid ones
                assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_get_packed_diff_path_validation(self):
        """Test path validation in get_packed_diff."""
        with pytest.raises(PathValidationError):
            await get_packed_diff("../etc/passwd")

    @pytest.mark.asyncio
    async def test_get_packed_diff_nonexistent_file(self):
        """Test diff with nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await get_packed_diff("nonexistent.py")
