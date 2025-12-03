"""Tests for utility functions."""

import pytest

from council.tools.exceptions import SubprocessError, SubprocessTimeoutError
from council.tools.utils import run_command_safely


class TestRunCommandSafely:
    """Test run_command_safely function."""

    @pytest.mark.asyncio
    async def test_successful_command(self):
        """Test successful command execution."""
        cmd = ["echo", "test"]
        stdout, stderr, return_code = await run_command_safely(cmd, check=False)
        assert return_code == 0
        assert "test" in stdout
        assert stderr == ""

    @pytest.mark.asyncio
    async def test_command_with_check_success(self):
        """Test command with check=True succeeds."""
        cmd = ["echo", "test"]
        stdout, stderr, return_code = await run_command_safely(cmd, check=True)
        assert return_code == 0

    @pytest.mark.asyncio
    async def test_command_with_check_failure(self):
        """Test command with check=True raises on failure."""
        cmd = ["false"]  # Command that always fails
        with pytest.raises(SubprocessError) as exc_info:
            await run_command_safely(cmd, check=True)
        assert exc_info.value.return_code != 0
        assert exc_info.value.command == cmd

    @pytest.mark.asyncio
    async def test_command_without_check_failure(self):
        """Test command with check=False returns error code."""
        cmd = ["false"]
        stdout, stderr, return_code = await run_command_safely(cmd, check=False)
        assert return_code != 0

    @pytest.mark.asyncio
    async def test_command_timeout(self):
        """Test command timeout handling."""
        # Use sleep command that will timeout
        cmd = ["sleep", "10"]
        with pytest.raises(SubprocessTimeoutError) as exc_info:
            await run_command_safely(cmd, timeout=0.1, check=False)
        assert exc_info.value.command == cmd
        assert isinstance(exc_info.value, TimeoutError)

    @pytest.mark.asyncio
    async def test_custom_working_directory(self, tmp_path):
        """Test command with custom working directory."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        cmd = ["cat", "test.txt"]
        stdout, stderr, return_code = await run_command_safely(cmd, cwd=tmp_path, check=False)
        assert return_code == 0
        assert "test content" in stdout

    @pytest.mark.asyncio
    async def test_output_size_limit(self):
        """Test output size limit enforcement."""
        # Generate large output
        cmd = ["python3", "-c", "print('x' * 20000000)"]  # 20MB output
        stdout, stderr, return_code = await run_command_safely(
            cmd, max_output_size=1024, check=False
        )
        # Output should be truncated
        assert len(stdout) <= 1024

    @pytest.mark.asyncio
    async def test_default_timeout(self):
        """Test default timeout from settings."""
        cmd = ["echo", "test"]
        # Should use settings.subprocess_timeout
        stdout, stderr, return_code = await run_command_safely(cmd, check=False)
        assert return_code == 0

    @pytest.mark.asyncio
    async def test_default_cwd(self):
        """Test default working directory."""
        cmd = ["pwd"]
        stdout, stderr, return_code = await run_command_safely(cmd, check=False)
        assert return_code == 0
        # Should use project root from settings

    @pytest.mark.asyncio
    async def test_unicode_output(self):
        """Test handling of unicode output."""
        cmd = ["python3", "-c", "print('测试')"]
        stdout, stderr, return_code = await run_command_safely(cmd, check=False)
        assert return_code == 0
        assert "测试" in stdout

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling for unexpected errors."""
        # Use invalid command that will fail
        cmd = ["nonexistent_command_xyz"]
        with pytest.raises(SubprocessError):
            await run_command_safely(cmd, check=True)
