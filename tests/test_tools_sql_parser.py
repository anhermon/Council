"""Tests for SQL parser."""

from council.tools.sql_parser import parse_schema_file, parse_sql_query


class TestParseSqlQuery:
    """Test parse_sql_query function."""

    def test_parse_simple_select(self):
        """Test parsing simple SELECT query."""
        query = "SELECT id, name FROM users WHERE id = 1"
        result = parse_sql_query(query)

        assert "users" in result["tables"]
        assert "id" in result["columns"]
        assert "name" in result["columns"]

    def test_parse_select_with_join(self):
        """Test parsing SELECT with JOIN."""
        query = """
        SELECT p.id, p.name, c.name AS category
        FROM products p
        JOIN categories c ON p.category_id = c.id
        """
        result = parse_sql_query(query)

        assert "products" in result["tables"]
        assert "categories" in result["tables"]
        assert len(result["joins"]) > 0

    def test_parse_insert(self):
        """Test parsing INSERT query."""
        query = "INSERT INTO users (username, email) VALUES ('test', 'test@example.com')"
        result = parse_sql_query(query)

        assert "users" in result["tables"]
        assert "username" in result["columns"]
        assert "email" in result["columns"]

    def test_parse_update(self):
        """Test parsing UPDATE query."""
        query = "UPDATE users SET email = 'new@example.com' WHERE id = 1"
        result = parse_sql_query(query)

        assert "users" in result["tables"]
        assert "email" in result["columns"]

    def test_parse_delete(self):
        """Test parsing DELETE query."""
        query = "DELETE FROM users WHERE id = 1"
        result = parse_sql_query(query)

        assert "users" in result["tables"]


class TestParseSchemaFile:
    """Test parse_schema_file function."""

    def test_parse_simple_table(self):
        """Test parsing simple CREATE TABLE."""
        schema = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) NOT NULL,
            email VARCHAR(100) UNIQUE
        );
        """
        result = parse_schema_file(schema)

        assert "users" in result["tables"]
        assert len(result["tables"]["users"]["columns"]) == 3
        assert "id" in [c["name"] for c in result["tables"]["users"]["columns"]]
        assert "id" in result["tables"]["users"]["primary_keys"]

    def test_parse_table_with_foreign_key_inline(self):
        """Test parsing table with inline FOREIGN KEY."""
        schema = """
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            total_amount DECIMAL(10, 2)
        );
        """
        result = parse_schema_file(schema)

        assert "orders" in result["tables"]
        fks = result["tables"]["orders"]["foreign_keys"]
        assert len(fks) > 0
        assert any(fk["column"] == "user_id" and fk["references_table"] == "users" for fk in fks)

    def test_parse_table_with_foreign_key_constraint(self):
        """Test parsing table with explicit FOREIGN KEY constraint."""
        schema = """
        CREATE TABLE order_items (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );
        """
        result = parse_schema_file(schema)

        assert "order_items" in result["tables"]
        fks = result["tables"]["order_items"]["foreign_keys"]
        assert len(fks) > 0

    def test_parse_multiple_tables(self):
        """Test parsing multiple tables."""
        schema = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50)
        );

        CREATE TABLE products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200)
        );
        """
        result = parse_schema_file(schema)

        assert "users" in result["tables"]
        assert "products" in result["tables"]
        assert len(result["tables"]) == 2

    def test_parse_table_with_index(self):
        """Test parsing CREATE INDEX statements."""
        schema = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(100)
        );

        CREATE INDEX idx_users_email ON users(email);
        """
        result = parse_schema_file(schema)

        assert "users" in result["tables"]
        assert "indexes" in result["tables"]["users"]
        assert len(result["tables"]["users"]["indexes"]) > 0

    def test_parse_relationships(self):
        """Test that relationships are extracted from foreign keys."""
        schema = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50)
        );

        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id)
        );
        """
        result = parse_schema_file(schema)

        assert len(result["relationships"]) > 0
        rel = result["relationships"][0]
        assert rel["from_table"] == "orders"
        assert rel["to_table"] == "users"
        assert rel["foreign_key"] == "user_id"

    def test_parse_self_referencing_foreign_key(self):
        """Test parsing self-referencing foreign key."""
        schema = """
        CREATE TABLE categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            parent_id INTEGER REFERENCES categories(id)
        );
        """
        result = parse_schema_file(schema)

        assert "categories" in result["tables"]
        fks = result["tables"]["categories"]["foreign_keys"]
        assert len(fks) > 0
        assert any(fk["references_table"] == "categories" for fk in fks)
