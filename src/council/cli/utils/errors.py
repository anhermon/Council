"""Error handling utilities."""

import sys

import click


def handle_common_errors(e: Exception) -> None:
    """
    Handle common CLI errors consistently.

    Args:
        e: The exception to handle. Will be categorized and appropriate
           error message will be displayed before exiting.
    """
    if isinstance(e, ValueError | TypeError | KeyError):
        click.echo(f"❌ Configuration error: {e}", err=True)
        sys.exit(1)
    elif isinstance(e, FileNotFoundError):
        click.echo(f"❌ File not found: {e}", err=True)
        sys.exit(1)
    else:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        sys.exit(1)
