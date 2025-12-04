"""Review command - perform code reviews."""

import asyncio
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import click
import logfire

from ...agents import CouncilDeps, ReviewResult
from ...config import get_settings
from ...tools.cache import cache_review, get_cached_review
from ...tools.git_tools import get_uncommitted_files
from ...tools.metrics_collector import get_metrics_collector
from ...tools.persistence import ReviewRecord, get_review_history
from ...tools.repomix import get_packed_context, get_packed_diff
from ..core.review_executor import run_agent_review
from ..ui.output import print_markdown, print_pretty
from ..ui.spinner import Spinner
from ..utils.constants import VALID_REVIEW_PHASES
from ..utils.paths import collect_files
from ..utils.validation import sanitize_extra_instructions

settings = get_settings()


@click.command()
@click.argument("paths", nargs=-1, required=False, type=click.Path(path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "markdown", "pretty"], case_sensitive=False),
    default="pretty",
    help="Output format for the review results (json, markdown, or pretty)",
)
@click.option(
    "--extra-instructions",
    "-i",
    help="Additional instructions for the review",
)
@click.option(
    "--diff",
    "-d",
    "base_ref",
    help="Review only changed code compared to git reference (e.g., HEAD, main). "
    "If provided, only modified files will be reviewed.",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Disable caching of review results",
)
@click.option(
    "--phases",
    help="Comma-separated list of review phases to run (security,performance,maintainability,best_practices). "
    "If not specified, runs all phases in a single pass.",
)
@click.option(
    "--uncommitted",
    "-u",
    is_flag=True,
    default=False,
    help="Review only uncommitted changes. If specified without paths, reviews all uncommitted files.",
)
def review(
    paths: tuple[Path, ...] | None,
    output: str,
    extra_instructions: str | None,
    base_ref: str | None,
    no_cache: bool,
    phases: str | None,
    uncommitted: bool,
) -> None:
    """Review code at the given file path(s) or directory/ies.

    You can specify multiple files and/or directories:

    \b
    Examples:
        council review file1.py file2.py
        council review @agents
        council review src/ tests/ file.py
        council review --uncommitted  # Review all uncommitted files
    """
    # Validate and sanitize extra_instructions
    if extra_instructions:
        extra_instructions = sanitize_extra_instructions(extra_instructions)

    # Handle --uncommitted without paths: use project root
    if uncommitted and (not paths or len(paths) == 0):
        paths = (settings.project_root,)

    # Validate that paths are provided (unless --uncommitted was used, which we handled above)
    if not paths or len(paths) == 0:
        click.echo("❌ No paths specified. Provide file(s) or directory/ies to review.", err=True)
        click.echo("   Use --uncommitted to review all uncommitted files.", err=True)
        sys.exit(1)

    # Collect all files to review
    files_to_review = collect_files(list(paths))

    # Filter to uncommitted files if --uncommitted flag is set
    if uncommitted:

        async def _filter_uncommitted():
            try:
                uncommitted_file_paths = await get_uncommitted_files()
                if not uncommitted_file_paths:
                    click.echo("⚠️  No uncommitted changes found", err=True)
                    sys.exit(0)

                # Convert to Path objects relative to project root
                project_root = settings.project_root.resolve()
                uncommitted_paths = {
                    (project_root / path).resolve() for path in uncommitted_file_paths
                }

                # If no specific paths were provided, use all uncommitted files
                if not paths or len(paths) == 0 or paths == (settings.project_root,):
                    # Use all uncommitted files directly, but filter out deleted files
                    filtered_files = [
                        (project_root / path).resolve()
                        for path in uncommitted_file_paths
                        if (project_root / path).exists()
                    ]
                else:
                    # Filter files_to_review to only include uncommitted files that exist
                    filtered_files = [
                        f
                        for f in files_to_review
                        if f.resolve() in uncommitted_paths and f.exists()
                    ]

                if not filtered_files:
                    click.echo(
                        "⚠️  None of the specified files have uncommitted changes",
                        err=True,
                    )
                    sys.exit(0)

                return filtered_files
            except Exception as e:
                click.echo(f"❌ Failed to get uncommitted files: {e}", err=True)
                sys.exit(1)

        files_to_review = asyncio.run(_filter_uncommitted())
        click.echo(
            f"📝 Filtered to {len(files_to_review)} uncommitted file(s) to review",
            err=True,
        )
        # When reviewing uncommitted changes, use HEAD as base reference for diff context
        if not base_ref:
            base_ref = "HEAD"

    if not files_to_review:
        click.echo("❌ No files found to review", err=True)
        sys.exit(1)

    click.echo(f"🔍 Found {len(files_to_review)} file(s) to review", err=True)

    async def _review_single_file(
        file_path: Path,
        idx: int,
        total: int,
        semaphore: asyncio.Semaphore,
    ) -> tuple[Path, ReviewResult] | None:
        """
        Review a single file.

        Args:
            file_path: Path to the file to review
            idx: Index of this file (1-based)
            total: Total number of files
            semaphore: Semaphore to limit concurrency

        Returns:
            Tuple of (file_path, ReviewResult) or None if review failed
        """
        async with semaphore:
            # Initialize metrics and persistence
            review_id = str(uuid.uuid4())[:8]
            metrics_collector = get_metrics_collector()
            review_history = get_review_history()
            review_metrics = metrics_collector.start_review(review_id, str(file_path))

            try:
                click.echo(f"\n[{idx}/{total}] 🔍 Reviewing: {file_path}", err=True)
                if base_ref:
                    click.echo(f"📦 Extracting diff context (base: {base_ref})...", err=True)
                else:
                    click.echo("📦 Extracting context with Repomix...", err=True)

                # Get packed context using Repomix (with diff if base_ref provided)
                context_start = time.time()
                try:
                    if base_ref:
                        packed_xml = await get_packed_diff(str(file_path), base_ref)
                    else:
                        packed_xml = await get_packed_context(str(file_path))
                    context_duration = time.time() - context_start
                    metrics_collector.record_tool_execution(
                        "repomix", context_duration, success=True
                    )
                except Exception as e:
                    context_duration = time.time() - context_start
                    metrics_collector.record_tool_execution(
                        "repomix", context_duration, success=False, error_type=type(e).__name__
                    )
                    raise

                # Parse review phases if provided
                review_phases = None
                if phases:
                    review_phases = [p.strip() for p in phases.split(",") if p.strip()]
                    review_phases = [p for p in review_phases if p in VALID_REVIEW_PHASES]
                    if not review_phases:
                        click.echo(
                            f"⚠️  No valid phases specified, using all phases. Valid phases: {', '.join(sorted(VALID_REVIEW_PHASES))}",
                            err=True,
                        )
                        review_phases = None

                # Create dependencies for the agent
                deps = CouncilDeps(
                    file_path=str(file_path),
                    extra_instructions=extra_instructions,
                    review_phases=review_phases,
                )

                # Check cache if enabled
                cached_result = None
                if not no_cache and settings.enable_cache:
                    model_name = os.getenv("COUNCIL_MODEL") or "unknown"
                    cached_data = await get_cached_review(str(file_path), model_name)
                    if cached_data:
                        # Reconstruct ReviewResult from cached data
                        cached_result = ReviewResult(**cached_data)
                        click.echo("✅ Using cached review result", err=True)

                if cached_result:
                    review_result = cached_result
                else:
                    # Run the agent review
                    click.echo("🤖 Running AI review...", err=True)
                    spinner = Spinner()
                    review_result = await run_agent_review(
                        packed_xml, deps, spinner, review_id=review_id
                    )

                    # Cache result if enabled
                    if not no_cache and settings.enable_cache:
                        model_name = os.getenv("COUNCIL_MODEL") or "unknown"
                        await cache_review(
                            str(file_path),
                            review_result.model_dump(),
                            model_name,
                        )

                # Finish metrics collection
                metrics_collector.finish_review(
                    review_id,
                    success=True,
                    issues_found=len(review_result.issues),
                    severity=review_result.severity,
                    context_size_bytes=len(packed_xml),
                )

                # Save review to history
                try:
                    review_record = ReviewRecord(
                        review_id=review_id,
                        file_path=str(file_path),
                        timestamp=datetime.now().isoformat(),
                        duration_seconds=review_metrics.duration_seconds or 0.0,
                        success=True,
                        error_type=None,
                        issues_found=len(review_result.issues),
                        severity=review_result.severity,
                        context_size_bytes=len(packed_xml),
                        token_usage={},  # Token usage not available in streaming mode
                        summary=review_result.summary,
                        metadata={
                            "base_ref": base_ref,
                            "extra_instructions": extra_instructions is not None,
                            "review_phases": deps.review_phases,
                        }
                        if base_ref or extra_instructions or deps.review_phases
                        else None,
                    )
                    review_history.save_review(review_record)
                except Exception as e:
                    # Don't fail the review if persistence fails
                    logfire.warning("Failed to save review history", error=str(e))

                return (file_path, review_result)

            except FileNotFoundError as e:
                click.echo(f"❌ File not found: {e}", err=True)
                metrics_collector.finish_review(
                    review_id, success=False, error_type="FileNotFoundError"
                )
                return None
            except RuntimeError as e:
                error_msg = str(e)
                error_type = "RuntimeError"
                if "No API keys configured" in error_msg or "API key" in error_msg.lower():
                    click.echo(f"❌ Configuration error: {e}", err=True)
                    click.echo(
                        "\n💡 Set environment variables:\n"
                        "  - OPENAI_API_KEY for direct provider access, or\n"
                        "  - LITELLM_BASE_URL and LITELLM_API_KEY for LiteLLM proxy",
                        err=True,
                    )
                    metrics_collector.finish_review(
                        review_id, success=False, error_type="ConfigurationError"
                    )
                    sys.exit(1)
                else:
                    click.echo(f"❌ Review failed for {file_path}: {e}", err=True)
                    metrics_collector.finish_review(review_id, success=False, error_type=error_type)
                    return None
            except Exception as e:
                error_str = str(e).lower()
                error_type = type(e).__name__
                metrics_collector.finish_review(review_id, success=False, error_type=error_type)
                # Check if this is a rate limit error
                is_rate_limit = (
                    "429" in error_str
                    or "rate limit" in error_str
                    or "ratelimiterror" in error_str
                    or "throttling" in error_str
                    or "too many tokens" in error_str
                )

                if is_rate_limit:
                    # Extract model name if available
                    model_match = None
                    if hasattr(e, "body") and isinstance(e.body, dict):
                        model_match = e.body.get("model_name", "unknown")
                    elif "model" in error_str:
                        # Try to extract model name from error message
                        model_match = re.search(
                            r"model[_\s]*[=:]?\s*([^\s,]+)", error_str, re.IGNORECASE
                        )
                        if model_match:
                            model_match = model_match.group(1)

                    click.echo(
                        f"❌ Review failed for {file_path}: Rate limit exceeded",
                        err=True,
                    )
                    if model_match:
                        click.echo(
                            f"   Model: {model_match}",
                            err=True,
                        )
                    click.echo(
                        "   💡 Consider:\n"
                        "   - Waiting a few minutes before retrying\n"
                        "   - Using a different model via COUNCIL_MODEL env var\n"
                        "   - Reducing the number of files reviewed at once",
                        err=True,
                    )
                else:
                    click.echo(f"❌ Unexpected error reviewing {file_path}: {e}", err=True)
                return None
            except (ValueError, TypeError, KeyError) as e:
                click.echo(f"❌ Error reviewing {file_path}: {e}", err=True)
                return None

    async def _review():
        all_results: list[tuple[Path, ReviewResult]] = []

        # Calculate concurrency limit based on number of files
        # More aggressive scaling: use at least 3, scale up to max_concurrent_reviews
        # For small batches, use higher concurrency
        if len(files_to_review) <= 5:
            concurrency_limit = len(files_to_review)
        else:
            concurrency_limit = min(
                settings.max_concurrent_reviews, max(3, len(files_to_review) // 2)
            )
        semaphore = asyncio.Semaphore(concurrency_limit)
        click.echo(
            f"⚡ Processing {len(files_to_review)} files with concurrency limit: {concurrency_limit}",
            err=True,
        )

        # Create tasks for all files
        tasks = [
            _review_single_file(file_path, idx + 1, len(files_to_review), semaphore)
            for idx, file_path in enumerate(files_to_review)
        ]

        # Run all reviews in parallel (with concurrency limit)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and filter out None values
        for result in results:
            if isinstance(result, Exception):
                logfire.error("Review task raised exception", error=str(result))
                continue
            if result is not None:
                all_results.append(result)

        # Output results
        if output == "json":
            # For JSON output, create a structured format with file paths
            results_dict = {
                "files": [
                    {
                        "file_path": str(file_path),
                        "summary": review_result.summary,
                        "issues": [
                            {
                                "description": issue.description,
                                "severity": issue.severity,
                                "category": issue.category,
                                "line_number": issue.line_number,
                                "code_snippet": issue.code_snippet,
                                "related_files": issue.related_files,
                                "suggested_priority": issue.suggested_priority,
                                "references": issue.references,
                                "auto_fixable": issue.auto_fixable,
                            }
                            for issue in review_result.issues
                        ],
                        "severity": review_result.severity,
                        "code_fix": review_result.code_fix,
                        "cross_file_issues": [
                            {
                                "description": issue.description,
                                "severity": issue.severity,
                                "files": issue.files,
                                "category": issue.category,
                            }
                            for issue in review_result.cross_file_issues
                        ],
                        "dependency_analysis": (
                            {
                                "external_dependencies": review_result.dependency_analysis.external_dependencies,
                                "internal_dependencies": review_result.dependency_analysis.internal_dependencies,
                                "circular_dependencies": review_result.dependency_analysis.circular_dependencies,
                                "unused_imports": review_result.dependency_analysis.unused_imports,
                            }
                            if review_result.dependency_analysis
                            else None
                        ),
                    }
                    for file_path, review_result in all_results
                ]
            }
            click.echo(json.dumps(results_dict, indent=2))
        else:
            # For markdown and pretty output, show each file's results separately
            for file_path, review_result in all_results:
                click.echo(f"\n{'=' * 80}", err=True)
                click.echo(f"📄 FILE: {file_path}", err=True)
                click.echo(f"{'=' * 80}\n", err=True)

                if output == "markdown":
                    print_markdown(review_result)
                else:  # pretty
                    print_pretty(review_result)

    asyncio.run(_review())
