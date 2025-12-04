"""CLI package for The Council."""

from .core.review_executor import run_agent_review
from .main import main
from .ui.output import print_markdown, print_pretty
from .ui.spinner import Spinner
from .ui.streaming import cleanup_spinner_task, create_event_stream_handler
from .utils.errors import handle_common_errors
from .utils.paths import collect_files, resolve_path

__all__ = [
    "main",
    "Spinner",
    "cleanup_spinner_task",
    "collect_files",
    "resolve_path",
    "create_event_stream_handler",
    "run_agent_review",
    "handle_common_errors",
    "print_pretty",
    "print_markdown",
]
