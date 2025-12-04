"""Tools for The Council."""

from .exceptions import (
    PathValidationError,
    RepomixError,
    RepomixTimeoutError,
    SecurityError,
    SubprocessError,
    SubprocessTimeoutError,
    ToolError,
    ValidationError,
)
from .metrics_collector import MetricsCollector, ReviewMetrics, get_metrics_collector
from .persistence import ReviewHistory, ReviewRecord, get_review_history
from .repomix import get_packed_context, get_packed_diff
from .scribe import fetch_and_summarize
from .validation import check_xml_security, validate_file_path, validate_include_pattern

__all__ = [
    # Context extraction
    "get_packed_context",
    "get_packed_diff",
    # Scribe
    "fetch_and_summarize",
    # Exceptions
    "ToolError",
    "ValidationError",
    "PathValidationError",
    "SecurityError",
    "RepomixError",
    "RepomixTimeoutError",
    "SubprocessError",
    "SubprocessTimeoutError",
    # Validation
    "validate_file_path",
    "validate_include_pattern",
    "check_xml_security",
    # Metrics
    "MetricsCollector",
    "ReviewMetrics",
    "get_metrics_collector",
    # Persistence
    "ReviewHistory",
    "ReviewRecord",
    "get_review_history",
]
