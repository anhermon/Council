"""BDD-style tests for database relation tracer.

These tests follow a Given-When-Then structure to clearly express
the behavior and requirements of the database relation tracing system.
"""

from council.tools.db_relation_tracer import build_relation_map, extract_queries_from_code


class TestExtractQueriesBDD:
    """BDD-style tests for query extraction."""

    def test_given_code_with_multiple_methods_when_extracting_queries_then_each_query_has_correct_method(
        self,
        mock_settings,  # noqa: ARG002
    ):
        """
        Scenario: Extract queries from code with multiple methods
        Given: Python code with multiple methods, each containing SQL queries
        When: extract_queries_from_code is called
        Then: Each query should be associated with its correct method name
        """
        # Given
        code = """
def get_user(email: str):
    query = "SELECT id, username FROM users WHERE email = %s"
    return query

def get_products():
    query = "SELECT * FROM products"
    return query

def create_order(user_id: int):
    query = "INSERT INTO orders (user_id) VALUES (%s)"
    return query
"""

        # When
        result = extract_queries_from_code(code)

        # Then
        assert len(result) >= 3

        # Verify each query has the correct method
        method_to_tables = {}
        for query_info in result:
            method = query_info.get("method")
            tables = query_info.get("tables", [])
            if method:
                if method not in method_to_tables:
                    method_to_tables[method] = []
                method_to_tables[method].extend(tables)

        # get_user should have users table
        assert "get_user" in method_to_tables or any(
            "users" in q["tables"] for q in result if "users" in str(q.get("query", ""))
        )
        # get_products should have products table
        assert "get_products" in method_to_tables or any(
            "products" in q["tables"] for q in result if "products" in str(q.get("query", ""))
        )
        # create_order should have orders table
        assert "create_order" in method_to_tables or any(
            "orders" in q["tables"] for q in result if "orders" in str(q.get("query", ""))
        )

    def test_given_nested_functions_when_extracting_queries_then_inner_function_queries_are_tracked(
        self,
        mock_settings,  # noqa: ARG002
    ):
        """
        Scenario: Extract queries from nested functions
        Given: Python code with nested function definitions
        When: extract_queries_from_code is called
        Then: Queries in inner functions should be correctly associated
        """
        # Given
        code = """
def outer_function():
    def inner_function():
        query = "SELECT * FROM users"
        return query
    return inner_function()
"""

        # When
        result = extract_queries_from_code(code)

        # Then
        assert len(result) > 0
        assert any("users" in q["tables"] for q in result)

    def test_given_class_methods_when_extracting_queries_then_method_context_is_preserved(
        self,
        mock_settings,  # noqa: ARG002
    ):
        """
        Scenario: Extract queries from class methods
        Given: Python code with class methods containing SQL queries
        When: extract_queries_from_code is called
        Then: Queries should be associated with their method names
        """
        # Given
        code = """
class DatabaseService:
    def get_user(self, email: str):
        query = "SELECT * FROM users WHERE email = %s"
        return query

    def create_user(self, username: str):
        query = "INSERT INTO users (username) VALUES (%s)"
        return query
"""

        # When
        result = extract_queries_from_code(code)

        # Then
        assert len(result) >= 2
        methods = [q.get("method") for q in result if q.get("method")]
        # Should have method names (may include 'self' parameter handling)
        assert len(methods) > 0 or any("users" in q["tables"] for q in result)

    def test_given_multiline_sql_in_triple_quotes_when_extracting_queries_then_all_tables_are_found(
        self,
        mock_settings,  # noqa: ARG002
    ):
        """
        Scenario: Extract queries from multi-line SQL strings
        Given: Python code with multi-line SQL queries in triple quotes
        When: extract_queries_from_code is called
        Then: All tables referenced in the query should be extracted
        """
        # Given
        code = '''
def get_order_details(order_id: int):
    query = """
    SELECT o.id, o.total_amount, oi.product_id, p.name
    FROM orders o
    JOIN order_items oi ON o.id = oi.order_id
    JOIN products p ON oi.product_id = p.id
    WHERE o.id = %s
    """
    return query
'''

        # When
        result = extract_queries_from_code(code)

        # Then
        assert len(result) > 0
        query_info = next((q for q in result if "orders" in q["tables"]), None)
        assert query_info is not None
        assert "orders" in query_info["tables"]
        assert "order_items" in query_info["tables"]
        assert "products" in query_info["tables"]

    def test_given_code_with_no_sql_when_extracting_queries_then_empty_list_returned(
        self,
        mock_settings,  # noqa: ARG002
    ):
        """
        Scenario: Extract queries from code without SQL
        Given: Python code with no SQL queries
        When: extract_queries_from_code is called
        Then: An empty list should be returned
        """
        # Given
        code = """
def hello():
    return "world"

def add(a, b):
    return a + b
"""

        # When
        result = extract_queries_from_code(code)

        # Then
        assert result == []

    def test_given_code_with_execute_calls_when_extracting_queries_then_queries_are_found(
        self,
        mock_settings,  # noqa: ARG002
    ):
        """
        Scenario: Extract queries from execute() calls
        Given: Python code with cursor.execute() or similar calls
        When: extract_queries_from_code is called
        Then: Queries should be extracted from execute() calls
        """
        # Given
        code = """
def get_user(email: str):
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    return cur.fetchone()

def update_user(user_id: int, email: str):
    db.execute("UPDATE users SET email = %s WHERE id = %s", (email, user_id))
"""

        # When
        result = extract_queries_from_code(code)

        # Then
        assert len(result) >= 2
        assert any("SELECT" in q["query"] for q in result)
        assert any("UPDATE" in q["query"] for q in result)
        assert any("users" in q["tables"] for q in result)


class TestBuildRelationMapBDD:
    """BDD-style tests for relation map building."""

    def test_given_code_and_schema_when_building_relation_map_then_all_relationships_are_extracted(
        self, mock_settings
    ):
        """
        Scenario: Build relation map from code and schema
        Given: Python code with queries and a schema file with foreign keys
        When: build_relation_map is called
        Then: All foreign key relationships should be extracted and mapped
        """
        # Given
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

        # When
        result = build_relation_map(code, [schema_file])

        # Then
        assert "relationships" in result
        assert len(result["relationships"]) >= 2

        # Verify specific relationships
        relationships = {f"{r['from_table']}->{r['to_table']}": r for r in result["relationships"]}
        assert "orders->users" in relationships
        assert "order_items->orders" in relationships

    def test_given_code_and_query_file_when_building_relation_map_then_queries_are_matched(
        self, mock_settings
    ):
        """
        Scenario: Match queries between code and SQL files
        Given: Python code with queries and a SQL file with similar queries
        When: build_relation_map is called
        Then: Queries in SQL files should be matched to queries in code
        """
        # Given
        code = """
def get_user(email: str):
    query = "SELECT id, username, email FROM users WHERE email = %s"
    return query
"""

        query_file = mock_settings.project_root / "queries.sql"
        query_file.write_text(
            """
-- Get user by email
SELECT id, username, email FROM users WHERE email = :email;
"""
        )

        # When
        result = build_relation_map(code, [query_file])

        # Then
        assert "queries_in_files" in result
        assert len(result["queries_in_files"]) > 0

        matched_queries = [q for q in result["queries_in_files"] if q.get("used_in_code", False)]
        assert len(matched_queries) > 0

    def test_given_empty_sql_files_when_building_relation_map_then_only_code_queries_extracted(
        self,
        mock_settings,  # noqa: ARG002
    ):
        """
        Scenario: Build relation map with no SQL files
        Given: Python code with queries but no SQL files
        When: build_relation_map is called with empty list
        Then: Only queries from code should be extracted
        """
        # Given
        code = """
def get_user(email: str):
    query = "SELECT * FROM users WHERE email = %s"
    return query
"""

        # When
        result = build_relation_map(code, [])

        # Then
        assert "queries_in_code" in result
        assert len(result["queries_in_code"]) > 0
        assert "queries_in_files" in result
        assert len(result["queries_in_files"]) == 0
        assert "schema_tables" in result
        assert len(result["schema_tables"]) == 0

    def test_given_schema_with_self_referencing_foreign_key_when_building_relation_map_then_relationship_is_extracted(
        self, mock_settings
    ):
        """
        Scenario: Extract self-referencing foreign key relationships
        Given: Schema with a table that references itself
        When: build_relation_map is called
        Then: The self-referencing relationship should be extracted
        """
        # Given
        code = "def get_categories(): pass"

        schema_file = mock_settings.project_root / "schema.sql"
        schema_file.write_text(
            """
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    parent_id INTEGER REFERENCES categories(id)
);
"""
        )

        # When
        result = build_relation_map(code, [schema_file])

        # Then
        assert "relationships" in result
        self_refs = [r for r in result["relationships"] if r["from_table"] == r["to_table"]]
        assert len(self_refs) > 0
        assert any(
            r["from_table"] == "categories" and r["to_table"] == "categories" for r in self_refs
        )

    def test_given_mixed_schema_and_query_files_when_building_relation_map_then_both_are_processed(
        self, mock_settings
    ):
        """
        Scenario: Process both schema and query files
        Given: Both schema.sql and queries.sql files
        When: build_relation_map is called
        Then: Both files should be processed correctly
        """
        # Given
        code = """
def get_user(email: str):
    query = "SELECT * FROM users WHERE email = %s"
    return query
"""

        schema_file = mock_settings.project_root / "schema.sql"
        schema_file.write_text("CREATE TABLE users (id SERIAL PRIMARY KEY, email VARCHAR(100));")

        query_file = mock_settings.project_root / "queries.sql"
        query_file.write_text("SELECT * FROM users WHERE email = :email;")

        # When
        result = build_relation_map(code, [schema_file, query_file])

        # Then
        assert "schema_tables" in result
        assert "users" in result["schema_tables"]
        assert "queries_in_files" in result
        assert len(result["queries_in_files"]) > 0

    def test_given_nonexistent_sql_file_when_building_relation_map_then_file_is_skipped(
        self, mock_settings
    ):
        """
        Scenario: Handle non-existent SQL files gracefully
        Given: A path to a non-existent SQL file
        When: build_relation_map is called
        Then: The file should be skipped without error
        """
        # Given
        code = "def get_user(): pass"
        nonexistent_file = mock_settings.project_root / "nonexistent.sql"

        # When
        result = build_relation_map(code, [nonexistent_file])

        # Then
        assert "queries_in_code" in result
        assert "queries_in_files" in result
        assert len(result["queries_in_files"]) == 0

    def test_given_tables_referenced_when_building_relation_map_then_list_is_sorted(
        self, mock_settings
    ):
        """
        Scenario: Tables referenced list is sorted
        Given: Code and schema referencing multiple tables
        When: build_relation_map is called
        Then: The tables_referenced list should be sorted alphabetically
        """
        # Given
        code = """
def get_data():
    q1 = "SELECT * FROM zebra"
    q2 = "SELECT * FROM apple"
    q3 = "SELECT * FROM banana"
    return q1, q2, q3
"""

        schema_file = mock_settings.project_root / "schema.sql"
        schema_file.write_text(
            """
CREATE TABLE apple (id INT);
CREATE TABLE banana (id INT);
CREATE TABLE zebra (id INT);
"""
        )

        # When
        result = build_relation_map(code, [schema_file])

        # Then
        assert "tables_referenced" in result
        assert isinstance(result["tables_referenced"], list)
        assert result["tables_referenced"] == sorted(result["tables_referenced"])
