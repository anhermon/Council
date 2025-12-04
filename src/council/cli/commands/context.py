"""Context command - output review context for external agents."""

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import click
import logfire

from ...agents import CouncilDeps
from ...tools.repomix import get_packed_context, get_packed_diff
from ..core.context_builder import build_review_context
from ..utils.constants import (
    MAX_OUTPUT_SIZE_WARNING_BYTES,
    OUTPUT_FORMAT_JSON,
    OUTPUT_FORMAT_MARKDOWN,
    VALID_REVIEW_PHASES,
)
from ..utils.paths import resolve_path
from ..utils.validation import sanitize_extra_instructions


@click.command()
@click.argument("file_path", type=str)
@click.option(
    "--output",
    "-o",
    type=click.Choice([OUTPUT_FORMAT_JSON, OUTPUT_FORMAT_MARKDOWN], case_sensitive=False),
    default=OUTPUT_FORMAT_JSON,
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

    Note: This command does NOT require an API key as it does not use Council's LLM.
    It only performs file operations, template rendering, and knowledge base loading.

    Examples:
        council context src/council/main.py
        council context src/council/main.py --output markdown
        council context src/council/main.py --diff HEAD
    """
    # Validate and sanitize extra_instructions
    if extra_instructions:
        extra_instructions = sanitize_extra_instructions(extra_instructions)

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
        review_phases = [p for p in review_phases if p in VALID_REVIEW_PHASES]
        if not review_phases:
            click.echo(
                f"⚠️  No valid phases specified. Valid phases: {', '.join(sorted(VALID_REVIEW_PHASES))}",
                err=True,
            )
            review_phases = None

    async def _get_context() -> None:
        # Suppress logfire output for both JSON and markdown to ensure clean output
        # Configure before any operations that might use logfire
        logfire.configure(send_to_logfire=False, console=False)
        logging.getLogger("logfire").setLevel(logging.CRITICAL)  # Only show critical errors
        # Also suppress other logfire loggers
        logging.getLogger("logfire.instrumentation").setLevel(logging.CRITICAL)
        logging.getLogger("logfire.otel").setLevel(logging.CRITICAL)

        try:
            if output != OUTPUT_FORMAT_JSON:  # Only show status messages for markdown output
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
            if output == OUTPUT_FORMAT_MARKDOWN:
                _output_markdown(context_data)
            else:
                _output_json(context_data)

        except ValueError as e:
            click.echo(f"❌ Invalid input: {e}", err=True)
            sys.exit(1)
        except FileNotFoundError as e:
            click.echo(f"❌ File not found: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Unexpected error: {e}", err=True)
            sys.exit(1)

    asyncio.run(_get_context())


def _output_json(context_data: dict) -> None:
    """Output context as JSON."""
    # Use sys.stdout directly to avoid any click formatting that might interfere
    print(json.dumps(context_data, indent=2), file=sys.stdout)


def _output_markdown(context_data: dict) -> None:
    """Output context as Markdown."""
    # Calculate approximate output size for warning
    output_size = len(str(context_data))
    if output_size > MAX_OUTPUT_SIZE_WARNING_BYTES:
        click.echo(
            f"⚠️  Warning: Large context file ({output_size / 1024:.1f}KB). "
            "Consider using --phases to focus on specific review areas.\n",
            err=True,
        )

    # Generate timestamp

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    click.echo("# Code Review Context\n")
    click.echo(f"**Generated:** {timestamp}\n")
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

    # Always show knowledge base section, even if empty
    click.echo("## Knowledge Base\n")
    knowledge_content = context_data.get("knowledge_base", "").strip()
    if knowledge_content:
        click.echo("```\n")
        click.echo(knowledge_content)
        click.echo("\n```\n")
    else:
        click.echo("*No relevant knowledge base content loaded.*\n")

    click.echo("## Code to Review\n")
    # Add language identifier for syntax highlighting
    language = context_data.get("language", "text")
    click.echo(f"```{language}\n")
    click.echo(context_data["extracted_code"])
    click.echo("\n```\n")

    # Display database relations if available
    database_relations = context_data.get("database_relations", {})
    if database_relations:
        click.echo("## Database Relations\n")

        # Tables referenced
        tables_referenced = database_relations.get("tables_referenced", [])
        if tables_referenced:
            click.echo(f"**Tables Referenced:** {', '.join(tables_referenced)}\n")

        # Queries in code
        queries_in_code = database_relations.get("queries_in_code", [])
        if queries_in_code:
            click.echo("\n### Queries in Code\n")
            for query_info in queries_in_code:
                method = query_info.get("method", "Unknown")
                tables = query_info.get("tables", [])
                click.echo(f"- **Method:** `{method}`\n")
                if tables:
                    click.echo(f"  - **Tables:** {', '.join(tables)}\n")
                query_preview = query_info.get("query", "")
                if len(query_preview) > 100:
                    query_preview = query_preview[:100] + "..."
                click.echo(f"  - **Query:** `{query_preview}`\n")

        # Schema tables
        schema_tables = database_relations.get("schema_tables", {})
        if schema_tables:
            click.echo("\n### Schema Tables\n")
            for table_name, table_info in schema_tables.items():
                click.echo(f"- **{table_name}**\n")
                columns = table_info.get("columns", [])
                if columns:
                    col_names = [col.get("name", "") for col in columns[:10]]  # Limit to first 10
                    click.echo(f"  - Columns: {', '.join(col_names)}\n")
                    if len(columns) > 10:
                        click.echo(f"  - ... and {len(columns) - 10} more columns\n")
                foreign_keys = table_info.get("foreign_keys", [])
                if foreign_keys:
                    click.echo(f"  - Foreign Keys: {len(foreign_keys)}\n")

        # Relationships
        relationships = database_relations.get("relationships", [])
        if relationships:
            click.echo("\n### Table Relationships\n")
            for rel in relationships[:10]:  # Limit to first 10
                from_table = rel.get("from_table", "")
                to_table = rel.get("to_table", "")
                fk = rel.get("foreign_key", "")
                click.echo(f"- `{from_table}` → `{to_table}` (via `{fk}`)\n")
            if len(relationships) > 10:
                click.echo(f"- ... and {len(relationships) - 10} more relationships\n")

        # Queries in files
        queries_in_files = database_relations.get("queries_in_files", [])
        if queries_in_files:
            click.echo("\n### Queries in SQL Files\n")
            for file_query in queries_in_files[:5]:  # Limit to first 5
                file_path = file_query.get("file", "")
                used = file_query.get("used_in_code", False)
                methods = file_query.get("used_in_methods", [])
                click.echo(f"- **File:** `{file_path}`\n")
                click.echo(f"  - **Used in code:** {'Yes' if used else 'No'}\n")
                if methods:
                    click.echo(f"  - **Methods:** {', '.join(methods)}\n")
            if len(queries_in_files) > 5:
                click.echo(f"- ... and {len(queries_in_files) - 5} more queries\n")

    click.echo("## Review Checklist\n")
    click.echo(context_data["review_checklist"])
