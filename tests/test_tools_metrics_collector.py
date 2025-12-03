"""Tests for metrics collector."""

import time
from unittest.mock import patch

import pytest

from council.tools.metrics_collector import (
    MetricsCollector,
    ReviewMetrics,
    get_metrics_collector,
)


class TestReviewMetrics:
    """Test ReviewMetrics dataclass."""

    def test_review_metrics_creation(self):
        """Test creating ReviewMetrics."""
        metrics = ReviewMetrics(
            review_id="test-123",
            file_path="test.py",
            start_time=time.time(),
        )
        assert metrics.review_id == "test-123"
        assert metrics.file_path == "test.py"
        assert metrics.success is False
        assert metrics.end_time is None

    def test_review_metrics_finish(self):
        """Test finishing a review."""
        start = time.time()
        metrics = ReviewMetrics(
            review_id="test-456",
            file_path="test.py",
            start_time=start,
        )

        with patch("time.time", return_value=start + 1.5):
            metrics.finish(success=True)

        assert metrics.end_time == start + 1.5
        assert metrics.duration_seconds == 1.5
        assert metrics.success is True

    def test_review_metrics_finish_with_error(self):
        """Test finishing a review with error."""
        start = time.time()
        metrics = ReviewMetrics(
            review_id="test-789",
            file_path="test.py",
            start_time=start,
        )

        with patch("time.time", return_value=start + 2.0):
            metrics.finish(success=False, error_type="TimeoutError")

        assert metrics.success is False
        assert metrics.error_type == "TimeoutError"
        assert metrics.duration_seconds == 2.0


class TestMetricsCollector:
    """Test MetricsCollector class."""

    def test_collector_initialization(self):
        """Test MetricsCollector initialization."""
        collector = MetricsCollector()
        assert collector._reviews == {}
        assert collector._tool_stats == {}

    def test_start_review(self):
        """Test starting a review."""
        collector = MetricsCollector()
        metrics = collector.start_review("review-1", "test.py")

        assert isinstance(metrics, ReviewMetrics)
        assert metrics.review_id == "review-1"
        assert metrics.file_path == "test.py"
        assert "review-1" in collector._reviews

    def test_finish_review_success(self):
        """Test finishing a successful review."""
        collector = MetricsCollector()
        collector.start_review("review-1", "test.py")

        collector.finish_review(
            review_id="review-1",
            success=True,
            issues_found=3,
            severity="medium",
            context_size_bytes=1000,
            token_usage={"input": 100, "output": 50},
        )

        metrics = collector.get_review_metrics("review-1")
        assert metrics is not None
        assert metrics.success is True
        assert metrics.issues_found == 3
        assert metrics.severity == "medium"
        assert metrics.context_size_bytes == 1000
        assert metrics.token_usage == {"input": 100, "output": 50}

    def test_finish_review_failure(self):
        """Test finishing a failed review."""
        collector = MetricsCollector()
        collector.start_review("review-2", "test.py")

        collector.finish_review(
            review_id="review-2",
            success=False,
            error_type="TimeoutError",
        )

        metrics = collector.get_review_metrics("review-2")
        assert metrics is not None
        assert metrics.success is False
        assert metrics.error_type == "TimeoutError"

    def test_finish_review_nonexistent(self):
        """Test finishing nonexistent review."""
        collector = MetricsCollector()
        # Should not raise, just log warning
        collector.finish_review("nonexistent", success=True)

    def test_record_tool_execution_success(self):
        """Test recording successful tool execution."""
        collector = MetricsCollector()
        collector.record_tool_execution("test_tool", duration_seconds=1.5, success=True)

        stats = collector.get_tool_stats("test_tool")
        assert stats["count"] == 1
        assert stats["success_count"] == 1
        assert stats["failure_count"] == 0
        assert stats["total_duration"] == 1.5

    def test_record_tool_execution_failure(self):
        """Test recording failed tool execution."""
        collector = MetricsCollector()
        collector.record_tool_execution(
            "test_tool", duration_seconds=0.5, success=False, error_type="ValueError"
        )

        stats = collector.get_tool_stats("test_tool")
        assert stats["count"] == 1
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 1
        assert stats["errors"]["ValueError"] == 1

    def test_record_tool_execution_multiple(self):
        """Test recording multiple tool executions."""
        collector = MetricsCollector()
        collector.record_tool_execution("tool1", duration_seconds=1.0, success=True)
        collector.record_tool_execution("tool1", duration_seconds=2.0, success=True)
        collector.record_tool_execution("tool1", duration_seconds=0.5, success=False)

        stats = collector.get_tool_stats("tool1")
        assert stats["count"] == 3
        assert stats["success_count"] == 2
        assert stats["failure_count"] == 1
        assert stats["total_duration"] == 3.5

    def test_get_review_metrics(self):
        """Test getting review metrics."""
        collector = MetricsCollector()
        collector.start_review("review-3", "test.py")

        metrics = collector.get_review_metrics("review-3")
        assert metrics is not None
        assert metrics.review_id == "review-3"

        # Nonexistent review
        assert collector.get_review_metrics("nonexistent") is None

    def test_get_tool_stats_all(self):
        """Test getting stats for all tools."""
        collector = MetricsCollector()
        collector.record_tool_execution("tool1", duration_seconds=1.0, success=True)
        collector.record_tool_execution("tool2", duration_seconds=2.0, success=True)

        all_stats = collector.get_tool_stats()
        assert "tool1" in all_stats
        assert "tool2" in all_stats

    def test_get_tool_stats_specific(self):
        """Test getting stats for specific tool."""
        collector = MetricsCollector()
        collector.record_tool_execution("tool1", duration_seconds=1.0, success=True)
        collector.record_tool_execution("tool2", duration_seconds=2.0, success=True)

        stats = collector.get_tool_stats("tool1")
        assert stats["count"] == 1
        assert stats["total_duration"] == 1.0

        # Nonexistent tool
        stats = collector.get_tool_stats("nonexistent")
        assert stats == {}

    def test_get_summary_no_reviews(self):
        """Test summary with no reviews."""
        collector = MetricsCollector()
        summary = collector.get_summary()

        assert summary["total_reviews"] == 0
        assert summary["successful_reviews"] == 0
        assert summary["failed_reviews"] == 0
        assert summary["success_rate"] == 0.0

    def test_get_summary_with_reviews(self):
        """Test summary with completed reviews."""
        collector = MetricsCollector()

        # Start and finish multiple reviews
        collector.start_review("review-1", "test1.py")
        collector.finish_review("review-1", success=True, issues_found=1)

        collector.start_review("review-2", "test2.py")
        collector.finish_review("review-2", success=True, issues_found=2)

        collector.start_review("review-3", "test3.py")
        collector.finish_review("review-3", success=False, error_type="Error")

        summary = collector.get_summary()
        assert summary["total_reviews"] == 3
        assert summary["successful_reviews"] == 2
        assert summary["failed_reviews"] == 1
        assert summary["success_rate"] == pytest.approx(2 / 3, rel=0.1)
        assert summary["average_duration_seconds"] > 0
        assert "tool_stats" in summary

    def test_get_summary_incomplete_reviews(self):
        """Test summary excludes incomplete reviews."""
        collector = MetricsCollector()

        collector.start_review("review-1", "test1.py")
        collector.finish_review("review-1", success=True)

        collector.start_review("review-2", "test2.py")
        # Don't finish this one

        summary = collector.get_summary()
        # Only completed reviews should be counted
        assert summary["total_reviews"] == 1


class TestGetMetricsCollector:
    """Test get_metrics_collector function."""

    def test_get_metrics_collector_singleton(self):
        """Test that get_metrics_collector returns singleton."""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()
        assert collector1 is collector2

    def test_get_metrics_collector_creates_instance(self):
        """Test that get_metrics_collector creates instance."""
        collector = get_metrics_collector()
        assert isinstance(collector, MetricsCollector)
