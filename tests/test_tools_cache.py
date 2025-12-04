"""Tests for cache functionality."""

import json

import pytest

from council.tools.cache import (
    cache_review,
    calculate_file_hash,
    clear_cache,
    get_cache_dir,
    get_cache_key,
    get_cache_path,
    get_cached_review,
)


class TestGetCacheDir:
    """Test get_cache_dir function."""

    def test_get_cache_dir(self):
        """Test cache directory creation."""
        cache_dir = get_cache_dir()
        assert cache_dir.exists()
        assert cache_dir.is_dir()
        assert cache_dir.name == "cache"
        assert ".council" in str(cache_dir)


class TestCalculateFileHash:
    """Test calculate_file_hash function."""

    def test_calculate_hash(self, tmp_path):
        """Test hash calculation for a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        hash1 = calculate_file_hash(test_file)
        assert len(hash1) == 64  # SHA256 hex length
        assert isinstance(hash1, str)

    def test_hash_consistency(self, tmp_path):
        """Test hash is consistent for same content."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        hash1 = calculate_file_hash(test_file)
        hash2 = calculate_file_hash(test_file)
        assert hash1 == hash2

    def test_hash_different_content(self, tmp_path):
        """Test hash differs for different content."""
        file1 = tmp_path / "test1.txt"
        file1.write_text("content 1")
        file2 = tmp_path / "test2.txt"
        file2.write_text("content 2")
        hash1 = calculate_file_hash(file1)
        hash2 = calculate_file_hash(file2)
        assert hash1 != hash2

    def test_hash_nonexistent_file(self, tmp_path):
        """Test hash calculation handles errors gracefully."""
        nonexistent = tmp_path / "nonexistent.txt"
        # The function will raise FileNotFoundError for nonexistent files
        # as it tries to stat the file in the fallback
        with pytest.raises(FileNotFoundError):
            calculate_file_hash(nonexistent)


class TestGetCacheKey:
    """Test get_cache_key function."""

    def test_cache_key_basic(self, tmp_path):
        """Test basic cache key generation."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")
        key = get_cache_key(str(test_file))
        assert isinstance(key, str)
        assert len(key) == 64  # SHA256 hex length

    def test_cache_key_with_model(self, tmp_path):
        """Test cache key with model name."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")
        key1 = get_cache_key(str(test_file), model_name="gpt-4")
        key2 = get_cache_key(str(test_file), model_name="claude-3")
        assert key1 != key2

    def test_cache_key_consistency(self, tmp_path):
        """Test cache key is consistent for same inputs."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")
        key1 = get_cache_key(str(test_file), model_name="gpt-4")
        key2 = get_cache_key(str(test_file), model_name="gpt-4")
        assert key1 == key2


class TestGetCachePath:
    """Test get_cache_path function."""

    def test_cache_path(self):
        """Test cache path generation."""
        cache_key = "a" * 64  # 64 char hash
        cache_path = get_cache_path(cache_key)
        assert cache_path.suffix == ".json"
        assert cache_path.name == f"{cache_key}.json"
        # Should be in subdirectory based on first 2 chars
        assert cache_path.parent.name == cache_key[:2]


class TestGetCachedReview:
    """Test get_cached_review function."""

    @pytest.mark.asyncio
    async def test_no_cache(self, tmp_path):
        """Test when cache doesn't exist."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")
        result = await get_cached_review(str(test_file))
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_settings):
        """Test successful cache retrieval."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")
        # First cache a result
        test_result = {"summary": "test", "issues": []}
        await cache_review(str(test_file), test_result)
        # Then retrieve it
        cached = await get_cached_review(str(test_file))
        assert cached == test_result

    @pytest.mark.asyncio
    async def test_cache_miss_on_file_change(self, mock_settings):
        """Test cache miss when file changes."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# original")
        test_result = {"summary": "test", "issues": []}
        await cache_review(str(test_file), test_result)
        # Change file content
        test_file.write_text("# modified")
        cached = await get_cached_review(str(test_file))
        assert cached is None

    @pytest.mark.asyncio
    async def test_cache_with_model(self, mock_settings):
        """Test cache with model name."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")
        result1 = {"summary": "result1"}
        result2 = {"summary": "result2"}
        await cache_review(str(test_file), result1, model_name="gpt-4")
        await cache_review(str(test_file), result2, model_name="claude-3")
        cached1 = await get_cached_review(str(test_file), model_name="gpt-4")
        cached2 = await get_cached_review(str(test_file), model_name="claude-3")
        assert cached1 == result1
        assert cached2 == result2


class TestCacheReview:
    """Test cache_review function."""

    @pytest.mark.asyncio
    async def test_cache_review(self, mock_settings):
        """Test caching a review result."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")
        result = {"summary": "test review", "issues": [{"line": 1, "message": "test"}]}
        await cache_review(str(test_file), result)
        # Verify cache file exists
        cache_key = get_cache_key(str(test_file))
        cache_path = get_cache_path(cache_key)
        assert cache_path.exists()
        # Verify content
        cache_data = json.loads(cache_path.read_text())
        assert cache_data["result"] == result
        assert cache_data["version"] == 1

    @pytest.mark.asyncio
    async def test_cache_review_with_model(self, mock_settings):
        """Test caching with model name."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")
        result = {"summary": "test"}
        await cache_review(str(test_file), result, model_name="gpt-4")
        cache_key = get_cache_key(str(test_file), model_name="gpt-4")
        cache_path = get_cache_path(cache_key)
        assert cache_path.exists()
        cache_data = json.loads(cache_path.read_text())
        assert cache_data["model_name"] == "gpt-4"


class TestClearCache:
    """Test clear_cache function."""

    @pytest.mark.asyncio
    async def test_clear_specific_file_cache(self, mock_settings):
        """Test clearing cache for specific file."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test")
        result = {"summary": "test"}
        await cache_review(str(test_file), result)
        # Clear cache
        cleared = await clear_cache(str(test_file))
        assert cleared == 1
        # Verify cache is gone
        cached = await get_cached_review(str(test_file))
        assert cached is None

    @pytest.mark.asyncio
    async def test_clear_all_cache(self, mock_settings):
        """Test clearing all cache."""
        # Create multiple cached files
        for i in range(3):
            test_file = mock_settings.project_root / f"test{i}.py"
            test_file.write_text(f"# test {i}")
            await cache_review(str(test_file), {"summary": f"test {i}"})
        # Clear all
        cleared = await clear_cache()
        assert cleared >= 3
