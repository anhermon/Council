"""Learn command - learn rules from documentation."""

import asyncio
import sys

import click

from ...tools.scribe import fetch_and_summarize, validate_topic, validate_url


@click.command()
@click.argument("url")
@click.argument("topic")
def learn(url: str, topic: str) -> None:
    """Learn rules from a documentation URL and add to knowledge base."""
    # Validate URL format and security using scribe.validate_url
    try:
        validate_url(url)
    except ValueError as e:
        click.echo(f"❌ Invalid URL: {e}", err=True)
        sys.exit(1)

    # Validate topic using scribe.validate_topic
    try:
        validated_topic = validate_topic(topic)
        topic = validated_topic  # Use validated topic
    except ValueError as e:
        click.echo(f"❌ Invalid topic: {e}", err=True)
        sys.exit(1)

    click.echo(f"📚 Learning from: {url}", err=True)
    click.echo(f"📝 Topic: {topic}", err=True)

    async def _learn() -> None:
        try:
            result = await fetch_and_summarize(url, topic)
            click.echo(f"✅ {result}")
        except (ValueError, TypeError, KeyError) as e:
            click.echo(f"❌ Configuration error: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Failed to learn rules: {e}", err=True)
            sys.exit(1)

    asyncio.run(_learn())
