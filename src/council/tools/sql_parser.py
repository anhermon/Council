"""SQL parsing utilities for extracting table and column information using sqlglot."""

from typing import Any

import logfire
import sqlglot
from sqlglot import exp

# Try to detect dialect from SQL content, fallback to postgres
_DEFAULT_DIALECT = "postgres"


def parse_sql_query(query: str) -> dict[str, Any]:
    """
    Parse a SQL query to extract table and column references.

    Args:
        query: SQL query string

    Returns:
        Dictionary with 'tables', 'columns', and 'joins' keys
    """
    tables: set[str] = set()
    columns: set[str] = set()
    joins: list[dict[str, str]] = []

    try:
        # Try to parse the query
        expression = sqlglot.parse_one(query, dialect=_DEFAULT_DIALECT)
        if not expression:
            return {"tables": [], "columns": [], "joins": []}

        # Extract tables from FROM and JOIN clauses
        for table in expression.find_all(exp.Table):
            table_name = table.name.lower()
            tables.add(table_name)
            if table.alias:
                tables.add(table.alias.lower())

        # Extract columns
        for column in expression.find_all(exp.Column):
            col_name = column.name.lower() if column.name else None
            if col_name:
                columns.add(col_name)

        # Handle INSERT statements specifically to extract column names from column list
        if isinstance(expression, exp.Insert) and expression.this:
            # Extract table name
            if isinstance(expression.this, exp.Table):
                tables.add(expression.this.name.lower())
            elif isinstance(expression.this, exp.Schema):
                # Schema contains table name in .this
                if expression.this.this and isinstance(expression.this.this, exp.Table):
                    tables.add(expression.this.this.name.lower())
                # Column names are in Schema.expressions as Identifier objects
                if expression.this.expressions:
                    for expr in expression.this.expressions:
                        if isinstance(expr, exp.Identifier):
                            col_name = expr.this.lower() if expr.this else None
                            if col_name:
                                columns.add(col_name)
                        elif isinstance(expr, exp.Column):
                            col_name = expr.name.lower() if expr.name else None
                            if col_name:
                                columns.add(col_name)

        # Extract JOIN relationships
        for join in expression.find_all(exp.Join):
            if isinstance(join.this, exp.Table):
                join_table = join.this.name.lower()
                tables.add(join_table)
                if join.this.alias:
                    tables.add(join.this.alias.lower())
                joins.append({"table": join_table, "alias": join.this.alias})

        # Also check for table references in UPDATE, DELETE
        if (
            isinstance(expression, (exp.Update, exp.Delete))
            and expression.this
            and isinstance(expression.this, exp.Table)
        ):
            tables.add(expression.this.name.lower())

    except Exception as e:
        logfire.debug("Failed to parse SQL query with sqlglot", error=str(e), query=query[:100])
        # Fallback to empty result rather than failing
        return {"tables": [], "columns": [], "joins": []}

    return {
        "tables": sorted(tables),
        "columns": sorted(columns),
        "joins": joins,
    }


def parse_schema_file(schema_content: str) -> dict[str, Any]:
    """
    Parse a SQL schema file to extract table definitions and relationships.

    Args:
        schema_content: Content of the schema SQL file

    Returns:
        Dictionary with 'tables' and 'relationships' keys
    """
    tables: dict[str, dict[str, Any]] = {}
    relationships: list[dict[str, Any]] = []

    try:
        # Parse all statements in the schema
        expressions = sqlglot.parse(schema_content, dialect=_DEFAULT_DIALECT)

        for expression in expressions:
            # Check for CREATE INDEX statements (they're also Create expressions)
            if isinstance(expression, exp.Create) and expression.kind == "INDEX":
                _parse_index(expression, tables)
                continue

            if not isinstance(expression, exp.Create):
                continue

            # Extract table name
            # For CREATE TABLE, expression.this is a Schema containing the table
            table_name = None
            if isinstance(expression.this, exp.Schema):
                # Schema contains the table name
                table_name = expression.this.this.name.lower() if expression.this.this else None
            elif isinstance(expression.this, exp.Table):
                table_name = expression.this.name.lower()

            if not table_name:
                continue
            columns: list[dict[str, str]] = []
            primary_keys: list[str] = []
            foreign_keys: list[dict[str, Any]] = []

            # Extract column definitions
            for column_def in expression.find_all(exp.ColumnDef):
                col_name = column_def.this.name.lower() if column_def.this else None
                if not col_name:
                    continue

                # Extract column type
                col_type = "UNKNOWN"
                if column_def.kind:
                    col_type = str(column_def.kind).upper()

                columns.append({"name": col_name, "type": col_type})

                # Check for PRIMARY KEY constraint
                for _constraint in column_def.find_all(exp.PrimaryKeyColumnConstraint):
                    primary_keys.append(col_name)

                # Check for FOREIGN KEY (REFERENCES) constraint
                for ref in column_def.find_all(exp.Reference):
                    ref_table = None
                    ref_column = None

                    # Reference.this is typically a Schema containing the table
                    if ref.this:
                        if isinstance(ref.this, exp.Schema) and ref.this.this:
                            if isinstance(ref.this.this, exp.Table):
                                ref_table = ref.this.this.name.lower()
                        elif isinstance(ref.this, exp.Table):
                            ref_table = ref.this.name.lower()

                    # Get referenced column from expressions or from Schema
                    if ref.expressions:
                        for expr_item in ref.expressions:
                            if (
                                isinstance(expr_item, exp.Column)
                                and expr_item.name
                                or hasattr(expr_item, "name")
                                and expr_item.name
                            ):
                                ref_column = expr_item.name.lower()
                                break
                    elif isinstance(ref.this, exp.Schema) and ref.this.expressions:
                        # Column might be in Schema.expressions
                        for expr_item in ref.this.expressions:
                            if isinstance(expr_item, exp.Column) and expr_item.name:
                                ref_column = expr_item.name.lower()
                                break

                    if ref_table:
                        foreign_keys.append(
                            {
                                "column": col_name,
                                "references_table": ref_table,
                                "references_column": ref_column
                                or "id",  # Default to 'id' if not specified
                            }
                        )

            # Also check for table-level constraints (FOREIGN KEY constraints)
            for constraint in expression.find_all(exp.ForeignKey):
                # Extract column name(s) from the constraint
                fk_columns: list[str] = []
                ref_table = None
                ref_column = None

                # Column names are in constraint.expressions as Identifier or Column expressions
                for expr in constraint.expressions:
                    if isinstance(expr, exp.Identifier):
                        fk_columns.append(expr.this.lower() if expr.this else "")
                    elif isinstance(expr, exp.Column):
                        fk_columns.append(expr.name.lower() if expr.name else "")

                # Find Reference expression to get referenced table and column
                for ref in constraint.find_all(exp.Reference):
                    if ref.this:
                        if isinstance(ref.this, exp.Schema):
                            # Schema.this contains the table name
                            if ref.this.this:
                                if isinstance(ref.this.this, exp.Table):
                                    ref_table = ref.this.this.name.lower()
                                elif isinstance(ref.this.this, exp.Identifier):
                                    ref_table = (
                                        ref.this.this.this.lower() if ref.this.this.this else None
                                    )

                            # Schema.expressions contains the referenced column names
                            if ref.this.expressions:
                                for ref_expr in ref.this.expressions:
                                    if isinstance(ref_expr, exp.Identifier):
                                        ref_column = (
                                            ref_expr.this.lower() if ref_expr.this else None
                                        )
                                        break
                                    elif isinstance(ref_expr, exp.Column) and ref_expr.name:
                                        ref_column = ref_expr.name.lower()
                                        break
                        elif isinstance(ref.this, exp.Table):
                            ref_table = ref.this.name.lower()

                # Add foreign key for each column
                if fk_columns and ref_table:
                    for fk_col in fk_columns:
                        if fk_col:  # Only add if column name is valid
                            foreign_keys.append(
                                {
                                    "column": fk_col,
                                    "references_table": ref_table,
                                    "references_column": ref_column or "id",
                                }
                            )

            # Check for table-level PRIMARY KEY
            for pk_constraint in expression.find_all(exp.PrimaryKey):
                for pk_col in pk_constraint.expressions:
                    if hasattr(pk_col, "name"):
                        primary_keys.append(pk_col.name.lower())

            tables[table_name] = {
                "columns": columns,
                "primary_keys": primary_keys,
                "foreign_keys": foreign_keys,
            }

            # Build relationships from foreign keys
            for fk in foreign_keys:
                relationships.append(
                    {
                        "from_table": table_name,
                        "to_table": fk["references_table"],
                        "relationship": "many-to-one",
                        "foreign_key": fk["column"],
                        "references_column": fk["references_column"],
                    }
                )

    except Exception as e:
        logfire.warning("Failed to parse schema with sqlglot", error=str(e))
        # Return empty result rather than failing
        return {"tables": {}, "relationships": []}

    return {
        "tables": tables,
        "relationships": relationships,
    }


def _parse_index(expression: exp.Create, tables: dict[str, dict[str, Any]]) -> None:
    """Parse CREATE INDEX statement and add to table metadata."""
    if not isinstance(expression, exp.Create) or expression.kind != "INDEX":
        return

    if not expression.this or not isinstance(expression.this, exp.Index):
        return

    idx = expression.this

    # Extract table name from Index (find Table nodes)
    table_name = None
    for table_node in idx.find_all(exp.Table):
        table_name = table_node.name.lower()
        break

    if not table_name or table_name not in tables:
        return

    # Extract indexed columns from Index (find Column nodes)
    indexed_columns: list[str] = []
    for col_node in idx.find_all(exp.Column):
        col_name = col_node.name.lower() if col_node.name else None
        if col_name:
            indexed_columns.append(col_name)

    if indexed_columns:
        index_name = expression.name.lower() if expression.name else "unknown"
        if "indexes" not in tables[table_name]:
            tables[table_name]["indexes"] = []
        tables[table_name]["indexes"].append({"name": index_name, "columns": indexed_columns})
