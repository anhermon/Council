"""Context command - output review context for external agents."""

import asyncio
import json
import sys
from pathlib import Path

import click

from ...agents import CouncilDeps
from ...tools.repomix import get_packed_context, get_packed_diff
from ..core.context_builder import build_review_context
from ..utils.paths import resolve_path

# Configuration constants
MAX_EXTRA_INSTRUCTIONS_LENGTH = 10000


@click.command()
@click.argument("file_path", type=str)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "markdown"], case_sensitive=False),
    default="json",
    help="Output format for the context (json or markdown)",
)
@click.option(
    "--diff",
    "-d",
    "base_ref",
    help="Extract context for diff-based review (e.g., HEAD, main). "
    "If provided, only changed code will be included.",
)
@click.option(
    "--extra-instructions",
    "-i",
    help="Additional instructions for the review",
)
@click.option(
    "--phases",
    help="Comma-separated list of review phases to focus on (security,performance,maintainability,best_practices).",
)
def context(
    file_path: str,
    output: str,
    base_ref: str | None,
    extra_instructions: str | None,
    phases: str | None,
) -> None:
    """Output review context for a file path.

    This command extracts code context, loads relevant knowledge base content,
    and generates a review checklist. The output can be used by external agents
    (like Gemini, Claude, Codex, etc.) to perform code reviews.

    Examples:
        council context src/council/main.py
        council context src/council/main.py --output markdown
        council context src/council/main.py --diff HEAD
    """
    # Validate and sanitize extra_instructions
    if extra_instructions:
        if len(extra_instructions) > MAX_EXTRA_INSTRUCTIONS_LENGTH:
            click.echo(
                f"❌ Extra instructions too long (max {MAX_EXTRA_INSTRUCTIONS_LENGTH} characters)",
                err=True,
            )
            sys.exit(1)

        # Basic sanitization
        sanitized = "".join(
            char for char in extra_instructions if ord(char) >= 32 or char in "\n\t"
        )
        if sanitized != extra_instructions:
            click.echo(
                "⚠️  Warning: Removed invalid control characters from extra instructions",
                err=True,
            )
        extra_instructions = sanitized

    # Validate file path
    try:
        resolved_path = resolve_path(Path(file_path))
        if not resolved_path.exists():
            click.echo(f"❌ File not found: {file_path}", err=True)
            sys.exit(1)
        file_path = str(resolved_path)
    except ValueError as e:
        click.echo(f"❌ Invalid path: {e}", err=True)
        sys.exit(1)

    # Parse review phases if provided
    review_phases = None
    if phases:
        review_phases = [p.strip() for p in phases.split(",") if p.strip()]
        valid_phases = {"security", "performance", "maintainability", "best_practices"}
        review_phases = [p for p in review_phases if p in valid_phases]
        if not review_phases:
            click.echo(
                f"⚠️  No valid phases specified. Valid phases: {', '.join(valid_phases)}",
                err=True,
            )
            review_phases = None

    async def _get_context() -> None:
        try:
            click.echo("📦 Extracting context...", err=True)

            # Get packed context using Repomix
            if base_ref:
                packed_xml = await get_packed_diff(file_path, base_ref)
            else:
                packed_xml = await get_packed_context(file_path)

            # Create dependencies
            deps = CouncilDeps(
                file_path=file_path,
                extra_instructions=extra_instructions,
                review_phases=review_phases,
            )

            # Build review context
            context_data = await build_review_context(packed_xml, deps)

            # Output based on format
            if output == "markdown":
                _output_markdown(context_data)
            else:
                _output_json(context_data)

        except Exception as e:
            click.echo(f"❌ Failed to get context: {e}", err=True)
            sys.exit(1)

    asyncio.run(_get_context())


def _output_json(context_data: dict) -> None:
    """Output context as JSON."""
    click.echo(json.dumps(context_data, indent=2))


def _output_markdown(context_data: dict) -> None:
    """Output context as Markdown."""
    click.echo("# Code Review Context\n")
    click.echo(f"## File: {context_data['file_path']}\n")
    click.echo(f"**Language:** {context_data['language']}\n")

    if context_data["metadata"]["extra_instructions"]:
        click.echo(f"**Extra Instructions:** {context_data['metadata']['extra_instructions']}\n")

    if context_data["metadata"]["review_phases"]:
        click.echo(f"**Review Phases:** {', '.join(context_data['metadata']['review_phases'])}\n")

    click.echo("## System Prompt\n")
    click.echo("```\n")
    click.echo(context_data["system_prompt"])
    click.echo("\n```\n")

    if context_data["knowledge_base"]:
        click.echo("## Knowledge Base\n")
        click.echo("```\n")
        click.echo(context_data["knowledge_base"])
        click.echo("\n```\n")

    click.echo("## Code to Review\n")
    click.echo("```\n")
    click.echo(context_data["extracted_code"])
    click.echo("\n```\n")

    click.echo("## Review Checklist\n")
    click.echo(context_data["review_checklist"])
