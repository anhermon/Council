"""CLI constants shared across commands."""

# Input validation constants
MAX_EXTRA_INSTRUCTIONS_LENGTH = 10000

# Output format constants
OUTPUT_FORMAT_JSON = "json"
OUTPUT_FORMAT_MARKDOWN = "markdown"

# Review phase constants
VALID_REVIEW_PHASES = {"security", "performance", "maintainability", "best_practices"}

# Output size constants
MAX_OUTPUT_SIZE_WARNING_BYTES = 100 * 1024  # 100KB

__all__ = [
    "MAX_EXTRA_INSTRUCTIONS_LENGTH",
    "OUTPUT_FORMAT_JSON",
    "OUTPUT_FORMAT_MARKDOWN",
    "VALID_REVIEW_PHASES",
    "MAX_OUTPUT_SIZE_WARNING_BYTES",
]
