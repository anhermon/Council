"""Integration tests for end-to-end review flow."""

from pathlib import Path

import pytest

from council.tools import PathValidationError, get_packed_context, validate_file_path


@pytest.fixture
def temp_repo(mock_settings) -> Path:
    """Create a temporary git repository with sample code."""
    # Create repo within project root for path validation
    repo_path = mock_settings.project_root / "test_repo"
    repo_path.mkdir(exist_ok=True)

    # Initialize git repo
    import subprocess

    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create sample Python file
    sample_file = repo_path / "sample.py"
    sample_file.write_text(
        '''"""Sample Python file for testing."""

def hello_world():
    """Print hello world."""
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
'''
    )

    # Create sample test file
    test_file = repo_path / "test_sample.py"
    test_file.write_text(
        '''"""Tests for sample.py."""

def test_hello_world():
    """Test hello_world function."""
    from sample import hello_world
    hello_world()
'''
    )

    # Commit files
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    yield repo_path

    # Cleanup: remove the test repo
    import shutil

    if repo_path.exists():
        shutil.rmtree(repo_path, ignore_errors=True)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_packed_context_success(temp_repo: Path) -> None:
    """Test successful context extraction."""
    sample_file = temp_repo / "sample.py"

    # This will fail if repomix is not available, which is expected in CI
    # In that case, we skip the test
    try:
        context = await get_packed_context(str(sample_file))
        assert context is not None
        assert len(context) > 0
        # Context should contain XML
        assert "<" in context or "xml" in context.lower()
    except Exception as e:
        # If repomix is not available, skip the test
        if "repomix" in str(e).lower() or "not found" in str(e).lower():
            pytest.skip(f"Repomix not available: {e}")
        raise


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_packed_context_nonexistent_file() -> None:
    """Test context extraction with non-existent file."""
    with pytest.raises(FileNotFoundError):
        await get_packed_context("/nonexistent/file.py")


def test_validate_file_path_success(mock_settings) -> None:
    """Test successful path validation."""
    # Create file within the mock project root
    test_file = mock_settings.project_root / "test.py"
    test_file.write_text("# test")

    resolved = validate_file_path(str(test_file))
    assert resolved == test_file.resolve()


def test_validate_file_path_traversal() -> None:
    """Test path validation rejects traversal attempts."""
    with pytest.raises(PathValidationError, match="Path traversal detected"):
        validate_file_path("../../../etc/passwd")


def test_validate_file_path_too_long() -> None:
    """Test path validation rejects overly long paths."""
    long_path = "/" + "a" * 5000
    with pytest.raises(PathValidationError, match="exceeds maximum length"):
        validate_file_path(long_path)
