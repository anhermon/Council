"""Git integration tools for incremental reviews and change analysis."""

from pathlib import Path
from typing import Any

import logfire

from ..config import get_settings
from .path_utils import resolve_file_path
from .utils import run_command_safely

settings = get_settings()

# Maximum number of history entries
MAX_HISTORY_LIMIT = 100


async def _run_git_command(
    cmd: list[str], cwd: Path | None = None, timeout: float | None = None
) -> tuple[str, str]:
    """
    Run a git command and return stdout/stderr.

    Args:
        cmd: Git command as list of strings
        cwd: Working directory for command
        timeout: Command timeout in seconds

    Returns:
        Tuple of (stdout, stderr)

    Raises:
        RuntimeError: If git command fails
        TimeoutError: If command times out
        ValueError: If output exceeds maximum size
    """
    if timeout is None:
        timeout = settings.git_timeout

    stdout_text, stderr_text, return_code = await run_command_safely(
        cmd,
        cwd=cwd,
        timeout=timeout,
        max_output_size=settings.max_output_size,
        check=True,
    )
    return stdout_text, stderr_text


async def get_git_diff(file_path: str, base_ref: str = "HEAD", base_path: str | None = None) -> str:
    """
    Get git diff for a file to review only changed lines.

    This tool retrieves the git diff for a file, showing what has changed
    compared to a base reference (default: HEAD). This enables incremental
    reviews focusing only on modified code.

    Args:
        file_path: Path to the file
        base_ref: Git reference to compare against (default: "HEAD")

    Returns:
        Git diff output as string

    Raises:
        ValueError: If path is invalid
        RuntimeError: If git command fails
        FileNotFoundError: If file doesn't exist in git
    """
    logfire.info("Getting git diff", file_path=file_path, base_ref=base_ref, base_path=base_path)

    try:
        resolved_path = resolve_file_path(file_path, base_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Get relative path from git root
        project_root = settings.project_root.resolve()
        try:
            if resolved_path.is_relative_to(project_root):
                rel_path = str(resolved_path.relative_to(project_root))
            else:
                rel_path = str(resolved_path)
        except AttributeError:
            # Python < 3.9 fallback
            resolved_str = str(resolved_path)
            project_root_str = str(project_root)
            rel_path = resolved_str.replace(project_root_str + "/", "")

        # Check if file is tracked in git
        try:
            stdout, _ = await _run_git_command(
                ["git", "ls-files", "--error-unmatch", rel_path],
                cwd=project_root,
            )
        except RuntimeError:
            # File not tracked in git
            return f"File {rel_path} is not tracked in git repository"

        # Get diff
        try:
            diff_output, _ = await _run_git_command(
                ["git", "diff", base_ref, "--", rel_path],
                cwd=project_root,
                timeout=settings.test_timeout,  # Use test_timeout for git diff operations
            )
        except RuntimeError as e:
            # No changes or error
            if "no changes" in str(e).lower() or "exit code 0" in str(e).lower():
                return f"No changes in {rel_path} compared to {base_ref}"
            raise

        if not diff_output.strip():
            return f"No changes in {rel_path} compared to {base_ref}"

        logfire.info("Git diff retrieved", file_path=file_path, size=len(diff_output))
        return diff_output

    except (ValueError, FileNotFoundError, RuntimeError, TimeoutError) as e:
        # Re-raise specific exceptions as-is
        logfire.error("Failed to get git diff", file_path=file_path, error=str(e))
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logfire.error("Failed to get git diff unexpectedly", file_path=file_path, error=str(e))
        raise RuntimeError(f"Failed to get git diff: {str(e)}") from e


async def get_uncommitted_files() -> list[str]:
    """
    Get list of uncommitted files (both staged and unstaged).

    Returns:
        List of relative file paths that have uncommitted changes

    Raises:
        RuntimeError: If git command fails
    """
    logfire.info("Getting uncommitted files")

    try:
        project_root = settings.project_root.resolve()

        # Get both staged and unstaged files
        # Use git diff --name-only to get unstaged changes
        # Use git diff --cached --name-only to get staged changes
        uncommitted_files: set[str] = set()

        # Get unstaged files
        try:
            stdout, _ = await _run_git_command(
                ["git", "diff", "--name-only"],
                cwd=project_root,
                timeout=30.0,
            )
            if stdout.strip():
                uncommitted_files.update(stdout.strip().split("\n"))
        except RuntimeError as e:
            # Re-raise if it's a real error (not just "no changes")
            if "no changes" not in str(e).lower() and "exit code 0" not in str(e).lower():
                raise
            # No unstaged changes - continue
            pass

        # Get staged files
        try:
            stdout, _ = await _run_git_command(
                ["git", "diff", "--cached", "--name-only"],
                cwd=project_root,
                timeout=30.0,
            )
            if stdout.strip():
                uncommitted_files.update(stdout.strip().split("\n"))
        except RuntimeError as e:
            # Re-raise if it's a real error (not just "no changes")
            if "no changes" not in str(e).lower() and "exit code 0" not in str(e).lower():
                raise
            # No staged changes - continue
            pass

        # Also get untracked files
        try:
            stdout, _ = await _run_git_command(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=project_root,
                timeout=30.0,
            )
            if stdout.strip():
                uncommitted_files.update(stdout.strip().split("\n"))
        except RuntimeError:
            # Error getting untracked files - continue
            pass

        result = sorted([f for f in uncommitted_files if f.strip()])
        logfire.info("Uncommitted files retrieved", count=len(result))
        return result

    except (RuntimeError, TimeoutError) as e:
        # Re-raise specific exceptions as-is
        logfire.error("Failed to get uncommitted files", error=str(e))
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logfire.error("Failed to get uncommitted files unexpectedly", error=str(e))
        raise RuntimeError(f"Failed to get uncommitted files: {str(e)}") from e


async def get_file_history(
    file_path: str, limit: int = 10, base_path: str | None = None
) -> list[dict[str, Any]]:
    """
    Get git history for a file to understand change context.

    This tool retrieves the commit history for a file, showing recent changes
    and commit messages. This helps understand the evolution of code and
    provides context for reviews.

    Args:
        file_path: Path to the file
        limit: Maximum number of history entries to return (default: 10, max: 100)

    Returns:
        List of dictionaries with commit information:
        - hash: Commit hash
        - author: Author name
        - date: Commit date
        - message: Commit message
        - changes: Number of lines changed

    Raises:
        ValueError: If path is invalid or limit is out of range
        RuntimeError: If git command fails
    """
    logfire.info("Getting file history", file_path=file_path, limit=limit, base_path=base_path)

    if limit < 1 or limit > MAX_HISTORY_LIMIT:
        raise ValueError(f"Limit must be between 1 and {MAX_HISTORY_LIMIT}")

    try:
        resolved_path = resolve_file_path(file_path, base_path)

        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Get relative path from git root
        project_root = settings.project_root.resolve()
        try:
            if resolved_path.is_relative_to(project_root):
                rel_path = str(resolved_path.relative_to(project_root))
            else:
                rel_path = str(resolved_path)
        except AttributeError:
            # Python < 3.9 fallback
            resolved_str = str(resolved_path)
            project_root_str = str(project_root)
            rel_path = resolved_str.replace(project_root_str + "/", "")

        # Get commit history
        try:
            stdout, _ = await _run_git_command(
                [
                    "git",
                    "log",
                    f"-{limit}",
                    "--pretty=format:%H|%an|%ad|%s|%N",
                    "--date=iso",
                    "--",
                    rel_path,
                ],
                cwd=project_root,
                timeout=60.0,
            )
        except RuntimeError:
            # File not tracked or no history
            return []

        if not stdout.strip():
            return []

        # Parse commit history (respect limit)
        history: list[dict[str, Any]] = []
        lines = stdout.strip().split("\n")
        for line in lines[:limit]:  # Respect the limit
            if not line.strip():
                continue

            parts = line.split("|", 4)
            if len(parts) >= 4:
                commit_hash = parts[0]
                author = parts[1]
                date = parts[2]
                message = parts[3] if len(parts) > 3 else ""
                notes = parts[4] if len(parts) > 4 else ""

                # Get number of changes in this commit
                try:
                    changes_stdout, _ = await _run_git_command(
                        ["git", "show", "--stat", "--format=", commit_hash, "--", rel_path],
                        cwd=project_root,
                        timeout=30.0,
                    )
                    # Parse stat output to get line changes
                    changes = 0
                    for stat_line in changes_stdout.split("\n"):
                        if rel_path in stat_line and "|" in stat_line:
                            # Extract number from "X files changed, Y insertions(+), Z deletions(-)"
                            import re

                            match = re.search(r"(\d+)\s+insertions", stat_line)
                            if match:
                                changes += int(match.group(1))
                            match = re.search(r"(\d+)\s+deletions", stat_line)
                            if match:
                                changes += int(match.group(1))
                except Exception:
                    changes = 0

                history.append(
                    {
                        "hash": commit_hash[:8],  # Short hash
                        "author": author,
                        "date": date,
                        "message": message,
                        "notes": notes,
                        "changes": changes,
                    }
                )

        logfire.info("File history retrieved", file_path=file_path, entries=len(history))
        return history

    except (ValueError, FileNotFoundError, RuntimeError, TimeoutError) as e:
        # Re-raise specific exceptions as-is
        logfire.error("Failed to get file history", file_path=file_path, error=str(e))
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logfire.error("Failed to get file history unexpectedly", file_path=file_path, error=str(e))
        raise RuntimeError(f"Failed to get file history: {str(e)}") from e
