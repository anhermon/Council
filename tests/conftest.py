import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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
        enable_cache=False,
    )

@pytest.fixture(autouse=True)
def patch_settings(mock_settings):
    """Patch the global settings object for all tests."""
    with patch("council.config.settings", mock_settings), \
         patch("council.tools.context.settings", mock_settings), \
         patch("council.tools.scribe.settings", mock_settings):
        yield mock_settings
