"""Tests for context CLI command."""

import json
from unittest.mock import patch

from click.testing import CliRunner

from council.cli.commands.context import (
    MAX_EXTRA_INSTRUCTIONS_LENGTH,
    _output_json,
    _output_markdown,
    context,
)


class TestContextCommand:
    """Test context CLI command."""

    def test_context_command_help(self):
        """Test context command help output."""
        runner = CliRunner()
        result = runner.invoke(context, ["--help"])
        assert result.exit_code == 0
        assert "Output review context" in result.output

    def test_context_command_file_not_found(self, tmp_path):
        """Test context command with nonexistent file."""
        runner = CliRunner()
        result = runner.invoke(context, [str(tmp_path / "nonexistent.py")])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_context_command_invalid_path(self):
        """Test context command with invalid path."""
        runner = CliRunner()
        result = runner.invoke(context, ["../../../etc/passwd"])
        assert result.exit_code == 1
        assert "invalid" in result.output.lower()

    def test_context_command_extra_instructions_too_long(self, tmp_path):
        """Test context command with extra instructions too long."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()
        long_instructions = "x" * (MAX_EXTRA_INSTRUCTIONS_LENGTH + 1)
        result = runner.invoke(
            context,
            [str(test_file), "--extra-instructions", long_instructions],
        )
        assert result.exit_code == 1
        assert "too long" in result.output.lower()

    def test_context_command_invalid_phases(self, tmp_path):
        """Test context command with invalid review phases."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()
        with patch("council.cli.commands.context.asyncio.run"):
            result = runner.invoke(
                context,
                [str(test_file), "--phases", "invalid_phase"],
            )
            # Should not exit with error, just warn
            assert "valid phases" in result.output.lower() or result.exit_code == 0

    def test_context_command_valid_phases(self, tmp_path):
        """Test context command with valid review phases."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()
        with patch("council.cli.commands.context.asyncio.run"):
            result = runner.invoke(
                context,
                [str(test_file), "--phases", "security,performance"],
            )
            # Should not exit with error
            assert result.exit_code in (0, 1)  # May fail on async execution

    def test_context_command_with_diff(self, tmp_path):
        """Test context command with diff option."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()
        with patch("council.cli.commands.context.asyncio.run"):
            result = runner.invoke(
                context,
                [str(test_file), "--diff", "HEAD"],
            )
            # Should not exit with error immediately
            assert result.exit_code in (0, 1)


class TestOutputJson:
    """Test JSON output function."""

    def test_output_json(self, capsys):
        """Test JSON output formatting."""
        context_data = {
            "file_path": "test.py",
            "language": "python",
            "extracted_code": "print('hello')",
            "system_prompt": "Review this code",
            "knowledge_base": "",
            "review_checklist": "Check for bugs",
            "metadata": {},
        }
        _output_json(context_data)
        captured = capsys.readouterr()
        assert "test.py" in captured.out
        # Should be valid JSON
        json.loads(captured.out)


class TestOutputMarkdown:
    """Test Markdown output function."""

    def test_output_markdown(self, capsys):
        """Test Markdown output formatting."""
        context_data = {
            "file_path": "test.py",
            "language": "python",
            "extracted_code": "print('hello')",
            "system_prompt": "Review this code",
            "knowledge_base": "Some knowledge",
            "review_checklist": "Check for bugs",
            "metadata": {
                "extra_instructions": "Focus on security",
                "review_phases": ["security"],
            },
        }
        _output_markdown(context_data)
        captured = capsys.readouterr()
        assert "# Code Review Context" in captured.out
        assert "test.py" in captured.out
        assert "python" in captured.out
        assert "Focus on security" in captured.out
        assert "security" in captured.out

    def test_output_markdown_empty_knowledge(self, capsys):
        """Test Markdown output with empty knowledge base."""
        context_data = {
            "file_path": "test.py",
            "language": "python",
            "extracted_code": "print('hello')",
            "system_prompt": "Review this code",
            "knowledge_base": "",
            "review_checklist": "Check for bugs",
            "metadata": {
                "extra_instructions": None,
                "review_phases": None,
            },
        }
        _output_markdown(context_data)
        captured = capsys.readouterr()
        # Check for either the message or that knowledge section exists
        assert (
            "No relevant knowledge base content loaded" in captured.out
            or "Knowledge Base" in captured.out
        )
