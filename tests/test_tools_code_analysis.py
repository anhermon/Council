"""Tests for code analysis tools."""

import pytest

from council.tools.code_analysis import (
    analyze_imports,
    read_file,
    search_codebase,
    write_file,
    write_file_chunk,
)


class TestReadFile:
    """Test read_file function."""

    @pytest.mark.asyncio
    async def test_read_file_success(self, mock_settings):
        """Test successful file reading."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("# test content")

        result = await read_file(str(test_file))
        assert "# test content" in result

    @pytest.mark.asyncio
    async def test_read_file_nonexistent(self):
        """Test reading nonexistent file."""
        result = await read_file("nonexistent.py")
        assert "Error" in result or "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_read_file_not_a_file(self, mock_settings):
        """Test reading directory."""
        test_dir = mock_settings.project_root / "test_dir"
        test_dir.mkdir()
        result = await read_file(str(test_dir))
        assert "not a file" in result.lower()

    @pytest.mark.asyncio
    async def test_read_file_too_large(self, mock_settings):
        """Test reading file that exceeds size limit."""
        test_file = mock_settings.project_root / "large.py"
        # Create file larger than max_file_size
        large_content = "x" * (mock_settings.max_file_size + 1)
        test_file.write_text(large_content)

        result = await read_file(str(test_file))
        assert "too large" in result.lower()

    @pytest.mark.asyncio
    async def test_read_file_with_base_path(self, tmp_path):
        """Test reading file with base_path."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# content")

        result = await read_file(str(test_file), base_path=str(tmp_path))
        assert "# content" in result

    @pytest.mark.asyncio
    async def test_read_file_src_council_fallback(self, mock_settings):
        """Test fallback to src/council path."""
        # Create file in src/council
        src_council = mock_settings.project_root / "src" / "council"
        src_council.mkdir(parents=True, exist_ok=True)
        test_file = src_council / "test.py"
        test_file.write_text("# src/council content")

        # Try reading with short path
        result = await read_file("test.py")
        assert "# src/council content" in result


class TestSearchCodebase:
    """Test search_codebase function."""

    @pytest.mark.asyncio
    async def test_search_codebase_success(self, mock_settings):
        """Test successful codebase search."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("def search_function(): pass")

        result = await search_codebase("search_function")
        assert len(result) > 0
        assert any("test.py" in r for r in result)

    @pytest.mark.asyncio
    async def test_search_codebase_empty_query(self):
        """Test search with empty query."""
        with pytest.raises(ValueError, match="cannot be empty"):
            await search_codebase("")

    @pytest.mark.asyncio
    async def test_search_codebase_too_long(self):
        """Test search with query too long."""
        long_query = "x" * 1001
        with pytest.raises(ValueError, match="too long"):
            await search_codebase(long_query)

    @pytest.mark.asyncio
    async def test_search_codebase_with_pattern(self, mock_settings):
        """Test search with file pattern."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("def test(): pass")

        result = await search_codebase("test", file_pattern="*.py")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_search_codebase_regex(self, mock_settings):
        """Test search with regex pattern."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("def test_function(): pass")

        result = await search_codebase(r"def\s+\w+", file_pattern="*.py")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_search_codebase_invalid_pattern(self):
        """Test search with invalid file pattern."""
        with pytest.raises(ValueError, match="cannot contain"):
            await search_codebase("test", file_pattern="../*.py")

    @pytest.mark.asyncio
    async def test_search_codebase_limit(self, mock_settings):
        """Test search respects MAX_SEARCH_RESULTS."""
        # Create many files
        for i in range(60):
            test_file = mock_settings.project_root / f"test{i}.py"
            test_file.write_text("def test(): pass")

        result = await search_codebase("test", file_pattern="*.py")
        assert len(result) <= 50  # MAX_SEARCH_RESULTS


class TestAnalyzeImports:
    """Test analyze_imports function."""

    @pytest.mark.asyncio
    async def test_analyze_imports_simple(self, mock_settings):
        """Test analyzing simple imports."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("import os\nfrom pathlib import Path")

        result = await analyze_imports(str(test_file))
        assert "imports" in result
        assert "from_imports" in result
        assert "os" in result["imports"]

    @pytest.mark.asyncio
    async def test_analyze_imports_nonexistent(self):
        """Test analyzing nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await analyze_imports("nonexistent.py")

    @pytest.mark.asyncio
    async def test_analyze_imports_not_python(self, mock_settings):
        """Test analyzing non-Python file."""
        test_file = mock_settings.project_root / "test.txt"
        test_file.write_text("text content")

        result = await analyze_imports(str(test_file))
        assert result["imports"] == []
        assert "Python files" in result["note"]

    @pytest.mark.asyncio
    async def test_analyze_imports_syntax_error(self, mock_settings):
        """Test analyzing file with syntax errors."""
        test_file = mock_settings.project_root / "syntax_error.py"
        test_file.write_text("import os\ninvalid syntax here")

        result = await analyze_imports(str(test_file))
        assert result["imports"] == []
        assert "syntax errors" in result["note"].lower()

    @pytest.mark.asyncio
    async def test_analyze_imports_from_imports(self, mock_settings):
        """Test analyzing from imports."""
        test_file = mock_settings.project_root / "test.py"
        test_file.write_text("from pathlib import Path, PosixPath")

        result = await analyze_imports(str(test_file))
        assert len(result["from_imports"]) > 0
        assert result["from_imports"][0]["module"] == "pathlib"

    @pytest.mark.asyncio
    async def test_analyze_imports_with_base_path(self, tmp_path):
        """Test analyzing imports with base_path."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        result = await analyze_imports(str(test_file), base_path=str(tmp_path))
        assert "imports" in result


class TestWriteFile:
    """Test write_file function."""

    @pytest.mark.asyncio
    async def test_write_file_success(self, mock_settings):
        """Test successful file writing."""
        test_file = mock_settings.project_root / "new_file.py"
        content = "# new file content"

        result = await write_file(str(test_file), content)
        assert "Successfully" in result
        assert test_file.exists()
        assert test_file.read_text() == content

    @pytest.mark.asyncio
    async def test_write_file_overwrite(self, mock_settings):
        """Test overwriting existing file."""
        test_file = mock_settings.project_root / "existing.py"
        test_file.write_text("# old content")

        new_content = "# new content"
        await write_file(str(test_file), new_content)
        assert test_file.read_text() == new_content

    @pytest.mark.asyncio
    async def test_write_file_creates_directories(self, mock_settings):
        """Test that parent directories are created."""
        test_file = mock_settings.project_root / "new" / "dir" / "file.py"
        content = "# content"

        await write_file(str(test_file), content)
        assert test_file.exists()
        assert test_file.read_text() == content

    @pytest.mark.asyncio
    async def test_write_file_too_large(self, mock_settings):
        """Test writing content that exceeds size limit."""
        test_file = mock_settings.project_root / "large.py"
        large_content = "x" * (mock_settings.max_file_size + 1)

        with pytest.raises(ValueError, match="too large"):
            await write_file(str(test_file), large_content)

    @pytest.mark.asyncio
    async def test_write_file_outside_project(self, tmp_path):
        """Test writing file outside project root without base_path."""
        outside_file = tmp_path / "outside.py"

        with pytest.raises(ValueError, match="within project root|outside allowed directories"):
            await write_file(str(outside_file), "# content")

    @pytest.mark.asyncio
    async def test_write_file_with_base_path(self, tmp_path):
        """Test writing file with base_path."""
        test_file = tmp_path / "test.py"
        content = "# content"

        # With base_path provided, writing should succeed
        result = await write_file(str(test_file), content, base_path=str(tmp_path))
        assert "Successfully" in result
        assert test_file.exists()
        assert test_file.read_text() == content


class TestWriteFileChunk:
    """Test write_file_chunk function."""

    @pytest.mark.asyncio
    async def test_write_file_chunk_first(self, mock_settings):
        """Test writing first chunk."""
        test_file = mock_settings.project_root / "chunked.py"
        content = "# chunk 1"

        result = await write_file_chunk(str(test_file), content, chunk_index=0, total_chunks=2)
        assert "chunk 1/2" in result
        assert test_file.exists()
        assert test_file.read_text() == content

    @pytest.mark.asyncio
    async def test_write_file_chunk_append(self, mock_settings):
        """Test appending subsequent chunks."""
        test_file = mock_settings.project_root / "chunked.py"
        test_file.write_text("# chunk 1")

        result = await write_file_chunk(
            str(test_file), "\n# chunk 2", chunk_index=1, total_chunks=2
        )
        assert "chunk 2/2" in result or "final" in result.lower()
        assert "# chunk 1" in test_file.read_text()
        assert "# chunk 2" in test_file.read_text()

    @pytest.mark.asyncio
    async def test_write_file_chunk_single(self, mock_settings):
        """Test writing single chunk."""
        test_file = mock_settings.project_root / "single.py"
        content = "# single chunk"

        await write_file_chunk(str(test_file), content, chunk_index=0, total_chunks=1)
        assert test_file.read_text() == content

    @pytest.mark.asyncio
    async def test_write_file_chunk_invalid_index(self, mock_settings):
        """Test with invalid chunk_index."""
        test_file = mock_settings.project_root / "test.py"

        with pytest.raises(ValueError):
            await write_file_chunk(str(test_file), "content", chunk_index=-1, total_chunks=1)

        with pytest.raises(ValueError):
            await write_file_chunk(str(test_file), "content", chunk_index=2, total_chunks=2)

    @pytest.mark.asyncio
    async def test_write_file_chunk_invalid_total(self, mock_settings):
        """Test with invalid total_chunks."""
        test_file = mock_settings.project_root / "test.py"

        with pytest.raises(ValueError):
            await write_file_chunk(str(test_file), "content", chunk_index=0, total_chunks=0)

    @pytest.mark.asyncio
    async def test_write_file_chunk_too_large(self, mock_settings):
        """Test chunk that exceeds size limit."""
        test_file = mock_settings.project_root / "large.py"
        large_content = "x" * (mock_settings.max_file_size + 1)

        with pytest.raises(ValueError, match="too large"):
            await write_file_chunk(str(test_file), large_content, chunk_index=0, total_chunks=1)
