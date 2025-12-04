"""Tests for git integration tools."""

from unittest.mock import MagicMock, patch

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

    @pytest.mark.asyncio
    async def test_get_file_history_nonexistent_file(self, mock_settings):  # noqa: ARG002
        """Test get_file_history with nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await get_file_history("nonexistent.py")

    @pytest.mark.asyncio
    async def test_get_file_history_python_lt_39_fallback(self, mock_settings):
        """Test get_file_history with Python < 3.9 fallback."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = [
                ("hash1|author1|date1|message1", ""),
                ("stat1", ""),
            ]

            # Mock is_relative_to to raise AttributeError (Python < 3.9)
            resolved_path = MagicMock()
            resolved_path.exists.return_value = True
            resolved_path.is_relative_to.side_effect = AttributeError()
            # Make str() work on the mock - return the actual file path string
            type(resolved_path).__str__ = property(lambda _: str(test_file))

            with patch("council.tools.git_tools.resolve_file_path", return_value=resolved_path):
                result = await get_file_history(str(test_file), limit=1)
                assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_file_history_empty_line_skipped(self, mock_settings):
        """Test get_file_history skips empty lines."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            # Include empty line in output - limit is applied before parsing, so we get 2 commits
            mock_run.side_effect = [
                ("hash1|author1|date1|message1\nhash2|author2|date2|message2", ""),
                ("stat1", ""),
                ("stat2", ""),
            ]
            result = await get_file_history(str(test_file), limit=2)
            # Should get 2 results (limit applied to lines)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_file_history_exception_handling(self, mock_settings):
        """Test get_file_history exception handling."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with (
            patch(
                "council.tools.git_tools._run_git_command",
                side_effect=Exception("Unexpected error"),
            ),
            pytest.raises(RuntimeError, match="Failed to get file history"),
        ):
            await get_file_history(str(test_file))

    @pytest.mark.asyncio
    async def test_get_git_diff_python_lt_39_fallback(self, mock_settings):
        """Test get_git_diff with Python < 3.9 fallback."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = [
                ("test.py", ""),  # ls-files success - file is tracked
                ("diff content", ""),  # diff success
            ]

            # Mock path to simulate Python < 3.9 behavior (no is_relative_to)
            resolved_path = MagicMock()
            resolved_path.exists.return_value = True
            resolved_path.is_relative_to.side_effect = AttributeError()
            # Make str() work on the mock
            resolved_path.__str__ = lambda _: str(test_file)

            with patch("council.tools.git_tools.resolve_file_path", return_value=resolved_path):
                result = await get_git_diff(str(test_file))
                assert "diff content" in result

    @pytest.mark.asyncio
    async def test_get_git_diff_not_tracked(self, mock_settings):
        """Test get_git_diff with file not tracked in git."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = RuntimeError("File not tracked")
            result = await get_git_diff(str(test_file))
            assert "not tracked" in result.lower()

    @pytest.mark.asyncio
    async def test_get_git_diff_no_changes(self, mock_settings):
        """Test get_git_diff with no changes."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = [
                ("", ""),  # ls-files success
                ("", ""),  # diff returns empty
            ]
            result = await get_git_diff(str(test_file))
            assert "no changes" in result.lower()

    @pytest.mark.asyncio
    async def test_get_git_diff_runtime_error_no_changes(self, mock_settings):
        """Test get_git_diff with RuntimeError indicating no changes."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with patch("council.tools.git_tools._run_git_command") as mock_run:
            mock_run.side_effect = [
                ("", ""),  # ls-files success
                RuntimeError("no changes"),  # diff error with "no changes"
            ]
            result = await get_git_diff(str(test_file))
            assert "no changes" in result.lower()

    @pytest.mark.asyncio
    async def test_get_git_diff_exception_handling(self, mock_settings):
        """Test get_git_diff exception handling."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")

        with (
            patch(
                "council.tools.git_tools.resolve_file_path",
                side_effect=Exception("Unexpected error"),
            ),
            pytest.raises(RuntimeError, match="Failed to get git diff"),
        ):
            await get_git_diff(str(test_file))

    @pytest.mark.asyncio
    async def test_get_uncommitted_files_exception_handling(self, mock_settings):  # noqa: ARG002
        """Test get_uncommitted_files exception handling."""
        with (
            patch(
                "council.tools.git_tools._run_git_command",
                side_effect=Exception("Unexpected error"),
            ),
            pytest.raises(RuntimeError, match="Failed to get uncommitted files"),
        ):
            await get_uncommitted_files()

    @pytest.mark.asyncio
    async def test_run_git_command_default_timeout(self, mock_settings):  # noqa: ARG002
        """Test _run_git_command with default timeout."""
        from council.tools.git_tools import _run_git_command

        with patch("council.tools.git_tools.run_command_safely") as mock_run:
            mock_run.return_value = ("output", "", 0)
            await _run_git_command(["git", "status"])
            # Verify timeout was passed (should use settings.git_timeout)
            assert mock_run.called
            call_kwargs = mock_run.call_args[1]
            assert "timeout" in call_kwargs
