from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from council.tools.scribe import fetch_and_summarize, validate_topic, validate_url


class TestValidateUrl:
    def test_valid_url(self):
        """Test valid URLs."""
        validate_url("https://example.com/docs")
        validate_url("http://api.service.com/v1/spec")
        validate_url("https://github.com/owner/repo")

    def test_invalid_scheme(self):
        """Test invalid URL schemes."""
        with pytest.raises(ValueError, match="Only http and https schemes are allowed"):
            validate_url("ftp://example.com")

        with pytest.raises(ValueError, match="Only http and https schemes are allowed"):
            validate_url("file:///etc/passwd")

    def test_localhost_blocked(self):
        """Test localhost blocking."""
        with pytest.raises(ValueError, match="Access to .* is not allowed"):
            validate_url("http://localhost:8000")

        with pytest.raises(ValueError, match="Access to .* is not allowed"):
            validate_url("http://127.0.0.1")

        with pytest.raises(ValueError, match="Access to .* is not allowed"):
            validate_url("http://[::1]")

    def test_private_ip_blocked(self):
        """Test private IP blocking."""
        with pytest.raises(ValueError, match="Access to private IP .* is not allowed"):
            validate_url("http://192.168.1.1")

        with pytest.raises(ValueError, match="Access to private IP .* is not allowed"):
            validate_url("http://10.0.0.1")

    def test_internal_domain_blocked(self):
        """Test internal domain blocking."""
        with pytest.raises(ValueError, match="Access to internal domain .* is not allowed"):
            validate_url("http://server.local")

        with pytest.raises(ValueError, match="Access to internal domain .* is not allowed"):
            validate_url("http://corp.internal")


class TestValidateTopic:
    def test_valid_topic(self):
        """Test valid topics."""
        assert validate_topic("python_best_practices") == "python_best_practices"
        assert validate_topic("react-patterns") == "react-patterns"
        assert validate_topic("v1_api_docs") == "v1_api_docs"

    def test_invalid_characters(self):
        """Test invalid characters in topic."""
        with pytest.raises(ValueError, match="Topic name must contain only alphanumeric"):
            validate_topic("my topic")

        with pytest.raises(ValueError, match="Topic name must contain only alphanumeric"):
            validate_topic("topic!")

    def test_path_traversal(self):
        """Test path traversal in topic."""
        # This hits the alphanumeric check first, which is fine as it blocks traversal chars too
        with pytest.raises(ValueError, match="Topic name must contain only alphanumeric"):
            validate_topic("../secret")

        with pytest.raises(ValueError, match="Topic name must contain only alphanumeric"):
            # This also hits alphanumeric check because / is not allowed
            validate_topic("dir/topic")


class TestFetchAndSummarize:
    """Test fetch_and_summarize function."""

    @pytest.mark.asyncio
    async def test_fetch_and_summarize_success(self, mock_settings):
        """Test successful knowledge fetching."""
        url = "https://example.com/docs"
        topic = "test_topic"
        mock_content = "# Documentation\n\nContent here"

        with patch("council.tools.scribe.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.text = mock_content
            mock_response.raise_for_status = AsyncMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await fetch_and_summarize(url, topic)
            assert "updated" in result.lower()
            assert topic in result

            # Verify file was saved
            knowledge_file = mock_settings.knowledge_dir / f"{topic}.md"
            assert knowledge_file.exists()

    @pytest.mark.asyncio
    async def test_fetch_and_summarize_invalid_url(self):
        """Test with invalid URL."""
        with pytest.raises(ValueError):
            await fetch_and_summarize("ftp://example.com", "topic")

    @pytest.mark.asyncio
    async def test_fetch_and_summarize_invalid_topic(self):
        """Test with invalid topic."""
        with pytest.raises(ValueError):
            await fetch_and_summarize("https://example.com", "invalid topic!")

    @pytest.mark.asyncio
    async def test_fetch_and_summarize_http_error(self):
        """Test handling of HTTP errors."""
        url = "https://example.com/docs"
        topic = "test_topic"

        with patch("council.tools.scribe.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            # raise_for_status should raise synchronously, not async
            mock_response.raise_for_status = MagicMock(side_effect=httpx.HTTPError("Not found"))
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(httpx.HTTPError):
                await fetch_and_summarize(url, topic)

    @pytest.mark.asyncio
    async def test_fetch_and_summarize_rate_limiting(self):
        """Test rate limiting is enforced."""
        url = "https://example.com/docs"
        topic = "test_topic"
        mock_content = "# Content"

        with patch("council.tools.scribe.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.text = mock_content
            mock_response.raise_for_status = AsyncMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            with patch("council.tools.scribe._check_rate_limit") as mock_rate_limit:
                mock_rate_limit.return_value = AsyncMock()
                await fetch_and_summarize(url, topic)
                # Rate limit should be checked
                assert mock_rate_limit.called

    @pytest.mark.asyncio
    async def test_fetch_and_summarize_creates_knowledge_dir(self, mock_settings):
        """Test that knowledge directory is created if it doesn't exist."""
        # Remove knowledge dir if it exists
        if mock_settings.knowledge_dir.exists():
            import shutil

            shutil.rmtree(mock_settings.knowledge_dir)

        url = "https://example.com/docs"
        topic = "test_topic"
        mock_content = "# Content"

        with patch("council.tools.scribe.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.text = mock_content
            mock_response.raise_for_status = AsyncMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            await fetch_and_summarize(url, topic)
            # Knowledge dir should be created
            assert mock_settings.knowledge_dir.exists()

    @pytest.mark.asyncio
    async def test_fetch_and_summarize_saves_content(self, mock_settings):
        """Test that fetched content is saved correctly."""
        url = "https://example.com/docs"
        topic = "test_topic"
        mock_content = "# Test Documentation\n\nThis is test content."

        with patch("council.tools.scribe.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.text = mock_content
            mock_response.raise_for_status = AsyncMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            await fetch_and_summarize(url, topic)

            # Verify content was saved
            knowledge_file = mock_settings.knowledge_dir / f"{topic}.md"
            assert knowledge_file.exists()
            assert knowledge_file.read_text() == mock_content
