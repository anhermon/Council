#!/usr/bin/env python3
"""Script to group files and generate review contexts."""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

# Define file groups according to the plan
FILE_GROUPS = {
    "core_entry_points": [
        "src/council/main.py",
        "src/council/config.py",
        "src/council/__init__.py",
    ],
    "agents": [
        "src/council/agents/councilor.py",
        "src/council/agents/__init__.py",
    ],
    "cli_commands": [
        "src/council/cli/commands/context.py",
        "src/council/cli/commands/review.py",
        "src/council/cli/commands/learn.py",
        "src/council/cli/commands/housekeeping.py",
        "src/council/cli/commands/__init__.py",
    ],
    "cli_core": [
        "src/council/cli/core/context_builder.py",
        "src/council/cli/core/review_executor.py",
        "src/council/cli/core/__init__.py",
    ],
    "cli_ui": [
        "src/council/cli/ui/output.py",
        "src/council/cli/ui/spinner.py",
        "src/council/cli/ui/streaming.py",
        "src/council/cli/ui/__init__.py",
    ],
    "cli_utils": [
        "src/council/cli/utils/constants.py",
        "src/council/cli/utils/errors.py",
        "src/council/cli/utils/paths.py",
        "src/council/cli/utils/validation.py",
        "src/council/cli/utils/__init__.py",
    ],
    "cli_main": [
        "src/council/cli/main.py",
        "src/council/cli/__init__.py",
    ],
    "database_tools": [
        "src/council/tools/db_file_discovery.py",
        "src/council/tools/db_relation_tracer.py",
        "src/council/tools/sql_parser.py",
    ],
    "code_analysis_tools": [
        "src/council/tools/code_analysis.py",
        "src/council/tools/architecture.py",
        "src/council/tools/static_analysis.py",
    ],
    "infrastructure_tools": [
        "src/council/tools/repomix.py",
        "src/council/tools/scribe.py",
        "src/council/tools/cache.py",
        "src/council/tools/persistence.py",
        "src/council/tools/git_tools.py",
    ],
    "metrics_debugging": [
        "src/council/tools/metrics_collector.py",
        "src/council/tools/metrics.py",
        "src/council/tools/debug.py",
    ],
    "security_testing": [
        "src/council/tools/security.py",
        "src/council/tools/testing.py",
    ],
    "utility_tools": [
        "src/council/tools/utils.py",
        "src/council/tools/validation.py",
        "src/council/tools/path_utils.py",
        "src/council/tools/exceptions.py",
        "src/council/tools/__init__.py",
    ],
    "core_parser": [
        "src/council/core/parser.py",
    ],
}


async def generate_context(file_path: str, output_dir: Path) -> dict[str, Any]:
    """Generate context for a single file."""
    file_name = Path(file_path).stem
    output_file = output_dir / f"{file_name}_context.md"

    try:
        # Run council context command
        result = subprocess.run(
            ["uv", "run", "council", "context", file_path, "--output", "markdown"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            # Save context to file
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(result.stdout, encoding="utf-8")
            return {
                "file": file_path,
                "success": True,
                "output_file": str(output_file),
                "error": None,
            }
        else:
            return {
                "file": file_path,
                "success": False,
                "output_file": None,
                "error": result.stderr or "Unknown error",
            }
    except subprocess.TimeoutExpired:
        return {
            "file": file_path,
            "success": False,
            "output_file": None,
            "error": "Timeout after 300 seconds",
        }
    except Exception as e:
        return {
            "file": file_path,
            "success": False,
            "output_file": None,
            "error": str(e),
        }


async def generate_contexts_for_group(
    group_name: str, files: list[str], base_dir: Path
) -> dict[str, Any]:
    """Generate contexts for all files in a group."""
    group_dir = base_dir / group_name
    group_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for file_path in files:
        if not Path(file_path).exists():
            results.append(
                {
                    "file": file_path,
                    "success": False,
                    "output_file": None,
                    "error": "File not found",
                }
            )
            continue

        result = await generate_context(file_path, group_dir)
        results.append(result)
        print(f"  {'✅' if result['success'] else '❌'} {file_path}")

    return {
        "group": group_name,
        "files": files,
        "results": results,
        "success_count": sum(1 for r in results if r["success"]),
        "total_count": len(results),
    }


async def main():
    """Main function to generate contexts for all groups."""
    project_root = Path(__file__).parent.parent
    contexts_dir = project_root / ".council" / "contexts"
    contexts_dir.mkdir(parents=True, exist_ok=True)

    print("📦 Generating review contexts for file groups...\n")

    all_results = {}

    for group_name, files in FILE_GROUPS.items():
        print(f"📁 Group: {group_name} ({len(files)} files)")
        group_results = await generate_contexts_for_group(group_name, files, contexts_dir)
        all_results[group_name] = group_results
        print(
            f"   Completed: {group_results['success_count']}/{group_results['total_count']} files\n"
        )

    # Save summary
    summary_file = contexts_dir / "generation_summary.json"
    summary = {
        "total_groups": len(FILE_GROUPS),
        "groups": all_results,
    }
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("✅ Context generation complete!")
    print(f"   Summary saved to: {summary_file}")

    # Print overall statistics
    total_files = sum(len(files) for files in FILE_GROUPS.values())
    total_success = sum(r["success_count"] for r in all_results.values())
    print(f"   Total files: {total_files}")
    print(f"   Successful: {total_success}")
    print(f"   Failed: {total_files - total_success}")


if __name__ == "__main__":
    asyncio.run(main())
