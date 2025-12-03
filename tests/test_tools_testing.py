"""Tests for testing tools."""

from unittest.mock import patch

import pytest

from council.tools.exceptions import SubprocessTimeoutError
from council.tools.testing import check_test_coverage, check_test_quality, find_related_tests


class TestFindRelatedTests:
    """Test find_related_tests function."""

    @pytest.mark.asyncio
    async def test_find_related_tests_by_name(self, mock_settings):
        """Test finding tests by naming convention."""
        # Create source file
        source_file = mock_settings.project_root / "src" / "module.py"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("# source code")

        # Create test file with matching name
        test_file = mock_settings.project_root / "tests" / "test_module.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_module(): pass")

        result = await find_related_tests(str(source_file))
        assert len(result) > 0
        assert any("test_module.py" in r for r in result)

    @pytest.mark.asyncio
    async def test_find_related_tests_by_import(self, mock_settings):
        """Test finding tests that import the module."""
        # Create source file
        source_file = mock_settings.project_root / "src" / "utils.py"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("# utils code")

        # Create test file that imports it
        test_file = mock_settings.project_root / "tests" / "test_utils.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("from src.utils import something\ndef test_something(): pass")

        result = await find_related_tests(str(source_file))
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_find_related_tests_nonexistent_file(self):
        """Test with nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await find_related_tests("nonexistent.py")

    @pytest.mark.asyncio
    async def test_find_related_tests_not_a_file(self, mock_settings):
        """Test with directory instead of file."""
        test_dir = mock_settings.project_root / "test_dir"
        test_dir.mkdir()
        with pytest.raises(ValueError, match="not a file"):
            await find_related_tests(str(test_dir))

    @pytest.mark.asyncio
    async def test_find_related_tests_limit(self, mock_settings):
        """Test that results are limited to 20."""
        # Create source file
        source_file = mock_settings.project_root / "module.py"
        source_file.write_text("# code")

        # Create many test files
        test_dir = mock_settings.project_root / "tests"
        test_dir.mkdir()
        for i in range(25):
            test_file = test_dir / f"test_module_{i}.py"
            test_file.write_text(f"def test_{i}(): pass")

        result = await find_related_tests(str(source_file))
        assert len(result) <= 20

    @pytest.mark.asyncio
    async def test_find_related_tests_with_base_path(self, tmp_path):
        """Test with base_path parameter."""
        source_file = tmp_path / "module.py"
        source_file.write_text("# code")

        result = await find_related_tests(str(source_file), base_path=str(tmp_path))
        assert isinstance(result, list)


class TestCheckTestCoverage:
    """Test check_test_coverage function."""

    @pytest.mark.asyncio
    async def test_check_test_coverage_success(self, mock_settings):
        """Test successful coverage check."""
        test_file = mock_settings.project_root / "module.py"
        test_file.write_text("# code")

        mock_coverage_json = {
            "files": {
                "module.py": {
                    "summary": {"covered_lines": 10, "num_statements": 20},
                    "missing_lines": [5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
                }
            }
        }

        with patch("council.tools.testing.run_command_safely") as mock_run:
            # Mock coverage tool availability check
            mock_run.side_effect = [
                ("coverage 7.0.0", "", 0),  # Version check
                (str(mock_coverage_json).replace("'", '"'), "", 0),  # Coverage report
            ]
            with patch("json.loads", return_value=mock_coverage_json):
                result = await check_test_coverage(str(test_file))
                assert result["covered"] is True
                assert result["coverage_percent"] == 50.0
                assert result["lines_covered"] == 10
                assert result["lines_total"] == 20

    @pytest.mark.asyncio
    async def test_check_test_coverage_not_python(self, mock_settings):
        """Test coverage check for non-Python file."""
        test_file = mock_settings.project_root / "file.txt"
        test_file.write_text("text content")

        result = await check_test_coverage(str(test_file))
        assert result["covered"] is False
        assert "Python files" in result["note"]

    @pytest.mark.asyncio
    async def test_check_test_coverage_tool_unavailable(self, mock_settings):
        """Test when coverage.py is not available."""
        test_file = mock_settings.project_root / "module.py"
        test_file.write_text("# code")

        with patch("council.tools.testing.run_command_safely") as mock_run:
            mock_run.side_effect = OSError("coverage not found")
            result = await check_test_coverage(str(test_file))
            assert result["covered"] is False
            assert "not available" in result["note"]

    @pytest.mark.asyncio
    async def test_check_test_coverage_no_data(self, mock_settings):
        """Test when no coverage data exists."""
        test_file = mock_settings.project_root / "module.py"
        test_file.write_text("# code")

        with patch("council.tools.testing.run_command_safely") as mock_run:
            mock_run.side_effect = [
                ("coverage 7.0.0", "", 0),  # Version check
                ("", "", 1),  # Coverage report fails
            ]
            result = await check_test_coverage(str(test_file))
            assert result["covered"] is False
            assert "not available" in result["note"]

    @pytest.mark.asyncio
    async def test_check_test_coverage_timeout(self, mock_settings):
        """Test timeout handling."""
        test_file = mock_settings.project_root / "module.py"
        test_file.write_text("# code")

        with patch("council.tools.testing.run_command_safely") as mock_run:
            mock_run.side_effect = [
                ("coverage 7.0.0", "", 0),  # Version check
                SubprocessTimeoutError("Command timed out"),  # Coverage report times out
            ]
            result = await check_test_coverage(str(test_file))
            assert result["covered"] is False
            assert "failed" in result["note"].lower()

    @pytest.mark.asyncio
    async def test_check_test_coverage_nonexistent_file(self):
        """Test with nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await check_test_coverage("nonexistent.py")

    @pytest.mark.asyncio
    async def test_check_test_coverage_not_a_file(self, mock_settings):
        """Test with directory."""
        test_dir = mock_settings.project_root / "test_dir"
        test_dir.mkdir()
        with pytest.raises(ValueError, match="not a file"):
            await check_test_coverage(str(test_dir))

    @pytest.mark.asyncio
    async def test_check_test_coverage_missing_lines_limit(self, mock_settings):
        """Test that missing_lines are limited to 100."""
        test_file = mock_settings.project_root / "module.py"
        test_file.write_text("# code")

        # Create coverage data with >100 missing lines
        mock_coverage_json = {
            "files": {
                "module.py": {
                    "summary": {"covered_lines": 10, "num_statements": 200},
                    "missing_lines": list(range(1, 150)),  # 149 missing lines
                }
            }
        }

        with patch("council.tools.testing.run_command_safely") as mock_run:
            mock_run.side_effect = [
                ("coverage 7.0.0", "", 0),
                ("", "", 0),
            ]
            with patch("json.loads", return_value=mock_coverage_json):
                result = await check_test_coverage(str(test_file))
                assert len(result["missing_lines"]) <= 100


class TestCheckTestQuality:
    """Test check_test_quality function."""

    @pytest.mark.asyncio
    async def test_check_test_quality_good_test(self, mock_settings):
        """Test quality check for a well-written test."""
        test_file = mock_settings.project_root / "test_module.py"
        test_file.write_text(
            '''"""Test module."""
import pytest

def test_function():
    """Test function."""
    assert True

def test_another():
    """Test another."""
    assert 1 == 1
    assert 2 == 2
'''
        )

        result = await check_test_quality(str(test_file))
        assert result["test_count"] >= 2
        assert result["assertion_count"] >= 2
        assert result["quality_score"] > 70

    @pytest.mark.asyncio
    async def test_check_test_quality_no_docstrings(self, mock_settings):
        """Test quality check detects missing docstrings."""
        test_file = mock_settings.project_root / "test_module.py"
        test_file.write_text(
            """def test_function():
    assert True
"""
        )

        result = await check_test_quality(str(test_file))
        assert "docstrings" in " ".join(result["issues"]).lower() or result["quality_score"] < 100

    @pytest.mark.asyncio
    async def test_check_test_quality_low_assertions(self, mock_settings):
        """Test quality check detects low assertion ratio."""
        test_file = mock_settings.project_root / "test_module.py"
        test_file.write_text(
            """def test_one():
    pass

def test_two():
    pass

def test_three():
    pass
"""
        )

        result = await check_test_quality(str(test_file))
        # Should detect low assertion ratio
        assert result["assertion_count"] < result["test_count"]

    @pytest.mark.asyncio
    async def test_check_test_quality_global_variables(self, mock_settings):
        """Test quality check detects global variables."""
        test_file = mock_settings.project_root / "test_module.py"
        test_file.write_text(
            """global state

def test_function():
    assert True
"""
        )

        result = await check_test_quality(str(test_file))
        assert "global" in " ".join(result["issues"]).lower()

    @pytest.mark.asyncio
    async def test_check_test_quality_not_python(self, mock_settings):
        """Test quality check for non-Python file."""
        test_file = mock_settings.project_root / "test.txt"
        test_file.write_text("test content")

        result = await check_test_quality(str(test_file))
        assert result["test_count"] == 0
        assert "Python files" in result["issues"][0]

    @pytest.mark.asyncio
    async def test_check_test_quality_nonexistent_file(self):
        """Test with nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await check_test_quality("nonexistent.py")

    @pytest.mark.asyncio
    async def test_check_test_quality_not_a_file(self, mock_settings):
        """Test with directory."""
        test_dir = mock_settings.project_root / "test_dir"
        test_dir.mkdir()
        with pytest.raises(ValueError, match="not a file"):
            await check_test_quality(str(test_dir))

    @pytest.mark.asyncio
    async def test_check_test_quality_complex_test(self, mock_settings):
        """Test quality check for complex test with many assertions."""
        test_file = mock_settings.project_root / "test_module.py"
        test_file.write_text(
            """def test_complex():
    assert 1 == 1
    assert 2 == 2
    assert 3 == 3
    assert 4 == 4
    assert 5 == 5
    assert 6 == 6
    assert 7 == 7
"""
        )

        result = await check_test_quality(str(test_file))
        # Should detect high assertion ratio
        assert result["assertion_count"] > 5

    @pytest.mark.asyncio
    async def test_check_test_quality_no_tests(self, mock_settings):
        """Test quality check for file without tests."""
        test_file = mock_settings.project_root / "not_a_test.py"
        test_file.write_text("def regular_function(): pass")

        result = await check_test_quality(str(test_file))
        assert result["test_count"] == 0 or result["quality_score"] < 80
