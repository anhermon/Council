"""Tests for councilor agent."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from council.agents.councilor import (
    CouncilDeps,
    Issue,
    ReviewResult,
    _validate_extra_instructions,
    detect_language,
    get_relevant_knowledge,
)


class TestIssue:
    """Test Issue model."""

    def test_issue_creation(self):
        """Test creating an Issue."""
        issue = Issue(
            description="Test issue",
            severity="medium",
            category="bug",
            line_number=10,
        )
        assert issue.description == "Test issue"
        assert issue.severity == "medium"
        assert issue.category == "bug"
        assert issue.line_number == 10

    def test_issue_defaults(self):
        """Test Issue with defaults."""
        issue = Issue(description="Test", severity="low")
        assert issue.category == "bug"
        assert issue.line_number is None
        assert issue.code_snippet is None
        assert issue.related_files == []
        assert issue.auto_fixable is False

    def test_issue_invalid_severity(self):
        """Test Issue with invalid severity."""
        with pytest.raises(ValidationError):
            Issue(description="Test", severity="invalid")


class TestReviewResult:
    """Test ReviewResult model."""

    def test_review_result_creation(self):
        """Test creating a ReviewResult."""
        result = ReviewResult(
            summary="Test summary",
            issues=[],
            severity="low",
        )
        assert result.summary == "Test summary"
        assert result.issues == []
        assert result.severity == "low"

    def test_review_result_with_issues(self):
        """Test ReviewResult with issues."""
        issues = [
            Issue(description="Issue 1", severity="medium"),
            Issue(description="Issue 2", severity="high"),
        ]
        result = ReviewResult(
            summary="Summary",
            issues=issues,
            severity="high",
        )
        assert len(result.issues) == 2


class TestCouncilDeps:
    """Test CouncilDeps dataclass."""

    def test_council_deps_creation(self):
        """Test creating CouncilDeps."""
        deps = CouncilDeps(file_path="test.py")
        assert deps.file_path == "test.py"
        assert deps.extra_instructions is None
        assert deps.review_phases is None

    def test_council_deps_with_extra_instructions(self):
        """Test CouncilDeps with extra instructions."""
        deps = CouncilDeps(file_path="test.py", extra_instructions="Focus on security")
        assert deps.extra_instructions == "Focus on security"

    def test_council_deps_empty_file_path(self):
        """Test CouncilDeps with empty file_path."""
        with pytest.raises(ValueError, match="cannot be empty"):
            CouncilDeps(file_path="")

    def test_council_deps_invalid_type(self):
        """Test CouncilDeps with invalid file_path type."""
        with pytest.raises(TypeError, match="must be a string"):
            CouncilDeps(file_path=123)  # type: ignore

    def test_council_deps_long_instructions(self):
        """Test CouncilDeps with instructions exceeding limit."""
        long_instructions = "x" * 10001
        with pytest.raises(ValueError, match="exceeds maximum length"):
            CouncilDeps(file_path="test.py", extra_instructions=long_instructions)

    def test_council_deps_with_review_phases(self):
        """Test CouncilDeps with review phases."""
        deps = CouncilDeps(file_path="test.py", review_phases=["security", "performance"])
        assert deps.review_phases == ["security", "performance"]


class TestDetectLanguage:
    """Test detect_language function."""

    def test_detect_python(self):
        """Test detecting Python."""
        assert detect_language("test.py") == "python"

    def test_detect_javascript(self):
        """Test detecting JavaScript."""
        assert detect_language("test.js") == "javascript"
        assert detect_language("test.jsx") == "javascript"

    def test_detect_typescript(self):
        """Test detecting TypeScript."""
        assert detect_language("test.ts") == "typescript"
        assert detect_language("test.tsx") == "typescript"

    def test_detect_unknown(self):
        """Test detecting unknown language."""
        assert detect_language("test.xyz") == "unknown"

    def test_detect_case_insensitive(self):
        """Test language detection is case-insensitive."""
        assert detect_language("test.PY") == "python"
        assert detect_language("test.JS") == "javascript"

    def test_detect_multiple_extensions(self):
        """Test various language extensions."""
        assert detect_language("file.go") == "go"
        assert detect_language("file.rs") == "rust"
        assert detect_language("file.java") == "java"
        assert detect_language("file.cpp") == "cpp"
        assert detect_language("file.html") == "html"
        assert detect_language("file.css") == "css"


class TestGetRelevantKnowledge:
    """Test get_relevant_knowledge function."""

    @pytest.mark.asyncio
    async def test_get_relevant_knowledge_no_dir(self, mock_settings):
        """Test when knowledge directory doesn't exist."""
        # Remove knowledge dir if it exists
        if mock_settings.knowledge_dir.exists():
            import shutil

            shutil.rmtree(mock_settings.knowledge_dir)

        content, loaded = await get_relevant_knowledge(["test.py"])
        assert content == ""

    @pytest.mark.asyncio
    async def test_get_relevant_knowledge_python_file(self, mock_settings):
        """Test getting knowledge for Python file."""
        # Create knowledge files
        mock_settings.knowledge_dir.mkdir(parents=True, exist_ok=True)
        general_file = mock_settings.knowledge_dir / "general.md"
        general_file.write_text("# General knowledge")
        python_file = mock_settings.knowledge_dir / "python.md"
        python_file.write_text("# Python knowledge")

        content, loaded = await get_relevant_knowledge(["test.py"])
        assert "General knowledge" in content
        assert "Python knowledge" in content

    @pytest.mark.asyncio
    async def test_get_relevant_knowledge_multiple_files(self, mock_settings):
        """Test getting knowledge for multiple files."""
        mock_settings.knowledge_dir.mkdir(parents=True, exist_ok=True)
        general_file = mock_settings.knowledge_dir / "general.md"
        general_file.write_text("# General")
        python_file = mock_settings.knowledge_dir / "python.md"
        python_file.write_text("# Python")
        javascript_file = mock_settings.knowledge_dir / "javascript.md"
        javascript_file.write_text("# JavaScript")

        content, loaded = await get_relevant_knowledge(["test.py", "test.js"])
        assert "Python" in content
        assert "JavaScript" in content

    @pytest.mark.asyncio
    async def test_get_relevant_knowledge_large_file(self, mock_settings):
        """Test skipping large knowledge files."""
        mock_settings.knowledge_dir.mkdir(parents=True, exist_ok=True)
        large_file = mock_settings.knowledge_dir / "python.md"
        # Create file larger than MAX_KNOWLEDGE_FILE_SIZE
        large_content = "x" * (11 * 1024 * 1024)  # > 10MB
        large_file.write_text(large_content)

        content, loaded = await get_relevant_knowledge(["test.py"])
        # Large file should be skipped
        assert content == "" or "x" not in content

    @pytest.mark.asyncio
    async def test_get_relevant_knowledge_read_error(self, mock_settings):
        """Test handling of read errors."""
        mock_settings.knowledge_dir.mkdir(parents=True, exist_ok=True)
        python_file = mock_settings.knowledge_dir / "python.md"
        python_file.write_text("# Python")

        # Make file unreadable
        python_file.chmod(0o000)
        try:
            content, loaded = await get_relevant_knowledge(["test.py"])
            # Should handle error gracefully
            assert isinstance(content, str)
        finally:
            python_file.chmod(0o644)


class TestValidateExtraInstructions:
    """Test _validate_extra_instructions function."""

    def test_validate_none(self):
        """Test validation with None."""
        result = _validate_extra_instructions(None)
        assert result is None

    def test_validate_normal(self):
        """Test validation with normal instructions."""
        instructions = "Focus on security"
        result = _validate_extra_instructions(instructions)
        assert result == instructions

    def test_validate_too_long(self):
        """Test validation with instructions too long."""
        long_instructions = "x" * 10001
        result = _validate_extra_instructions(long_instructions)
        assert len(result) == 10000  # Should be truncated
        assert result == long_instructions[:10000]

    def test_validate_at_limit(self):
        """Test validation at limit."""
        instructions = "x" * 10000
        result = _validate_extra_instructions(instructions)
        assert result == instructions


class TestGetCouncilorAgent:
    """Test get_councilor_agent function."""

    def test_get_councilor_agent_creates_agent(self):
        """Test that get_councilor_agent creates an agent."""
        from council.agents.councilor import get_councilor_agent

        # Mock MODEL_NAME to avoid requiring actual API key
        with (
            patch("council.agents.councilor.MODEL_NAME", "test-model"),
            patch("council.agents.councilor._create_model") as mock_create,
        ):
            mock_model = MagicMock()
            mock_create.return_value = mock_model

            # Mock Agent creation
            with patch("council.agents.councilor.Agent") as mock_agent_class:
                mock_agent_instance = MagicMock()
                mock_agent_class.return_value = mock_agent_instance

                agent = get_councilor_agent()
                assert agent is not None

    def test_get_councilor_agent_singleton(self):
        """Test that get_councilor_agent returns singleton."""
        from council.agents.councilor import get_councilor_agent

        with (
            patch("council.agents.councilor.MODEL_NAME", "test-model"),
            patch("council.agents.councilor._create_model") as mock_create,
        ):
            mock_model = MagicMock()
            mock_create.return_value = mock_model

            with patch("council.agents.councilor.Agent") as mock_agent_class:
                mock_agent_instance = MagicMock()
                mock_agent_class.return_value = mock_agent_instance

                agent1 = get_councilor_agent()
                agent2 = get_councilor_agent()
                assert agent1 is agent2
