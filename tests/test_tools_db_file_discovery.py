"""Tests for database file discovery."""

from council.tools.db_file_discovery import discover_sql_files, has_database_code


class TestHasDatabaseCode:
    """Test has_database_code function."""

    def test_has_database_code_with_psycopg2(self, mock_settings):
        """Test detection of psycopg2 import."""
        test_file = mock_settings.project_root / "db_code.py"
        test_file.write_text("import psycopg2\n\nconn = psycopg2.connect()")

        assert has_database_code(test_file) is True

    def test_has_database_code_with_sqlalchemy(self, mock_settings):
        """Test detection of SQLAlchemy import."""
        test_file = mock_settings.project_root / "db_code.py"
        test_file.write_text("from sqlalchemy import create_engine")

        assert has_database_code(test_file) is True

    def test_has_database_code_with_sql_query(self, mock_settings):
        """Test detection of SQL query string."""
        test_file = mock_settings.project_root / "db_code.py"
        test_file.write_text('query = "SELECT * FROM users"')

        assert has_database_code(test_file) is True

    def test_has_database_code_without_db_code(self, mock_settings):
        """Test file without database code."""
        test_file = mock_settings.project_root / "normal.py"
        test_file.write_text("def hello():\n    return 'world'")

        assert has_database_code(test_file) is False

    def test_has_database_code_nonexistent_file(self, mock_settings):
        """Test with non-existent file."""
        test_file = mock_settings.project_root / "nonexistent.py"
        assert has_database_code(test_file) is False


class TestDiscoverSqlFiles:
    """Test discover_sql_files function."""

    def test_discover_sql_files_finds_schema(self, mock_settings):
        """Test discovery of schema.sql file."""
        # Create database code file
        db_file = mock_settings.project_root / "src" / "database.py"
        db_file.parent.mkdir(parents=True, exist_ok=True)
        db_file.write_text("import psycopg2\n\nconn = psycopg2.connect()")

        # Create SQL files
        db_dir = mock_settings.project_root / "db"
        db_dir.mkdir(exist_ok=True)
        schema_file = db_dir / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id INT);")

        sql_files = discover_sql_files(db_file, mock_settings.project_root)
        assert len(sql_files) > 0
        assert any("schema.sql" in str(f) for f in sql_files)

    def test_discover_sql_files_finds_queries(self, mock_settings):
        """Test discovery of queries.sql file."""
        # Create database code file
        db_file = mock_settings.project_root / "src" / "database.py"
        db_file.parent.mkdir(parents=True, exist_ok=True)
        db_file.write_text("import psycopg2")

        # Create queries file
        db_dir = mock_settings.project_root / "db"
        db_dir.mkdir(exist_ok=True)
        queries_file = db_dir / "queries.sql"
        queries_file.write_text("SELECT * FROM users;")

        sql_files = discover_sql_files(db_file, mock_settings.project_root)
        assert len(sql_files) > 0
        assert any("queries.sql" in str(f) for f in sql_files)

    def test_discover_sql_files_no_db_code(self, mock_settings):
        """Test that SQL files are not discovered for non-database code."""
        normal_file = mock_settings.project_root / "normal.py"
        normal_file.write_text("def hello():\n    return 'world'")

        # Create SQL files
        db_dir = mock_settings.project_root / "db"
        db_dir.mkdir(exist_ok=True)
        schema_file = db_dir / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id INT);")

        sql_files = discover_sql_files(normal_file, mock_settings.project_root)
        assert len(sql_files) == 0

    def test_discover_sql_files_searches_parent_directories(self, mock_settings):
        """Test that discovery searches parent directories."""
        # Create nested structure
        nested_file = mock_settings.project_root / "app" / "services" / "db_service.py"
        nested_file.parent.mkdir(parents=True, exist_ok=True)
        nested_file.write_text("import psycopg2")

        # Create SQL files in parent directory
        db_dir = mock_settings.project_root / "db"
        db_dir.mkdir(exist_ok=True)
        schema_file = db_dir / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id INT);")

        sql_files = discover_sql_files(nested_file, mock_settings.project_root)
        assert len(sql_files) > 0
