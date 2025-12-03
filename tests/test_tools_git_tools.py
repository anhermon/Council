"""Tests for git integration tools."""

from unittest.mock import patch

import pytest

from council.tools.git_tools import (
    get_file_history,
    get_git_diff,
    get_uncommitted_files,
)


class TestGetGitDiff:
    """Test get_git_diff function."""

    @pytest.mark.asyncio
    async def test_get_git_diff_success(self, mock_settings):
        """Test successful git diff retrieval."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test content")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.return_value = ("diff content", "")
            result = await get_git_diff(str(test_file), base_ref="HEAD")
            assert result == "diff content"
            assert mock_run.called

    @pytest.mark.asyncio
    async def test_get_git_diff_with_base_ref(self, mock_settings):
        """Test git diff with custom base reference."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.return_value = ("diff", "")
            result = await get_git_diff(str(test_file), base_ref="main")
            assert result == "diff"
            # Verify base_ref was used in command
            call_args = mock_run.call_args[0][0]
            assert "main" in call_args

    @pytest.mark.asyncio
    async def test_get_git_diff_nonexistent_file(self):
        """Test git diff with nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await get_git_diff("nonexistent.py")

    @pytest.mark.asyncio
    async def test_get_git_diff_timeout(self, mock_settings):
        """Test git diff timeout handling."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = TimeoutError("Command timed out")
            with pytest.raises(TimeoutError):
                await get_git_diff(str(test_file))

    @pytest.mark.asyncio
    async def test_get_git_diff_with_base_path(self, tmp_path):
        """Test git diff with base_path parameter."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.return_value = ("diff", "")
            result = await get_git_diff(str(test_file), base_path=str(tmp_path))
            assert result == "diff"


class TestGetUncommittedFiles:
    """Test get_uncommitted_files function."""

    @pytest.mark.asyncio
    async def test_get_uncommitted_files_success(self):
        """Test successful retrieval of uncommitted files."""
        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = [
                ("file1.py\nfile2.py\n", ""),  # unstaged
                ("", ""),  # staged
                ("", ""),  # untracked
            ]
            result = await get_uncommitted_files()
            assert len(result) == 2
            assert "file1.py" in result
            assert "file2.py" in result

    @pytest.mark.asyncio
    async def test_get_uncommitted_files_empty(self):
        """Test when no uncommitted files exist."""
        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = [("", ""), ("", ""), ("", "")]
            result = await get_uncommitted_files()
            assert result == []

    @pytest.mark.asyncio
    async def test_get_uncommitted_files_with_whitespace(self):
        """Test handling of files with whitespace."""
        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = [
                ("file1.py\n\nfile2.py\n  \n", ""),
                ("", ""),
                ("", ""),
            ]
            result = await get_uncommitted_files()
            assert len(result) == 2
            assert "file1.py" in result
            assert "file2.py" in result

    @pytest.mark.asyncio
    async def test_get_uncommitted_files_git_error(self):
        """Test handling of git errors."""
        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = RuntimeError("Git command failed")
            with pytest.raises(RuntimeError):
                await get_uncommitted_files()

    @pytest.mark.asyncio
    async def test_get_uncommitted_files_timeout(self):
        """Test timeout handling."""
        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = TimeoutError("Command timed out")
            with pytest.raises(TimeoutError):
                await get_uncommitted_files()


class TestGetFileHistory:
    """Test get_file_history function."""

    @pytest.mark.asyncio
    async def test_get_file_history_success(self, mock_settings):
        """Test successful file history retrieval."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        # Mock git log output
        git_log_output = """abc123|2024-01-01|Author Name|Fix bug
def456|2024-01-02|Author Name|Add feature"""

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = [
                (git_log_output, ""),  # git log
                ("", ""),  # git show (for changes)
                ("", ""),  # git show (for changes)
            ]
            result = await get_file_history(str(test_file), limit=10)
            assert len(result) == 2
            assert result[0]["hash"] == "abc123"[:8]
            assert result[0]["message"] == "Fix bug"
            assert result[1]["hash"] == "def456"[:8]

    @pytest.mark.asyncio
    async def test_get_file_history_with_limit(self, mock_settings):
        """Test file history with custom limit."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        git_log_output = "\n".join([f"commit{i}|2024-01-01|Author|Message {i}" for i in range(5)])

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = [
                (git_log_output, ""),  # git log
            ] + [("", "")] * 5  # git show for each commit
            result = await get_file_history(str(test_file), limit=3)
            assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_get_file_history_empty(self, mock_settings):
        """Test file history when no history exists."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools.run_command_safely") as mock_run:
            mock_run.return_value = ("", "", 0)
            result = await get_file_history(str(test_file))
            assert result == []

    @pytest.mark.asyncio
    async def test_get_file_history_max_limit(self, mock_settings):
        """Test file history respects MAX_HISTORY_LIMIT."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = [
                ("commit1|date|author|msg", ""),  # git log
                ("", ""),  # git show
            ]
            # Request more than max limit
            with pytest.raises(ValueError):
                await get_file_history(str(test_file), limit=200)

    @pytest.mark.asyncio
    async def test_get_file_history_with_base_path(self, tmp_path):
        """Test file history with base_path parameter."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = [
                ("commit1|date|author|msg", ""),  # git log
                ("", ""),  # git show
            ]
            result = await get_file_history(str(test_file), base_path=str(tmp_path))
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_file_history_git_error(self, mock_settings):
        """Test handling of git errors."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = RuntimeError("Git command failed")
            # Should return empty list on error
            result = await get_file_history(str(test_file))
            assert result == []

    @pytest.mark.asyncio
    async def test_get_file_history_timeout(self, mock_settings):
        """Test timeout handling."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = TimeoutError("Command timed out")
            with pytest.raises(TimeoutError):
                await get_file_history(str(test_file))

    @pytest.mark.asyncio
    async def test_get_file_history_malformed_output(self, mock_settings):
        """Test handling of malformed git log output."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        # Malformed output (missing fields)
        with patch("council.tools.git_tools.run_command_safely") as mock_run:
            mock_run.return_value = ("invalid|output", "", 0)
            result = await get_file_history(str(test_file))
            # Should handle gracefully, possibly returning empty or partial results
            assert isinstance(result, list)
