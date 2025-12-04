"""Configuration and settings for The Council."""

import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Constants
DEFAULT_HTTP_TIMEOUT = 60.0
DEFAULT_SUBPROCESS_TIMEOUT = 300.0

# Default timeouts for specific operations (in seconds)
DEFAULT_STATIC_ANALYSIS_TIMEOUT = 300.0
DEFAULT_TEST_TIMEOUT = 60.0
DEFAULT_GIT_TIMEOUT = 30.0
DEFAULT_TOOL_CHECK_TIMEOUT = 10.0

# Default file size limits (in bytes)
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_MAX_OUTPUT_SIZE = 10 * 1024 * 1024  # 10MB

# Static analysis tool names
RUFF_TOOL_NAME = "ruff"
MYPY_TOOL_NAME = "mypy"
PYLINT_TOOL_NAME = "pylint"
COVERAGE_TOOL_NAME = "coverage"


@dataclass
class Settings:
    """Application settings."""

    # Paths
    project_root: Path
    knowledge_dir: Path
    templates_dir: Path

    # API Keys
    openai_api_key: str | None = None
    litellm_base_url: str | None = None
    litellm_api_key: str | None = None

    # Timeouts (in seconds)
    http_timeout: float = DEFAULT_HTTP_TIMEOUT
    subprocess_timeout: float = DEFAULT_SUBPROCESS_TIMEOUT
    static_analysis_timeout: float = DEFAULT_STATIC_ANALYSIS_TIMEOUT
    test_timeout: float = DEFAULT_TEST_TIMEOUT
    git_timeout: float = DEFAULT_GIT_TIMEOUT
    tool_check_timeout: float = DEFAULT_TOOL_CHECK_TIMEOUT

    # File size limits (in bytes)
    max_file_size: int = DEFAULT_MAX_FILE_SIZE
    max_output_size: int = DEFAULT_MAX_OUTPUT_SIZE

    # Tool names
    ruff_tool_name: str = RUFF_TOOL_NAME
    mypy_tool_name: str = MYPY_TOOL_NAME
    pylint_tool_name: str = PYLINT_TOOL_NAME
    coverage_tool_name: str = COVERAGE_TOOL_NAME

    # Caching
    enable_cache: bool = True

    # Concurrency
    max_concurrent_reviews: int = 2

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables."""
        project_root = cls._resolve_project_root()
        knowledge_dir = project_root / "knowledge"
        templates_dir = cls._resolve_templates_dir()

        # Ensure knowledge directory exists
        knowledge_dir.mkdir(parents=True, exist_ok=True)

        # Validate templates directory exists
        if not templates_dir.exists():
            raise RuntimeError(f"Templates directory does not exist: {templates_dir}")

        return cls(
            project_root=project_root,
            knowledge_dir=knowledge_dir,
            templates_dir=templates_dir,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            litellm_base_url=os.getenv("LITELLM_BASE_URL"),
            litellm_api_key=os.getenv("LITELLM_API_KEY"),
            http_timeout=cls._parse_float_env("COUNCIL_HTTP_TIMEOUT", DEFAULT_HTTP_TIMEOUT),
            subprocess_timeout=cls._parse_float_env(
                "COUNCIL_SUBPROCESS_TIMEOUT", DEFAULT_SUBPROCESS_TIMEOUT
            ),
            static_analysis_timeout=cls._parse_float_env(
                "COUNCIL_STATIC_ANALYSIS_TIMEOUT", DEFAULT_STATIC_ANALYSIS_TIMEOUT
            ),
            test_timeout=cls._parse_float_env("COUNCIL_TEST_TIMEOUT", DEFAULT_TEST_TIMEOUT),
            git_timeout=cls._parse_float_env("COUNCIL_GIT_TIMEOUT", DEFAULT_GIT_TIMEOUT),
            tool_check_timeout=cls._parse_float_env(
                "COUNCIL_TOOL_CHECK_TIMEOUT", DEFAULT_TOOL_CHECK_TIMEOUT
            ),
            max_file_size=cls._parse_int_env("COUNCIL_MAX_FILE_SIZE", DEFAULT_MAX_FILE_SIZE),
            max_output_size=cls._parse_int_env("COUNCIL_MAX_OUTPUT_SIZE", DEFAULT_MAX_OUTPUT_SIZE),
            enable_cache=cls._parse_bool_env("COUNCIL_ENABLE_CACHE", True),
            max_concurrent_reviews=cls._parse_int_env("COUNCIL_MAX_CONCURRENT_REVIEWS", 2),
        )

    @staticmethod
    def _resolve_project_root() -> Path:
        """Resolve the project root directory."""
        project_root_env = os.getenv("COUNCIL_PROJECT_ROOT")
        if project_root_env:
            project_root = Path(project_root_env).resolve()
        else:
            # Calculate from config file location (assumes config.py is in src/council/)
            config_file_path = Path(__file__).resolve()
            # Go up from config.py -> council -> src -> project root
            project_root = config_file_path.parent.parent.parent.resolve()

        # Validate that project root exists
        if not project_root.exists():
            raise RuntimeError(
                f"Project root does not exist: {project_root}. "
                "Set COUNCIL_PROJECT_ROOT environment variable to override."
            )

        return project_root

    @staticmethod
    def _resolve_templates_dir() -> Path:
        """Resolve the templates directory location."""
        # First try __file__ based approach (works in development and most install scenarios)
        config_file_path = Path(__file__).resolve()
        templates_dir = config_file_path.parent / "templates"

        # If templates don't exist relative to config file, try using importlib.resources
        # This handles cases where the package is installed in a non-standard location
        if not templates_dir.exists():
            try:
                templates_resource = resources.files("council.templates")
                # Try to get a real file system path
                if hasattr(templates_resource, "__fspath__"):
                    templates_dir = Path(templates_resource.__fspath__())
                else:
                    # Try to find any file in the templates package and use its parent
                    for item in templates_resource.iterdir():
                        if hasattr(item, "__fspath__"):
                            templates_dir = Path(item.__fspath__()).parent
                            break
            except (ModuleNotFoundError, AttributeError, TypeError) as e:
                # Log the specific error for debugging
                # In production, you might want to use proper logging
                import sys

                print(
                    f"Warning: Could not resolve templates directory via importlib.resources: {e}",
                    file=sys.stderr,
                )
                # Keep the __file__ based path as fallback

        return templates_dir

    @staticmethod
    def _parse_float_env(env_var: str, default: float) -> float:
        """Parse a float value from environment variable."""
        try:
            return float(os.getenv(env_var, str(default)))
        except ValueError:
            return default

    @staticmethod
    def _parse_bool_env(env_var: str, default: bool) -> bool:
        """Parse a boolean value from environment variable."""
        value = os.getenv(env_var, str(default)).lower()
        return value in ("true", "1", "yes", "on")

    @staticmethod
    def _parse_int_env(env_var: str, default: int) -> int:
        """Parse an integer value from environment variable."""
        try:
            return int(os.getenv(env_var, str(default)))
        except ValueError:
            return default


def get_settings() -> Settings:
    """Get the settings instance. Use this instead of global variable for better testability."""
    return Settings.from_env()


# For backward compatibility - but consider using get_settings() instead
settings = get_settings()
