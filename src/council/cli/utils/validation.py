"""Input validation utilities for CLI."""

import sys

import click

from .constants import MAX_EXTRA_INSTRUCTIONS_LENGTH


def sanitize_extra_instructions(instructions: str) -> str:
    """
    Sanitize and validate extra instructions input.

    Args:
        instructions: Raw instructions string from user input

    Returns:
        Sanitized instructions string

    Raises:
        SystemExit: If instructions exceed maximum length
    """
    # Check length to prevent API limit issues
    if len(instructions) > MAX_EXTRA_INSTRUCTIONS_LENGTH:
        click.echo(
            f"❌ Extra instructions too long (max {MAX_EXTRA_INSTRUCTIONS_LENGTH} characters)",
            err=True,
        )
        sys.exit(1)

    # Basic sanitization: remove null bytes and control characters that could cause issues
    # Keep newlines and tabs as they might be intentional
    sanitized = "".join(char for char in instructions if ord(char) >= 32 or char in "\n\t")

    if sanitized != instructions:
        click.echo(
            "⚠️  Warning: Removed invalid control characters from extra instructions",
            err=True,
        )

    return sanitized
