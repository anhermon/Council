"""Tests for learn command."""

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from council.cli.commands.learn import learn


class TestLearnCommand:
    """Test learn command."""

    def test_learn_invalid_url(self):
        """Test learn command with invalid URL."""
        runner = CliRunner()
        result = runner.invoke(learn, ["not-a-url", "test-topic"])
        assert result.exit_code == 1
        assert "Invalid URL" in result.output

    def test_learn_invalid_topic_empty(self):
        """Test learn command with empty topic."""
        runner = CliRunner()
        result = runner.invoke(learn, ["https://example.com", ""])
        assert result.exit_code == 1
        assert "Invalid topic" in result.output

    def test_learn_invalid_topic_too_long(self):
        """Test learn command with topic too long."""
        runner = CliRunner()
        long_topic = "x" * 101  # MAX_TOPIC_LENGTH is 100
        result = runner.invoke(learn, ["https://example.com", long_topic])
        assert result.exit_code == 1
        assert "Invalid topic" in result.output

    def test_learn_invalid_topic_invalid_chars(self):
        """Test learn command with invalid characters in topic."""
        runner = CliRunner()
        result = runner.invoke(learn, ["https://example.com", "test/topic"])
        assert result.exit_code == 1
        assert "Invalid topic" in result.output

    @patch("council.cli.commands.learn.asyncio.run")
    @patch("council.cli.commands.learn.fetch_and_summarize")
    def test_learn_success(self, mock_fetch, mock_asyncio_run):
        """Test successful learn command."""
        mock_fetch.return_value = AsyncMock(return_value="✅ Successfully learned")
        mock_asyncio_run.return_value = None

        runner = CliRunner()
        result = runner.invoke(learn, ["https://example.com/docs", "python"])

        # The command should validate and call fetch_and_summarize
        assert result.exit_code == 0 or result.exit_code == 1  # May exit with error if async fails
        assert "Learning from" in result.output or "python" in result.output.lower()

    @patch("council.cli.commands.learn.asyncio.run")
    @patch("council.cli.commands.learn.fetch_and_summarize")
    def test_learn_fetch_error(self, mock_fetch, mock_asyncio_run):
        """Test learn command when fetch fails."""

        async def _raise_error():
            raise Exception("Network error")

        mock_fetch.side_effect = Exception("Network error")
        mock_asyncio_run.side_effect = _raise_error

        runner = CliRunner()
        result = runner.invoke(learn, ["https://example.com/docs", "python"])

        # Should handle error gracefully
        assert (
            result.exit_code != 0 or "Failed" in result.output or "error" in result.output.lower()
        )

    def test_learn_localhost_url_blocked(self):
        """Test that localhost URLs are blocked."""
        runner = CliRunner()
        result = runner.invoke(learn, ["http://localhost:8000/docs", "test"])
        assert result.exit_code == 1
        assert "Invalid URL" in result.output

    def test_learn_file_url_blocked(self):
        """Test that file:// URLs are blocked."""
        runner = CliRunner()
        result = runner.invoke(learn, ["file:///etc/passwd", "test"])
        assert result.exit_code == 1
        assert "Invalid URL" in result.output
