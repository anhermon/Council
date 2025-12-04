"""Persistence layer for review history and state."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import logfire

from ..config import get_settings

settings = get_settings()


@dataclass
class ReviewRecord:
    """Record of a completed code review."""

    review_id: str
    file_path: str
    timestamp: str
    duration_seconds: float
    success: bool
    error_type: str | None
    issues_found: int
    severity: str | None
    context_size_bytes: int
    token_usage: dict[str, int]
    summary: str | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewRecord":
        """Create ReviewRecord from dictionary."""
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Convert ReviewRecord to dictionary."""
        return asdict(self)


class ReviewHistory:
    """Manages persistent storage of review history."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        """
        Initialize review history storage.

        Args:
            storage_dir: Directory for storing review history. Defaults to project_root/.council/history
        """
        if storage_dir is None:
            storage_dir = settings.project_root / ".council" / "history"
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_review(self, record: ReviewRecord) -> None:
        """
        Save a review record to persistent storage.

        Args:
            record: Review record to save
        """
        try:
            # Create filename from review_id and timestamp
            filename = f"{record.review_id}_{record.timestamp}.json"
            filepath = self.storage_dir / filename

            # Write JSON file
            with filepath.open("w") as f:
                json.dump(record.to_dict(), f, indent=2)

            logfire.debug("Review saved", review_id=record.review_id, filepath=str(filepath))
        except Exception as e:
            logfire.error("Failed to save review", review_id=record.review_id, error=str(e))
            # Don't raise - persistence failures shouldn't break reviews

    def load_review(self, review_id: str) -> ReviewRecord | None:
        """
        Load a review record by ID.

        Args:
            review_id: Review ID to load

        Returns:
            ReviewRecord if found, None otherwise
        """
        try:
            # Find file matching review_id
            for filepath in self.storage_dir.glob(f"{review_id}_*.json"):
                with filepath.open() as f:
                    data = json.load(f)
                    return ReviewRecord.from_dict(data)
            return None
        except Exception as e:
            logfire.error("Failed to load review", review_id=review_id, error=str(e))
            return None

    def list_reviews(self, file_path: str | None = None, limit: int = 100) -> list[ReviewRecord]:
        """
        List recent reviews.

        Args:
            file_path: Optional filter by file path
            limit: Maximum number of reviews to return

        Returns:
            List of ReviewRecord instances, sorted by timestamp (newest first)
        """
        try:
            records: list[ReviewRecord] = []
            for filepath in sorted(
                self.storage_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
            ):
                try:
                    with filepath.open() as f:
                        data = json.load(f)
                        record = ReviewRecord.from_dict(data)

                        # Filter by file_path if specified
                        if file_path and record.file_path != file_path:
                            continue

                        records.append(record)
                        if len(records) >= limit:
                            break
                except Exception as e:
                    logfire.warning(
                        "Failed to load review file", filepath=str(filepath), error=str(e)
                    )
                    continue

            return records
        except Exception as e:
            logfire.error("Failed to list reviews", error=str(e))
            return []

    def get_review_history_for_file(self, file_path: str) -> list[ReviewRecord]:
        """
        Get review history for a specific file.

        Args:
            file_path: File path to get history for

        Returns:
            List of ReviewRecord instances for the file
        """
        return self.list_reviews(file_path=file_path)


# Global review history instance
_review_history: ReviewHistory | None = None


def get_review_history() -> ReviewHistory:
    """Get the global review history instance."""
    global _review_history
    if _review_history is None:
        _review_history = ReviewHistory()
    return _review_history
