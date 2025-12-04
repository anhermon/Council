"""Housekeeping command - comprehensive codebase maintenance."""

import ast
import asyncio
import re
import subprocess
from pathlib import Path

import click

from ...agents import CouncilDeps, get_councilor_agent
from ...config import settings
from ..ui.spinner import Spinner
from ..ui.streaming import create_event_stream_handler


async def _agent_edit_file(file_path: Path, instruction: str, spinner: Spinner) -> tuple[bool, str]:
    """
    Use the agent to edit a file based on instructions.

    Args:
        file_path: Path to the file to edit
        instruction: Instruction for what the agent should do
        spinner: Spinner instance for status updates

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        agent = get_councilor_agent()
        event_handler = create_event_stream_handler(spinner)

        # Read current file content
        current_content = file_path.read_text(encoding="utf-8")

        # For very large files, truncate content in prompt to avoid token limits
        # The agent can use read_file tool to get full content if needed
        MAX_PROMPT_CONTENT = 50000  # ~50k chars to leave room for tool calls
        content_preview = (
            current_content[:MAX_PROMPT_CONTENT]
            if len(current_content) > MAX_PROMPT_CONTENT
            else current_content
        )
        content_truncated = len(current_content) > MAX_PROMPT_CONTENT

        # Create prompt for the agent
        truncation_note = (
            "\n\nNote: File content is truncated in this prompt. Use the read_file tool to get the full content before making changes."
            if content_truncated
            else ""
        )

        # Determine if file is large enough to need chunked writes
        file_size = len(current_content)
        use_chunked_writes = file_size > 100000  # 100KB threshold

        chunked_write_note = (
            "\n\nIMPORTANT: This file is large. Use write_file_chunk tool instead of write_file to write it in chunks. "
            "Split the modified content into chunks of ~50KB each and write them sequentially using write_file_chunk "
            "with chunk_index (0-based) and total_chunks parameters."
            if use_chunked_writes
            else ""
        )

        prompt = f"""You are performing housekeeping on this file. {instruction}

Current file content:
```python
{content_preview}
```{truncation_note}{chunked_write_note}

Please read the file using read_file tool first (to get full content if truncated), make the requested changes, and write the updated content back to the file.
{"Use write_file_chunk tool for large files (split into ~50KB chunks)." if use_chunked_writes else "Use write_file tool for small files."}
Only make the changes requested - do not make other modifications unless they are clearly necessary for the requested change."""

        deps = CouncilDeps(file_path=str(file_path), extra_instructions=instruction)

        async with agent.run_stream(
            prompt, deps=deps, event_stream_handler=event_handler
        ) as agent_run:
            async for _ in agent_run.stream_output():
                pass
            await agent_run.get_output()

        return True, f"Successfully edited {file_path.name}"

    except Exception as e:
        error_str = str(e).lower()
        # Check if this is a Bedrock tool call serialization error
        is_bedrock_error = (
            "bedrock" in error_str
            or "tool call" in error_str
            or "jsondecodeerror" in error_str
            or "expecting" in error_str
            or "unable to convert" in error_str
        )

        if is_bedrock_error:
            # Fallback: Use text-based approach - ask agent to provide modified content in response
            click.echo(
                "    ⚠️  Bedrock tool call issue detected, using text fallback method...",
                err=True,
            )
            try:
                agent = get_councilor_agent()
                event_handler = create_event_stream_handler(spinner)

                # Read current file content
                current_content = file_path.read_text(encoding="utf-8")
                MAX_PROMPT_CONTENT = 50000
                content_preview = (
                    current_content[:MAX_PROMPT_CONTENT]
                    if len(current_content) > MAX_PROMPT_CONTENT
                    else current_content
                )
                content_truncated = len(current_content) > MAX_PROMPT_CONTENT

                truncation_note = (
                    "\n\nNote: File content is truncated. Please use read_file tool to get full content first."
                    if content_truncated
                    else ""
                )

                prompt = f"""You are performing housekeeping on this file. {instruction}

Current file content:
```python
{content_preview}
```{truncation_note}

IMPORTANT: Due to technical limitations with tool calls, please provide the COMPLETE modified file content in a code block in your response.
Read the file using read_file tool first if needed to get the full content, then provide the entire modified file in a ```python code block.
Only make the changes requested - do not make other modifications unless clearly necessary."""

                deps = CouncilDeps(file_path=str(file_path), extra_instructions=instruction)

                async with agent.run_stream(
                    prompt, deps=deps, event_stream_handler=event_handler
                ) as agent_run:
                    # Collect text parts from stream
                    text_parts = []
                    async for part in agent_run.stream_output():
                        if hasattr(part, "text") and part.text:
                            text_parts.append(part.text)

                    result = await agent_run.get_output()

                # Extract code block from response
                full_response = "".join(text_parts)

                # Try to get text from result if available
                if (
                    hasattr(result, "data")
                    and isinstance(result.data, dict)
                    and "text" in result.data
                ):
                    full_response += result.data["text"]

                # Extract Python code block
                code_block_pattern = r"```python\s*\n(.*?)```"
                matches = re.findall(code_block_pattern, full_response, re.DOTALL)
                if not matches:
                    # Try without language tag
                    code_block_pattern = r"```\s*\n(.*?)```"
                    matches = re.findall(code_block_pattern, full_response, re.DOTALL)

                if matches:
                    # Use the largest code block (likely the full file)
                    modified_content = max(matches, key=len).strip()
                    # Write the modified content
                    file_path.write_text(modified_content, encoding="utf-8")
                    return True, f"Successfully edited {file_path.name} (using text fallback)"
                else:
                    return (
                        False,
                        "Could not extract code block from agent response - no code blocks found",
                    )

            except Exception as fallback_error:
                return False, f"Fallback also failed: {str(fallback_error)[:200]}"
        else:
            return False, f"Failed to edit {file_path.name}: {str(e)[:200]}"


@click.command()
def housekeeping() -> None:
    """Execute comprehensive codebase maintenance and cleanup following a structured 4-phase protocol."""
    project_root = settings.project_root.resolve()
    gitignore_path = project_root / ".gitignore"

    # Get project name early (used in multiple phases)
    pyproject_path = project_root / "pyproject.toml"
    project_name = "The Council"
    python_version = "3.12+"
    if pyproject_path.exists():
        try:
            # Try standard library tomllib first (Python 3.11+)
            try:
                import tomllib  # noqa: F401
            except ImportError:
                # Fall back to tomli if available
                try:
                    import tomli as tomllib  # type: ignore[no-redef]
                except ImportError:
                    tomllib = None

            if tomllib:
                with pyproject_path.open("rb") as f:
                    pyproject_data = tomllib.load(f)
                    if "project" in pyproject_data:
                        project_name = pyproject_data["project"].get("name", project_name)
                        if "requires-python" in pyproject_data["project"]:
                            python_version = pyproject_data["project"]["requires-python"]
        except Exception:
            pass  # Use defaults if parsing fails

    click.echo("🧹 Starting Agent Housekeeping Protocol...\n", err=True)
    click.echo("=" * 80, err=True)
    click.echo("Phase 1: Hygiene & Safety (The 'Sweep')", err=True)
    click.echo("=" * 80 + "\n", err=True)

    # Phase 1.1: Gitignore Audit
    click.echo("📋 Phase 1.1: Gitignore Audit", err=True)
    gitignore_additions: list[str] = []
    gitignore_content = gitignore_path.read_text() if gitignore_path.exists() else ""

    # Scan for common untracked files that should be ignored
    patterns_to_check = {
        ".env.local": ".env.local",
        ".env.*.local": ".env.*.local",
        "*.swp": "*.swp",
        "*.swo": "*.swo",
        "*~": "*~",
        ".DS_Store": ".DS_Store",
        "Thumbs.db": "Thumbs.db",
        "*.log": "*.log",
        "*.tmp": "*.tmp",
        "*.temp": "*.temp",
        "__pycache__": "__pycache__/",
        ".pytest_cache": ".pytest_cache/",
        ".mypy_cache": ".mypy_cache/",
        ".ruff_cache": ".ruff_cache/",
        "node_modules": "node_modules/",
        ".next": ".next/",
        "dist": "dist/",
        "build": "build/",
    }

    for _pattern, addition in patterns_to_check.items():
        if addition not in gitignore_content:
            gitignore_additions.append(addition)

    if gitignore_additions:
        click.echo(f"  ➕ Adding {len(gitignore_additions)} patterns to .gitignore", err=True)
        with gitignore_path.open("a") as f:
            f.write("\n# Added by housekeeping\n")
            for addition in gitignore_additions:
                f.write(f"{addition}\n")
                click.echo(f"    ✓ {addition}", err=True)
    else:
        click.echo("  ✅ .gitignore is up to date", err=True)

    # Phase 1.2: Root Directory Cleanup
    click.echo("\n📁 Phase 1.2: Root Directory Cleanup", err=True)
    root_files_to_delete: list[Path] = []
    standard_files = {
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "docker-compose.yml",
        "Dockerfile",
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        ".eslintrc",
        ".eslintrc.json",
        ".eslintrc.js",
        ".prettierrc",
        "tsconfig.json",
        ".gitignore",
        ".env",
        ".env.example",
        "uv.lock",
    }

    for item in project_root.iterdir():
        if (
            item.is_file()
            and item.name not in standard_files
            and item.suffix in (".tmp", ".temp", ".log", ".bak")
        ):
            root_files_to_delete.append(item)
            click.echo(f"  🗑️  Will delete: {item.name}", err=True)

    if root_files_to_delete:
        for file_path in root_files_to_delete:
            try:
                file_path.unlink()
                click.echo(f"    ✓ Deleted {file_path.name}", err=True)
            except Exception as e:
                click.echo(f"    ⚠️  Failed to delete {file_path.name}: {e}", err=True)
    else:
        click.echo("  ✅ No temporary files found in root", err=True)

    # Phase 1.3: Dead Code Removal
    click.echo("\n🔍 Phase 1.3: Dead Code Removal", err=True)
    source_files = list((project_root / "src").rglob("*.py"))
    files_with_commented_code: list[Path] = []

    for file_path in source_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")

            # Check for large commented-out code blocks (not docstrings)
            in_multiline_string = False
            multiline_string_char = None
            found_commented_block = False

            for i, line in enumerate(lines):
                stripped = line.strip()
                # Skip docstrings
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    if not in_multiline_string:
                        in_multiline_string = True
                        multiline_string_char = stripped[:3]
                    elif stripped.startswith(multiline_string_char):
                        in_multiline_string = False
                        multiline_string_char = None
                    continue

                if in_multiline_string:
                    continue

                # Look for commented-out code blocks (3+ consecutive commented lines)
                if stripped.startswith("#") and len(stripped) > 1 and i + 2 < len(lines):
                    # Check if next 2 lines are also comments
                    next_two_comments = all(
                        line.strip().startswith("#") and len(line.strip()) > 1
                        for line in lines[i + 1 : i + 3]
                    )
                    if next_two_comments:
                        found_commented_block = True
                        break

            if found_commented_block:
                files_with_commented_code.append(file_path)

        except Exception as e:
            click.echo(
                f"    ⚠️  Error analyzing {file_path.relative_to(project_root)}: {e}", err=True
            )

    if files_with_commented_code:
        click.echo(
            f"  🔧 Found {len(files_with_commented_code)} file(s) with commented code blocks",
            err=True,
        )
        click.echo("  🤖 Using AI agent to remove commented code...", err=True)

        spinner = Spinner()
        spinner_task = None
        if spinner.enabled:
            spinner_task = asyncio.create_task(spinner.run())

        async def _remove_commented_code():
            edited_count = 0
            for file_path in files_with_commented_code:
                rel_path = file_path.relative_to(project_root)
                click.echo(f"    📝 Processing {rel_path}...", err=True)
                success, message = await _agent_edit_file(
                    file_path,
                    "Remove all commented-out code blocks (3+ consecutive commented lines). Keep docstrings and single-line explanatory comments. Only remove actual commented code.",
                    spinner,
                )
                if success:
                    edited_count += 1
                    click.echo(f"      ✓ {message}", err=True)
                else:
                    click.echo(f"      ⚠️  {message}", err=True)
            return edited_count

        try:
            edited_count = asyncio.run(_remove_commented_code())
            if spinner_task:
                spinner.stop()
                if not spinner_task.done():
                    spinner_task.cancel()
            click.echo(f"  ✅ Removed commented code from {edited_count} file(s)", err=True)
        except Exception as e:
            if spinner_task:
                spinner.stop()
                if not spinner_task.done():
                    spinner_task.cancel()
            click.echo(f"  ⚠️  Error during commented code removal: {e}", err=True)
    else:
        click.echo("  ✅ No commented code blocks found", err=True)

    click.echo("\n" + "=" * 80, err=True)
    click.echo("✅ Phase 1 Complete", err=True)
    click.echo("=" * 80 + "\n", err=True)

    # Phase 2: Standardization & Quality
    click.echo("=" * 80, err=True)
    click.echo("Phase 2: Standardization & Quality", err=True)
    click.echo("=" * 80 + "\n", err=True)

    # Phase 2.1: Linting & Formatting
    click.echo("🔧 Phase 2.1: Linting & Formatting", err=True)

    # Check for Ruff (Python linter/formatter)
    try:
        result = subprocess.run(
            ["uv", "run", "ruff", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            click.echo("  ✓ Ruff detected", err=True)
            # Run ruff check --fix
            click.echo("  🔧 Running ruff check --fix...", err=True)
            result = subprocess.run(
                ["uv", "run", "ruff", "check", "--fix", "src/"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                click.echo("    ✅ Ruff check completed", err=True)
            else:
                click.echo(f"    ⚠️  Ruff found issues: {result.stdout[:200]}", err=True)

            # Run ruff format
            click.echo("  🎨 Running ruff format...", err=True)
            result = subprocess.run(
                ["uv", "run", "ruff", "format", "src/"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                click.echo("    ✅ Ruff format completed", err=True)
            else:
                click.echo(f"    ⚠️  Ruff format issues: {result.stdout[:200]}", err=True)
        else:
            click.echo("  ⚠️  Ruff not available", err=True)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        click.echo(f"  ⚠️  Could not run Ruff: {e}", err=True)

    # Phase 2.2: DRY Scan (simplified - just report potential duplicates)
    click.echo("\n🔄 Phase 2.2: DRY Scan", err=True)
    click.echo("  ℹ️  DRY analysis requires manual review", err=True)
    click.echo("  💡 Consider using tools like jscpd or pydup for detailed analysis", err=True)

    click.echo("\n" + "=" * 80, err=True)
    click.echo("✅ Phase 2 Complete", err=True)
    click.echo("=" * 80 + "\n", err=True)

    # Phase 3: Documentation Alignment
    click.echo("=" * 80, err=True)
    click.echo("Phase 3: Documentation Alignment", err=True)
    click.echo("=" * 80 + "\n", err=True)

    # Phase 3.1: Docstring Audit
    click.echo("📝 Phase 3.1: Docstring Audit", err=True)
    files_needing_docstrings: list[Path] = []
    functions_without_docs = 0

    for file_path in source_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))
            file_needs_docs = False
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                    and not ast.get_docstring(node)
                    and not node.name.startswith("_")
                ):
                    # Public function without docstring
                    functions_without_docs += 1
                    file_needs_docs = True
            if file_needs_docs and file_path not in files_needing_docstrings:
                files_needing_docstrings.append(file_path)
        except Exception:
            pass  # Skip files that can't be parsed

    if files_needing_docstrings:
        click.echo(
            f"  🔧 Found {functions_without_docs} public functions without docstrings in {len(files_needing_docstrings)} file(s)",
            err=True,
        )
        click.echo("  🤖 Using AI agent to add docstrings...", err=True)

        spinner = Spinner()
        spinner_task = None
        if spinner.enabled:
            spinner_task = asyncio.create_task(spinner.run())

        async def _add_docstrings():
            edited_count = 0
            for file_path in files_needing_docstrings:
                rel_path = file_path.relative_to(project_root)
                click.echo(f"    📝 Processing {rel_path}...", err=True)
                success, message = await _agent_edit_file(
                    file_path,
                    "Add docstrings to all public functions and classes that are missing them. Docstrings should follow Google-style format and describe what the function/class does, its parameters, and return values.",
                    spinner,
                )
                if success:
                    edited_count += 1
                    click.echo(f"      ✓ {message}", err=True)
                else:
                    click.echo(f"      ⚠️  {message}", err=True)
            return edited_count

        try:
            edited_count = asyncio.run(_add_docstrings())
            if spinner_task:
                spinner.stop()
                if not spinner_task.done():
                    spinner_task.cancel()
            click.echo(f"  ✅ Added docstrings to {edited_count} file(s)", err=True)
        except Exception as e:
            if spinner_task:
                spinner.stop()
                if not spinner_task.done():
                    spinner_task.cancel()
            click.echo(f"  ⚠️  Error during docstring addition: {e}", err=True)
    else:
        click.echo("  ✅ All public functions have docstrings", err=True)

    # Phase 3.2: README Reality Check
    click.echo("\n📖 Phase 3.2: README Reality Check", err=True)
    readme_path = project_root / "README.md"

    if readme_path.exists():
        readme_content = readme_path.read_text()
        # Check if README mentions the correct commands
        has_cli_commands = "uv run council" in readme_content or "council review" in readme_content
        has_uv_sync = "uv sync" in readme_content
        has_housekeeping = "housekeeping" in readme_content.lower()
        has_context = "context" in readme_content.lower()

        if not has_cli_commands or not has_uv_sync or not has_housekeeping or not has_context:
            click.echo("  🔧 README needs updates", err=True)
            if not has_cli_commands:
                click.echo("    - Missing CLI command examples", err=True)
            if not has_uv_sync:
                click.echo("    - Missing uv sync in setup instructions", err=True)
            if not has_housekeeping:
                click.echo("    - Missing housekeeping command documentation", err=True)
            if not has_context:
                click.echo("    - Missing context command documentation", err=True)

            click.echo("  🤖 Using AI agent to update README...", err=True)

            spinner = Spinner()
            spinner_task = None
            if spinner.enabled:
                spinner_task = asyncio.create_task(spinner.run())

            async def _update_readme():
                success, message = await _agent_edit_file(
                    readme_path,
                    "Update the README to ensure it includes: 1) All CLI commands (review, learn, context, housekeeping) with examples, 2) uv sync in setup instructions, 3) Housekeeping command documentation, 4) Context command documentation. Verify all commands and setup steps are accurate and match the actual implementation.",
                    spinner,
                )
                return success, message

            try:
                success, message = asyncio.run(_update_readme())
                if spinner_task:
                    spinner.stop()
                    if not spinner_task.done():
                        spinner_task.cancel()
                if success:
                    click.echo(f"  ✅ {message}", err=True)
                else:
                    click.echo(f"  ⚠️  {message}", err=True)
            except Exception as e:
                if spinner_task:
                    spinner.stop()
                    if not spinner_task.done():
                        spinner_task.cancel()
                click.echo(f"  ⚠️  Error updating README: {e}", err=True)
        else:
            click.echo("  ✅ README is up to date", err=True)
    else:
        click.echo("  ⚠️  README.md not found - creating it...", err=True)
        # Create a basic README using the agent
        spinner = Spinner()
        spinner_task = None
        if spinner.enabled:
            spinner_task = asyncio.create_task(spinner.run())

        async def _create_readme():
            # Read project context to understand the project
            context_path = project_root / "ai_docs" / "project_context.md"
            context_content = ""
            if context_path.exists():
                context_content = context_path.read_text()

            initial_readme = f"""# {project_name}

AI-powered code review agent.

## Setup

1. Install dependencies: `uv sync`
2. Configure API keys in `.env` file
3. Run: `uv run council review <file_path>`

## Commands

- `uv run council review <file_path>` - Review code
- `uv run council learn <url> <topic>` - Learn from documentation
- `uv run council context <file_path>` - Get review context for external agents
- `uv run council housekeeping` - Run maintenance protocol
"""

            readme_path.write_text(initial_readme, encoding="utf-8")
            success, message = await _agent_edit_file(
                readme_path,
                f"Create a comprehensive README.md based on this project context: {context_content[:2000]}. Include setup instructions, all CLI commands with examples, and project overview.",
                spinner,
            )
            return success, message

        try:
            success, message = asyncio.run(_create_readme())
            if spinner_task:
                spinner.stop()
                if not spinner_task.done():
                    spinner_task.cancel()
            if success:
                click.echo(f"  ✅ {message}", err=True)
            else:
                click.echo(f"  ⚠️  {message}", err=True)
        except Exception as e:
            if spinner_task:
                spinner.stop()
                if not spinner_task.done():
                    spinner_task.cancel()
            click.echo(f"  ⚠️  Error creating README: {e}", err=True)

    click.echo("\n" + "=" * 80, err=True)
    click.echo("✅ Phase 3 Complete", err=True)
    click.echo("=" * 80 + "\n", err=True)

    # Phase 4: The "Mental Map"
    click.echo("=" * 80, err=True)
    click.echo("Phase 4: The 'Mental Map'", err=True)
    click.echo("=" * 80 + "\n", err=True)

    click.echo("🗺️  Phase 4.1: Creating Project Mental Map", err=True)

    # Ensure ai_docs directory exists
    ai_docs_dir = project_root / "ai_docs"
    ai_docs_dir.mkdir(exist_ok=True)

    # Generate project context
    context_content = f"""# Project Mental Map

## 1. Purpose & Core Logic

The Council is an AI-powered code review agent. It uses Repomix to extract comprehensive code context, Pydantic-AI for structured AI outputs, and Jina Reader to learn from documentation. The agent performs automated code reviews with severity assessments, issue detection, and suggested fixes. It can dynamically learn coding standards from documentation URLs and apply them to future reviews.

## 2. Tech Stack & Key Libraries

- Language: Python {python_version}
- Frameworks:
  - Pydantic-AI (type-safe AI agent framework)
  - Click (CLI framework)
- Key DB/Services: None (file-based knowledge storage)
- Critical Libs:
  - `repomix` (via uvx) - Code context extraction
  - `httpx` - HTTP client for Jina Reader API
  - `logfire` - Structured logging
  - `jinja2` - Template engine for system prompts
  - `python-dotenv` - Environment variable management

## 3. Architecture & Key Patterns

- **Architecture:** CLI-based agent review system
  - CLI Layer: Click commands (review, learn, context, housekeeping)
  - Logic Layer: Pydantic-AI agent (`councilor.py`) performs reviews
  - Context Layer: Repomix wrapper extracts code context as XML
  - Knowledge Layer: Jina Reader fetches docs, stored in `knowledge/` directory
- **State Management:** Stateless agent with lazy initialization (thread-safe singleton pattern)
- **Auth Pattern:** API keys via environment variables (OpenAI, LiteLLM proxy, or direct providers)

## 4. Operational Context

- **Run Locally:**
  - CLI Review: `uv run council review <file_path> [options]`
  - Learn Rules: `uv run council learn <url> <topic>`
  - Get Context: `uv run council context <file_path>` - Output review context for external agents
  - Housekeeping: `uv run council housekeeping`
- **Run Tests:** (Not yet implemented - placeholder in README)
- **Build/Deploy:**
  - Install: `uv sync`
  - Package: Standard Python packaging via `pyproject.toml` (hatchling backend)

## 5. File Structure Map

```
council/
├── pyproject.toml          # Project config, dependencies, Ruff linting config
├── README.md               # User-facing documentation
├── .gitignore              # Git ignore patterns
├── knowledge/              # Dynamic knowledge base (markdown files loaded into prompts)
│   └── .keep
├── ai_docs/                # AI agent context documentation
│   └── project_context.md  # This file
└── src/
    └── council/
        ├── __init__.py     # Package init, version
        ├── cli/
        │   ├── main.py     # Main CLI entry point
        │   ├── commands/   # CLI commands (review, learn, context, housekeeping)
        │   ├── core/       # Core review execution and context building
        │   ├── ui/         # UI components (spinner, streaming, output)
        │   └── utils/      # Utility functions (paths, errors)
        ├── config.py       # Settings management, path resolution, env vars
        ├── templates/
        │   └── system_prompt.j2  # Jinja2 template for agent system prompt
        ├── agents/
        │   ├── __init__.py        # Agent exports
        │   └── councilor.py       # Core Pydantic-AI agent, model creation, knowledge loading
        └── tools/
            ├── __init__.py        # Tool exports
            ├── context.py         # Repomix wrapper, path validation, XML security checks
            ├── git_tools.py       # Git integration (diff, history, uncommitted files)
            └── scribe.py          # Jina Reader wrapper, URL validation, SSRF protection
```

## 6. Known Gotchas & Debugging

- **API Key Configuration:** Must set either `OPENAI_API_KEY` for direct providers OR `LITELLM_BASE_URL` + `LITELLM_API_KEY` for proxy. The `COUNCIL_MODEL` environment variable is required and must be set to specify which model to use. No hardcoded defaults - all configuration must come from environment variables.
- **Path Resolution:** Project root is auto-detected from `config.py` location. Can override with `COUNCIL_PROJECT_ROOT` env var if needed. Paths are validated for security (no path traversal, must be within project root or CWD).
- **Knowledge Base:** Markdown files in `knowledge/` are loaded alphabetically and injected into system prompt as "RULESET" sections. Files are loaded dynamically on each agent run.
- **Repomix Integration:** Runs via `uvx repomix` subprocess. Uses temporary XML files for output. Timeout is configurable via `COUNCIL_SUBPROCESS_TIMEOUT` (default 300s).
- **Template Loading:** Templates directory is resolved via `__file__` path or `importlib.resources` fallback. Must exist or runtime error occurs.
- **Security:** Extensive validation for path traversal, SSRF (URL validation), XXE (XML security checks), and command injection prevention in all user inputs.
- **Code Quality:** Project uses Ruff for linting and formatting. Run `uv run ruff check --fix src/` and `uv run ruff format src/` to maintain code quality. All linting issues should be resolved before committing.
- **Configuration Separation:** No user-specific configuration values should be hardcoded in the repository. All model names, API endpoints, and other user-specific settings must come from environment variables.
- **Uncommitted Reviews:** Use `--uncommitted` flag to review only files with uncommitted changes. This is useful for pre-commit reviews.
- **Context Command:** Use `council context <file_path>` to get review context (code, prompt, knowledge) for external agents to perform reviews without Council's LLM.
"""

    context_file = ai_docs_dir / "project_context.md"
    context_file.write_text(context_content, encoding="utf-8")
    click.echo(f"  ✅ Updated {context_file.relative_to(project_root)}", err=True)

    click.echo("\n" + "=" * 80, err=True)
    click.echo("✅ Phase 4 Complete", err=True)
    click.echo("=" * 80 + "\n", err=True)

    click.echo("🎉 Housekeeping protocol complete!", err=True)
    click.echo("\n💡 Next steps:", err=True)
    click.echo("  - Review the changes made in Phase 1", err=True)
    click.echo("  - Check linting/formatting results from Phase 2", err=True)
    click.echo("  - Verify documentation updates from Phase 3", err=True)
    click.echo("  - Review the updated project context in ai_docs/project_context.md", err=True)
