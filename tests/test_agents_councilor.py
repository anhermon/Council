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
        deps = CouncilDeps(file_path="test.py", extra_instructions=long_instructions)
        # Should be truncated to MAX_EXTRA_INSTRUCTIONS_LENGTH
        assert len(deps.extra_instructions) == 10000
        assert deps.extra_instructions == long_instructions[:10000]

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

        # Patch settings in the councilor module
        from council.agents import councilor

        original_knowledge_dir = councilor.settings.knowledge_dir
        councilor.settings.knowledge_dir = mock_settings.knowledge_dir
        try:
            content, loaded = await get_relevant_knowledge(["test.py"])
            assert "General knowledge" in content
            assert "Python knowledge" in content
        finally:
            councilor.settings.knowledge_dir = original_knowledge_dir

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

        # Patch settings in the councilor module
        from council.agents import councilor

        original_knowledge_dir = councilor.settings.knowledge_dir
        councilor.settings.knowledge_dir = mock_settings.knowledge_dir
        try:
            content, loaded = await get_relevant_knowledge(["test.py", "test.js"])
            assert "Python" in content
            assert "JavaScript" in content
        finally:
            councilor.settings.knowledge_dir = original_knowledge_dir

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

        # Mock _create_model to avoid requiring actual API key
        with patch("council.agents.councilor._create_model") as mock_create:
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

        with patch("council.agents.councilor._create_model") as mock_create:
            mock_model = MagicMock()
            mock_create.return_value = mock_model

            with patch("council.agents.councilor.Agent") as mock_agent_class:
                mock_agent_instance = MagicMock()
                mock_agent_class.return_value = mock_agent_instance

                agent1 = get_councilor_agent()
                agent2 = get_councilor_agent()
                assert agent1 is agent2

    def test_get_councilor_agent_error_handling(self):
        """Test error handling in get_councilor_agent."""
        # Reset the global agent
        import council.agents.councilor as councilor_module
        from council.agents.councilor import get_councilor_agent

        councilor_module._councilor_agent = None

        with (
            patch(
                "council.agents.councilor._create_model",
                side_effect=RuntimeError("Model creation failed"),
            ),
            pytest.raises(RuntimeError, match="Model creation failed"),
        ):
            get_councilor_agent()

    def test_council_deps_path_outside_project_root(self, tmp_path):
        """Test CouncilDeps with path outside project root."""
        from council.agents.councilor import CouncilDeps

        # Create a path outside project root
        outside_path = tmp_path / "outside" / "file.py"
        outside_path.parent.mkdir(parents=True)

        # Should log warning but not raise error
        deps = CouncilDeps(file_path=str(outside_path))
        assert deps.file_path == str(outside_path)

    def test_council_deps_invalid_review_phases(self):
        """Test CouncilDeps with invalid review phases."""
        with pytest.raises(ValueError, match="Invalid review phases"):
            CouncilDeps(file_path="test.py", review_phases=["invalid_phase"])

    def test_council_deps_valid_review_phases(self):
        """Test CouncilDeps with valid review phases."""
        deps = CouncilDeps(
            file_path="test.py",
            review_phases=["security", "performance", "maintainability", "best_practices"],
        )
        assert deps.review_phases == [
            "security",
            "performance",
            "maintainability",
            "best_practices",
        ]


class TestCreateModel:
    """Test _create_model function."""

    def test_create_model_no_model_name(self):
        """Test _create_model without model name."""
        from council.agents.councilor import _create_model

        with (
            patch("council.agents.councilor._get_model_name", return_value=None),
            pytest.raises(RuntimeError, match="COUNCIL_MODEL environment variable is required"),
        ):
            _create_model()

    def test_create_model_litellm_config(self):
        """Test _create_model with LiteLLM configuration."""
        from pydantic_ai.models.openai import OpenAIChatModel

        from council.agents.councilor import _create_model

        with (
            patch("council.agents.councilor._get_model_name", return_value="test-model"),
            patch("council.agents.councilor.settings") as mock_settings,
        ):
            mock_settings.litellm_base_url = "https://api.example.com"
            mock_settings.litellm_api_key = "test-key"
            mock_settings.openai_api_key = None

            result = _create_model()
            assert isinstance(result, OpenAIChatModel)

    def test_create_model_openai_direct(self):
        """Test _create_model with OpenAI direct configuration."""
        from council.agents.councilor import _create_model

        with (
            patch("council.agents.councilor._get_model_name", return_value="gpt-4"),
            patch("council.agents.councilor.settings") as mock_settings,
        ):
            mock_settings.litellm_base_url = None
            mock_settings.litellm_api_key = None
            mock_settings.openai_api_key = "test-key"

            result = _create_model()
            assert result == "openai:gpt-4"

    def test_create_model_openai_with_provider_prefix(self):
        """Test _create_model with provider prefix."""
        from council.agents.councilor import _create_model

        with (
            patch(
                "council.agents.councilor._get_model_name",
                return_value="anthropic:claude-3-5-sonnet",
            ),
            patch("council.agents.councilor.settings") as mock_settings,
        ):
            mock_settings.litellm_base_url = None
            mock_settings.litellm_api_key = None
            mock_settings.openai_api_key = "test-key"

            result = _create_model()
            assert result == "anthropic:claude-3-5-sonnet"

    def test_create_model_no_api_keys(self):
        """Test _create_model without any API keys."""
        from council.agents.councilor import _create_model

        with (
            patch("council.agents.councilor._get_model_name", return_value="test-model"),
            patch("council.agents.councilor.settings") as mock_settings,
        ):
            mock_settings.litellm_base_url = None
            mock_settings.litellm_api_key = None
            mock_settings.openai_api_key = None

            with pytest.raises(RuntimeError, match="No API keys configured"):
                _create_model()


class TestGetJinjaEnv:
    """Test _get_jinja_env function."""

    def test_get_jinja_env_creates_environment(self, tmp_path):
        """Test _get_jinja_env creates Jinja2 environment."""
        import council.agents.councilor as councilor_module
        from council.agents.councilor import _get_jinja_env

        # Reset global
        councilor_module._jinja_env = None

        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        template_file = templates_dir / "system_prompt.j2"
        template_file.write_text("Test template")

        with patch("council.agents.councilor.settings") as mock_settings:
            mock_settings.templates_dir = templates_dir

            env = _get_jinja_env()
            assert env is not None
            assert env.loader is not None

    def test_get_jinja_env_template_dir_not_exists(self, tmp_path):
        """Test _get_jinja_env when template directory doesn't exist."""
        import council.agents.councilor as councilor_module
        from council.agents.councilor import _get_jinja_env

        # Reset global
        councilor_module._jinja_env = None

        nonexistent_dir = tmp_path / "nonexistent_templates"

        with patch("council.agents.councilor.settings") as mock_settings:
            mock_settings.templates_dir = nonexistent_dir

            with pytest.raises(FileNotFoundError, match="Templates directory does not exist"):
                _get_jinja_env()

    def test_get_jinja_env_singleton(self, tmp_path):
        """Test _get_jinja_env returns singleton."""
        import council.agents.councilor as councilor_module
        from council.agents.councilor import _get_jinja_env

        # Reset global
        councilor_module._jinja_env = None

        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        template_file = templates_dir / "system_prompt.j2"
        template_file.write_text("Test template")

        with patch("council.agents.councilor.settings") as mock_settings:
            mock_settings.templates_dir = templates_dir

            env1 = _get_jinja_env()
            env2 = _get_jinja_env()
            assert env1 is env2


class TestAddDynamicKnowledge:
    """Test add_dynamic_knowledge function."""

    @pytest.mark.asyncio
    async def test_add_dynamic_knowledge_basic(self, tmp_path):
        """Test add_dynamic_knowledge with basic setup."""

        from council.agents.councilor import CouncilDeps, add_dynamic_knowledge

        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        template_file = templates_dir / "system_prompt.j2"
        template_file.write_text("Template: {{ domain_rules }}")

        python_file = knowledge_dir / "python.md"
        python_file.write_text("# Python Knowledge")

        deps = CouncilDeps(file_path="test.py")
        # Create a mock RunContext - RunContext is created by pydantic-ai internally
        ctx = MagicMock()
        ctx.deps = deps

        with (
            patch("council.agents.councilor.settings") as mock_settings,
            patch("council.agents.councilor._get_jinja_env") as mock_get_env,
        ):
            mock_settings.knowledge_dir = knowledge_dir
            mock_settings.templates_dir = templates_dir

            from jinja2 import Environment, FileSystemLoader

            mock_env = Environment(loader=FileSystemLoader(str(templates_dir)))
            mock_get_env.return_value = mock_env

            result = await add_dynamic_knowledge(ctx)
            assert isinstance(result, str)
            assert "Python" in result or "python" in result.lower()

    @pytest.mark.asyncio
    async def test_add_dynamic_knowledge_with_review_phases(self, tmp_path):
        """Test add_dynamic_knowledge with review phases."""
        from council.agents.councilor import CouncilDeps, add_dynamic_knowledge

        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        template_file = templates_dir / "system_prompt.j2"
        template_file.write_text("Template")

        deps = CouncilDeps(file_path="test.py", review_phases=["security", "performance"])
        # Create a mock RunContext - RunContext is created by pydantic-ai internally
        ctx = MagicMock()
        ctx.deps = deps

        with (
            patch("council.agents.councilor.settings") as mock_settings,
            patch("council.agents.councilor._get_jinja_env") as mock_get_env,
        ):
            mock_settings.knowledge_dir = knowledge_dir
            mock_settings.templates_dir = templates_dir

            from jinja2 import Environment, FileSystemLoader

            mock_env = Environment(loader=FileSystemLoader(str(templates_dir)))
            mock_get_env.return_value = mock_env

            result = await add_dynamic_knowledge(ctx)
            assert "security" in result.lower()
            assert "performance" in result.lower()

    @pytest.mark.asyncio
    async def test_add_dynamic_knowledge_template_error(self, tmp_path):
        """Test add_dynamic_knowledge with template error."""
        from jinja2 import TemplateError

        from council.agents.councilor import CouncilDeps, add_dynamic_knowledge

        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        deps = CouncilDeps(file_path="test.py")
        # Create a mock RunContext - RunContext is created by pydantic-ai internally
        ctx = MagicMock()
        ctx.deps = deps

        with (
            patch("council.agents.councilor.settings") as mock_settings,
            patch("council.agents.councilor._get_jinja_env") as mock_get_env,
        ):
            mock_settings.knowledge_dir = knowledge_dir

            mock_env = MagicMock()
            mock_env.get_template.side_effect = TemplateError("Template not found")
            mock_get_env.return_value = mock_env

            with pytest.raises(TemplateError):
                await add_dynamic_knowledge(ctx)
