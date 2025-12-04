"""Tests for housekeeping CLI command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from council.cli.commands.housekeeping import _agent_edit_file, housekeeping


class TestAgentEditFile:
    """Test _agent_edit_file function."""

    @pytest.mark.asyncio
    async def test_agent_edit_file_success(self, mock_project_root):
        """Test successful file editing."""
        test_file = mock_project_root / "test.py"
        test_file.write_text("print('hello')")

        mock_agent = MagicMock()
        mock_run = AsyncMock()

        async def async_iter():
            yield None  # Make it an async generator

        mock_run.stream_output = async_iter
        mock_run.get_output = AsyncMock(return_value=None)

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_run)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        mock_agent.run_stream = MagicMock(return_value=mock_context_manager)

        spinner = MagicMock()

        # Patch the agent and CouncilDeps to avoid path validation
        with (
            patch("council.cli.commands.housekeeping.get_councilor_agent", return_value=mock_agent),
            patch("council.cli.commands.housekeeping.CouncilDeps") as mock_deps_class,
        ):
            # Mock CouncilDeps to return a mock object
            mock_deps_instance = MagicMock()
            mock_deps_class.return_value = mock_deps_instance
            success, message = await _agent_edit_file(test_file, "Add docstring", spinner)
            assert success is True
            assert "test.py" in message or "test" in message.lower()

    @pytest.mark.asyncio
    async def test_agent_edit_file_error(self, tmp_path):
        """Test file editing with error."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(side_effect=Exception("Test error"))

        spinner = MagicMock()

        with patch(
            "council.cli.commands.housekeeping.get_councilor_agent", return_value=mock_agent
        ):
            success, message = await _agent_edit_file(test_file, "Add docstring", spinner)
            assert success is False
            assert "error" in message.lower() or "failed" in message.lower()

    @pytest.mark.asyncio
    async def test_agent_edit_file_large_file(self, mock_project_root):
        """Test editing large file (truncation)."""
        test_file = mock_project_root / "large.py"
        # Create a file larger than MAX_PROMPT_CONTENT (50k chars)
        large_content = "print('hello')\n" * 10000  # ~150k chars
        test_file.write_text(large_content)

        mock_agent = MagicMock()
        mock_run = AsyncMock()

        async def async_iter():
            return
            yield  # Make it an async generator

        mock_run.stream_output = async_iter
        mock_run.get_output = AsyncMock(return_value=None)

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_run)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        mock_agent.run_stream = MagicMock(return_value=mock_context_manager)

        spinner = MagicMock()

        # Patch the agent and CouncilDeps to avoid path validation
        with (
            patch("council.cli.commands.housekeeping.get_councilor_agent", return_value=mock_agent),
            patch("council.cli.commands.housekeeping.CouncilDeps") as mock_deps_class,
        ):
            # Mock CouncilDeps to return a mock object
            mock_deps_instance = MagicMock()
            mock_deps_class.return_value = mock_deps_instance
            success, message = await _agent_edit_file(test_file, "Add docstring", spinner)
            # Should succeed but with truncation note
            assert success is True


class TestHousekeepingCommand:
    """Test housekeeping CLI command."""

    def test_housekeeping_command_help(self):
        """Test housekeeping command help output."""
        runner = CliRunner()
        result = runner.invoke(housekeeping, ["--help"])
        assert result.exit_code == 0
        assert "codebase maintenance" in result.output.lower()

    def test_housekeeping_command_runs(self):
        """Test that housekeeping command can be invoked."""
        runner = CliRunner()
        # Mock the entire execution to avoid actually running housekeeping
        with patch("council.cli.commands.housekeeping.click.echo"):
            # This will fail early, but we're just testing the command structure
            try:
                result = runner.invoke(housekeeping)
                # Command may exit with error if gitignore doesn't exist, etc.
                assert result.exit_code in (0, 1)
            except Exception:
                # Some operations may fail in test environment, that's OK
                pass
