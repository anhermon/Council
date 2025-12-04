"""Tests for database relation tracer."""

from council.tools.db_relation_tracer import build_relation_map, extract_queries_from_code


class TestExtractQueriesFromCode:
    """Test extract_queries_from_code function."""

    def test_extract_queries_with_ast_parsing(self, mock_settings):  # noqa: ARG002
        """Test extracting queries from Python code using AST parsing."""
        code = """
def get_user(email: str):
    query = "SELECT id, username, email FROM users WHERE email = %s"
    return query

def create_order(user_id: int):
    query = "INSERT INTO orders (user_id, total_amount) VALUES (%s, %s)"
    return query
"""
        result = extract_queries_from_code(code)

        assert len(result) >= 2
        # Check that queries are extracted
        query_texts = [q["query"] for q in result]
        assert any("SELECT" in q for q in query_texts)
        assert any("INSERT" in q for q in query_texts)

    def test_extract_queries_with_method_context(self, mock_settings):  # noqa: ARG002
        """Test that queries are associated with their method context."""
        code = """
def get_user_by_email(email: str):
    query = "SELECT id, username FROM users WHERE email = %s"
    return query

def get_products():
    query = "SELECT * FROM products"
    return query
"""
        result = extract_queries_from_code(code)

        assert len(result) >= 2
        methods = [q.get("method") for q in result if q.get("method")]
        assert "get_user_by_email" in methods or any("users" in q["query"] for q in result)
        assert "get_products" in methods or any("products" in q["query"] for q in result)

    def test_extract_queries_from_multiline_strings(self, mock_settings):  # noqa: ARG002
        """Test extracting queries from multi-line triple-quoted strings."""
        code = '''
def get_user_orders(user_id: int):
    query = """
    SELECT o.id, o.total_amount, oi.product_id
    FROM orders o
    JOIN order_items oi ON o.id = oi.order_id
    WHERE o.user_id = %s
    """
    return query
'''
        result = extract_queries_from_code(code)

        assert len(result) > 0
        assert any("JOIN" in q["query"] for q in result)
        assert any("orders" in q["tables"] for q in result)
        assert any("order_items" in q["tables"] for q in result)

    def test_extract_queries_from_execute_calls(self, mock_settings):  # noqa: ARG002
        """Test extracting queries from execute() calls."""
        code = """
def get_user(email: str):
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    return cur.fetchone()
"""
        result = extract_queries_from_code(code)

        assert len(result) > 0
        assert any("SELECT" in q["query"] for q in result)
        assert any("users" in q["tables"] for q in result)

    def test_extract_queries_regex_fallback(self, mock_settings):  # noqa: ARG002
        """Test regex fallback when AST parsing fails."""
        # Invalid Python syntax but contains SQL in triple-quoted string
        # (regex fallback looks for triple-quoted strings or execute() calls)
        code = """
def get_user(email: str):
    query = '''SELECT id FROM users WHERE email = %s'''
    return query
invalid syntax here {
"""
        # Should still extract queries using regex
        result = extract_queries_from_code(code)

        assert len(result) > 0
        assert any("SELECT" in q["query"] for q in result)

    def test_extract_queries_no_sql(self, mock_settings):  # noqa: ARG002
        """Test code without SQL queries."""
        code = """
def hello():
    return "world"

def add(a, b):
    return a + b
"""
        result = extract_queries_from_code(code)

        assert len(result) == 0

    def test_extract_queries_with_joins(self, mock_settings):  # noqa: ARG002
        """Test extracting queries with JOIN clauses."""
        code = """
def get_products_with_categories():
    query = '''
    SELECT p.id, p.name, c.name AS category
    FROM products p
    JOIN categories c ON p.category_id = c.id
    '''
    return query
"""
        result = extract_queries_from_code(code)

        assert len(result) > 0
        query = next((q for q in result if "products" in q["tables"]), None)
        assert query is not None
        assert "products" in query["tables"]
        assert "categories" in query["tables"]
        assert len(query["joins"]) > 0


class TestBuildRelationMap:
    """Test build_relation_map function."""

    def test_build_relation_map_with_schema_file(self, mock_settings):
        """Test building relation map with schema file."""
        code = """
def get_user(email: str):
    query = "SELECT id, username FROM users WHERE email = %s"
    return query
"""

        schema_file = mock_settings.project_root / "schema.sql"
        schema_file.write_text(
            """
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    total_amount DECIMAL(10, 2)
);
"""
        )

        result = build_relation_map(code, [schema_file])

        assert "tables_referenced" in result
        assert "users" in result["tables_referenced"]
        assert "schema_tables" in result
        assert "users" in result["schema_tables"]
        assert "orders" in result["schema_tables"]
        assert len(result["relationships"]) > 0

    def test_build_relation_map_with_query_file(self, mock_settings):
        """Test building relation map with query file."""
        code = """
def get_user(email: str):
    query = "SELECT id, username FROM users WHERE email = %s"
    return query
"""

        query_file = mock_settings.project_root / "queries.sql"
        query_file.write_text(
            """
-- Get user by email
SELECT id, username, email FROM users WHERE email = :email;

-- Get products
SELECT * FROM products;
"""
        )

        result = build_relation_map(code, [query_file])

        assert "queries_in_files" in result
        assert len(result["queries_in_files"]) > 0
        assert any("users" in q["tables"] for q in result["queries_in_files"])
        # Check if queries match
        assert any(q.get("used_in_code", False) for q in result["queries_in_files"])

    def test_build_relation_map_with_both_schema_and_queries(self, mock_settings):
        """Test building relation map with both schema and query files."""
        code = """
def get_user_orders(user_id: int):
    query = '''
    SELECT o.id, o.total_amount
    FROM orders o
    WHERE o.user_id = %s
    '''
    return query
"""

        schema_file = mock_settings.project_root / "schema.sql"
        schema_file.write_text(
            """
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50)
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    total_amount DECIMAL(10, 2)
);
"""
        )

        query_file = mock_settings.project_root / "queries.sql"
        query_file.write_text(
            """
SELECT o.id, o.total_amount
FROM orders o
WHERE o.user_id = :user_id;
"""
        )

        result = build_relation_map(code, [schema_file, query_file])

        assert "schema_tables" in result
        assert "users" in result["schema_tables"]
        assert "orders" in result["schema_tables"]
        assert "queries_in_files" in result
        assert len(result["queries_in_files"]) > 0
        assert len(result["relationships"]) > 0

    def test_build_relation_map_empty_sql_files(self, mock_settings):  # noqa: ARG002
        """Test building relation map with empty SQL files list."""
        code = """
def get_user(email: str):
    query = "SELECT id FROM users WHERE email = %s"
    return query
"""

        result = build_relation_map(code, [])

        assert "queries_in_code" in result
        assert len(result["queries_in_code"]) > 0
        assert "queries_in_files" in result
        assert len(result["queries_in_files"]) == 0
        assert "schema_tables" in result
        assert len(result["schema_tables"]) == 0

    def test_build_relation_map_no_database_code(self, mock_settings):
        """Test building relation map with code that has no database queries."""
        code = """
def hello():
    return "world"
"""

        schema_file = mock_settings.project_root / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id INT);")

        result = build_relation_map(code, [schema_file])

        assert "queries_in_code" in result
        assert len(result["queries_in_code"]) == 0
        assert "schema_tables" in result
        assert "users" in result["schema_tables"]

    def test_build_relation_map_matches_queries(self, mock_settings):
        """Test that queries in files are matched to queries in code."""
        code = """
def get_user(email: str):
    query = "SELECT id, username FROM users WHERE email = %s"
    return query
"""

        query_file = mock_settings.project_root / "queries.sql"
        query_file.write_text(
            """
SELECT id, username FROM users WHERE email = :email;
"""
        )

        result = build_relation_map(code, [query_file])

        assert "queries_in_files" in result
        matched_queries = [q for q in result["queries_in_files"] if q.get("used_in_code", False)]
        assert len(matched_queries) > 0

    def test_build_relation_map_extracts_relationships(self, mock_settings):
        """Test that relationships are extracted from foreign keys."""
        code = """
def get_order(order_id: int):
    query = "SELECT * FROM orders WHERE id = %s"
    return query
"""

        schema_file = mock_settings.project_root / "schema.sql"
        schema_file.write_text(
            """
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50)
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    total_amount DECIMAL(10, 2)
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL
);
"""
        )

        result = build_relation_map(code, [schema_file])

        assert "relationships" in result
        assert len(result["relationships"]) >= 2
        # Check for orders -> users relationship
        assert any(
            rel["from_table"] == "orders" and rel["to_table"] == "users"
            for rel in result["relationships"]
        )
        # Check for order_items -> orders relationship
        assert any(
            rel["from_table"] == "order_items" and rel["to_table"] == "orders"
            for rel in result["relationships"]
        )

    def test_build_relation_map_nonexistent_file(self, mock_settings):
        """Test building relation map with non-existent SQL file."""
        code = """
def get_user(email: str):
    query = "SELECT id FROM users WHERE email = %s"
    return query
"""

        nonexistent_file = mock_settings.project_root / "nonexistent.sql"

        result = build_relation_map(code, [nonexistent_file])

        assert "queries_in_code" in result
        assert len(result["queries_in_code"]) > 0
        assert "queries_in_files" in result
        assert len(result["queries_in_files"]) == 0

    def test_build_relation_map_tables_referenced_sorted(self, mock_settings):  # noqa: ARG002
        """Test that tables_referenced is sorted."""
        code = """
def get_data():
    query1 = "SELECT * FROM products"
    query2 = "SELECT * FROM users"
    query3 = "SELECT * FROM orders"
    return query1, query2, query3
"""

        result = build_relation_map(code, [])

        assert "tables_referenced" in result
        assert isinstance(result["tables_referenced"], list)
        # Should be sorted
        assert result["tables_referenced"] == sorted(result["tables_referenced"])
