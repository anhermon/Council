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
