"""The Councilor Agent - Core code review logic using Pydantic-AI."""

import ast
import asyncio
import html
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import logfire
from jinja2 import Environment, FileSystemLoader, TemplateError
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, ToolDefinition
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider

from ..config import get_settings
from ..tools.architecture import analyze_architecture
from ..tools.code_analysis import (
    analyze_imports,
    read_file,
    search_codebase,
    write_file,
    write_file_chunk,
)
from ..tools.debug import DebugWriter
from ..tools.exceptions import PathValidationError
from ..tools.git_tools import get_file_history, get_git_diff
from ..tools.metrics import calculate_complexity
from ..tools.security import scan_security_vulnerabilities
from ..tools.static_analysis import run_static_analysis
from ..tools.testing import check_test_coverage, check_test_quality, find_related_tests
from ..tools.validation import validate_file_path

settings = get_settings()

# Resource limits for knowledge base files
MAX_KNOWLEDGE_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_KNOWLEDGE_CONTENT_LENGTH = 50000  # 50KB per knowledge file content
MAX_EXTRA_INSTRUCTIONS_LENGTH = 10000  # Maximum length for extra instructions

# Thread-safe storage for debug writers (keyed by file_path)
_debug_writers: dict[str, "DebugWriter"] = {}
_debug_writers_lock = threading.Lock()

EXTENSION_MAP = {
    ".py": ["python"],
    ".js": ["javascript"],
    ".jsx": ["javascript", "react"],
    ".ts": ["typescript"],
    ".tsx": ["typescript", "react"],
    ".java": ["java"],
    ".go": ["go"],
    ".rs": ["rust"],
    ".cpp": ["cpp"],
    ".c": ["c"],
    ".h": ["c"],
    ".hpp": ["cpp"],
    ".cs": ["csharp"],
    ".php": ["php"],
    ".rb": ["ruby"],
    ".swift": ["swift"],
    ".kt": ["kotlin"],
    ".scala": ["scala"],
    ".r": ["r"],
    ".m": ["objectivec"],
    ".mm": ["objectivec"],
    ".sh": ["shell"],
    ".bash": ["shell"],
    ".zsh": ["shell"],
    ".fish": ["shell"],
    ".ps1": ["powershell"],
    ".bat": ["batch"],
    ".cmd": ["batch"],
    ".sql": ["sql"],
    ".html": ["html"],
    ".css": ["css"],
    ".scss": ["scss"],
    ".sass": ["sass"],
    ".less": ["less"],
    ".vue": ["vue"],
    ".svelte": ["svelte"],
    ".clj": ["clojure"],
    ".cljs": ["clojure"],
    ".lua": ["lua"],
    ".pl": ["perl"],
    ".pm": ["perl"],
    ".dart": ["dart"],
    ".ex": ["elixir"],
    ".exs": ["elixir"],
    ".jl": ["julia"],
    ".nim": ["nim"],
    ".cr": ["crystal"],
    ".d": ["d"],
    ".pas": ["pascal"],
    ".f": ["fortran"],
    ".f90": ["fortran"],
    ".f95": ["fortran"],
    ".ml": ["ocaml"],
    ".mli": ["ocaml"],
    ".fs": ["fsharp"],
    ".fsi": ["fsharp"],
    ".fsx": ["fsharp"],
    ".vb": ["vbnet"],
    ".vbs": ["vbscript"],
    ".yaml": ["yaml"],
    ".yml": ["yaml"],
    ".json": ["json"],
    ".toml": ["toml"],
    ".ini": ["ini"],
    ".cfg": ["config"],
    ".conf": ["config"],
    ".xml": ["xml"],
    ".makefile": ["makefile"],
    ".mk": ["makefile"],
    ".dockerfile": ["dockerfile"],
    ".cmake": ["cmake"],
    ".proto": ["protobuf"],
    ".thrift": ["thrift"],
    ".graphql": ["graphql"],
    ".gql": ["graphql"],
    ".tf": ["terraform"],
    ".tfvars": ["terraform"],
    ".hcl": ["hcl"],
    ".md": ["markdown"],
    ".j2": ["jinja2", "python"],  # Jinja2 templates (often used with Python)
    ".jinja": ["jinja2", "python"],
    ".jinja2": ["jinja2", "python"],
}


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

        # Use centralized path validation to ensure consistency
        try:
            validate_file_path(self.file_path)
        except PathValidationError as e:
            # Re-raise as ValueError for consistency with existing behavior
            raise ValueError(str(e)) from e

        # Validate and truncate extra_instructions length
        if self.extra_instructions and len(self.extra_instructions) > MAX_EXTRA_INSTRUCTIONS_LENGTH:
            self.extra_instructions = self.extra_instructions[:MAX_EXTRA_INSTRUCTIONS_LENGTH]

        # Validate review_phases
        if self.review_phases:
            valid_phases = {"security", "performance", "maintainability", "best_practices"}
            invalid_phases = set(self.review_phases) - valid_phases
            if invalid_phases:
                raise ValueError(
                    f"Invalid review phases: {invalid_phases}. Valid phases: {valid_phases}"
                )


def _get_model_name() -> str | None:
    """Get model name from environment variable (lazy evaluation)."""
    return os.getenv("COUNCIL_MODEL")


def _create_model() -> OpenAIChatModel | str:
    """
    Create the model instance based on configuration.

    Returns:
        OpenAIChatModel instance for LiteLLM provider, or a string in the format
        "provider:model-name" (e.g., "openai:gpt-4o", "anthropic:claude-3-5-sonnet-20241022")
        for direct provider access.
    """
    model_name = _get_model_name()
    if not model_name:
        raise RuntimeError(
            "COUNCIL_MODEL environment variable is required. Please set it in your .env file or environment.\n"
            "Examples:\n"
            "  - For LiteLLM: COUNCIL_MODEL=your-model-name\n"
            "  - For direct providers: COUNCIL_MODEL=openai:gpt-4o or COUNCIL_MODEL=anthropic:claude-3-5-sonnet-20241022"
        )

    if settings.litellm_base_url and settings.litellm_api_key:
        # Use LiteLLM provider with custom base URL
        return OpenAIChatModel(
            model_name,
            provider=LiteLLMProvider(
                api_base=settings.litellm_base_url,
                api_key=settings.litellm_api_key,
            ),
        )
    elif settings.openai_api_key:
        # Use direct OpenAI provider if API key is available
        if ":" not in model_name:
            # No provider prefix, default to OpenAI
            return f"openai:{model_name}"
        else:
            # Already has provider prefix (e.g., "anthropic:claude-3-5-sonnet")
            return model_name
    else:
        # No API keys configured - raise error with helpful message
        raise RuntimeError(
            "No API keys configured. Please set either:\n"
            "  - OPENAI_API_KEY for direct provider access, or\n"
            "  - LITELLM_BASE_URL and LITELLM_API_KEY for LiteLLM proxy access.\n"
            "Create a .env file or set environment variables before running the server."
        )


# Tools that are only applicable to Python files
PYTHON_ONLY_TOOLS = {
    "analyze_imports",  # Only analyzes Python imports
    "check_test_coverage",  # Python test coverage tools
    "check_test_quality",  # Python test quality checks
    "find_related_tests",  # Python test discovery
}

# Tools that are only applicable to code files (not templates/config files)
CODE_ONLY_TOOLS = {
    "run_static_analysis",  # Static analysis tools (ruff, mypy, pylint)
    "calculate_complexity",  # Code complexity metrics
}

# Template/config file extensions that shouldn't use code analysis tools
TEMPLATE_EXTENSIONS = {
    ".j2",
    ".jinja",
    ".jinja2",
    ".html",
    ".xml",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
}


async def prepare_tools(
    ctx: RunContext[CouncilDeps], tool_defs: list[ToolDefinition]
) -> list[ToolDefinition] | None:
    """
    Filter tools based on file type being reviewed.

    This prevents calling irrelevant tools (e.g., analyze_imports on Jinja templates).

    Args:
        ctx: Run context containing file path
        tool_defs: List of available tool definitions

    Returns:
        Filtered list of tool definitions, or None to disable all tools
    """
    file_path = ctx.deps.file_path
    if not file_path:
        # If no file path, return all tools
        return tool_defs

    path = Path(file_path)
    extension = path.suffix.lower()

    # Filter out Python-only tools for non-Python files
    if extension != ".py":
        tool_defs = [td for td in tool_defs if td.name not in PYTHON_ONLY_TOOLS]

    # Filter out code analysis tools for template/config files
    if extension in TEMPLATE_EXTENSIONS:
        tool_defs = [td for td in tool_defs if td.name not in CODE_ONLY_TOOLS]

    return tool_defs


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
                        prepare_tools=prepare_tools,
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
                        autoescape=True,  # Enable autoescape for XSS protection
                        trim_blocks=True,
                        lstrip_blocks=True,
                    )
                except Exception as e:
                    logfire.error("Failed to initialize Jinja2 environment", error=str(e))
                    raise
    return _jinja_env


def _validate_extra_instructions(extra_instructions: str | None) -> str | None:
    """
    Validate and sanitize extra instructions.

    Truncates to MAX_EXTRA_INSTRUCTIONS_LENGTH if too long.
    """
    if extra_instructions is None:
        return None
    if len(extra_instructions) > MAX_EXTRA_INSTRUCTIONS_LENGTH:
        return extra_instructions[:MAX_EXTRA_INSTRUCTIONS_LENGTH]
    return extra_instructions


def _clean_knowledge_content(content: str) -> str:
    """
    Clean and optimize knowledge base content.

    Removes unnecessary elements like images, badges, and normalizes whitespace
    to reduce file size and improve readability.

    Args:
        content: Raw knowledge base content

    Returns:
        Cleaned content string
    """
    # Remove image markdown: [![alt](url)](link)
    content = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", content)
    # Remove standalone image links: ![alt](url)
    content = re.sub(r"!\[.*?\]\(.*?\)", "", content)
    # Remove badge patterns (shields.io, etc.) - more specific pattern
    content = re.sub(r"\[!\[.*?badge.*?\]\(.*?\)\]", "", content, flags=re.IGNORECASE)
    # Remove any remaining badge-like patterns
    content = re.sub(
        r"\[!\[.*?\]\(https?://.*?shields\.io.*?\)\]", "", content, flags=re.IGNORECASE
    )
    # Normalize excessive whitespace (3+ newlines to 2)
    content = re.sub(r"\n{3,}", "\n\n", content)
    # Remove trailing whitespace from lines
    content = "\n".join(line.rstrip() for line in content.split("\n"))
    return content.strip()


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

    # Special handling for extensions that need language normalization
    # (EXTENSION_MAP may include framework names like "react" but we want the base language)
    language_overrides = {
        ".jsx": "javascript",  # EXTENSION_MAP has ["javascript", "react"]
        ".tsx": "typescript",  # EXTENSION_MAP has ["typescript", "react"]
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "zsh",
        ".fish": "fish",
    }

    # Check overrides first
    if extension in language_overrides:
        return language_overrides[extension]

    # Then check EXTENSION_MAP
    if extension in EXTENSION_MAP:
        languages = EXTENSION_MAP[extension]
        # Return the first language (primary language for this extension)
        return languages[0] if isinstance(languages, list) else languages

    return "unknown"


async def get_relevant_knowledge(file_paths: list[str]) -> tuple[str, set[str]]:
    """


    Retrieve relevant knowledge based on file extensions asynchronously.





    Args:


        file_paths: List of file paths to identify relevant topics.





    Returns:


        Tuple of (concatenated content string, set of loaded filenames).


    """

    knowledge_dir = settings.knowledge_dir

    if not knowledge_dir.exists():
        return "", set()

    topics = set()
    library_topics = set()

    # Get available knowledge files (library-specific)
    available_knowledge_files = {f.stem for f in knowledge_dir.glob("*.md") if f.is_file()}

    # Collect files to process for library detection
    files_to_process: list[Path] = []

    # Process file paths (both existing files and directories)
    for file_path in file_paths:
        path = Path(file_path)

        if path.is_dir():
            # If it's a directory, find all code files recursively
            for ext in EXTENSION_MAP:
                for code_file in path.rglob(f"*{ext}"):
                    if code_file.is_file():
                        files_to_process.append(code_file)
                        # Extract language topics from file extension
                        file_ext = code_file.suffix.lower()
                        if file_ext in EXTENSION_MAP:
                            mapped = EXTENSION_MAP[file_ext]
                            if isinstance(mapped, list):
                                topics.update(mapped)
                            else:
                                topics.add(mapped)
        else:
            # For file paths, check extension even if file doesn't exist
            # (useful for language detection from path alone)
            ext = path.suffix.lower()
            if ext in EXTENSION_MAP:
                mapped = EXTENSION_MAP[ext]
                if isinstance(mapped, list):
                    topics.update(mapped)
                else:
                    topics.add(mapped)

            # Only add to processing list if file exists
            if path.exists():
                files_to_process.append(path)

    # Process each file for library detection
    for path in files_to_process:
        ext = path.suffix.lower()

        # For Python files, try to detect library imports using AST parsing
        if ext == ".py" and path.exists():
            try:
                content = await asyncio.to_thread(
                    lambda fp=path: fp.read_text(encoding="utf-8", errors="replace")
                )
                # Use AST parsing for accurate import detection
                try:
                    tree = ast.parse(content, filename=str(path))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            # Handle: import lib_name, import lib_name as alias
                            for alias in node.names:
                                module_name = alias.name.split(".")[0]  # Get top-level module
                                if module_name in available_knowledge_files:
                                    library_topics.add(module_name)
                        elif isinstance(node, ast.ImportFrom) and node.module:
                            # Handle: from lib_name import ...
                            module_name = node.module.split(".")[0]  # Get top-level module
                            if module_name in available_knowledge_files:
                                library_topics.add(module_name)
                except SyntaxError:
                    # If AST parsing fails (e.g., syntax errors), fall back to regex matching
                    # This is a fallback for files with syntax errors or non-Python code
                    for lib_name in available_knowledge_files:
                        # Check for import patterns with word boundaries to avoid false positives
                        patterns = [
                            rf"\bimport\s+{re.escape(lib_name)}\b",
                            rf"\bfrom\s+{re.escape(lib_name)}\s+import\b",
                        ]
                        for pattern in patterns:
                            if re.search(pattern, content):
                                library_topics.add(lib_name)
                                break
            except Exception as e:
                # Log the error for debugging but continue processing
                logfire.debug(
                    f"Failed to detect library imports in {path}",
                    error=str(e),
                    error_type=type(e).__name__,
                )

    relevant_files: list[Path] = []

    loaded_filenames: set[str] = set()

    # Always load general.md if it exists

    general_file = knowledge_dir / "general.md"

    if general_file.exists():
        relevant_files.append(general_file)

    # Load language-specific knowledge
    for topic in topics:
        topic_file = knowledge_dir / f"{topic}.md"

        if topic_file.exists():
            relevant_files.append(topic_file)
        else:
            # Log warning as requested
            logfire.debug(f"Knowledge topic file not found: {topic}.md")

    # Load library-specific knowledge
    for lib_topic in library_topics:
        lib_file = knowledge_dir / f"{lib_topic}.md"
        if lib_file.exists() and lib_file.name not in loaded_filenames:
            relevant_files.append(lib_file)

    knowledge_content = []

    for file_path in relevant_files:
        # Skip if already processed (e.g. general.md added twice? unlikely due to logic but safe)

        if file_path.name in loaded_filenames:
            continue

        try:
            # Check size limit per file (reusing constant)

            if file_path.stat().st_size > MAX_KNOWLEDGE_FILE_SIZE:
                logfire.warning(f"Skipping large knowledge file: {file_path}")

                continue

            # Async read - capture file_path in closure
            file_path_capture = file_path
            content = await asyncio.to_thread(
                lambda fp=file_path_capture: fp.read_text(encoding="utf-8")
            )

            # Decode HTML entities (e.g., &#39; -> ', &quot; -> ", &amp; -> &)
            content = html.unescape(content)

            # Clean and optimize content (remove images, badges, normalize whitespace)
            content = _clean_knowledge_content(content)

            # Truncate if content is too long after cleaning
            if len(content) > MAX_KNOWLEDGE_CONTENT_LENGTH:
                content = content[:MAX_KNOWLEDGE_CONTENT_LENGTH] + "\n\n[... content truncated ...]"
                logfire.debug(
                    f"Truncated knowledge file {file_path.name} to {MAX_KNOWLEDGE_CONTENT_LENGTH} characters"
                )

            knowledge_content.append(content)

            loaded_filenames.add(file_path.name)

        except Exception as e:
            logfire.warning(f"Failed to read knowledge file {file_path}: {e}")

    return "\n\n".join(knowledge_content), loaded_filenames


# System prompt function (will be registered when agent is created)


async def add_dynamic_knowledge(ctx: RunContext[CouncilDeps]) -> str:
    """


    Dynamically load knowledge base files and inject into system prompt.





    This function loads specialized rules based on the file types detected in the review target,


    using the EXTENSION_MAP and checking the knowledge/ directory.


    It also loads generic knowledge files but prioritizes specific topics.


    """

    knowledge_dir = settings.knowledge_dir

    # Dynamic Knowledge Injection: Load relevant knowledge based on file extensions
    domain_rules, _loaded_filenames = await get_relevant_knowledge([ctx.deps.file_path])

    # Get debug writer from thread-safe storage
    debug_writer: DebugWriter | None = None
    with _debug_writers_lock:
        debug_writer = _debug_writers.get(ctx.deps.file_path)

    # Load and render the Jinja2 template

    try:
        jinja_env = _get_jinja_env()

        template = jinja_env.get_template("system_prompt.j2")

        # Validate extra instructions

        validated_extra_instructions = _validate_extra_instructions(ctx.deps.extra_instructions)

        # Detect language for existing language-specific guidelines

        language = detect_language(ctx.deps.file_path)

        language_specific_files: list[str] = []

        if language != "unknown" and knowledge_dir.exists():
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
                phase_instructions += (
                    "Focus on performance bottlenecks, optimization opportunities, and efficiency. "
                )

            if "maintainability" in ctx.deps.review_phases:
                phase_instructions += (
                    "Emphasize code maintainability, readability, and long-term sustainability. "
                )

            if "best_practices" in ctx.deps.review_phases:
                phase_instructions += "Apply general best practices and coding standards. "

        prompt = template.render(
            domain_rules=domain_rules,  # Injected domain rules based on file extensions
            extra_instructions=validated_extra_instructions,
            language=language,
            language_specific_files=language_specific_files,
        )

        final_prompt = prompt + phase_instructions

        # Write system prompt to debug file if enabled
        if debug_writer:
            debug_writer.write_system_prompt(
                final_prompt,
                metadata={
                    "language": language,
                    "language_specific_files": language_specific_files,
                    "loaded_filenames": list(_loaded_filenames),
                    "domain_rules_length": len(domain_rules),
                    "extra_instructions": validated_extra_instructions is not None,
                    "review_phases": ctx.deps.review_phases,
                },
            )

        return final_prompt

    except TemplateError as e:
        logfire.error("Template rendering failed", error=str(e))

        raise

    except Exception as e:
        logfire.error("Failed to generate system prompt", error=str(e))

        raise
