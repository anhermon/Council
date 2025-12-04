"""Tests for main MCP server module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from council.main import LearnRulesResponse, ReviewCodeResponse
from council.main import learn_rules as learn_rules_tool

# Access the underlying functions (FastMCP wraps them)
from council.main import review_code as review_code_tool

review_code = review_code_tool.fn
learn_rules = learn_rules_tool.fn


class TestReviewCode:
    """Test review_code MCP tool."""

    @pytest.mark.asyncio
    async def test_review_code_empty_path(self):
        """Test review_code with empty file path."""
        result = await review_code("")
        assert isinstance(result, ReviewCodeResponse)
        assert result.success is False
        assert result.error is not None
        assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_review_code_whitespace_path(self):
        """Test review_code with whitespace-only path."""
        result = await review_code("   ")
        assert isinstance(result, ReviewCodeResponse)
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_review_code_success(self, mock_settings):
        """Test successful review_code execution."""
        # Use a path within the mock project root
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test code")
        file_path_str = str(test_file)

        from council.agents import ReviewResult

        mock_review_result_obj = ReviewResult(
            summary="Test summary",
            issues=[],
            severity="low",
        )

        mock_agent_result = MagicMock()
        mock_agent_result.output = mock_review_result_obj
        mock_agent_result.usage = None

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_agent_result)

        with (
            patch("council.main.get_packed_context", new_callable=AsyncMock) as mock_context,
            patch("council.main.get_councilor_agent", return_value=mock_agent),
            patch("council.main.get_metrics_collector"),
            patch("council.main.get_review_history"),
        ):
            mock_context.return_value = "<code>test</code>"
            result = await review_code(file_path_str)
            assert isinstance(result, ReviewCodeResponse)
            assert result.success is True
            assert result.summary == "Test summary"

    @pytest.mark.asyncio
    async def test_review_code_timeout(self, mock_settings):
        """Test review_code with timeout."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test code")

        with (
            patch("council.main.get_packed_context", new_callable=AsyncMock) as mock_context,
            patch("council.main.get_metrics_collector"),
            patch("council.main.get_review_history"),
        ):
            mock_context.side_effect = TimeoutError()
            result = await review_code(str(test_file))
            assert isinstance(result, ReviewCodeResponse)
            assert result.success is False
            assert "timeout" in result.error.lower() or "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_review_code_with_base_ref(self, mock_settings):
        """Test review_code with base_ref parameter."""
        # Use a path within the mock project root
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test code")
        file_path_str = str(test_file)

        from council.agents import ReviewResult

        mock_review_result_obj = ReviewResult(
            summary="Test summary",
            issues=[],
            severity="low",
        )

        mock_agent_result = MagicMock()
        mock_agent_result.output = mock_review_result_obj
        mock_agent_result.usage = None

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_agent_result)

        with (
            patch("council.main.get_packed_diff", new_callable=AsyncMock) as mock_diff,
            patch("council.main.get_councilor_agent", return_value=mock_agent),
            patch("council.main.get_metrics_collector"),
            patch("council.main.get_review_history"),
        ):
            mock_diff.return_value = "<code>diff</code>"
            result = await review_code(file_path_str, base_ref="main")
            assert isinstance(result, ReviewCodeResponse)
            assert result.success is True
            mock_diff.assert_called_once()

    @pytest.mark.asyncio
    async def test_review_code_large_content(self, mock_settings):
        """Test review_code with content exceeding size limit."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test code")

        large_content = "x" * (11 * 1024 * 1024)  # 11MB, exceeding 10MB limit

        with (
            patch("council.main.get_packed_context", new_callable=AsyncMock) as mock_context,
            patch("council.main.get_metrics_collector"),
            patch("council.main.get_review_history"),
        ):
            mock_context.return_value = large_content
            result = await review_code(str(test_file))
            assert isinstance(result, ReviewCodeResponse)
            assert result.success is False
            assert "large" in result.error.lower() or "size" in result.error.lower()

    @pytest.mark.asyncio
    async def test_review_code_agent_timeout(self, mock_settings):
        """Test review_code when agent execution times out."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test code")

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=TimeoutError())

        with (
            patch("council.main.get_packed_context", new_callable=AsyncMock) as mock_context,
            patch("council.main.get_councilor_agent", return_value=mock_agent),
            patch("council.main.get_metrics_collector"),
            patch("council.main.get_review_history"),
        ):
            mock_context.return_value = "<code>test</code>"
            result = await review_code(str(test_file))
            assert isinstance(result, ReviewCodeResponse)
            assert result.success is False
            assert "timeout" in result.error.lower() or "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_review_code_agent_validation_error(self, mock_settings):
        """Test review_code with agent validation error."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test code")

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=ValueError("Validation failed"))

        with (
            patch("council.main.get_packed_context", new_callable=AsyncMock) as mock_context,
            patch("council.main.get_councilor_agent", return_value=mock_agent),
            patch("council.main.get_metrics_collector"),
            patch("council.main.get_review_history"),
        ):
            mock_context.return_value = "<code>test</code>"
            result = await review_code(str(test_file))
            assert isinstance(result, ReviewCodeResponse)
            assert result.success is False
            assert "validation" in result.error.lower()

    @pytest.mark.asyncio
    async def test_review_code_file_not_found(self, _mock_settings):
        """Test review_code with nonexistent file."""
        with (
            patch("council.main.get_packed_context", new_callable=AsyncMock) as mock_context,
            patch("council.main.get_metrics_collector"),
            patch("council.main.get_review_history"),
        ):
            mock_context.side_effect = FileNotFoundError("File not found")
            result = await review_code("nonexistent.py")
            assert isinstance(result, ReviewCodeResponse)
            assert result.success is False
            assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_review_code_permission_error(self, _mock_settings):
        """Test review_code with permission error."""
        with (
            patch("council.main.get_packed_context", new_callable=AsyncMock) as mock_context,
            patch("council.main.get_metrics_collector"),
            patch("council.main.get_review_history"),
        ):
            mock_context.side_effect = PermissionError("Permission denied")
            result = await review_code("test.py")
            assert isinstance(result, ReviewCodeResponse)
            assert result.success is False
            assert "permission" in result.error.lower()


class TestLearnRules:
    """Test learn_rules MCP tool."""

    @pytest.mark.asyncio
    async def test_learn_rules_empty_url(self):
        """Test learn_rules with empty URL."""
        result = await learn_rules("", "test_topic")
        assert isinstance(result, LearnRulesResponse)
        assert result.success is False
        assert result.error is not None
        assert result.error_code == "EMPTY_URL"

    @pytest.mark.asyncio
    async def test_learn_rules_whitespace_url(self):
        """Test learn_rules with whitespace-only URL."""
        result = await learn_rules("   ", "test_topic")
        assert isinstance(result, LearnRulesResponse)
        assert result.success is False
        assert result.error_code == "EMPTY_URL"

    @pytest.mark.asyncio
    async def test_learn_rules_invalid_topic(self):
        """Test learn_rules with invalid topic."""
        result = await learn_rules("https://example.com", "../invalid")
        assert isinstance(result, LearnRulesResponse)
        assert result.success is False
        assert result.error_code == "INVALID_TOPIC"

    @pytest.mark.asyncio
    async def test_learn_rules_invalid_url(self):
        """Test learn_rules with invalid URL."""
        result = await learn_rules("not-a-url", "test_topic")
        assert isinstance(result, LearnRulesResponse)
        assert result.success is False
        assert result.error_code == "INVALID_URL"

    @pytest.mark.asyncio
    async def test_learn_rules_success(self, _mock_settings):
        """Test successful learn_rules execution."""
        with (
            patch("council.main.fetch_and_summarize", new_callable=AsyncMock) as mock_fetch,
            patch("council.main.validate_url"),
            patch("council.main.validate_topic"),
        ):
            mock_fetch.return_value = "Successfully learned rules"
            result = await learn_rules("https://example.com/docs", "test_topic")
            assert isinstance(result, LearnRulesResponse)
            assert result.success is True
            assert result.message == "Successfully learned rules"

    @pytest.mark.asyncio
    async def test_learn_rules_timeout(self, _mock_settings):
        """Test learn_rules with timeout."""
        with (
            patch("council.main.fetch_and_summarize", new_callable=AsyncMock) as mock_fetch,
            patch("council.main.validate_url"),
            patch("council.main.validate_topic"),
        ):
            mock_fetch.side_effect = TimeoutError()
            result = await learn_rules("https://example.com/docs", "test_topic")
            assert isinstance(result, LearnRulesResponse)
            assert result.success is False
            assert "timeout" in result.error.lower() or "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_learn_rules_exception(self, _mock_settings):
        """Test learn_rules with general exception."""
        with (
            patch("council.main.fetch_and_summarize", new_callable=AsyncMock) as mock_fetch,
            patch("council.main.validate_url"),
            patch("council.main.validate_topic"),
        ):
            mock_fetch.side_effect = Exception("Unexpected error")
            result = await learn_rules("https://example.com/docs", "test_topic")
            assert isinstance(result, LearnRulesResponse)
            assert result.success is False
            assert result.error is not None
