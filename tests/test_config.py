"""Tests for config module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from council.config import Settings


class TestSettings:
    """Tests for Settings class."""

    def test_templates_dir_not_exists_raises_error(self, tmp_path):
        """Test that missing templates directory raises RuntimeError."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        knowledge_dir = project_root / "knowledge"
        knowledge_dir.mkdir()
        templates_dir = project_root / "nonexistent_templates"
        # Don't create templates_dir

        with pytest.raises(RuntimeError, match="Templates directory does not exist"):
            Settings.create(
                project_root=project_root,
                knowledge_dir=knowledge_dir,
                templates_dir=templates_dir,
            )

    def test_project_root_from_env(self, tmp_path):
        """Test project root resolution from environment variable."""
        project_root = tmp_path / "custom_root"
        project_root.mkdir()
        (project_root / "knowledge").mkdir()
        (project_root / "templates").mkdir()

        with patch.dict(os.environ, {"COUNCIL_PROJECT_ROOT": str(project_root)}):
            resolved = Settings._resolve_project_root()
            assert resolved == project_root.resolve()

    def test_project_root_not_exists_raises_error(self, tmp_path):
        """Test that nonexistent project root raises RuntimeError."""
        nonexistent_root = tmp_path / "nonexistent"

        with (
            patch.dict(os.environ, {"COUNCIL_PROJECT_ROOT": str(nonexistent_root)}),
            pytest.raises(RuntimeError, match="Project root does not exist"),
        ):
            Settings._resolve_project_root()

    def test_templates_dir_fallback_to_importlib(self):
        """Test templates directory fallback to importlib.resources."""
        # This test verifies the fallback mechanism exists
        # The actual fallback will use importlib.resources which should work
        result = Settings._resolve_templates_dir()
        # Should return a valid path
        assert isinstance(result, Path)

    def test_templates_dir_fallback_importlib_error(self, tmp_path):
        """Test templates directory fallback when importlib fails."""
        from unittest.mock import MagicMock

        # Mock Path(__file__) to point to a location without templates
        fake_config_path = tmp_path / "council" / "config.py"
        fake_config_path.parent.mkdir(parents=True)

        with patch("council.config.Path") as mock_path_class:
            # Mock the Path(__file__) call
            mock_config_path = MagicMock()
            mock_config_path.resolve.return_value = fake_config_path
            mock_config_path.parent = Path(fake_config_path.parent)
            mock_path_class.return_value = mock_config_path

            # Mock templates directory to not exist
            fake_config_path.parent / "templates"
            with (
                patch.object(Path, "exists", return_value=False),
                patch("council.config.resources.files", side_effect=ModuleNotFoundError("test")),
            ):
                result = Settings._resolve_templates_dir()
                # Should return the fallback path even when importlib fails
                assert isinstance(result, Path)

    def test_parse_float_env(self):
        """Test parsing float environment variables."""
        with patch.dict(os.environ, {"TEST_FLOAT": "123.45"}):
            result = Settings._parse_float_env("TEST_FLOAT", 0.0)
            assert result == 123.45

        # Test default value
        if "TEST_FLOAT_DEFAULT" in os.environ:
            del os.environ["TEST_FLOAT_DEFAULT"]
        result = Settings._parse_float_env("TEST_FLOAT_DEFAULT", 99.9)
        assert result == 99.9

    def test_parse_int_env(self):
        """Test parsing int environment variables."""
        with patch.dict(os.environ, {"TEST_INT": "42"}):
            result = Settings._parse_int_env("TEST_INT", 0)
            assert result == 42

        # Test default value
        if "TEST_INT_DEFAULT" in os.environ:
            del os.environ["TEST_INT_DEFAULT"]
        result = Settings._parse_int_env("TEST_INT_DEFAULT", 100)
        assert result == 100

    def test_parse_bool_env(self):
        """Test parsing bool environment variables."""
        with patch.dict(os.environ, {"TEST_BOOL": "true"}):
            result = Settings._parse_bool_env("TEST_BOOL", False)
            assert result is True

        with patch.dict(os.environ, {"TEST_BOOL": "false"}):
            result = Settings._parse_bool_env("TEST_BOOL", True)
            assert result is False

        # Test default value
        if "TEST_BOOL_DEFAULT" in os.environ:
            del os.environ["TEST_BOOL_DEFAULT"]
        result = Settings._parse_bool_env("TEST_BOOL_DEFAULT", True)
        assert result is True

    def test_parse_float_env_invalid_value(self):
        """Test parsing float environment variable with invalid value."""
        with patch.dict(os.environ, {"TEST_FLOAT_INVALID": "not_a_float"}):
            result = Settings._parse_float_env("TEST_FLOAT_INVALID", 99.9)
            assert result == 99.9  # Should return default on ValueError

    def test_parse_int_env_invalid_value(self):
        """Test parsing int environment variable with invalid value."""
        with patch.dict(os.environ, {"TEST_INT_INVALID": "not_an_int"}):
            result = Settings._parse_int_env("TEST_INT_INVALID", 100)
            assert result == 100  # Should return default on ValueError

    def test_parse_bool_env_various_values(self):
        """Test parsing bool environment variable with various truthy values."""
        for value in ["1", "yes", "on"]:
            with patch.dict(os.environ, {"TEST_BOOL_VAR": value}):
                result = Settings._parse_bool_env("TEST_BOOL_VAR", False)
                assert result is True

        # Test falsy values
        for value in ["false", "0", "no", "off", "anything_else"]:
            with patch.dict(os.environ, {"TEST_BOOL_VAR": value}):
                result = Settings._parse_bool_env("TEST_BOOL_VAR", True)
                assert result is False

    def test_resolve_templates_dir_with_importlib_fspath(self, tmp_path):
        """Test templates directory resolution using importlib with __fspath__."""
        from unittest.mock import MagicMock

        fake_config_path = tmp_path / "council" / "config.py"
        fake_config_path.parent.mkdir(parents=True)
        templates_path = fake_config_path.parent / "templates"

        with patch("council.config.Path") as mock_path_class:
            mock_config_path = MagicMock()
            mock_config_path.resolve.return_value = fake_config_path
            mock_config_path.parent = Path(fake_config_path.parent)
            mock_path_class.return_value = mock_config_path

            with patch.object(Path, "exists", return_value=False):
                mock_resource = MagicMock()
                mock_resource.__fspath__ = lambda: str(templates_path)
                type(mock_resource).__fspath__ = property(lambda _: str(templates_path))

                with patch("council.config.resources.files", return_value=mock_resource):
                    result = Settings._resolve_templates_dir()
                    assert isinstance(result, Path)

    def test_resolve_templates_dir_with_importlib_iterdir(self, tmp_path):
        """Test templates directory resolution using importlib iterdir fallback."""
        from unittest.mock import MagicMock

        fake_config_path = tmp_path / "council" / "config.py"
        fake_config_path.parent.mkdir(parents=True)
        templates_path = fake_config_path.parent / "templates"
        template_file = templates_path / "system_prompt.j2"
        template_file.parent.mkdir(parents=True)

        with patch("council.config.Path") as mock_path_class:
            mock_config_path = MagicMock()
            mock_config_path.resolve.return_value = fake_config_path
            mock_config_path.parent = Path(fake_config_path.parent)
            mock_path_class.return_value = mock_config_path

            with patch.object(Path, "exists", return_value=False):
                # Mock resource without __fspath__
                mock_resource = MagicMock()
                del mock_resource.__fspath__

                # Mock iterdir to return an item with __fspath__
                mock_item = MagicMock()
                mock_item.__fspath__ = lambda: str(template_file)
                type(mock_item).__fspath__ = property(lambda _: str(template_file))
                mock_resource.iterdir.return_value = [mock_item]

                with patch("council.config.resources.files", return_value=mock_resource):
                    result = Settings._resolve_templates_dir()
                    assert isinstance(result, Path)
