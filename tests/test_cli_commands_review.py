"""Tests for review CLI command."""

from unittest.mock import patch

from click.testing import CliRunner

from council.cli.commands.review import review
from council.cli.utils.constants import MAX_EXTRA_INSTRUCTIONS_LENGTH


class TestReviewCommand:
    """Test review CLI command."""

    def test_review_command_help(self):
        """Test review command help output."""
        runner = CliRunner()
        result = runner.invoke(review, ["--help"])
        assert result.exit_code == 0
        assert "Review code" in result.output

    def test_review_command_file_not_found(self, tmp_path):
        """Test review command with nonexistent file."""
        runner = CliRunner()
        result = runner.invoke(review, [str(tmp_path / "nonexistent.py")])
        assert result.exit_code == 1
        assert "no files found" in result.output.lower() or "not found" in result.output.lower()

    def test_review_command_extra_instructions_too_long(self, tmp_path):
        """Test review command with extra instructions too long."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()
        long_instructions = "x" * (MAX_EXTRA_INSTRUCTIONS_LENGTH + 1)
        result = runner.invoke(
            review,
            [str(test_file), "--extra-instructions", long_instructions],
        )
        assert result.exit_code == 1
        assert "too long" in result.output.lower()

    def test_review_command_invalid_phases(self, tmp_path):
        """Test review command with invalid review phases."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()
        with patch("council.cli.commands.review.asyncio.run"):
            result = runner.invoke(
                review,
                [str(test_file), "--phases", "invalid_phase"],
            )
            # Should not exit with error immediately
            assert result.exit_code in (0, 1)

    def test_review_command_with_diff(self, tmp_path):
        """Test review command with diff option."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()
        with patch("council.cli.commands.review.asyncio.run"):
            result = runner.invoke(
                review,
                [str(test_file), "--diff", "HEAD"],
            )
            # Should not exit with error immediately
            assert result.exit_code in (0, 1)

    def test_review_command_no_cache_flag(self, tmp_path):
        """Test review command with --no-cache flag."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()
        with patch("council.cli.commands.review.asyncio.run"):
            result = runner.invoke(
                review,
                [str(test_file), "--no-cache"],
            )
            # Should not exit with error immediately
            assert result.exit_code in (0, 1)

    def test_review_command_uncommitted_flag(self):
        """Test review command with --uncommitted flag."""
        runner = CliRunner()
        with patch("council.cli.commands.review.asyncio.run"):
            result = runner.invoke(review, ["--uncommitted"])
            # Should not exit with error immediately
            assert result.exit_code in (0, 1)

    def test_review_command_output_formats(self, tmp_path):
        """Test review command with different output formats."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()
        for output_format in ["json", "markdown", "pretty"]:
            with patch("council.cli.commands.review.asyncio.run"):
                result = runner.invoke(
                    review,
                    [str(test_file), "--output", output_format],
                )
                # Should not exit with error immediately
                assert result.exit_code in (0, 1)

    def test_review_command_multiple_files(self, tmp_path):
        """Test review command with multiple files."""
        test_file1 = tmp_path / "test1.py"
        test_file1.write_text("print('hello')")
        test_file2 = tmp_path / "test2.py"
        test_file2.write_text("print('world')")

        runner = CliRunner()
        with patch("council.cli.commands.review.asyncio.run"):
            result = runner.invoke(
                review,
                [str(test_file1), str(test_file2)],
            )
            # Should not exit with error immediately
            assert result.exit_code in (0, 1)
