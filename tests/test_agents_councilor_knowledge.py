import pytest

from council.agents import councilor
from council.agents.councilor import EXTENSION_MAP, get_relevant_knowledge


def test_extension_map_coverage():
    assert ".py" in EXTENSION_MAP
    assert "python" in EXTENSION_MAP[".py"]
    assert ".ts" in EXTENSION_MAP
    assert "typescript" in EXTENSION_MAP[".ts"]
    assert ".tsx" in EXTENSION_MAP
    assert "react" in EXTENSION_MAP[".tsx"]
    assert "typescript" in EXTENSION_MAP[".tsx"]


@pytest.fixture
def mock_knowledge_dir(tmp_path):
    # Create a dummy knowledge directory
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()

    # Create generic file
    (knowledge_dir / "general.md").write_text("General knowledge content.")

    # Create specific topic files
    (knowledge_dir / "python.md").write_text("Python specific knowledge.")
    (knowledge_dir / "react.md").write_text("React specific knowledge.")

    return knowledge_dir


@pytest.mark.asyncio
async def test_get_relevant_knowledge_python(mock_knowledge_dir):
    original_knowledge_dir = councilor.settings.knowledge_dir
    councilor.settings.knowledge_dir = mock_knowledge_dir
    try:
        # Test with a python file
        content, loaded = await get_relevant_knowledge(["/path/to/script.py"])

        assert "General knowledge content." in content
        assert "Python specific knowledge." in content
        assert "React specific knowledge." not in content
        assert "general.md" in loaded
        assert "python.md" in loaded
    finally:
        councilor.settings.knowledge_dir = original_knowledge_dir


@pytest.mark.asyncio
async def test_get_relevant_knowledge_react(mock_knowledge_dir):
    original_knowledge_dir = councilor.settings.knowledge_dir
    councilor.settings.knowledge_dir = mock_knowledge_dir
    try:
        # Test with a react file
        content, loaded = await get_relevant_knowledge(["/path/to/app.tsx"])

        assert "General knowledge content." in content
        assert "React specific knowledge." in content
        assert "Python specific knowledge." not in content
        assert "general.md" in loaded
        assert "react.md" in loaded
    finally:
        councilor.settings.knowledge_dir = original_knowledge_dir


@pytest.mark.asyncio
async def test_get_relevant_knowledge_mixed(mock_knowledge_dir):
    original_knowledge_dir = councilor.settings.knowledge_dir
    councilor.settings.knowledge_dir = mock_knowledge_dir
    try:
        # Test with both
        content, loaded = await get_relevant_knowledge(["/path/to/script.py", "/path/to/app.tsx"])

        assert "General knowledge content." in content
        assert "Python specific knowledge." in content
        assert "React specific knowledge." in content
        assert "general.md" in loaded
        assert "python.md" in loaded
        assert "react.md" in loaded
    finally:
        councilor.settings.knowledge_dir = original_knowledge_dir


@pytest.mark.asyncio
async def test_get_relevant_knowledge_unknown(mock_knowledge_dir):
    original_knowledge_dir = councilor.settings.knowledge_dir
    councilor.settings.knowledge_dir = mock_knowledge_dir
    try:
        # Test with unknown extension
        content, loaded = await get_relevant_knowledge(["/path/to/unknown.xyz"])

        assert "General knowledge content." in content
        assert "Python specific knowledge." not in content
        assert "React specific knowledge." not in content
        assert "general.md" in loaded
    finally:
        councilor.settings.knowledge_dir = original_knowledge_dir


@pytest.mark.asyncio
async def test_get_relevant_knowledge_missing_topic_file(mock_knowledge_dir):
    original_knowledge_dir = councilor.settings.knowledge_dir
    councilor.settings.knowledge_dir = mock_knowledge_dir
    try:
        # Test with an extension that is mapped but file is missing
        # e.g. .sql -> sql.md (not created in mock)
        content, loaded = await get_relevant_knowledge(["/path/to/query.sql"])

        assert "General knowledge content." in content
        # Should not crash
    finally:
        councilor.settings.knowledge_dir = original_knowledge_dir


@pytest.mark.asyncio
async def test_get_relevant_knowledge_directory(tmp_path):
    """Test that directory paths are handled correctly."""
    # Create a test directory with Python files
    test_dir = tmp_path / "test_project"
    test_dir.mkdir()

    # Create Python files with imports
    (test_dir / "main.py").write_text("import click\nimport logfire")
    (test_dir / "utils.py").write_text("import pydantic_ai")
    (test_dir / "config.txt").write_text("config data")  # Non-code file

    # Create knowledge directory with library files
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "general.md").write_text("General knowledge.")
    (knowledge_dir / "python.md").write_text("Python knowledge.")
    (knowledge_dir / "click.md").write_text("Click library knowledge.")
    (knowledge_dir / "logfire.md").write_text("Logfire library knowledge.")
    (knowledge_dir / "pydantic_ai.md").write_text("Pydantic AI library knowledge.")

    original_knowledge_dir = councilor.settings.knowledge_dir
    councilor.settings.knowledge_dir = knowledge_dir
    try:
        # Test with directory path
        content, loaded = await get_relevant_knowledge([str(test_dir)])

        # Should load general.md and python.md (from file extensions)
        assert "General knowledge." in content
        assert "Python knowledge." in content

        # Should detect library imports from Python files
        assert "Click library knowledge." in content
        assert "Logfire library knowledge." in content
        assert "Pydantic AI library knowledge." in content

        # Verify loaded files
        assert "general.md" in loaded
        assert "python.md" in loaded
        assert "click.md" in loaded
        assert "logfire.md" in loaded
        assert "pydantic_ai.md" in loaded
    finally:
        councilor.settings.knowledge_dir = original_knowledge_dir


@pytest.mark.asyncio
async def test_get_relevant_knowledge_directory_nested(tmp_path):
    """Test that nested directories are handled correctly."""
    # Create nested directory structure
    test_dir = tmp_path / "src" / "app"
    test_dir.mkdir(parents=True)

    # Create Python files in nested structure
    (test_dir / "main.py").write_text("import click")
    (test_dir / "subdir").mkdir()
    (test_dir / "subdir" / "utils.py").write_text("import logfire")

    # Create knowledge directory
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "python.md").write_text("Python knowledge.")
    (knowledge_dir / "click.md").write_text("Click knowledge.")
    (knowledge_dir / "logfire.md").write_text("Logfire knowledge.")

    original_knowledge_dir = councilor.settings.knowledge_dir
    councilor.settings.knowledge_dir = knowledge_dir
    try:
        # Test with directory path
        content, loaded = await get_relevant_knowledge([str(test_dir)])

        # Should find files in nested directories
        assert "Python knowledge." in content
        assert "Click knowledge." in content
        assert "Logfire knowledge." in content

        assert "python.md" in loaded
        assert "click.md" in loaded
        assert "logfire.md" in loaded
    finally:
        councilor.settings.knowledge_dir = original_knowledge_dir
