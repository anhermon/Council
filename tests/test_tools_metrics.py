"""Tests for code metrics tools."""

import pytest

from council.tools.metrics import ComplexityVisitor, calculate_complexity


class TestComplexityVisitor:
    """Test ComplexityVisitor class."""

    def test_visitor_initialization(self):
        """Test visitor initialization."""
        visitor = ComplexityVisitor()
        assert visitor.complexity == 1
        assert visitor.functions == []

    def test_visit_simple_function(self):
        """Test visiting a simple function."""
        import ast

        code = """def simple_function():
    return 1
"""
        tree = ast.parse(code)
        visitor = ComplexityVisitor()
        visitor.visit(tree)
        assert len(visitor.functions) == 1
        assert visitor.functions[0]["name"] == "simple_function"
        assert visitor.functions[0]["complexity"] == 1

    def test_visit_function_with_conditionals(self):
        """Test visiting function with conditionals."""
        import ast

        code = """def complex_function(x):
    if x > 0:
        return 1
    elif x < 0:
        return -1
    else:
        return 0
"""
        tree = ast.parse(code)
        visitor = ComplexityVisitor()
        visitor.visit(tree)
        assert len(visitor.functions) == 1
        # Should have complexity > 1 due to if/elif
        assert visitor.functions[0]["complexity"] > 1

    def test_visit_function_with_loops(self):
        """Test visiting function with loops."""
        import ast

        code = """def loop_function(items):
    for item in items:
        if item:
            process(item)
    while condition:
        do_something()
"""
        tree = ast.parse(code)
        visitor = ComplexityVisitor()
        visitor.visit(tree)
        assert len(visitor.functions) == 1
        # Should have complexity > 1 due to for/while/if
        assert visitor.functions[0]["complexity"] > 1

    def test_visit_class_definitions(self):
        """Test visiting class definitions."""
        import ast

        code = """class MyClass:
    def method(self):
        return 1
"""
        tree = ast.parse(code)
        visitor = ComplexityVisitor()
        visitor.visit(tree)
        # Should visit methods inside class
        assert len(visitor.functions) == 1


class TestCalculateComplexity:
    """Test calculate_complexity function."""

    @pytest.mark.asyncio
    async def test_calculate_complexity_simple_file(self, mock_settings):
        """Test complexity calculation for simple Python file."""
        test_file = mock_settings.project_root / "simple.py"
        test_file.write_text(
            """def hello():
    return "world"
"""
        )

        result = await calculate_complexity(str(test_file))
        assert "cyclomatic_complexity" in result
        assert "maintainability_index" in result
        assert "function_complexities" in result
        assert result["cyclomatic_complexity"] >= 1

    @pytest.mark.asyncio
    async def test_calculate_complexity_complex_file(self, mock_settings):
        """Test complexity calculation for complex file."""
        test_file = mock_settings.project_root / "complex.py"
        test_file.write_text(
            """def complex_function(x, y):
    if x > 0:
        if y > 0:
            return x + y
        else:
            return x - y
    else:
        if y > 0:
            return -x + y
        else:
            return -x - y

def another_function(items):
    result = []
    for item in items:
        if item:
            result.append(item)
    return result
"""
        )

        result = await calculate_complexity(str(test_file))
        assert result["cyclomatic_complexity"] > 1
        assert len(result["function_complexities"]) == 2
        assert result["maintainability_index"] >= 0
        assert result["maintainability_index"] <= 100

    @pytest.mark.asyncio
    async def test_calculate_complexity_not_python(self, mock_settings):
        """Test complexity calculation for non-Python file."""
        test_file = mock_settings.project_root / "file.txt"
        test_file.write_text("text content")

        result = await calculate_complexity(str(test_file))
        assert result["cyclomatic_complexity"] == 0
        assert "Python files" in result["note"]

    @pytest.mark.asyncio
    async def test_calculate_complexity_syntax_error(self, mock_settings):
        """Test complexity calculation with syntax errors."""
        test_file = mock_settings.project_root / "syntax_error.py"
        test_file.write_text(
            """def broken_function(
    # Missing closing parenthesis
"""
        )

        result = await calculate_complexity(str(test_file))
        assert "syntax errors" in result["note"].lower()
        assert result["cyclomatic_complexity"] == 0

    @pytest.mark.asyncio
    async def test_calculate_complexity_nonexistent_file(self):
        """Test with nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await calculate_complexity("nonexistent.py")

    @pytest.mark.asyncio
    async def test_calculate_complexity_not_a_file(self, mock_settings):
        """Test with directory."""
        test_dir = mock_settings.project_root / "test_dir"
        test_dir.mkdir()
        with pytest.raises(ValueError, match="not a file"):
            await calculate_complexity(str(test_dir))

    @pytest.mark.asyncio
    async def test_calculate_complexity_with_comments(self, mock_settings):
        """Test complexity calculation includes comment ratio."""
        test_file = mock_settings.project_root / "commented.py"
        test_file.write_text(
            """# This is a comment
# Another comment
def function():
    # Function comment
    return 1  # Inline comment
"""
        )

        result = await calculate_complexity(str(test_file))
        assert "comment_ratio" in result
        assert result["comment_ratio"] > 0

    @pytest.mark.asyncio
    async def test_calculate_complexity_empty_file(self, mock_settings):
        """Test complexity calculation for empty file."""
        test_file = mock_settings.project_root / "empty.py"
        test_file.write_text("")

        result = await calculate_complexity(str(test_file))
        assert result["cyclomatic_complexity"] >= 0
        assert len(result["function_complexities"]) == 0

    @pytest.mark.asyncio
    async def test_calculate_complexity_with_base_path(self, tmp_path):
        """Test complexity calculation with base_path."""
        test_file = tmp_path / "module.py"
        test_file.write_text("def func(): return 1")

        result = await calculate_complexity(str(test_file), base_path=str(tmp_path))
        assert "cyclomatic_complexity" in result

    @pytest.mark.asyncio
    async def test_calculate_complexity_bool_ops(self, mock_settings):
        """Test complexity calculation includes boolean operations."""
        test_file = mock_settings.project_root / "bool_ops.py"
        test_file.write_text(
            """def function(x, y):
    if x > 0 and y > 0 or x < 0:
        return 1
    return 0
"""
        )

        result = await calculate_complexity(str(test_file))
        # Boolean operations should increase complexity
        assert result["cyclomatic_complexity"] > 1
