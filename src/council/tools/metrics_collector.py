"""Metrics collection for observability and monitoring."""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import logfire


@dataclass
class ReviewMetrics:
    """Metrics for a single code review."""

    review_id: str
    file_path: str
    start_time: float
    end_time: float | None = None
    duration_seconds: float | None = None
    success: bool = False
    error_type: str | None = None
    context_size_bytes: int = 0
    issues_found: int = 0
    severity: str | None = None
    tool_executions: dict[str, dict[str, Any]] = field(default_factory=dict)
    token_usage: dict[str, int] = field(default_factory=dict)

    def finish(self, success: bool = True, error_type: str | None = None) -> None:
        """Mark review as finished and calculate duration."""
        self.end_time = time.time()
        self.duration_seconds = self.end_time - self.start_time
        self.success = success
        self.error_type = error_type


class MetricsCollector:
    """Collects and aggregates metrics for code reviews and tool executions."""

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self._reviews: dict[str, ReviewMetrics] = {}
        self._tool_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "count": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_duration": 0.0,
                "errors": defaultdict(int),
            }
        )

    def start_review(self, review_id: str, file_path: str) -> ReviewMetrics:
        """
        Start tracking a new review.

        Args:
            review_id: Unique identifier for the review
            file_path: Path to the file being reviewed

        Returns:
            ReviewMetrics instance for tracking
        """
        metrics = ReviewMetrics(
            review_id=review_id,
            file_path=file_path,
            start_time=time.time(),
        )
        self._reviews[review_id] = metrics
        logfire.info("Review started", review_id=review_id, file_path=file_path)
        return metrics

    def finish_review(
        self,
        review_id: str,
        success: bool = True,
        error_type: str | None = None,
        issues_found: int = 0,
        severity: str | None = None,
        context_size_bytes: int = 0,
        token_usage: dict[str, int] | None = None,
    ) -> None:
        """
        Finish tracking a review.

        Args:
            review_id: Unique identifier for the review
            success: Whether the review completed successfully
            error_type: Type of error if review failed
            issues_found: Number of issues found
            severity: Overall severity assessment
            context_size_bytes: Size of context extracted
            token_usage: Token usage statistics
        """
        if review_id not in self._reviews:
            logfire.warning("Attempted to finish unknown review", review_id=review_id)
            return

        metrics = self._reviews[review_id]
        metrics.finish(success, error_type)
        metrics.issues_found = issues_found
        metrics.severity = severity
        metrics.context_size_bytes = context_size_bytes
        if token_usage:
            metrics.token_usage = token_usage

        # Log metrics
        logfire.info(
            "Review completed",
            review_id=review_id,
            success=success,
            duration_seconds=metrics.duration_seconds,
            issues_found=issues_found,
            severity=severity,
            context_size_bytes=context_size_bytes,
        )

    def record_tool_execution(
        self,
        tool_name: str,
        duration_seconds: float,
        success: bool = True,
        error_type: str | None = None,
    ) -> None:
        """
        Record a tool execution for statistics.

        Args:
            tool_name: Name of the tool executed
            duration_seconds: Duration of execution
            success: Whether execution succeeded
            error_type: Type of error if execution failed
        """
        stats = self._tool_stats[tool_name]
        stats["count"] += 1
        stats["total_duration"] += duration_seconds

        if success:
            stats["success_count"] += 1
        else:
            stats["failure_count"] += 1
            if error_type:
                stats["errors"][error_type] += 1

        logfire.debug(
            "Tool execution recorded",
            tool=tool_name,
            duration_seconds=duration_seconds,
            success=success,
        )

    def get_review_metrics(self, review_id: str) -> ReviewMetrics | None:
        """Get metrics for a specific review."""
        return self._reviews.get(review_id)

    def get_tool_stats(self, tool_name: str | None = None) -> dict[str, Any]:
        """
        Get statistics for tools.

        Args:
            tool_name: Specific tool name, or None for all tools

        Returns:
            Dictionary of tool statistics
        """
        if tool_name:
            return dict(self._tool_stats.get(tool_name, {}))
        return {name: dict(stats) for name, stats in self._tool_stats.items()}

    def get_summary(self) -> dict[str, Any]:
        """
        Get summary statistics.

        Returns:
            Dictionary with summary metrics
        """
        completed_reviews = [r for r in self._reviews.values() if r.end_time is not None]
        successful_reviews = [r for r in completed_reviews if r.success]

        total_duration = sum(r.duration_seconds or 0 for r in completed_reviews)
        avg_duration = total_duration / len(completed_reviews) if completed_reviews else 0.0

        return {
            "total_reviews": len(completed_reviews),
            "successful_reviews": len(successful_reviews),
            "failed_reviews": len(completed_reviews) - len(successful_reviews),
            "success_rate": (
                len(successful_reviews) / len(completed_reviews) if completed_reviews else 0.0
            ),
            "average_duration_seconds": avg_duration,
            "total_duration_seconds": total_duration,
            "tool_stats": self.get_tool_stats(),
        }


# Global metrics collector instance
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
