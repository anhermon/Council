"""Tests for context_builder module."""

from unittest.mock import MagicMock, patch

import pytest

from council.agents import CouncilDeps
from council.cli.core.context_builder import (
    _build_system_prompt,
    _create_review_checklist,
    build_review_context,
)


class TestBuildReviewContext:
    """Test build_review_context function."""

    @pytest.mark.asyncio
    @patch("council.cli.core.context_builder.get_relevant_knowledge")
    @patch("council.cli.core.context_builder.detect_language")
    @patch("council.cli.core.context_builder.extract_code_from_xml")
    async def test_build_review_context_success(self, mock_extract, mock_detect, mock_knowledge):
        """Test successful context building."""
        mock_extract.return_value = "def hello(): pass"
        mock_detect.return_value = "python"
        mock_knowledge.return_value = ("Knowledge content", {"file1.md"})

        deps = CouncilDeps(
            file_path="test.py",
            extra_instructions="Test instructions",
            review_phases=["security"],
        )

        result = await build_review_context("<xml>code</xml>", deps)

        assert result["extracted_code"] == "def hello(): pass"
        assert result["file_path"] == "test.py"
        assert result["language"] == "python"
        assert result["knowledge_base"] == "Knowledge content"
        assert "system_prompt" in result
        assert "review_checklist" in result
        assert result["metadata"]["extra_instructions"] == "Test instructions"
        assert result["metadata"]["review_phases"] == ["security"]

    @pytest.mark.asyncio
    @patch("council.cli.core.context_builder.get_relevant_knowledge")
    @patch("council.cli.core.context_builder.detect_language")
    @patch("council.cli.core.context_builder.extract_code_from_xml")
    async def test_build_review_context_no_phases(self, mock_extract, mock_detect, mock_knowledge):
        """Test context building without review phases."""
        mock_extract.return_value = "code"
        mock_detect.return_value = "javascript"
        mock_knowledge.return_value = ("Knowledge", set())

        deps = CouncilDeps(
            file_path="test.js",
            extra_instructions=None,
            review_phases=None,
        )

        result = await build_review_context("<xml>code</xml>", deps)

        assert result["language"] == "javascript"
        assert result["metadata"]["review_phases"] is None


class TestBuildSystemPrompt:
    """Test _build_system_prompt function."""

    @pytest.mark.asyncio
    @patch("council.cli.core.context_builder.settings")
    @patch("council.agents.councilor._get_jinja_env")
    async def test_build_system_prompt_basic(self, mock_jinja_env, mock_settings):
        """Test basic system prompt building."""
        mock_settings.knowledge_dir.exists.return_value = False

        mock_template = MagicMock()
        mock_template.render.return_value = "System prompt content"
        mock_env = MagicMock()
        mock_env.get_template.return_value = mock_template
        mock_jinja_env.return_value = mock_env

        deps = CouncilDeps(
            file_path="test.py",
            extra_instructions="Test",
            review_phases=["security"],
        )

        result = await _build_system_prompt(deps, "domain rules", "python", set())

        assert "System prompt content" in result
        assert "REVIEW PHASES" in result
        assert "security" in result

    @pytest.mark.asyncio
    @patch("council.cli.core.context_builder.settings")
    @patch("council.agents.councilor._get_jinja_env")
    async def test_build_system_prompt_with_language_files(self, mock_jinja_env, mock_settings):
        """Test system prompt with language-specific files."""
        mock_knowledge_dir = MagicMock()
        mock_knowledge_dir.exists.return_value = True
        mock_python_file = MagicMock()
        mock_python_file.exists.return_value = True
        mock_knowledge_dir.__truediv__ = MagicMock(return_value=mock_python_file)
        mock_settings.knowledge_dir = mock_knowledge_dir

        mock_template = MagicMock()
        mock_template.render.return_value = "Prompt"
        mock_env = MagicMock()
        mock_env.get_template.return_value = mock_template
        mock_jinja_env.return_value = mock_env

        deps = CouncilDeps(
            file_path="test.py",
            extra_instructions=None,
            review_phases=None,
        )

        result = await _build_system_prompt(deps, "rules", "python", set())

        assert "Prompt" in result

    @pytest.mark.asyncio
    @patch("council.cli.core.context_builder.settings")
    @patch("council.agents.councilor._get_jinja_env")
    async def test_build_system_prompt_all_phases(self, mock_jinja_env, mock_settings):
        """Test system prompt with all review phases."""
        mock_settings.knowledge_dir.exists.return_value = False

        mock_template = MagicMock()
        mock_template.render.return_value = "Prompt"
        mock_env = MagicMock()
        mock_env.get_template.return_value = mock_template
        mock_jinja_env.return_value = mock_env

        deps = CouncilDeps(
            file_path="test.py",
            extra_instructions="Test",
            review_phases=["security", "performance", "maintainability", "best_practices"],
        )

        result = await _build_system_prompt(deps, "rules", "python", set())

        assert "security" in result
        assert "performance" in result
        assert "maintainability" in result
        assert "best_practices" in result


class TestCreateReviewChecklist:
    """Test _create_review_checklist function."""

    def test_create_review_checklist_basic(self):
        """Test basic checklist creation."""
        checklist = _create_review_checklist("python", None)

        assert "Code Review Checklist" in checklist
        assert "Security" in checklist
        assert "Performance" in checklist
        assert "python" in checklist.lower()

    def test_create_review_checklist_unknown_language(self):
        """Test checklist with unknown language."""
        checklist = _create_review_checklist("unknown", None)

        assert "Code Review Checklist" in checklist
        assert "unknown" not in checklist.lower()

    def test_create_review_checklist_with_phases(self):
        """Test checklist with review phases."""
        checklist = _create_review_checklist("python", ["security", "performance"])

        assert "Review Focus" in checklist
        assert "security" in checklist
        assert "performance" in checklist

    def test_create_review_checklist_all_sections(self):
        """Test that checklist contains all required sections."""
        checklist = _create_review_checklist("javascript", ["security"])

        assert "Security" in checklist
        assert "Performance" in checklist
        assert "Code Quality" in checklist
        assert "Best Practices" in checklist
        assert "Bugs & Edge Cases" in checklist
        assert "Expected Output Format" in checklist
        assert "Severity Guidelines" in checklist
