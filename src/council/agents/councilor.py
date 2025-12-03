"""The Councilor Agent - Core code review logic using Pydantic-AI."""

import os
import threading
from dataclasses import dataclass
from pathlib import Path

import logfire
from jinja2 import Environment, FileSystemLoader, TemplateError
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider

from ..config import settings
from ..tools.architecture import analyze_architecture
from ..tools.code_analysis import (
    analyze_imports,
    read_file,
    search_codebase,
    write_file,
    write_file_chunk,
)
from ..tools.git_tools import get_file_history, get_git_diff
from ..tools.metrics import calculate_complexity
from ..tools.security import scan_security_vulnerabilities
from ..tools.static_analysis import run_static_analysis
from ..tools.testing import check_test_coverage, check_test_quality, find_related_tests

# Resource limits for knowledge base files
MAX_KNOWLEDGE_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_KNOWLEDGE_FILES = 50  # Maximum number of knowledge files to load
MAX_EXTRA_INSTRUCTIONS_LENGTH = 10000  # Maximum length for extra instructions

# Determine model from environment variable (required)
# Users must set COUNCIL_MODEL in their environment or .env file
MODEL_NAME = os.getenv("COUNCIL_MODEL")


class Issue(BaseModel):
    """Represents a code issue found during review."""

    description: str = Field(
        description="Clear description of the issue. Must accurately reflect what exists in the code - verify the issue exists before reporting."
    )
    severity: str = Field(
        description="Severity level: 'low' for minor/style issues, 'medium' for code quality concerns, 'high' for bugs or significant issues, 'critical' for security vulnerabilities or serious bugs",
        pattern="^(low|medium|high|critical)$",
    )
    category: str = Field(
        default="bug",
        description="Issue category: 'security', 'performance', 'maintainability', 'bug', 'style', or 'documentation'",
        pattern="^(security|performance|maintainability|bug|style|documentation)$",
    )
    line_number: int | None = Field(
        default=None,
        description="Exact line number where the issue occurs. Must be accurate - verify by checking the actual code.",
    )
    code_snippet: str | None = Field(
        default=None,
        description="Exact code snippet showing the issue. Must match the actual code provided - do not invent or modify code.",
    )
    related_files: list[str] = Field(
        default_factory=list,
        description="List of related files that are affected by or related to this issue",
    )
    suggested_priority: int | None = Field(
        default=None,
        description="Suggested priority score from 1-10, where 10 is highest priority. Higher severity and security issues should have higher priority.",
        ge=1,
        le=10,
    )
    references: list[str] = Field(
        default_factory=list,
        description="List of references, documentation links, CVE numbers, or other relevant information about this issue",
    )
    auto_fixable: bool = Field(
        default=False,
        description="Whether this issue can be automatically fixed",
    )


class CrossFileIssue(BaseModel):
    """Represents an issue that spans multiple files."""

    description: str = Field(description="Description of the cross-file issue")
    severity: str = Field(
        description="Severity level",
        pattern="^(low|medium|high|critical)$",
    )
    files: list[str] = Field(description="List of files involved in this issue")
    category: str = Field(
        default="maintainability",
        description="Issue category",
        pattern="^(security|performance|maintainability|bug|style|documentation)$",
    )


class DependencyAnalysis(BaseModel):
    """Analysis of code dependencies."""

    external_dependencies: list[str] = Field(
        default_factory=list, description="List of external dependencies"
    )
    internal_dependencies: list[str] = Field(
        default_factory=list, description="List of internal dependencies"
    )
    circular_dependencies: list[list[str]] = Field(
        default_factory=list, description="List of circular dependency chains"
    )
    unused_imports: list[str] = Field(default_factory=list, description="List of unused imports")


class ReviewResult(BaseModel):
    """Structured output from code review."""

    summary: str = Field(description="Overall summary of the code review")
    issues: list[Issue] = Field(
        default_factory=list,
        description="List of issues found. Report all significant issues comprehensively - aim to identify all legitimate issues in a single review. Prioritize by severity but include all real issues.",
    )
    severity: str = Field(
        description="Overall severity assessment based on the highest severity issue found",
        pattern="^(low|medium|high|critical)$",
    )
    code_fix: str | None = Field(default=None, description="Optional suggested code fix")
    cross_file_issues: list[CrossFileIssue] = Field(
        default_factory=list,
        description="List of issues that span multiple files or affect file relationships",
    )
    dependency_analysis: DependencyAnalysis | None = Field(
        default=None, description="Analysis of code dependencies and imports"
    )


@dataclass
class CouncilDeps:
    """Dependencies injected into the councilor agent."""

    file_path: str
    extra_instructions: str | None = None
    review_phases: list[str] | None = None  # Optional: specific phases to run

    def __post_init__(self) -> None:
        """Validate inputs after initialization."""
        # Validate file_path
        if not isinstance(self.file_path, str):
            raise TypeError("file_path must be a string")
        if not self.file_path or not self.file_path.strip():
            raise ValueError("file_path cannot be empty")

        # Check for path traversal attempts
        if ".." in self.file_path or self.file_path.startswith("/"):
            # Allow absolute paths but validate they're safe
            path_obj = Path(self.file_path)
            if path_obj.is_absolute():
                # Check if path is within project root
                try:
                    path_obj.resolve().relative_to(settings.project_root.resolve())
                except ValueError:
                    # Path is outside project root - this might be intentional for some use cases
                    # but log a warning
                    logfire.warning(
                        "file_path is outside project root",
                        file_path=self.file_path,
                        project_root=str(settings.project_root),
                    )

        # Validate extra_instructions length
        if self.extra_instructions and len(self.extra_instructions) > MAX_EXTRA_INSTRUCTIONS_LENGTH:
            raise ValueError(
                f"extra_instructions exceeds maximum length of {MAX_EXTRA_INSTRUCTIONS_LENGTH}"
            )

        # Validate review_phases
        if self.review_phases:
            valid_phases = {"security", "performance", "maintainability", "best_practices"}
            invalid_phases = set(self.review_phases) - valid_phases
            if invalid_phases:
                raise ValueError(
                    f"Invalid review phases: {invalid_phases}. Valid phases: {valid_phases}"
                )


def _create_model() -> OpenAIChatModel | str:
    """Create the model instance based on configuration."""
    if not MODEL_NAME:
        raise RuntimeError(
            "COUNCIL_MODEL environment variable is required. Please set it in your .env file or environment.\n"
            "Examples:\n"
            "  - For LiteLLM: COUNCIL_MODEL=your-model-name\n"
            "  - For direct providers: COUNCIL_MODEL=openai:gpt-4o or COUNCIL_MODEL=anthropic:claude-3-5-sonnet-20241022"
        )

    if settings.litellm_base_url and settings.litellm_api_key:
        # Use LiteLLM provider with custom base URL
        return OpenAIChatModel(
            MODEL_NAME,
            provider=LiteLLMProvider(
                api_base=settings.litellm_base_url,
                api_key=settings.litellm_api_key,
            ),
        )
    elif settings.openai_api_key:
        # Use direct OpenAI provider if API key is available
        if ":" not in MODEL_NAME:
            # No provider prefix, default to OpenAI
            return f"openai:{MODEL_NAME}"
        else:
            # Already has provider prefix (e.g., "anthropic:claude-3-5-sonnet")
            return MODEL_NAME
    else:
        # No API keys configured - raise error with helpful message
        raise RuntimeError(
            "No API keys configured. Please set either:\n"
            "  - OPENAI_API_KEY for direct provider access, or\n"
            "  - LITELLM_BASE_URL and LITELLM_API_KEY for LiteLLM proxy access.\n"
            "Create a .env file or set environment variables before running the server."
        )


# Create the agent with structured output (lazy initialization)
# The agent will be created when first accessed
_councilor_agent: Agent[CouncilDeps, ReviewResult] | None = None
_agent_lock = threading.Lock()


def get_councilor_agent() -> Agent[CouncilDeps, ReviewResult]:
    """Get or create the councilor agent (thread-safe lazy initialization)."""
    global _councilor_agent
    # Double-check locking pattern for thread safety
    if _councilor_agent is None:
        with _agent_lock:
            # Check again inside the lock to avoid race conditions
            if _councilor_agent is None:
                try:
                    model = _create_model()
                    _councilor_agent = Agent(
                        model,
                        deps_type=CouncilDeps,
                        output_type=ReviewResult,
                        tools=[
                            read_file,
                            write_file,
                            write_file_chunk,
                            search_codebase,
                            analyze_imports,
                            get_git_diff,
                            get_file_history,
                            run_static_analysis,
                            scan_security_vulnerabilities,
                            find_related_tests,
                            check_test_coverage,
                            check_test_quality,
                            calculate_complexity,
                            analyze_architecture,
                        ],
                    )
                    # Register the system prompt function
                    _councilor_agent.system_prompt(add_dynamic_knowledge)
                except Exception as e:
                    logfire.error("Failed to create councilor agent", error=str(e))
                    raise
    return _councilor_agent


# Initialize Jinja2 environment for prompt templates
_jinja_env: Environment | None = None
_jinja_lock = threading.Lock()


def _get_jinja_env() -> Environment:
    """Get or create Jinja2 environment for loading templates."""
    global _jinja_env
    if _jinja_env is None:
        with _jinja_lock:
            if _jinja_env is None:
                try:
                    if not settings.templates_dir.exists():
                        raise FileNotFoundError(
                            f"Templates directory does not exist: {settings.templates_dir}"
                        )
                    _jinja_env = Environment(
                        loader=FileSystemLoader(str(settings.templates_dir)),
                        autoescape=False,
                        trim_blocks=True,
                        lstrip_blocks=True,
                    )
                except Exception as e:
                    logfire.error("Failed to initialize Jinja2 environment", error=str(e))
                    raise
    return _jinja_env


def _validate_extra_instructions(extra_instructions: str | None) -> str | None:
    """Validate and sanitize extra instructions."""
    if extra_instructions is None:
        return None

    if len(extra_instructions) > MAX_EXTRA_INSTRUCTIONS_LENGTH:
        logfire.warning(
            f"Extra instructions too long ({len(extra_instructions)} chars), "
            f"truncating to {MAX_EXTRA_INSTRUCTIONS_LENGTH}"
        )
        return extra_instructions[:MAX_EXTRA_INSTRUCTIONS_LENGTH]

    return extra_instructions


def detect_language(file_path: str) -> str:
    """
    Detect programming language from file extension.

    Args:
        file_path: Path to file

    Returns:
        Language name (e.g., 'python', 'javascript', 'typescript')
    """
    path = Path(file_path)
    extension = path.suffix.lower()

    language_map = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".php": "php",
        ".rb": "ruby",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".r": "r",
        ".m": "objectivec",
        ".mm": "objectivec",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "zsh",
        ".fish": "fish",
        ".ps1": "powershell",
        ".bat": "batch",
        ".cmd": "batch",
        ".sql": "sql",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".sass": "sass",
        ".less": "less",
        ".vue": "vue",
        ".svelte": "svelte",
        ".clj": "clojure",
        ".cljs": "clojure",
        ".lua": "lua",
        ".pl": "perl",
        ".pm": "perl",
        ".dart": "dart",
        ".ex": "elixir",
        ".exs": "elixir",
        ".jl": "julia",
        ".nim": "nim",
        ".cr": "crystal",
        ".d": "d",
        ".pas": "pascal",
        ".f": "fortran",
        ".f90": "fortran",
        ".f95": "fortran",
        ".ml": "ocaml",
        ".mli": "ocaml",
        ".fs": "fsharp",
        ".fsi": "fsharp",
        ".fsx": "fsharp",
        ".vb": "vbnet",
        ".vbs": "vbscript",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".ini": "ini",
        ".cfg": "config",
        ".conf": "config",
        ".xml": "xml",
        ".makefile": "makefile",
        ".mk": "makefile",
        ".dockerfile": "dockerfile",
        ".cmake": "cmake",
        ".proto": "protobuf",
        ".thrift": "thrift",
        ".graphql": "graphql",
        ".gql": "graphql",
        ".tf": "terraform",
        ".tfvars": "terraform",
        ".hcl": "hcl",
        ".groovy": "groovy",
        ".gradle": "gradle",
        ".jinja": "jinja",
        ".jinja2": "jinja",
        ".j2": "jinja",
        ".mustache": "mustache",
        ".handlebars": "handlebars",
        ".hbs": "handlebars",
        ".ejs": "ejs",
        ".pug": "pug",
        ".jade": "jade",
        ".njk": "nunjucks",
    }

    return language_map.get(extension, "unknown")


# System prompt function (will be registered when agent is created)
async def add_dynamic_knowledge(ctx: RunContext[CouncilDeps]) -> str:
    """
    Dynamically load knowledge base files and inject into system prompt.

    This function scans the knowledge/ directory for .md files and includes
    their content in the system prompt using Jinja2 templating, allowing the
    agent to learn from documentation fetched via the scribe tool.
    It also loads language-specific rulesets based on the file being reviewed.
    """
    knowledge_dir = settings.knowledge_dir
    knowledge_rulesets: list[tuple[str, str]] = []

    # Detect language from file path
    language = detect_language(ctx.deps.file_path)
    language_specific_files: list[str] = []

    # Look for language-specific knowledge files
    if language != "unknown" and knowledge_dir.exists():
        # Check for files like: python_best_practices.md, javascript_patterns.md, etc.
        language_patterns = [
            f"{language}_best_practices.md",
            f"{language}_patterns.md",
            f"{language}_guidelines.md",
            f"{language}_standards.md",
            f"{language}_rules.md",
        ]
        for pattern in language_patterns:
            lang_file = knowledge_dir / pattern
            if lang_file.exists():
                language_specific_files.append(pattern)

    # Scan all markdown files in knowledge directory with resource limits
    if knowledge_dir.exists():
        file_count = 0
        for md_file in sorted(knowledge_dir.glob("*.md")):
            # Enforce maximum file count limit
            if file_count >= MAX_KNOWLEDGE_FILES:
                logfire.warning(
                    f"Maximum knowledge file limit ({MAX_KNOWLEDGE_FILES}) reached, "
                    "skipping remaining files"
                )
                break

            try:
                # Check file size before reading
                file_size = md_file.stat().st_size
                if file_size > MAX_KNOWLEDGE_FILE_SIZE:
                    logfire.warning(
                        "Knowledge file too large, skipping",
                        file=str(md_file),
                        size=file_size,
                        max_size=MAX_KNOWLEDGE_FILE_SIZE,
                    )
                    continue

                content = md_file.read_text(encoding="utf-8")
                knowledge_rulesets.append((md_file.stem, content))
                file_count += 1
            except (OSError, PermissionError) as e:
                # Log but don't fail if a file can't be read due to OS/permission issues
                logfire.warning(
                    "Failed to load knowledge file (OS/permission error)",
                    file=str(md_file),
                    error=str(e),
                )
            except UnicodeDecodeError as e:
                # Log but don't fail if a file can't be decoded
                logfire.warning(
                    "Failed to decode knowledge file",
                    file=str(md_file),
                    error=str(e),
                )

        # Load and render the Jinja2 template
        try:
            jinja_env = _get_jinja_env()
            template = jinja_env.get_template("system_prompt.j2")

            # Validate extra instructions
            validated_extra_instructions = _validate_extra_instructions(ctx.deps.extra_instructions)

            # Add phase-specific instructions if phases are specified
            phase_instructions = ""
            if ctx.deps.review_phases:
                phase_instructions = (
                    f"\n\nREVIEW PHASES: Focus on {', '.join(ctx.deps.review_phases)}. "
                )
                if "security" in ctx.deps.review_phases:
                    phase_instructions += (
                        "Prioritize security vulnerabilities and security best practices. "
                    )
                if "performance" in ctx.deps.review_phases:
                    phase_instructions += "Focus on performance bottlenecks, optimization opportunities, and efficiency. "
                if "maintainability" in ctx.deps.review_phases:
                    phase_instructions += "Emphasize code maintainability, readability, and long-term sustainability. "
                if "best_practices" in ctx.deps.review_phases:
                    phase_instructions += "Apply general best practices and coding standards. "

            prompt = template.render(
                knowledge_rulesets=knowledge_rulesets,
                extra_instructions=validated_extra_instructions,
                language=language,
                language_specific_files=language_specific_files,
            )

            return prompt + phase_instructions
        except TemplateError as e:
            logfire.error("Template rendering failed", error=str(e))
            raise
        except Exception as e:
            logfire.error("Failed to generate system prompt", error=str(e))
            raise
