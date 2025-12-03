"""Security scanning tools for vulnerability detection."""

import asyncio
import json
from pathlib import Path
from typing import Any

import logfire

from ..config import settings
from .path_utils import resolve_file_path

# Maximum output size (10MB)
MAX_OUTPUT_SIZE = 10 * 1024 * 1024

# Timeout for security scanning tools (5 minutes)
SECURITY_SCAN_TIMEOUT = 300.0


async def _run_security_tool(
    cmd: list[str], cwd: Path | None = None, timeout: float = SECURITY_SCAN_TIMEOUT
) -> tuple[str, str, int]:
    """
    Run a security scanning tool command.

    Args:
        cmd: Command as list of strings
        cwd: Working directory
        timeout: Command timeout

    Returns:
        Tuple of (stdout, stderr, return_code)
    """
    if cwd is None:
        cwd = settings.project_root.resolve()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        # Check output size
        if len(stdout_text) > MAX_OUTPUT_SIZE:
            logfire.warning("Security tool output too large, truncating", size=len(stdout_text))
            stdout_text = stdout_text[:MAX_OUTPUT_SIZE]

        return stdout_text, stderr_text, proc.returncode

    except TimeoutError as e:
        raise TimeoutError(f"Security scan command timed out after {timeout} seconds") from e
    except Exception as e:
        logfire.error("Security scan command failed", cmd=cmd, error=str(e))
        raise


async def scan_security_vulnerabilities(
    file_path: str, base_path: str | None = None
) -> dict[str, Any]:
    """
    Scan code for security vulnerabilities using bandit and semgrep.

    This tool runs security scanners to detect common vulnerabilities and
    security issues. Results are included in the review context.

    Args:
        file_path: Path to the file or directory to scan

    Returns:
        Dictionary with security scan results:
        - bandit: Bandit results (Python only)
        - semgrep: Semgrep results (multi-language)
        - available_tools: List of tools that were available

    Raises:
        ValueError: If path is invalid
        FileNotFoundError: If file doesn't exist
    """
    logfire.info("Scanning for security vulnerabilities", file_path=file_path, base_path=base_path)

    try:
        resolved_path = resolve_file_path(file_path, base_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"File or directory not found: {file_path}")

        project_root = settings.project_root.resolve()
        results: dict[str, Any] = {
            "bandit": None,
            "semgrep": None,
            "available_tools": [],
        }

        # Determine if this is a Python file or directory
        is_python = False
        if resolved_path.is_file():
            is_python = resolved_path.suffix == ".py"
        elif resolved_path.is_dir():
            # Check if directory contains Python files
            py_files = list(resolved_path.rglob("*.py"))
            is_python = len(py_files) > 0

        # Run Bandit (Python security scanner)
        if is_python:
            try:
                # Check if bandit is available
                check_proc = await asyncio.create_subprocess_exec(
                    "bandit",
                    "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await check_proc.wait()
                if check_proc.returncode == 0:
                    results["available_tools"].append("bandit")
                    try:
                        # Run bandit with JSON output
                        target = str(resolved_path)
                        stdout, stderr, return_code = await _run_security_tool(
                            [
                                "bandit",
                                "-r",
                                target,
                                "-f",
                                "json",
                                "-ll",  # Low confidence, low severity (show all)
                            ],
                            cwd=project_root,
                            timeout=180.0,
                        )
                        # Parse JSON output
                        try:
                            bandit_results = json.loads(stdout) if stdout.strip() else {}
                            results["bandit"] = {
                                "results": bandit_results,
                                "return_code": return_code,
                                "stderr": stderr,
                            }
                        except json.JSONDecodeError:
                            # Fallback to text output
                            results["bandit"] = {
                                "output": stdout,
                                "stderr": stderr,
                                "return_code": return_code,
                            }
                    except Exception as e:
                        logfire.warning("Bandit scan failed", error=str(e))
                        results["bandit"] = {"error": str(e)}
            except Exception:
                # Bandit not available
                pass

        # Run Semgrep (multi-language security scanner)
        try:
            # Check if semgrep is available
            check_proc = await asyncio.create_subprocess_exec(
                "semgrep",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await check_proc.wait()
            if check_proc.returncode == 0:
                results["available_tools"].append("semgrep")
                try:
                    target = str(resolved_path)
                    stdout, stderr, return_code = await _run_security_tool(
                        [
                            "semgrep",
                            "--json",
                            "--quiet",
                            "--config=auto",  # Use auto config for security rules
                            target,
                        ],
                        cwd=project_root,
                        timeout=180.0,
                    )
                    # Parse JSON output
                    try:
                        semgrep_results = json.loads(stdout) if stdout.strip() else {}
                        results["semgrep"] = {
                            "results": semgrep_results,
                            "return_code": return_code,
                            "stderr": stderr,
                        }
                    except json.JSONDecodeError:
                        # Fallback to text output
                        results["semgrep"] = {
                            "output": stdout,
                            "stderr": stderr,
                            "return_code": return_code,
                        }
                except Exception as e:
                    logfire.warning("Semgrep scan failed", error=str(e))
                    results["semgrep"] = {"error": str(e)}
        except Exception:
            # Semgrep not available
            pass

        logfire.info(
            "Security scan completed",
            file_path=file_path,
            tools=results["available_tools"],
        )
        return results

    except Exception as e:
        logfire.error("Security scan failed", file_path=file_path, error=str(e))
        raise
