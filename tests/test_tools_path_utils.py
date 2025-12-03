"""Tests for path_utils module."""

import pytest

from council.tools.path_utils import (
    _is_safe_path,
    _search_project_recursive,
    _try_resolve_relative,
    _validate_and_resolve_candidate,
    resolve_file_path,
)


class TestIsSafePath:
    """Tests for _is_safe_path function."""

    def test_safe_path_in_allowed_root(self, mock_settings):
        """Test path within allowed root is safe."""
        allowed_roots = {mock_settings.project_root.resolve()}
        test_path = mock_settings.project_root / "test.py"
        test_path.touch()

        assert _is_safe_path(test_path, allowed_roots) is True

    def test_path_with_traversal(self, mock_settings):
        """Test path with traversal attempt is not safe."""
        allowed_roots = {mock_settings.project_root.resolve()}
        test_path = mock_settings.project_root / ".." / "outside.py"

        assert _is_safe_path(test_path, allowed_roots) is False

    def test_path_outside_allowed_root(self, mock_settings, tmp_path):
        """Test path outside allowed root is not safe."""
        allowed_roots = {mock_settings.project_root.resolve()}
        outside_path = tmp_path / "outside.py"
        outside_path.touch()

        assert _is_safe_path(outside_path, allowed_roots) is False


class TestValidateAndResolveCandidate:
    """Tests for _validate_and_resolve_candidate function."""

    def test_valid_existing_candidate(self, mock_settings):
        """Test valid existing candidate is resolved."""
        allowed_roots = {mock_settings.project_root.resolve()}
        test_file = mock_settings.project_root / "test.py"
        test_file.touch()

        result = _validate_and_resolve_candidate(test_file, allowed_roots)
        assert result == test_file.resolve()

    def test_nonexistent_candidate(self, mock_settings):
        """Test nonexistent candidate returns None."""
        allowed_roots = {mock_settings.project_root.resolve()}
        test_file = mock_settings.project_root / "nonexistent.py"

        result = _validate_and_resolve_candidate(test_file, allowed_roots)
        assert result is None

    def test_unsafe_candidate(self, mock_settings, tmp_path):
        """Test unsafe candidate returns None."""
        allowed_roots = {mock_settings.project_root.resolve()}
        outside_file = tmp_path / "outside.py"
        outside_file.touch()

        result = _validate_and_resolve_candidate(outside_file, allowed_roots)
        assert result is None


class TestTryResolveRelative:
    """Tests for _try_resolve_relative function."""

    def test_resolve_relative_to_project_root(self, mock_settings):
        """Test resolving relative to project root."""
        allowed_roots = {mock_settings.project_root.resolve()}
        test_file = mock_settings.project_root / "test.py"
        test_file.touch()

        candidates = _try_resolve_relative("test.py", None, allowed_roots)
        assert len(candidates) > 0
        assert test_file.resolve() in candidates

    def test_resolve_relative_to_base_path(self, mock_settings):
        """Test resolving relative to base path."""
        allowed_roots = {mock_settings.project_root.resolve()}
        subdir = mock_settings.project_root / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.py"
        test_file.touch()

        candidates = _try_resolve_relative("test.py", str(subdir), allowed_roots)
        assert len(candidates) > 0
        assert test_file.resolve() in candidates

    def test_no_candidates_for_nonexistent_file(self, mock_settings):
        """Test no candidates returned for nonexistent file."""
        allowed_roots = {mock_settings.project_root.resolve()}

        candidates = _try_resolve_relative("nonexistent.py", None, allowed_roots)
        assert len(candidates) == 0


class TestSearchProjectRecursive:
    """Tests for _search_project_recursive function."""

    def test_find_file_in_subdirectory(self, mock_settings):
        """Test finding file in subdirectory."""
        allowed_roots = {mock_settings.project_root.resolve()}
        subdir = mock_settings.project_root / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.py"
        test_file.touch()

        result = _search_project_recursive("test.py", allowed_roots)
        assert result == test_file.resolve()

    def test_find_closest_match(self, mock_settings):
        """Test finding closest match to root."""
        allowed_roots = {mock_settings.project_root.resolve()}
        # Create file at root level
        root_file = mock_settings.project_root / "test.py"
        root_file.touch()
        # Create file in subdirectory
        subdir = mock_settings.project_root / "subdir"
        subdir.mkdir()
        subdir_file = subdir / "test.py"
        subdir_file.touch()

        result = _search_project_recursive("test.py", allowed_roots)
        # Should return the one closest to root
        assert result == root_file.resolve()

    def test_no_match_for_nonexistent_file(self, mock_settings):
        """Test no match for nonexistent file."""
        allowed_roots = {mock_settings.project_root.resolve()}

        result = _search_project_recursive("nonexistent.py", allowed_roots)
        assert result is None

    def test_skip_paths_with_separators(self, mock_settings):
        """Test that paths with separators are skipped."""
        allowed_roots = {mock_settings.project_root.resolve()}

        result = _search_project_recursive("subdir/test.py", allowed_roots)
        assert result is None


class TestResolveFilePath:
    """Tests for resolve_file_path function."""

    def test_resolve_absolute_path(self, mock_settings):
        """Test resolving absolute path."""
        test_file = mock_settings.project_root / "test.py"
        test_file.touch()

        result = resolve_file_path(str(test_file.resolve()))
        assert result == test_file.resolve()

    def test_resolve_relative_path(self, mock_settings):
        """Test resolving relative path."""
        test_file = mock_settings.project_root / "test.py"
        test_file.touch()

        result = resolve_file_path("test.py")
        assert result == test_file.resolve()

    def test_resolve_with_base_path(self, mock_settings):
        """Test resolving with base path."""
        subdir = mock_settings.project_root / "subdir"
        subdir.mkdir()
        test_file = subdir / "test.py"
        test_file.touch()

        result = resolve_file_path("test.py", base_path=str(subdir))
        assert result == test_file.resolve()

    def test_resolve_filename_recursive(self, mock_settings):
        """Test resolving filename recursively."""
        subdir = mock_settings.project_root / "subdir"
        subdir.mkdir()
        test_file = subdir / "unique.py"
        test_file.touch()

        result = resolve_file_path("unique.py")
        assert result == test_file.resolve()

    def test_invalid_type(self):
        """Test invalid type raises TypeError."""
        with pytest.raises(TypeError, match="file_path must be a string"):
            resolve_file_path(123)

    def test_empty_path(self):
        """Test empty path raises ValueError."""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            resolve_file_path("")

        with pytest.raises(ValueError, match="file_path cannot be empty"):
            resolve_file_path("   ")

    def test_path_too_long(self):
        """Test path exceeding max length raises ValueError."""
        long_path = "a/" * 2500  # > 4096 chars
        with pytest.raises(ValueError, match="Path exceeds maximum length"):
            resolve_file_path(long_path)

    def test_absolute_path_outside_allowed(self, tmp_path):
        """Test absolute path outside allowed directories raises ValueError."""
        outside_file = tmp_path / "outside.py"
        outside_file.touch()

        with pytest.raises(ValueError, match="Absolute path outside allowed directories"):
            resolve_file_path(str(outside_file.resolve()))

    def test_nonexistent_file_creates_safe_path(self, mock_settings):
        """Test nonexistent file creates safe path candidate."""
        result = resolve_file_path("new_file.py")
        assert result == (mock_settings.project_root / "new_file.py").resolve()

    def test_nonexistent_file_with_base_path(self, mock_settings):
        """Test nonexistent file with base path creates safe path."""
        subdir = mock_settings.project_root / "subdir"
        subdir.mkdir()

        result = resolve_file_path("new_file.py", base_path=str(subdir))
        assert result == (subdir / "new_file.py").resolve()
