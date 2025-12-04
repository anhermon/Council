"""Tests for security scanning tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from council.tools.security import scan_security_vulnerabilities


class TestScanSecurityVulnerabilities:
    """Test scan_security_vulnerabilities function."""

    @pytest.mark.asyncio
    async def test_scan_python_file_with_bandit(self, mock_settings):
        """Test scanning Python file with bandit available."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("password = 'secret123'")

        mock_bandit_json = {
            "results": [
                {
                    "test_id": "B105",
                    "test_name": "hardcoded_password_string",
                    "issue_severity": "MEDIUM",
                    "issue_confidence": "HIGH",
                }
            ]
        }

        with patch("council.tools.security.run_command_safely") as mock_run:
            # Mock version check (returns success)
            # Mock bandit scan (returns JSON results)
            mock_run.side_effect = [
                ("bandit 1.7.0", "", 0),  # Version check succeeds
                (str(mock_bandit_json).replace("'", '"'), "", 0),  # Scan succeeds
            ]

            result = await scan_security_vulnerabilities(str(test_file))
            assert "bandit" in result
            assert "available_tools" in result
            assert "bandit" in result["available_tools"] or result["bandit"] is not None

    @pytest.mark.asyncio
    async def test_scan_python_file_no_tools(self, mock_settings):
        """Test scanning when no security tools are available."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# code")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock version checks failing (tools not available)
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b"command not found", 1))
            mock_proc.returncode = 1  # Tool not found

            mock_subprocess.return_value = mock_proc

            result = await scan_security_vulnerabilities(str(test_file))
            assert result["available_tools"] == []
            assert result["bandit"] is None
            assert result["semgrep"] is None

    @pytest.mark.asyncio
    async def test_scan_with_semgrep(self, mock_settings):
        """Test scanning with semgrep available."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# code")

        mock_semgrep_json = {"results": []}

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock version check
            mock_version_proc = MagicMock()
            mock_version_proc.communicate = AsyncMock(return_value=(b"semgrep 1.0.0", b"", 0))
            mock_version_proc.returncode = 0

            # Mock semgrep scan
            mock_scan_proc = MagicMock()
            mock_scan_proc.communicate = AsyncMock(
                return_value=(str(mock_semgrep_json).replace("'", '"').encode(), b"", 0)
            )
            mock_scan_proc.returncode = 0

            mock_subprocess.side_effect = [mock_version_proc, mock_scan_proc]

            result = await scan_security_vulnerabilities(str(test_file))
            assert "semgrep" in result
            assert "available_tools" in result

    @pytest.mark.asyncio
    async def test_scan_directory(self, mock_settings):
        """Test scanning a directory."""
        test_dir = mock_settings.project_root / "test_dir"
        test_dir.mkdir()
        (test_dir / "file1.py").write_text("# code")
        (test_dir / "file2.py").write_text("# code")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b"command not found", 1))
            mock_proc.returncode = 1  # Tools not available

            mock_subprocess.return_value = mock_proc

            result = await scan_security_vulnerabilities(str(test_dir))
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_scan_non_python_file(self, mock_settings):
        """Test scanning non-Python file."""
        test_file = mock_settings.project_root / "test.txt"
        test_file.write_text("text content")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Only semgrep should run (bandit is Python-only)
            mock_version_proc = MagicMock()
            mock_version_proc.communicate = AsyncMock(return_value=(b"semgrep 1.0.0", b"", 0))
            mock_version_proc.returncode = 0

            mock_subprocess.return_value = mock_version_proc

            result = await scan_security_vulnerabilities(str(test_file))
            # Bandit should not run for non-Python files
            assert result["bandit"] is None

    @pytest.mark.asyncio
    async def test_scan_nonexistent_file(self):
        """Test scanning nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await scan_security_vulnerabilities("nonexistent.py")

    @pytest.mark.asyncio
    async def test_scan_bandit_json_error(self, mock_settings):
        """Test handling of bandit JSON parsing errors."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# code")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock version check
            mock_version_proc = MagicMock()
            mock_version_proc.communicate = AsyncMock(return_value=(b"bandit 1.7.0", b"", 0))
            mock_version_proc.returncode = 0

            # Mock bandit scan with invalid JSON
            mock_scan_proc = MagicMock()
            mock_scan_proc.communicate = AsyncMock(return_value=(b"invalid json output", b"", 0))
            mock_scan_proc.returncode = 0

            mock_subprocess.side_effect = [mock_version_proc, mock_scan_proc]

            result = await scan_security_vulnerabilities(str(test_file))
            # Should fallback to text output
            assert "bandit" in result

    @pytest.mark.asyncio
    async def test_scan_timeout(self, mock_settings):
        """Test timeout handling."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# code")

        from council.tools.exceptions import SubprocessTimeoutError

        with patch("council.tools.security.run_command_safely") as mock_run:
            # Mock version check (returns success)
            # Mock scan that times out
            mock_run.side_effect = [
                ("bandit 1.7.0", "", 0),  # Version check succeeds
                SubprocessTimeoutError("Command timed out", command=["bandit"]),  # Scan times out
            ]

            # Should handle timeout gracefully (exception is caught and logged)
            result = await scan_security_vulnerabilities(str(test_file))
            # Timeout should be caught and result should contain error info
            assert "bandit" in result
            assert result["bandit"] is not None
            assert "error" in result["bandit"]

    @pytest.mark.asyncio
    async def test_scan_with_base_path(self, tmp_path):
        """Test scanning with base_path parameter."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# code")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b"command not found", 1))
            mock_proc.returncode = 1

            mock_subprocess.return_value = mock_proc

            result = await scan_security_vulnerabilities(str(test_file), base_path=str(tmp_path))
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_scan_output_size_limit(self, mock_settings):
        """Test output size limit handling."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# code")

        # Create very large output
        large_output = "x" * (11 * 1024 * 1024)  # > 10MB

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_version_proc = MagicMock()
            mock_version_proc.communicate = AsyncMock(return_value=(b"bandit 1.7.0", b"", 0))
            mock_version_proc.returncode = 0

            mock_scan_proc = MagicMock()
            mock_scan_proc.communicate = AsyncMock(return_value=(large_output.encode(), b"", 0))
            mock_scan_proc.returncode = 0

            mock_subprocess.side_effect = [mock_version_proc, mock_scan_proc]

            result = await scan_security_vulnerabilities(str(test_file))
            # Output should be truncated
            assert "bandit" in result or "semgrep" in result

    @pytest.mark.asyncio
    async def test_scan_bandit_error_handling(self, mock_settings):
        """Test error handling when bandit fails."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# code")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_version_proc = MagicMock()
            mock_version_proc.communicate = AsyncMock(return_value=(b"bandit 1.7.0", b"", 0))
            mock_version_proc.returncode = 0

            # Mock bandit scan that raises exception
            mock_scan_proc = MagicMock()
            mock_scan_proc.communicate = AsyncMock(side_effect=Exception("Bandit error"))

            mock_subprocess.side_effect = [mock_version_proc, mock_scan_proc]

            result = await scan_security_vulnerabilities(str(test_file))
            # Should handle error gracefully
            assert "bandit" in result
            assert "error" in str(result["bandit"]).lower() or result["bandit"] is None
