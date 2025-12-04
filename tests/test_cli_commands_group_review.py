"""Tests for group-review CLI command."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from council.cli.commands.group_review import group_review


class TestGroupReviewCommand:
    """Test group-review CLI command."""

    def test_group_review_command_help(self):
        """Test group-review command help output."""
        runner = CliRunner()
        result = runner.invoke(group_review, ["--help"])
        assert result.exit_code == 0
        assert "Group related files" in result.output
        assert "generate review contexts" in result.output

    def test_group_review_command_no_files_found(self, tmp_path):
        """Test group-review command with no files found."""
        runner = CliRunner()

        with patch("council.cli.commands.group_review.collect_files", return_value=[]):
            result = runner.invoke(group_review, [str(tmp_path)])
            assert result.exit_code == 1
            assert "no files found" in result.output.lower()

    def test_group_review_command_basic(self, tmp_path):
        """Test group-review command basic functionality."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()

        with (
            patch("council.cli.commands.group_review.collect_files") as mock_collect,
            patch("council.cli.commands.group_review.load_gitignore_patterns", return_value=[]),
            patch("council.cli.commands.group_review.matches_gitignore", return_value=False),
            patch("council.cli.commands.group_review.group_files_by_structure") as mock_group,
            patch("council.cli.commands.group_review.asyncio.run") as mock_run,
            patch("council.cli.commands.group_review.settings") as mock_settings,
        ):
            mock_settings.project_root = tmp_path
            mock_collect.return_value = [test_file]
            mock_group.return_value = {"test_group": [test_file]}

            # Mock the async context generation
            mock_run.return_value = {
                "test_group": {
                    "group": "test_group",
                    "files": [str(test_file)],
                    "results": [
                        {
                            "file": str(test_file),
                            "success": True,
                            "output_file": str(tmp_path / "test_context.md"),
                            "error": None,
                        }
                    ],
                    "success_count": 1,
                    "total_count": 1,
                }
            }

            result = runner.invoke(
                group_review, [str(tmp_path), "--output-dir", str(tmp_path / "output")]
            )
            assert result.exit_code == 0
            assert "Context generation complete" in result.output

    def test_group_review_command_with_gitignore(self, tmp_path):
        """Test group-review command respects gitignore."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()

        with (
            patch("council.cli.commands.group_review.collect_files") as mock_collect,
            patch(
                "council.cli.commands.group_review.load_gitignore_patterns", return_value=["*.py"]
            ),
            patch("council.cli.commands.group_review.matches_gitignore", return_value=True),
            patch("council.cli.commands.group_review.asyncio.run"),
        ):
            mock_collect.return_value = [test_file]

            result = runner.invoke(group_review, [str(tmp_path)])
            assert result.exit_code == 1  # All files filtered out
            assert "no files found" in result.output.lower()

    def test_group_review_command_no_gitignore_flag(self, tmp_path):
        """Test group-review command with --no-gitignore flag."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()

        with (
            patch("council.cli.commands.group_review.collect_files") as mock_collect,
            patch("council.cli.commands.group_review.group_files_by_structure") as mock_group,
            patch("council.cli.commands.group_review.asyncio.run") as mock_run,
        ):
            mock_collect.return_value = [test_file]
            mock_group.return_value = {"test_group": [test_file]}
            mock_run.return_value = {
                "test_group": {
                    "group": "test_group",
                    "files": [str(test_file)],
                    "results": [
                        {
                            "file": str(test_file),
                            "success": True,
                            "output_file": str(tmp_path / "test_context.md"),
                            "error": None,
                        }
                    ],
                    "success_count": 1,
                    "total_count": 1,
                }
            }

            result = runner.invoke(group_review, [str(tmp_path), "--no-gitignore"])
            assert result.exit_code == 0
            # Should not show gitignore filtering message
            assert "Filtering files using .gitignore" not in result.output

    def test_group_review_command_output_dir_validation(self, tmp_path):
        """Test group-review command validates output directory is writable."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)  # Read-only

        runner = CliRunner()

        try:
            with (
                patch("council.cli.commands.group_review.collect_files") as mock_collect,
                patch("council.cli.commands.group_review.load_gitignore_patterns", return_value=[]),
                patch("council.cli.commands.group_review.matches_gitignore", return_value=False),
                patch("council.cli.commands.group_review.group_files_by_structure") as mock_group,
                patch("council.cli.commands.group_review.settings") as mock_settings,
            ):
                mock_settings.project_root = tmp_path
                mock_collect.return_value = [test_file]
                mock_group.return_value = {"test_group": [test_file]}

                result = runner.invoke(
                    group_review, [str(tmp_path), "--output-dir", str(readonly_dir)]
                )
                assert result.exit_code == 1
                assert "not writable" in result.output.lower()
        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(0o755)

    def test_group_review_command_group_by_directory(self, tmp_path):
        """Test group-review command with --group-by directory option."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        runner = CliRunner()

        with (
            patch("council.cli.commands.group_review.collect_files") as mock_collect,
            patch("council.cli.commands.group_review.load_gitignore_patterns", return_value=[]),
            patch("council.cli.commands.group_review.matches_gitignore", return_value=False),
            patch("council.cli.commands.group_review.asyncio.run") as mock_run,
            patch("council.cli.commands.group_review.settings") as mock_settings,
        ):
            mock_settings.project_root = tmp_path
            mock_collect.return_value = [test_file]

            # Mock directory grouping
            mock_run.return_value = {
                "root": {
                    "group": "root",
                    "files": [str(test_file)],
                    "results": [
                        {
                            "file": str(test_file),
                            "success": True,
                            "output_file": str(tmp_path / "test_context.md"),
                            "error": None,
                        }
                    ],
                    "success_count": 1,
                    "total_count": 1,
                }
            }

            result = runner.invoke(group_review, [str(tmp_path), "--group-by", "directory"])
            assert result.exit_code == 0
            assert "Grouping files by directory" in result.output

    @pytest.mark.asyncio
    async def test_generate_context_success(self, tmp_path):
        """Test generate_context function success case."""
        from council.cli.commands.group_review import generate_context

        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        output_dir = tmp_path / "output"

        with patch("council.cli.commands.group_review.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="# Code Review Context\n\n## Code to Review\n```python\nprint('hello')\n```",
            )

            result = await generate_context(test_file, output_dir)

            assert result["success"] is True
            assert result["file"] == str(test_file)
            assert result["error"] is None
            assert output_dir.exists()

    @pytest.mark.asyncio
    async def test_generate_context_failure(self, tmp_path):
        """Test generate_context function failure case."""
        from council.cli.commands.group_review import generate_context

        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        output_dir = tmp_path / "output"

        with patch("council.cli.commands.group_review.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Error: File not found")

            result = await generate_context(test_file, output_dir)

            assert result["success"] is False
            assert result["error"] is not None

    def test_load_gitignore_patterns(self, tmp_path):
        """Test load_gitignore_patterns function."""
        from council.cli.commands.group_review import load_gitignore_patterns

        gitignore_file = tmp_path / ".gitignore"
        gitignore_file.write_text("*.pyc\n__pycache__/\n# Comment\n\n*.log\n")

        patterns = load_gitignore_patterns(tmp_path)

        assert "*.pyc" in patterns
        assert "__pycache__" in patterns
        assert "*.log" in patterns
        assert "# Comment" not in patterns  # Comments should be filtered
        assert "" not in patterns  # Empty lines should be filtered

    def test_matches_gitignore(self, tmp_path):
        """Test matches_gitignore function."""
        from council.cli.commands.group_review import matches_gitignore

        test_file = tmp_path / "test.pyc"
        patterns = ["*.pyc", "__pycache__"]

        assert matches_gitignore(test_file, patterns, tmp_path) is True

        test_file2 = tmp_path / "test.py"
        assert matches_gitignore(test_file2, patterns, tmp_path) is False

    def test_group_files_by_structure(self, tmp_path):
        """Test group_files_by_structure function."""
        from council.cli.commands.group_review import group_files_by_structure

        # Create test files in different structures
        (tmp_path / "src" / "council" / "tools").mkdir(parents=True)
        (tmp_path / "src" / "council" / "cli").mkdir(parents=True)
        file1 = tmp_path / "src" / "council" / "tools" / "test1.py"
        file2 = tmp_path / "src" / "council" / "cli" / "test2.py"
        file3 = tmp_path / "root.py"

        file1.write_text("print('1')")
        file2.write_text("print('2')")
        file3.write_text("print('3')")

        groups = group_files_by_structure([file1, file2, file3], tmp_path)

        assert len(groups) > 0
        # All files should be in groups
        all_grouped_files = [f for files in groups.values() for f in files]
        assert len(all_grouped_files) == 3
