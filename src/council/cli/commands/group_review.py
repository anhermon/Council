"""Group review command - group related files and generate review contexts."""

import asyncio
import fnmatch
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import click

from ...config import get_settings
from ..utils.paths import collect_files

settings = get_settings()


def load_gitignore_patterns(project_root: Path) -> list[str]:
    """
    Load patterns from .gitignore file.

    Args:
        project_root: Project root directory

    Returns:
        List of gitignore patterns
    """
    gitignore_path = project_root / ".gitignore"
    if not gitignore_path.exists():
        return []

    patterns = []
    with gitignore_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Remove trailing slash for directories
            if line.endswith("/"):
                line = line[:-1]
            patterns.append(line)

    return patterns


def matches_gitignore(file_path: Path, patterns: list[str], project_root: Path) -> bool:
    """
    Check if a file matches any gitignore pattern.

    Args:
        file_path: File path to check
        patterns: List of gitignore patterns
        project_root: Project root directory

    Returns:
        True if file should be ignored, False otherwise
    """
    # Get relative path from project root
    try:
        rel_path = file_path.relative_to(project_root)
    except ValueError:
        # File is outside project root, ignore it
        return True

    rel_path_str = str(rel_path)
    rel_path_parts = rel_path.parts

    for pattern in patterns:
        # Handle negation patterns (starting with !)
        if pattern.startswith("!"):
            continue  # Skip negation for now, can be enhanced later

        # Handle directory patterns
        if "/" in pattern:
            # Pattern contains path separator, match against full relative path
            if fnmatch.fnmatch(rel_path_str, pattern) or fnmatch.fnmatch(
                rel_path_str, f"**/{pattern}"
            ):
                return True
        else:
            # Pattern is a filename/glob, check against filename and any part
            if fnmatch.fnmatch(file_path.name, pattern):
                return True
            # Also check if pattern matches any directory in the path
            for part in rel_path_parts:
                if fnmatch.fnmatch(part, pattern):
                    return True

    return False


def group_files_by_structure(files: list[Path], project_root: Path) -> dict[str, list[Path]]:
    """
    Group files by their directory structure.

    Files are grouped by their parent directory structure, with related
    subdirectories grouped together.

    Args:
        files: List of file paths
        project_root: Project root directory

    Returns:
        Dictionary mapping group names to lists of files
    """
    groups: dict[str, list[Path]] = defaultdict(list)

    for file_path in files:
        try:
            rel_path = file_path.relative_to(project_root)
        except ValueError:
            continue

        parts = rel_path.parts

        if len(parts) == 1:
            # Root level file
            group_name = "root"
        elif len(parts) == 2:
            # One level deep - use parent directory name
            group_name = parts[0]
        elif len(parts) >= 3:
            # Multiple levels - group by first two levels
            # e.g., src/council/tools -> cli_tools
            # e.g., src/council/cli/commands -> cli_commands
            parent1, parent2 = parts[0], parts[1]
            if parent1 == "src" and len(parts) > 2:
                # For src/ structure, use second and third level
                group_name = f"{parts[1]}_{parts[2]}" if len(parts) > 2 else parts[1]
            else:
                group_name = f"{parent1}_{parent2}"
        else:
            group_name = "other"

        groups[group_name].append(file_path)

    return dict(groups)


async def generate_context(file_path: Path, output_dir: Path) -> dict[str, Any]:
    """Generate context for a single file."""
    # Create safe filename from full path
    safe_name = str(file_path).replace("/", "_").replace("\\", "_").replace(".", "_")
    output_file = output_dir / f"{safe_name}_context.md"

    try:
        # Run council context command
        result = subprocess.run(
            ["uv", "run", "council", "context", str(file_path), "--output", "markdown"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=settings.project_root,
        )

        if result.returncode == 0:
            # Save context to file
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(result.stdout, encoding="utf-8")
            return {
                "file": str(file_path),
                "success": True,
                "output_file": str(output_file),
                "error": None,
            }
        else:
            return {
                "file": str(file_path),
                "success": False,
                "output_file": None,
                "error": result.stderr or "Unknown error",
            }
    except subprocess.TimeoutExpired:
        return {
            "file": str(file_path),
            "success": False,
            "output_file": None,
            "error": "Timeout after 300 seconds",
        }
    except Exception as e:
        return {
            "file": str(file_path),
            "success": False,
            "output_file": None,
            "error": str(e),
        }


async def run_review(file_path: Path) -> dict[str, Any]:
    """Run review for a single file."""
    try:
        result = subprocess.run(
            ["uv", "run", "council", "review", str(file_path), "--output", "json"],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=settings.project_root,
        )

        if result.returncode == 0:
            # Extract JSON from stdout - it might have log messages before it
            stdout_text = result.stdout.strip()

            # Try to find JSON in the output - look for the first { or [
            json_start = -1
            for i, char in enumerate(stdout_text):
                if char in ("{", "["):
                    json_start = i
                    break

            if json_start == -1:
                return {
                    "file": str(file_path),
                    "success": False,
                    "review": None,
                    "error": "No JSON found in output",
                }

            # Extract from the start of JSON to the end
            json_text = stdout_text[json_start:]

            # Try to parse the JSON, handling potential trailing text
            # Find the matching closing brace/bracket
            try:
                # Use json.JSONDecoder to find where valid JSON ends
                decoder = json.JSONDecoder()
                json_data, idx = decoder.raw_decode(json_text)
                review_data = json_data
            except json.JSONDecodeError:
                # Fallback: try parsing the whole thing
                try:
                    review_data = json.loads(json_text)
                except json.JSONDecodeError as e:
                    return {
                        "file": str(file_path),
                        "success": False,
                        "review": None,
                        "error": f"Failed to parse review JSON: {str(e)}. Output preview: {json_text[:500]}",
                    }

            return {
                "file": str(file_path),
                "success": True,
                "review": review_data,
                "error": None,
            }
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            return {
                "file": str(file_path),
                "success": False,
                "review": None,
                "error": error_msg[:500],  # Limit error message length
            }
    except subprocess.TimeoutExpired:
        return {
            "file": str(file_path),
            "success": False,
            "review": None,
            "error": "Timeout after 600 seconds",
        }
    except Exception as e:
        return {
            "file": str(file_path),
            "success": False,
            "review": None,
            "error": str(e),
        }


@click.command()
@click.argument("paths", nargs=-1, required=False, type=click.Path(path_type=Path, exists=True))
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory to save context files (default: .council/contexts/)",
)
@click.option(
    "--review",
    "-r",
    is_flag=True,
    default=False,
    help="Also run reviews after generating contexts",
)
@click.option(
    "--no-gitignore",
    is_flag=True,
    default=False,
    help="Don't filter files using .gitignore patterns",
)
@click.option(
    "--group-by",
    type=click.Choice(["structure", "directory"], case_sensitive=False),
    default="structure",
    help="Grouping strategy: 'structure' (smart grouping) or 'directory' (by parent directory)",
)
def group_review(
    paths: tuple[Path, ...] | None,
    output_dir: Path | None,
    review: bool,
    no_gitignore: bool,
    group_by: str,
) -> None:
    """Group related files and generate review contexts.

    This command scans the project, groups related files together, and generates
    review contexts for each group. Files are automatically filtered using
    .gitignore patterns unless --no-gitignore is specified.

    By default, this command only generates contexts. Use --review to also run
    automated reviews after context generation.

    Examples:
        council group-review                    # Generate contexts for entire project
        council group-review src/ tests/        # Generate contexts for specific directories
        council group-review --review          # Generate contexts AND run automated reviews
        council group-review --no-gitignore    # Include gitignored files
    """
    project_root = settings.project_root

    # Determine paths to scan
    scan_paths = [project_root] if not paths or len(paths) == 0 else list(paths)

    # Collect all files
    click.echo("📦 Collecting files...", err=True)
    all_files = collect_files(scan_paths)
    click.echo(f"   Found {len(all_files)} files", err=True)

    # Filter by gitignore if enabled
    if not no_gitignore:
        click.echo("🔍 Filtering files using .gitignore...", err=True)
        gitignore_patterns = load_gitignore_patterns(project_root)
        filtered_files = [
            f for f in all_files if not matches_gitignore(f, gitignore_patterns, project_root)
        ]
        click.echo(f"   {len(all_files) - len(filtered_files)} files filtered out", err=True)
        all_files = filtered_files

    if not all_files:
        click.echo("❌ No files found to process", err=True)
        sys.exit(1)

    # Group files
    click.echo(f"\n📁 Grouping files by {group_by}...", err=True)
    if group_by == "structure":
        groups = group_files_by_structure(all_files, project_root)
    else:
        # Simple directory grouping
        groups = defaultdict(list)
        for file_path in all_files:
            try:
                rel_path = file_path.relative_to(project_root)
                group_name = rel_path.parts[0] if len(rel_path.parts) > 1 else "root"
                groups[group_name].append(file_path)
            except ValueError:
                continue
        groups = dict(groups)

    click.echo(f"   Created {len(groups)} groups", err=True)
    for group_name, group_files in groups.items():
        click.echo(f"   - {group_name}: {len(group_files)} files", err=True)

    # Set up output directory
    if output_dir is None:
        output_dir = project_root / ".council" / "contexts"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validate output directory is writable
    try:
        test_file = output_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
    except (PermissionError, OSError) as e:
        click.echo(f"❌ Output directory is not writable: {output_dir}", err=True)
        click.echo(f"   Error: {e}", err=True)
        sys.exit(1)

    # Generate contexts for each group
    async def _generate_contexts() -> dict[str, Any]:
        click.echo("\n📝 Generating contexts...", err=True)
        all_results = {}

        async def process_group(group_name: str, group_files: list[Path]) -> dict[str, Any]:
            """Process a single group."""
            group_output_dir = output_dir / group_name
            group_output_dir.mkdir(parents=True, exist_ok=True)

            results = []
            for file_path in group_files:
                result = await generate_context(file_path, group_output_dir)
                results.append(result)
                status = "✅" if result["success"] else "❌"
                click.echo(f"  {status} {file_path}", err=True)

            return {
                "group": group_name,
                "files": [str(f) for f in group_files],
                "results": results,
                "success_count": sum(1 for r in results if r["success"]),
                "total_count": len(results),
            }

        # Process groups sequentially to avoid overwhelming the system
        for group_name, group_files in groups.items():
            click.echo(f"\n📁 Processing group: {group_name}", err=True)
            group_results = await process_group(group_name, group_files)
            all_results[group_name] = group_results
            click.echo(
                f"   Completed: {group_results['success_count']}/{group_results['total_count']} files",
                err=True,
            )

        return all_results

    all_results = asyncio.run(_generate_contexts())

    # Save summary
    summary_file = output_dir / "generation_summary.json"
    summary = {
        "total_groups": len(groups),
        "groups": all_results,
        "settings": {
            "project_root": str(project_root),
            "output_dir": str(output_dir),
            "review_enabled": review,
            "gitignore_enabled": not no_gitignore,
            "group_by": group_by,
        },
    }
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    click.echo("\n✅ Context generation complete!")
    click.echo(f"   Summary saved to: {summary_file}")

    # Print overall statistics
    total_files = sum(len(files) for files in groups.values())
    total_success = sum(r["success_count"] for r in all_results.values())
    click.echo(f"   Total files: {total_files}")
    click.echo(f"   Successful: {total_success}")
    click.echo(f"   Failed: {total_files - total_success}")
    click.echo("\n💡 Context files are ready for review.")
    if not review:
        click.echo("   Use --review flag to also run automated reviews via council review command.")

    # Run reviews if explicitly requested
    if review:

        async def _run_reviews() -> None:
            click.echo("\n🔍 Running reviews...", err=True)
            review_results = {}

            async def review_group(group_name: str, group_files: list[Path]) -> dict[str, Any]:
                """Review all files in a group."""
                results = []
                for file_path in group_files:
                    result = await run_review(file_path)
                    results.append(result)
                    status = "✅" if result["success"] else "❌"
                    click.echo(f"  {status} {file_path}", err=True)

                return {
                    "group": group_name,
                    "files": [str(f) for f in group_files],
                    "results": results,
                    "success_count": sum(1 for r in results if r["success"]),
                    "total_count": len(results),
                }

            for group_name, group_files in groups.items():
                click.echo(f"\n📁 Reviewing group: {group_name}", err=True)
                group_review_results = await review_group(group_name, group_files)
                review_results[group_name] = group_review_results
                click.echo(
                    f"   Completed: {group_review_results['success_count']}/{group_review_results['total_count']} files",
                    err=True,
                )

            # Save review summary
            review_summary_file = output_dir / "review_summary.json"
            review_summary = {
                "total_groups": len(groups),
                "groups": review_results,
            }
            review_summary_file.write_text(json.dumps(review_summary, indent=2), encoding="utf-8")
            click.echo("\n✅ Review complete!")
            click.echo(f"   Review summary saved to: {review_summary_file}")

        asyncio.run(_run_reviews())
