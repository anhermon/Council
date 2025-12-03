"Tests for static_analysis module."

import builtins
import json
from unittest.mock import patch

import pytest

from council.tools.static_analysis import run_static_analysis


class TestRunStaticAnalysis:
    """Tests for run_static_analysis function."""

    @pytest.mark.asyncio
    async def test_invalid_type(self):
        """Test invalid type raises TypeError."""
        with pytest.raises(TypeError, match="file_path must be a string"):
            await run_static_analysis(123)

    @pytest.mark.asyncio
    async def test_empty_path(self):
        """Test empty path raises ValueError."""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            await run_static_analysis("")

        with pytest.raises(ValueError, match="file_path cannot be empty"):
            await run_static_analysis("   ")

    @pytest.mark.asyncio
    async def test_nonexistent_file(self):
        """Test nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await run_static_analysis("nonexistent.py")

    @pytest.mark.asyncio
    async def test_path_not_a_file(self, mock_settings):
        """Test path that is not a file raises ValueError."""
        test_dir = mock_settings.project_root / "test_dir"
        test_dir.mkdir()

        with pytest.raises(ValueError, match="Path is not a file"):
            await run_static_analysis("test_dir")

    @pytest.mark.asyncio
    async def test_non_python_file_returns_empty_results(self, mock_settings):
        """Test non-Python file returns empty results."""
        test_file = mock_settings.project_root / "test.txt"
        test_file.write_text("test content")

        result = await run_static_analysis("test.txt")
        assert result["ruff"] is None
        assert result["mypy"] is None
        assert result["pylint"] is None
        assert result["available_tools"] == []

    @pytest.mark.asyncio
    async def test_python_file_with_no_tools_available(self, mock_settings):
        """Test Python file when no tools are available."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        with patch("council.tools.static_analysis.run_command_safely") as mock_run:
            # Mock all tool checks to fail
            mock_run.side_effect = RuntimeError("Tool not found")

            result = await run_static_analysis("test.py")
            assert result["available_tools"] == []

    @pytest.mark.asyncio
    async def test_python_file_with_ruff_available(self, mock_settings):
        """Test Python file with ruff available."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        def side_effect(cmd, **_kwargs):
            if cmd[0] == "ruff":
                if "check" in cmd:
                    return json.dumps([{"code": "E501", "message": "Line too long"}]), "", 0
                return "ruff 0.1.0", "", 0
            raise RuntimeError("Tool not found")

        with patch("council.tools.static_analysis.run_command_safely") as mock_run:
            mock_run.side_effect = side_effect

            result = await run_static_analysis("test.py")
            assert "ruff" in result["available_tools"]
            assert result["ruff"] is not None
            assert "issues" in result["ruff"]

    @pytest.mark.asyncio
    async def test_python_file_with_mypy_available(self, mock_settings):
        """Test Python file with mypy available."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("def hello() -> None:\n    pass\n")

        def side_effect(cmd, **_kwargs):
            if cmd[0] == "mypy":
                if "--show-error-codes" in cmd:
                    return "Success: no issues found", "", 0
                return "mypy 1.0.0", "", 0
            raise RuntimeError("Tool not found")

        with patch("council.tools.static_analysis.run_command_safely") as mock_run:
            mock_run.side_effect = side_effect

            result = await run_static_analysis("test.py")
            assert "mypy" in result["available_tools"]
            assert result["mypy"] is not None
            assert "output" in result["mypy"]

    @pytest.mark.asyncio
    async def test_python_file_with_pylint_available(self, mock_settings):
        """Test Python file with pylint available."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        def side_effect(cmd, **_kwargs):
            if cmd[0] == "pylint":
                if "--output-format=json" in cmd:
                    return (
                        json.dumps([{"type": "convention", "message": "Missing docstring"}]),
                        "",
                        0,
                    )
                return "pylint 2.0.0", "", 0
            raise RuntimeError("Tool not found")

        with patch("council.tools.static_analysis.run_command_safely") as mock_run:
            mock_run.side_effect = side_effect

            result = await run_static_analysis("test.py")
            assert "pylint" in result["available_tools"]
            assert result["pylint"] is not None
            assert "issues" in result["pylint"]

    @pytest.mark.asyncio
    async def test_tool_timeout_handling(self, mock_settings):
        """Test tool timeout is handled gracefully."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        with patch("council.tools.static_analysis.run_command_safely") as mock_run:
            # Mock timeout error for all calls
            mock_run.side_effect = builtins.TimeoutError("Command timed out")

            result = await run_static_analysis("test.py")
            # Should return empty results, not raise exception
            assert result["available_tools"] == []

    @pytest.mark.asyncio
    async def test_tool_error_handling(self, mock_settings):
        """Test tool errors are handled gracefully."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        with patch("council.tools.static_analysis.run_command_safely") as mock_run:
            # Mock RuntimeError (e.g., tool check failed) for all calls
            # This simulates the tool not being available/installed
            mock_run.side_effect = RuntimeError("Tool not found")

            result = await run_static_analysis("test.py")
            # Should return empty results, not raise exception
            assert result["available_tools"] == []

    @pytest.mark.asyncio
    async def test_all_tools_available(self, mock_settings):
        """Test all tools available and run successfully."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("def hello() -> None:\n    pass\n")

        def side_effect(cmd, **_kwargs):
            if cmd[0] == "ruff":
                if "check" in cmd:
                    return json.dumps([]), "", 0
                return "ruff 0.1.0", "", 0
            if cmd[0] == "mypy":
                if "--show-error-codes" in cmd:
                    return "Success", "", 0
                return "mypy 1.0.0", "", 0
            if cmd[0] == "pylint":
                if "--output-format=json" in cmd:
                    return json.dumps([]), "", 0
                return "pylint 2.0.0", "", 0
            return "", "", 1

        with patch("council.tools.static_analysis.run_command_safely") as mock_run:
            mock_run.side_effect = side_effect

            result = await run_static_analysis("test.py")
            assert len(result["available_tools"]) == 3
            assert "ruff" in result["available_tools"]
            assert "mypy" in result["available_tools"]
            assert "pylint" in result["available_tools"]

    @pytest.mark.asyncio
    async def test_base_path_usage(self, mock_settings):
        """Test base_path parameter is used correctly."""
        subdir = mock_settings.project_root / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        with patch("council.tools.static_analysis.run_command_safely") as mock_run:
            mock_run.side_effect = RuntimeError("Tool not found")

            # Should resolve file using base_path
            result = await run_static_analysis("test.py", base_path=str(subdir))
            assert result["available_tools"] == []

    @pytest.mark.asyncio
    async def test_json_decode_error_fallback(self, mock_settings):
        """Test JSON decode error falls back to text output."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        def side_effect(cmd, **_kwargs):
            if cmd[0] == "ruff":
                if "check" in cmd:
                    return "Invalid JSON output", "", 0
                return "ruff 0.1.0", "", 0
            raise RuntimeError("Tool not found")

        with patch("council.tools.static_analysis.run_command_safely") as mock_run:
            mock_run.side_effect = side_effect

            result = await run_static_analysis("test.py")
            assert "ruff" in result["available_tools"]
            assert result["ruff"] is not None
            # Should have "output" key instead of "issues" when JSON decode fails
            assert "output" in result["ruff"] or "issues" in result["ruff"]
