"""Tests for architecture analysis tools."""

import pytest

from council.tools.architecture import analyze_architecture


class TestAnalyzeArchitecture:
    """Test analyze_architecture function."""

    @pytest.mark.asyncio
    async def test_analyze_simple_file(self, mock_settings):
        """Test architecture analysis for simple file."""
        test_file = mock_settings.project_root / "simple.py"
        test_file.write_text(
            """def hello():
    return "world"
"""
        )

        result = await analyze_architecture(str(test_file))
        assert "design_patterns" in result
        assert "anti_patterns" in result
        assert "coupling_analysis" in result
        assert "cohesion_score" in result
        assert "recommendations" in result
        assert isinstance(result["cohesion_score"], int | float)
        assert 0 <= result["cohesion_score"] <= 100

    @pytest.mark.asyncio
    async def test_analyze_singleton_pattern(self, mock_settings):
        """Test detection of Singleton pattern."""
        test_file = mock_settings.project_root / "singleton.py"
        test_file.write_text(
            """class Singleton:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
"""
        )

        result = await analyze_architecture(str(test_file))
        assert "Singleton" in result["design_patterns"]

    @pytest.mark.asyncio
    async def test_analyze_factory_pattern(self, mock_settings):
        """Test detection of Factory pattern."""
        test_file = mock_settings.project_root / "factory.py"
        test_file.write_text(
            """class Factory:
    def create_object(self, type):
        if type == "A":
            return ObjectA()
        return ObjectB()
"""
        )

        result = await analyze_architecture(str(test_file))
        assert "Factory" in result["design_patterns"]

    @pytest.mark.asyncio
    async def test_analyze_observer_pattern(self, mock_settings):
        """Test detection of Observer pattern."""
        test_file = mock_settings.project_root / "observer.py"
        test_file.write_text(
            """class Observer:
    def notify(self, event):
        pass

def subscribe(observer):
    pass
"""
        )

        result = await analyze_architecture(str(test_file))
        assert "Observer" in result["design_patterns"]

    @pytest.mark.asyncio
    async def test_analyze_strategy_pattern(self, mock_settings):
        """Test detection of Strategy pattern."""
        test_file = mock_settings.project_root / "strategy.py"
        test_file.write_text(
            """class Strategy:
    def algorithm(self):
        pass
"""
        )

        result = await analyze_architecture(str(test_file))
        assert "Strategy" in result["design_patterns"]

    @pytest.mark.asyncio
    async def test_analyze_god_object(self, mock_settings):
        """Test detection of God Object anti-pattern."""
        test_file = mock_settings.project_root / "god_object.py"
        # Create a class with many methods
        methods = "\n".join([f"    def method_{i}(self): pass" for i in range(25)])
        test_file.write_text(
            f"""class GodObject:
{methods}
"""
        )

        result = await analyze_architecture(str(test_file))
        assert any("God Object" in anti for anti in result["anti_patterns"])

    @pytest.mark.asyncio
    async def test_analyze_long_parameter_list(self, mock_settings):
        """Test detection of long parameter list anti-pattern."""
        test_file = mock_settings.project_root / "long_params.py"
        test_file.write_text(
            """def function_with_many_params(a, b, c, d, e, f, g, h, i):
    return a + b + c + d + e + f + g + h + i
"""
        )

        result = await analyze_architecture(str(test_file))
        assert any("Long Parameter List" in anti for anti in result["anti_patterns"])

    @pytest.mark.asyncio
    async def test_analyze_deep_nesting(self, mock_settings):
        """Test detection of deep nesting anti-pattern."""
        test_file = mock_settings.project_root / "deep_nesting.py"
        test_file.write_text(
            """def deeply_nested():
    if True:
        if True:
            if True:
                if True:
                    if True:
                        if True:
                            return 1
"""
        )

        result = await analyze_architecture(str(test_file))
        assert any("Deep Nesting" in anti for anti in result["anti_patterns"])

    @pytest.mark.asyncio
    async def test_analyze_high_coupling(self, mock_settings):
        """Test detection of high coupling."""
        test_file = mock_settings.project_root / "high_coupling.py"
        imports = "\n".join([f"import module_{i}" for i in range(20)])
        test_file.write_text(
            f"""{imports}

def function():
    pass
"""
        )

        result = await analyze_architecture(str(test_file))
        assert any("High Coupling" in issue for issue in result["coupling_analysis"]["issues"])

    @pytest.mark.asyncio
    async def test_analyze_directory(self, mock_settings):
        """Test architecture analysis for directory."""
        test_dir = mock_settings.project_root / "test_dir"
        test_dir.mkdir()
        (test_dir / "file1.py").write_text("def func1(): pass")
        (test_dir / "file2.py").write_text("def func2(): pass")

        result = await analyze_architecture(str(test_dir))
        assert "design_patterns" in result
        assert isinstance(result["cohesion_score"], int | float)

    @pytest.mark.asyncio
    async def test_analyze_not_python_file(self, mock_settings):
        """Test analysis for non-Python file."""
        test_file = mock_settings.project_root / "file.txt"
        test_file.write_text("text content")

        result = await analyze_architecture(str(test_file))
        assert result["cohesion_score"] == 0
        # Should have a recommendation about unsupported file type
        assert len(result["recommendations"]) > 0
        assert (
            "not supported" in result["recommendations"][0].lower()
            or ".txt" in result["recommendations"][0]
        )

    @pytest.mark.asyncio
    async def test_analyze_nonexistent_file(self):
        """Test with nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await analyze_architecture("nonexistent.py")

    @pytest.mark.asyncio
    async def test_analyze_syntax_error(self, mock_settings):
        """Test handling of files with syntax errors."""
        test_file = mock_settings.project_root / "syntax_error.py"
        test_file.write_text(
            """def broken_function(
    # Missing closing parenthesis
"""
        )

        result = await analyze_architecture(str(test_file))
        # Should handle gracefully, skipping files with syntax errors
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_analyze_with_base_path(self, tmp_path):
        """Test analysis with base_path parameter."""
        test_file = tmp_path / "module.py"
        test_file.write_text("def func(): pass")

        result = await analyze_architecture(str(test_file), base_path=str(tmp_path))
        assert "design_patterns" in result

    @pytest.mark.asyncio
    async def test_analyze_cohesion_score_calculation(self, mock_settings):
        """Test cohesion score calculation."""
        test_file = mock_settings.project_root / "clean.py"
        test_file.write_text(
            """def function1():
    return 1

def function2():
    return 2
"""
        )

        result = await analyze_architecture(str(test_file))
        # Clean code should have high cohesion score
        assert result["cohesion_score"] >= 80

    @pytest.mark.asyncio
    async def test_analyze_removes_duplicates(self, mock_settings):
        """Test that duplicate patterns are removed."""
        test_file = mock_settings.project_root / "patterns.py"
        test_file.write_text(
            """class Singleton1:
    _instance = None

class Singleton2:
    __instance = None
"""
        )

        result = await analyze_architecture(str(test_file))
        # Should only have one "Singleton" entry
        assert result["design_patterns"].count("Singleton") == 1

    @pytest.mark.asyncio
    async def test_analyze_directory_limit(self, mock_settings):
        """Test that directory analysis is limited to 50 files."""
        test_dir = mock_settings.project_root / "large_dir"
        test_dir.mkdir()
        # Create more than 50 files
        for i in range(60):
            (test_dir / f"file_{i}.py").write_text(f"def func_{i}(): pass")

        result = await analyze_architecture(str(test_dir))
        # Should still complete successfully
        assert isinstance(result, dict)
