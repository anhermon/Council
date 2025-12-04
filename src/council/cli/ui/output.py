"""Output formatting for review results."""

import click

from ...agents import ReviewResult


def print_pretty(review_result: ReviewResult) -> None:
    """Print review results in a pretty format."""
    click.echo("\n" + "=" * 80)
    click.echo("📋 REVIEW SUMMARY")
    click.echo("=" * 80)
    click.echo(f"\n{review_result.summary}\n")
    click.echo(f"Overall Severity: {review_result.severity.upper()}\n")

    if review_result.issues:
        click.echo("=" * 80)
        click.echo("🔍 ISSUES FOUND")
        click.echo("=" * 80)
        for i, issue in enumerate(review_result.issues, 1):
            click.echo(f"\n{i}. [{issue.severity.upper()}] {issue.description}")
            if issue.line_number:
                click.echo(f"   Line: {issue.line_number}")
            if issue.code_snippet:
                click.echo(f"   Code: {click.style(issue.code_snippet, dim=True)}")
    else:
        click.echo("✅ No issues found!")

    if review_result.code_fix:
        click.echo("\n" + "=" * 80)
        click.echo("💡 SUGGESTED FIX")
        click.echo("=" * 80)
        click.echo(f"\n{review_result.code_fix}\n")


def print_markdown(review_result: ReviewResult) -> None:
    """Print review results in markdown format."""
    click.echo("# Code Review Results\n")
    click.echo(f"## Summary\n\n{review_result.summary}\n")
    click.echo(f"**Overall Severity:** {review_result.severity.upper()}\n")

    if review_result.issues:
        click.echo("## Issues Found\n")
        for i, issue in enumerate(review_result.issues, 1):
            click.echo(f"### {i}. {issue.description}\n")
            click.echo(f"- **Severity:** {issue.severity.upper()}")
            click.echo(f"- **Category:** {issue.category.upper()}")
            if issue.line_number:
                click.echo(f"- **Line:** {issue.line_number}")
            if issue.code_snippet:
                click.echo(f"- **Code:**\n  ```\n  {issue.code_snippet}\n  ```")
            if issue.related_files:
                click.echo(f"- **Related Files:** {', '.join(issue.related_files)}")
            if issue.suggested_priority:
                click.echo(f"- **Priority:** {issue.suggested_priority}/10")
            if issue.references:
                click.echo(f"- **References:** {', '.join(issue.references)}")
            if issue.auto_fixable:
                click.echo("- **Auto-fixable:** Yes")
            click.echo()

    if review_result.code_fix:
        click.echo("## Suggested Fix\n")
        click.echo(f"```\n{review_result.code_fix}\n```\n")
