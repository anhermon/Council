"""Knowledge acquisition using Jina Reader."""

import asyncio
import contextlib
import ipaddress
import re
import time
from urllib.parse import urlparse

import httpx
import logfire

from ..config import get_settings

settings = get_settings()

# Private IP ranges and localhost patterns to block
PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("::1/128"),  # IPv6 localhost
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
]

# Blocked hostname patterns
BLOCKED_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",  # nosec B104 - This is a blocked hostname, not a binding address
    "::1",
}

# Topic validation constants
MAX_TOPIC_LENGTH = 100
MIN_TOPIC_LENGTH = 1

# Simple rate limiter state
_rate_limiter_lock = asyncio.Lock()
_rate_limiter_requests: list[float] = []  # Timestamps of recent requests


def validate_url(url: str) -> None:
    """
    Validate URL to prevent SSRF attacks.

    Args:
        url: URL to validate

    Raises:
        ValueError: If URL is invalid or contains security risks
    """
    # Parse the URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {e}") from e

    # Only allow http and https schemes
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http and https schemes are allowed, got: {parsed.scheme}")

    # Check if hostname is provided
    if not parsed.hostname:
        raise ValueError("URL must contain a hostname")

    hostname = parsed.hostname.lower()

    # Check against blocked hostname patterns
    if hostname in BLOCKED_HOSTNAMES:
        raise ValueError(f"Access to {hostname} is not allowed")

    # Check for localhost variations
    if hostname.startswith("localhost") or hostname.endswith(".localhost"):
        raise ValueError("Access to localhost is not allowed")

    # Check for private/internal domain patterns
    if any(
        pattern in hostname for pattern in [".local", ".internal", ".corp", ".lan", ".localdomain"]
    ):
        raise ValueError(f"Access to internal domain {hostname} is not allowed")

    # Try to resolve hostname to IP and check if it's a private IP
    ip = None
    with contextlib.suppress(ValueError):
        # Check if hostname is already an IP address
        ip = ipaddress.ip_address(hostname)

    if ip:
        # Check if it's in any private range
        for private_range in PRIVATE_IP_RANGES:
            if ip in private_range:
                raise ValueError(f"Access to private IP {hostname} is not allowed")

    # Additional validation: check for suspicious patterns
    if re.search(r"[@#]", url):
        raise ValueError("URL contains suspicious characters")

    # Validate URL length (prevent DoS)
    if len(url) > 2048:
        raise ValueError("URL exceeds maximum length of 2048 characters")


def validate_topic(topic: str) -> str:
    """
    Validate topic name to prevent path traversal and injection attacks.

    Args:
        topic: Topic name to validate

    Returns:
        Validated topic name

    Raises:
        ValueError: If topic contains invalid characters or is invalid length
    """
    if not topic:
        raise ValueError("Topic name cannot be empty")

    if len(topic) < MIN_TOPIC_LENGTH:
        raise ValueError(f"Topic name too short (minimum {MIN_TOPIC_LENGTH} character)")

    if len(topic) > MAX_TOPIC_LENGTH:
        raise ValueError(f"Topic name too long (maximum {MAX_TOPIC_LENGTH} characters)")

    # Only allow alphanumeric characters, underscores, and dashes
    if not re.match(r"^[a-zA-Z0-9_-]+$", topic):
        raise ValueError(
            "Topic name must contain only alphanumeric characters, underscores, and dashes"
        )

    # Prevent path traversal attempts
    if ".." in topic or "/" in topic or "\\" in topic:
        raise ValueError("Topic name cannot contain path traversal characters (.., /, \\)")

    return topic


async def _check_rate_limit() -> None:
    """
    Check and enforce rate limiting for external API calls.

    Uses a simple token bucket algorithm to limit requests per time window.

    Note: The rate limiter state is stored in memory and resets on application restart.
    This means that immediately after a restart, the rate limiter won't remember recent
    requests and may allow bursts that exceed API limits. This is an acceptable trade-off
    for simplicity - implementing persistent state would require disk I/O and state management
    complexity. For production deployments with strict rate limit requirements, consider
    using an external rate limiting service or implementing persistent state storage.
    """
    global _rate_limiter_requests

    async with _rate_limiter_lock:
        current_time = time.time()

        # Remove requests outside the time window
        _rate_limiter_requests = [
            req_time
            for req_time in _rate_limiter_requests
            if current_time - req_time < settings.scribe_rate_limit_window
        ]

        # Check if we've exceeded the rate limit
        if len(_rate_limiter_requests) >= settings.scribe_rate_limit_requests:
            # Calculate wait time until the oldest request expires
            oldest_request = min(_rate_limiter_requests)
            wait_time = settings.scribe_rate_limit_window - (current_time - oldest_request) + 1

            logfire.warning(
                "Rate limit exceeded, waiting before next request",
                wait_seconds=wait_time,
                current_requests=len(_rate_limiter_requests),
                limit=settings.scribe_rate_limit_requests,
            )

            # Wait until we can make another request
            await asyncio.sleep(wait_time)

            # Clean up again after waiting
            current_time = time.time()
            _rate_limiter_requests = [
                req_time
                for req_time in _rate_limiter_requests
                if current_time - req_time < settings.scribe_rate_limit_window
            ]

        # Record this request
        _rate_limiter_requests.append(time.time())


async def fetch_and_summarize(url: str, topic: str) -> str:
    """
    Fetch documentation from URL using Jina Reader and save to knowledge base.

    Args:
        url: URL to fetch documentation from
        topic: Topic name for the knowledge file (will be saved as {topic}.md)

    Returns:
        Confirmation message

    Raises:
        ValueError: If the URL is invalid or contains security risks
        httpx.HTTPError: If the HTTP request fails
    """
    logfire.info("Fetching knowledge", url=url, topic=topic)

    # Validate URL to prevent SSRF attacks
    validate_url(url)

    # Validate topic to prevent path traversal
    validated_topic = validate_topic(topic)

    # Check rate limit before making external API call
    await _check_rate_limit()

    # Ensure knowledge directory exists
    settings.knowledge_dir.mkdir(parents=True, exist_ok=True)

    # Construct Jina Reader URL
    jina_url = f"https://r.jina.ai/{url}"

    # Fetch the content with configurable timeout
    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        try:
            response = await client.get(jina_url)
            response.raise_for_status()
            markdown_content = response.text
        except httpx.HTTPError as e:
            logfire.error("Failed to fetch from Jina Reader", url=jina_url, error=str(e))
            raise

    # Save to knowledge base (use validated topic)
    knowledge_file = settings.knowledge_dir / f"{validated_topic}.md"
    knowledge_file.write_text(markdown_content, encoding="utf-8")

    logfire.info("Knowledge saved", file=str(knowledge_file), size=len(markdown_content))

    return f"Knowledge base updated: {validated_topic}"
