"""Tests for CLI module."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from council.agents import CouncilDeps, ReviewResult
from council.cli import (
    Spinner,
    cleanup_spinner_task,
    collect_files,
    create_event_stream_handler,
    main,
    resolve_path,
    run_agent_review,
)


class TestSpinner:
    """Test Spinner class."""

    def test_spinner_initialization_enabled(self):
        """Test spinner initialization with enabled=True."""
        spinner = Spinner(enabled=True)
        assert spinner.enabled is True
        assert spinner.active is False
        assert spinner.current_status == "Analyzing code structure..."

    def test_spinner_initialization_disabled(self):
        """Test spinner initialization with enabled=False."""
        spinner = Spinner(enabled=False)
        assert spinner.enabled is False
        assert spinner.active is False

    def test_spinner_initialization_auto_detect(self):
        """Test spinner initialization with auto-detection."""
        spinner = Spinner(enabled=None)
        # Should auto-detect based on TTY
        assert isinstance(spinner.enabled, bool)

    def test_spinner_show_status_disabled(self):
        """Test show_status when spinner is disabled."""
        spinner = Spinner(enabled=False)
        spinner.show_status("Test message")
        # Should return early without error

    def test_spinner_show_status_enabled(self):
        """Test show_status when spinner is enabled."""
        spinner = Spinner(enabled=True)
        spinner.show_status("Test message")
        assert spinner.current_status == "Test message"

    def test_spinner_stop(self):
        """Test spinner stop."""
        spinner = Spinner(enabled=True)
        spinner.active = True
        spinner.stop()
        assert spinner.active is False

    def test_spinner_stop_disabled(self):
        """Test spinner stop when disabled."""
        spinner = Spinner(enabled=False)
        spinner.stop()
        # Should return early without error

    @pytest.mark.asyncio
    async def test_spinner_run_disabled(self):
        """Test spinner run when disabled."""
        spinner = Spinner(enabled=False)
        await spinner.run()
        assert spinner.active is False

    @pytest.mark.asyncio
    async def test_spinner_run_enabled(self):
        """Test spinner run when enabled."""
        spinner = Spinner(enabled=True)
        spinner.active = True

        # Cancel after a short delay
        async def cancel_after_delay():
            await asyncio.sleep(0.1)
            spinner.stop()

        task = asyncio.create_task(spinner.run())
        cancel_task = asyncio.create_task(cancel_after_delay())
        await cancel_task
        await task
        assert spinner.active is False

    def test_spinner_is_tty(self):
        """Test _is_tty method."""
        result = Spinner._is_tty()
        assert isinstance(result, bool)

    def test_spinner_safe_stderr_write(self):
        """Test _safe_stderr_write method."""
        Spinner._safe_stderr_write("test message")


class TestCreateEventStreamHandler:
    """Test create_event_stream_handler function."""

    @pytest.mark.asyncio
    async def test_event_stream_handler_part_start(self):
        """Test event handler with PartStartEvent."""
        spinner = Spinner(enabled=False)
        handler = create_event_stream_handler(spinner)

        from pydantic_ai.messages import PartStartEvent

        class MockPart:
            tool_name = "test_tool"

        event = PartStartEvent(part=MockPart(), index=0)
        event_stream = [event]

        async def async_iter():
            for e in event_stream:
                yield e

        await handler(None, async_iter())

    @pytest.mark.asyncio
    async def test_event_stream_handler_final_result(self):
        """Test event handler with FinalResultEvent."""
        spinner = Spinner(enabled=False)
        handler = create_event_stream_handler(spinner)

        from pydantic_ai.messages import FinalResultEvent

        event = FinalResultEvent(tool_name="test_tool", tool_call_id="123")
        event_stream = [event]

        async def async_iter():
            for e in event_stream:
                yield e

        await handler(None, async_iter())


class TestCleanupSpinnerTask:
    """Test _cleanup_spinner_task function."""

    @pytest.mark.asyncio
    async def test_cleanup_spinner_task_none(self):
        """Test cleanup with None task."""
        spinner = Spinner(enabled=False)
        await cleanup_spinner_task(None, spinner)

    @pytest.mark.asyncio
    async def test_cleanup_spinner_task_done(self):
        """Test cleanup with done task."""
        spinner = Spinner(enabled=False)
        task = asyncio.create_task(asyncio.sleep(0))
        await task  # Ensure it's done
        await cleanup_spinner_task(task, spinner)

    @pytest.mark.asyncio
    async def test_cleanup_spinner_task_cancel(self):
        """Test cleanup with active task."""
        spinner = Spinner(enabled=False)
        task = asyncio.create_task(asyncio.sleep(10))
        await cleanup_spinner_task(task, spinner)
        assert task.cancelled()


class TestResolvePath:
    """Test _resolve_path function."""

    def test_resolve_path_absolute(self, tmp_path):
        """Test resolving absolute path."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")
        result = resolve_path(test_file)
        assert result == test_file.resolve()

    def test_resolve_path_relative(self, tmp_path, monkeypatch):
        """Test resolving relative path."""
        monkeypatch.chdir(tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")
        result = resolve_path(Path("test.py"))
        assert result == test_file.resolve()

    def test_resolve_path_nonexistent(self, tmp_path, monkeypatch):
        """Test resolving nonexistent path."""
        monkeypatch.chdir(tmp_path)
        result = resolve_path(Path("nonexistent.py"))
        # Should still return a resolved path even if file doesn't exist
        assert isinstance(result, Path)


class TestCollectFiles:
    """Test _collect_files function."""

    def test_collect_files_single_file(self, tmp_path):
        """Test collecting single file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")
        result = collect_files([test_file])
        assert len(result) == 1
        assert result[0] == test_file

    def test_collect_files_directory(self, tmp_path):
        """Test collecting files from directory."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        (test_dir / "file1.py").write_text("# test1")
        (test_dir / "file2.py").write_text("# test2")
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "file3.py").write_text("# test3")

        result = collect_files([test_dir])
        assert len(result) == 3
        assert all(f.suffix == ".py" for f in result)

    def test_collect_files_mixed(self, tmp_path):
        """Test collecting files from mixed sources."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        (test_dir / "file1.py").write_text("# test1")

        result = collect_files([test_file, test_dir])
        assert len(result) == 2

    def test_collect_files_nonexistent(self, tmp_path):
        """Test collecting from nonexistent path."""
        nonexistent = tmp_path / "nonexistent.py"
        result = collect_files([nonexistent])
        assert len(result) == 0


class TestRunAgentReview:
    """Test run_agent_review function."""

    @pytest.mark.asyncio
    async def test_run_agent_review_success(self):
        """Test successful agent review."""
        spinner = Spinner(enabled=False)
        deps = CouncilDeps(file_path="test.py")
        packed_xml = "<code>test code</code>"

        mock_review_result = ReviewResult(
            summary="Test summary",
            issues=[],
            severity="low",
        )

        mock_agent = MagicMock()
        mock_run = AsyncMock()

        async def async_iter():
            yield mock_review_result

        mock_run.stream_output = async_iter
        mock_run.get_output = AsyncMock(return_value=mock_review_result)

        class MockContextManager:
            async def __aenter__(self):
                return mock_run

            async def __aexit__(self, *args):
                return None

        mock_agent.run_stream = MagicMock(return_value=MockContextManager())

        with (
            patch("council.cli.core.review_executor.get_councilor_agent", return_value=mock_agent),
            patch("council.agents.councilor._debug_writers_lock", create=True),
            patch("council.agents.councilor._debug_writers", create=True, new={}),
            patch("council.cli.core.review_executor.DebugWriter", create=True),
        ):
            result = await run_agent_review(packed_xml, deps, spinner)
            assert isinstance(result, ReviewResult)
            assert result.summary == "Test summary"


class TestMainCLI:
    """Test main CLI command."""

    def test_main_command(self):
        """Test main command exists."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "The Council" in result.output or "council" in result.output.lower()

    def test_main_version(self):
        """Test version option."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0


class TestHandleCommonErrors:
    """Test _handle_common_errors function."""

    def test_handle_value_error(self):
        """Test handling ValueError."""
        from council.cli.utils.errors import handle_common_errors

        with pytest.raises(SystemExit) as exc_info:
            handle_common_errors(ValueError("Test error"))
        assert exc_info.value.code == 1

    def test_handle_type_error(self):
        """Test handling TypeError."""
        from council.cli.utils.errors import handle_common_errors

        with pytest.raises(SystemExit) as exc_info:
            handle_common_errors(TypeError("Test error"))
        assert exc_info.value.code == 1

    def test_handle_file_not_found_error(self):
        """Test handling FileNotFoundError."""
        from council.cli.utils.errors import handle_common_errors

        with pytest.raises(SystemExit) as exc_info:
            handle_common_errors(FileNotFoundError("Test file"))
        assert exc_info.value.code == 1

    def test_handle_generic_error(self):
        """Test handling generic Exception."""
        from council.cli.utils.errors import handle_common_errors

        with pytest.raises(SystemExit) as exc_info:
            handle_common_errors(Exception("Unexpected error"))
        assert exc_info.value.code == 1


class TestPrintPretty:
    """Test _print_pretty function."""

    def test_print_pretty_with_issues(self):
        """Test printing pretty format with issues."""
        from council.agents import ReviewResult
        from council.agents.councilor import Issue
        from council.cli.ui.output import print_pretty

        review_result = ReviewResult(
            summary="Test summary",
            issues=[
                Issue(
                    description="Test issue",
                    severity="medium",
                    line_number=10,
                    code_snippet="test code",
                )
            ],
            severity="medium",
        )

        # Should not raise an error
        print_pretty(review_result)

    def test_print_pretty_no_issues(self):
        """Test printing pretty format without issues."""
        from council.agents import ReviewResult
        from council.cli.ui.output import print_pretty

        review_result = ReviewResult(
            summary="Test summary",
            issues=[],
            severity="low",
        )

        # Should not raise an error
        print_pretty(review_result)

    def test_print_pretty_with_code_fix(self):
        """Test printing pretty format with code fix."""
        from council.agents import ReviewResult
        from council.cli.ui.output import print_pretty

        review_result = ReviewResult(
            summary="Test summary",
            issues=[],
            severity="low",
            code_fix="Fix code here",
        )

        # Should not raise an error
        print_pretty(review_result)


class TestPrintMarkdown:
    """Test _print_markdown function."""

    def test_print_markdown_with_issues(self):
        """Test printing markdown format with issues."""
        from council.agents import ReviewResult
        from council.agents.councilor import Issue
        from council.cli.ui.output import print_markdown

        review_result = ReviewResult(
            summary="Test summary",
            issues=[
                Issue(
                    description="Test issue",
                    severity="medium",
                    line_number=10,
                    code_snippet="test code",
                )
            ],
            severity="medium",
        )

        # Should not raise an error
        print_markdown(review_result)

    def test_print_markdown_no_issues(self):
        """Test printing markdown format without issues."""
        from council.agents import ReviewResult
        from council.cli.ui.output import print_markdown

        review_result = ReviewResult(
            summary="Test summary",
            issues=[],
            severity="low",
        )

        # Should not raise an error
        print_markdown(review_result)
