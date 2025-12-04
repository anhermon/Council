"""Main CLI entry point for The Council."""

import click
import logfire

from .commands.commit import commit
from .commands.context import context
from .commands.housekeeping import housekeeping
from .commands.learn import learn
from .commands.review import review

# Initialize logfire
logfire.configure(send_to_logfire=False)


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """The Council - AI Code Review Agent main CLI entry point."""
    pass


# Register all commands
main.add_command(commit)
main.add_command(context)
main.add_command(housekeeping)
main.add_command(learn)
main.add_command(review)

__all__ = ["main"]
