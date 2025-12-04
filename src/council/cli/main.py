"""Main CLI entry point for The Council."""

import click
import logfire

from .. import __version__
from .commands.context import context
from .commands.housekeeping import housekeeping
from .commands.learn import learn
from .commands.review import review

# Initialize logfire
logfire.configure(send_to_logfire=False)


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """The Council - AI Code Review Agent main CLI entry point."""
    pass


# Register all commands
main.add_command(review)
main.add_command(learn)
main.add_command(context)
main.add_command(housekeeping)

__all__ = ["main"]
