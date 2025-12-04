"""Git commit command with LibreChat-style commit messages."""

import asyncio
import subprocess
import sys

import click

from ...tools.git_tools import get_uncommitted_files

# Emoji mapping for commit types
COMMIT_EMOJIS: dict[str, str] = {
    "feat": "🚀",
    "fix": "🐛",
    "docs": "📚",
    "style": "💄",
    "refactor": "♻️",
    "test": "🧪",
    "chore": "📦",
    "perf": "⚡",
    "ci": "👷",
    "build": "🔧",
    "revert": "⏪",
    "security": "🔐",
    "i18n": "🌍",
    "config": "⚙️",
    "deps": "📦",
    "ui": "🎨",
    "ux": "✨",
    "api": "🔌",
    "db": "🗃️",
    "docker": "🐳",
    "k8s": "☸️",
    "helm": "🪣",
    "merge": "🔀",
    "hotfix": "🚨",
    "wip": "🚧",
    "cleanup": "🧹",
    "init": "🎉",
    "deploy": "🚀",
    "release": "🏷️",
}


def get_commit_type_choices() -> list[str]:
    """Get available commit type choices."""
    return list(COMMIT_EMOJIS.keys())


def format_commit_message(commit_type: str, message: str, body: str | None = None) -> str:
    """Format commit message with emoji and type."""
    emoji = COMMIT_EMOJIS.get(commit_type, "📝")
    formatted_message = f"{emoji} {commit_type}: {message}"

    if body:
        formatted_message += f"\n\n{body}"

    return formatted_message


async def get_staged_files() -> list[str]:
    """Get list of staged files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get staged files: {e}") from e


async def stage_files(files: list[str]) -> None:
    """Stage specified files."""
    try:
        subprocess.run(["git", "add"] + files, check=True)
        click.echo(f"✅ Staged {len(files)} file(s)", err=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to stage files: {e}") from e


async def create_commit(message: str) -> None:
    """Create git commit with formatted message."""
    try:
        subprocess.run(["git", "commit", "-m", message], check=True)
        click.echo("✅ Commit created successfully", err=True)
    except subprocess.CalledProcessError as e:
        if e.returncode == 1:
            # No changes to commit
            click.echo("⚠️ Nothing to commit, working tree clean", err=True)
        else:
            raise RuntimeError(f"Failed to create commit: {e}") from e


@click.command()
@click.option(
    "--type",
    "-t",
    "commit_type",
    type=click.Choice(get_commit_type_choices(), case_sensitive=False),
    required=True,
    help="Type of commit (determines emoji prefix)",
)
@click.option(
    "--message",
    "-m",
    required=True,
    help="Commit message description",
)
@click.option(
    "--body",
    "-b",
    help="Optional commit message body (additional details)",
)
@click.option(
    "--add",
    "-a",
    "add_files",
    multiple=True,
    help="Files to stage before committing (can be used multiple times)",
)
@click.option(
    "--all",
    "-A",
    "add_all",
    is_flag=True,
    help="Stage all modified files before committing",
)
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    help="Show what would be committed without actually creating the commit",
)
def commit(
    commit_type: str,
    message: str,
    body: str | None,
    add_files: tuple[str, ...],
    add_all: bool,
    dry_run: bool,
) -> None:
    """Create a git commit with LibreChat-style formatting.

    This command creates commits with emoji prefixes and consistent formatting
    following the LibreChat project style.

    Examples:
        council commit --type feat --message "Add user authentication"
        council commit -t fix -m "Fix login validation bug" -b "Resolves issue with empty password validation"
        council commit -t chore -m "Update dependencies" --add package.json --add package-lock.json
        council commit -t refactor -m "Restructure auth module" --all
    """

    async def _commit():
        try:
            # Check if we're in a git repository
            try:
                subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, check=True)
            except subprocess.CalledProcessError:
                click.echo("❌ Not in a git repository", err=True)
                sys.exit(1)

            # Stage files if requested
            if add_all:
                try:
                    uncommitted_files = await get_uncommitted_files()
                    if uncommitted_files:
                        await stage_files(uncommitted_files)
                    else:
                        click.echo("⚠️ No uncommitted files to stage", err=True)
                except Exception as e:
                    click.echo(f"❌ Failed to get uncommitted files: {e}", err=True)
                    sys.exit(1)
            elif add_files:
                await stage_files(list(add_files))

            # Get staged files to show what will be committed
            staged_files = await get_staged_files()

            if not staged_files:
                click.echo("❌ No staged changes to commit", err=True)
                click.echo(
                    "   Use --add to stage specific files or --all to stage all changes", err=True
                )
                sys.exit(1)

            # Format the commit message
            formatted_message = format_commit_message(commit_type, message, body)

            if dry_run:
                click.echo("🔍 Dry run - would commit the following:", err=True)
                click.echo(f"\nCommit message:\n{formatted_message}\n", err=True)
                click.echo("Staged files:", err=True)
                for file in staged_files:
                    click.echo(f"  📄 {file}", err=True)
                return

            # Show what will be committed
            click.echo("📝 Creating commit with:", err=True)
            click.echo(
                f"   Message: {formatted_message.split(chr(10))[0]}", err=True
            )  # First line only
            click.echo(f"   Files: {len(staged_files)} staged", err=True)

            # Create the commit
            await create_commit(formatted_message)

        except RuntimeError as e:
            click.echo(f"❌ {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Unexpected error: {e}", err=True)
            sys.exit(1)

    asyncio.run(_commit())
