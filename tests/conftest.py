import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add src to path so we can import from council
sys.path.append(str(Path(__file__).parent.parent / "src"))

from council.config import Settings


@pytest.fixture
def mock_project_root(tmp_path):
    """Create a mock project root with necessary directories."""
    root = tmp_path / "mock_project"
    root.mkdir()
    (root / "src").mkdir()
    (root / "knowledge").mkdir()
    (root / "templates").mkdir()
    return root


@pytest.fixture
def mock_settings(mock_project_root):
    """Create mock settings."""
    return Settings(
        project_root=mock_project_root,
        knowledge_dir=mock_project_root / "knowledge",
        templates_dir=mock_project_root / "templates",
        openai_api_key="mock-key",
        http_timeout=1.0,
        subprocess_timeout=1.0,
        static_analysis_timeout=300.0,
        test_timeout=60.0,
        git_timeout=30.0,
        tool_check_timeout=10.0,
        max_file_size=10 * 1024 * 1024,
        max_output_size=10 * 1024 * 1024,
        ruff_tool_name="ruff",
        mypy_tool_name="mypy",
        pylint_tool_name="pylint",
        coverage_tool_name="coverage",
        enable_cache=False,
    )


@pytest.fixture(autouse=True)
def patch_settings(mock_settings):
    """Patch the global settings object for all tests."""
    # Patch get_settings() first, then patch module-level settings with create=True
    # to handle cases where modules haven't been imported yet
    with (
        patch("council.config.get_settings", return_value=mock_settings),
        patch("council.config.settings", mock_settings, create=True),
        patch("council.tools.repomix.settings", mock_settings, create=True),
        patch("council.tools.scribe.settings", mock_settings, create=True),
        patch("council.tools.path_utils.settings", mock_settings, create=True),
        patch("council.tools.static_analysis.settings", mock_settings, create=True),
        patch("council.tools.testing.settings", mock_settings, create=True),
        patch("council.tools.git_tools.settings", mock_settings, create=True),
        patch("council.tools.utils.settings", mock_settings, create=True),
        patch("council.tools.validation.settings", mock_settings, create=True),
        patch("council.tools.cache.settings", mock_settings, create=True),
        patch("council.tools.code_analysis.settings", mock_settings, create=True),
        patch("council.tools.persistence.settings", mock_settings, create=True),
        patch("council.tools.security.settings", mock_settings, create=True),
    ):
        yield mock_settings
