"""Tests for persistence layer."""

import json

from council.tools.persistence import (
    ReviewHistory,
    ReviewRecord,
    get_review_history,
)


class TestReviewRecord:
    """Test ReviewRecord dataclass."""

    def test_review_record_creation(self):
        """Test creating a ReviewRecord."""
        record = ReviewRecord(
            review_id="test-123",
            file_path="test.py",
            timestamp="2024-01-01T00:00:00",
            duration_seconds=1.5,
            success=True,
            error_type=None,
            issues_found=3,
            severity="medium",
            context_size_bytes=1000,
            token_usage={"input": 100, "output": 50},
        )
        assert record.review_id == "test-123"
        assert record.file_path == "test.py"
        assert record.success is True

    def test_review_record_from_dict(self):
        """Test creating ReviewRecord from dictionary."""
        data = {
            "review_id": "test-456",
            "file_path": "test2.py",
            "timestamp": "2024-01-02T00:00:00",
            "duration_seconds": 2.0,
            "success": False,
            "error_type": "TimeoutError",
            "issues_found": 0,
            "severity": None,
            "context_size_bytes": 500,
            "token_usage": {},
        }
        record = ReviewRecord.from_dict(data)
        assert record.review_id == "test-456"
        assert record.success is False
        assert record.error_type == "TimeoutError"

    def test_review_record_to_dict(self):
        """Test converting ReviewRecord to dictionary."""
        record = ReviewRecord(
            review_id="test-789",
            file_path="test3.py",
            timestamp="2024-01-03T00:00:00",
            duration_seconds=0.5,
            success=True,
            error_type=None,
            issues_found=5,
            severity="high",
            context_size_bytes=2000,
            token_usage={"input": 200},
            summary="Test summary",
            metadata={"key": "value"},
        )
        data = record.to_dict()
        assert isinstance(data, dict)
        assert data["review_id"] == "test-789"
        assert data["summary"] == "Test summary"
        assert data["metadata"]["key"] == "value"


class TestReviewHistory:
    """Test ReviewHistory class."""

    def test_review_history_initialization(self, tmp_path):
        """Test ReviewHistory initialization."""
        storage_dir = tmp_path / "history"
        history = ReviewHistory(storage_dir=storage_dir)
        assert history.storage_dir == storage_dir
        assert storage_dir.exists()

    def test_review_history_default_storage(self):
        """Test ReviewHistory uses default storage directory."""
        history = ReviewHistory()
        assert ".council" in str(history.storage_dir)
        assert "history" in str(history.storage_dir)

    def test_save_review(self, tmp_path):
        """Test saving a review record."""
        storage_dir = tmp_path / "history"
        history = ReviewHistory(storage_dir=storage_dir)

        record = ReviewRecord(
            review_id="save-test",
            file_path="test.py",
            timestamp="2024-01-01T00:00:00",
            duration_seconds=1.0,
            success=True,
            error_type=None,
            issues_found=2,
            severity="low",
            context_size_bytes=500,
            token_usage={},
        )

        history.save_review(record)

        # Verify file was created
        files = list(storage_dir.glob("save-test_*.json"))
        assert len(files) == 1
        assert files[0].exists()

        # Verify content
        data = json.loads(files[0].read_text())
        assert data["review_id"] == "save-test"

    def test_load_review(self, tmp_path):
        """Test loading a review record."""
        storage_dir = tmp_path / "history"
        history = ReviewHistory(storage_dir=storage_dir)

        record = ReviewRecord(
            review_id="load-test",
            file_path="test.py",
            timestamp="2024-01-01T00:00:00",
            duration_seconds=1.0,
            success=True,
            error_type=None,
            issues_found=1,
            severity="medium",
            context_size_bytes=1000,
            token_usage={},
        )

        history.save_review(record)
        loaded = history.load_review("load-test")

        assert loaded is not None
        assert loaded.review_id == "load-test"
        assert loaded.file_path == "test.py"

    def test_load_review_nonexistent(self, tmp_path):
        """Test loading nonexistent review."""
        storage_dir = tmp_path / "history"
        history = ReviewHistory(storage_dir=storage_dir)

        loaded = history.load_review("nonexistent")
        assert loaded is None

    def test_list_reviews(self, tmp_path):
        """Test listing reviews."""
        storage_dir = tmp_path / "history"
        history = ReviewHistory(storage_dir=storage_dir)

        # Create multiple reviews
        for i in range(5):
            record = ReviewRecord(
                review_id=f"list-test-{i}",
                file_path=f"test{i}.py",
                timestamp=f"2024-01-0{i + 1}T00:00:00",
                duration_seconds=1.0,
                success=True,
                error_type=None,
                issues_found=i,
                severity="low",
                context_size_bytes=1000,
                token_usage={},
            )
            history.save_review(record)

        reviews = history.list_reviews()
        assert len(reviews) == 5

    def test_list_reviews_with_limit(self, tmp_path):
        """Test listing reviews with limit."""
        storage_dir = tmp_path / "history"
        history = ReviewHistory(storage_dir=storage_dir)

        # Create more reviews than limit
        for i in range(10):
            record = ReviewRecord(
                review_id=f"limit-test-{i}",
                file_path=f"test{i}.py",
                timestamp=f"2024-01-0{i + 1}T00:00:00",
                duration_seconds=1.0,
                success=True,
                error_type=None,
                issues_found=0,
                severity="low",
                context_size_bytes=1000,
                token_usage={},
            )
            history.save_review(record)

        reviews = history.list_reviews(limit=5)
        assert len(reviews) <= 5

    def test_list_reviews_filter_by_file(self, tmp_path):
        """Test listing reviews filtered by file path."""
        storage_dir = tmp_path / "history"
        history = ReviewHistory(storage_dir=storage_dir)

        # Create reviews for different files
        for i in range(3):
            record = ReviewRecord(
                review_id=f"filter-test-{i}",
                file_path="target.py" if i == 1 else f"other{i}.py",
                timestamp=f"2024-01-0{i + 1}T00:00:00",
                duration_seconds=1.0,
                success=True,
                error_type=None,
                issues_found=0,
                severity="low",
                context_size_bytes=1000,
                token_usage={},
            )
            history.save_review(record)

        reviews = history.list_reviews(file_path="target.py")
        assert len(reviews) == 1
        assert reviews[0].file_path == "target.py"

    def test_get_review_history_for_file(self, tmp_path):
        """Test getting review history for specific file."""
        storage_dir = tmp_path / "history"
        history = ReviewHistory(storage_dir=storage_dir)

        # Create multiple reviews for same file
        for i in range(3):
            record = ReviewRecord(
                review_id=f"history-test-{i}",
                file_path="history.py",
                timestamp=f"2024-01-0{i + 1}T00:00:00",
                duration_seconds=1.0,
                success=True,
                error_type=None,
                issues_found=i,
                severity="low",
                context_size_bytes=1000,
                token_usage={},
            )
            history.save_review(record)

        history_list = history.get_review_history_for_file("history.py")
        assert len(history_list) == 3
        assert all(r.file_path == "history.py" for r in history_list)

    def test_save_review_error_handling(self, tmp_path):
        """Test error handling when saving fails."""
        storage_dir = tmp_path / "history"
        history = ReviewHistory(storage_dir=storage_dir)

        # Create invalid record (missing required fields)
        # This should not raise, but log error
        record = ReviewRecord(
            review_id="error-test",
            file_path="test.py",
            timestamp="2024-01-01T00:00:00",
            duration_seconds=1.0,
            success=True,
            error_type=None,
            issues_found=0,
            severity=None,
            context_size_bytes=0,
            token_usage={},
        )

        # Should not raise even if there's an issue
        history.save_review(record)

    def test_load_review_error_handling(self, tmp_path):
        """Test error handling when loading fails."""
        storage_dir = tmp_path / "history"
        history = ReviewHistory(storage_dir=storage_dir)

        # Create invalid JSON file
        invalid_file = storage_dir / "invalid_review.json"
        invalid_file.write_text("invalid json content")

        # Should return None instead of raising
        loaded = history.load_review("invalid_review")
        assert loaded is None


class TestGetReviewHistory:
    """Test get_review_history function."""

    def test_get_review_history_singleton(self):
        """Test that get_review_history returns singleton."""
        history1 = get_review_history()
        history2 = get_review_history()
        assert history1 is history2

    def test_get_review_history_creates_default(self):
        """Test that get_review_history creates default instance."""
        history = get_review_history()
        assert isinstance(history, ReviewHistory)
        assert history.storage_dir.exists()
