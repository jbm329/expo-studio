"""DuckDB SQL syntax and selected-catalog metadata queries."""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from expo_jbm329.db.core.interfaces import DialectProtocol


class DuckDbDialect(DialectProtocol):
    """DuckDB identifiers, row limits and user table/view metadata."""

    name = "duckdb"
    limit_keyword = "LIMIT"

    def quote_ident(self, name: str) -> str:
        """Quote an identifier, escaping embedded double quotes."""
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def qualify(self, schema: str, object_name: str) -> str:
        """Qualify an object with its schema when supplied."""
        if not schema.strip():
            return self.quote_ident(object_name)
        return f"{self.quote_ident(schema)}.{self.quote_ident(object_name)}"

    def qualify_column(self, schema: str, object_name: str, column: str) -> str:
        """Qualify a column with its object and optional schema."""
        return f"{self.qualify(schema, object_name)}.{self.quote_ident(column)}"

    def apply_limit(self, sql: str, n: int) -> str:
        """Limit the outer query without confusing nested limits or comments.

        Args:
            sql: SQL query text.
            n: Maximum row count to add when no outer limit exists.

        Returns:
            DuckDB SQL with a limit, or the original SQL if no limit is needed.

        Raises:
            ValueError: If the SQL cannot be parsed as a single statement.
        """
        if not sql.strip() or n <= 0:
            return sql
        try:
            statements = sqlglot.parse(sql, read="duckdb")
        except SqlglotError as exc:
            # DbService logs ValueError and retains its client-side row cap.
            msg = "Could not parse DuckDB SQL for server-side row limiting."
            raise ValueError(msg) from exc
        expressions = [statement for statement in statements if statement is not None]
        if len(expressions) != 1:
            msg = "DuckDB row limiting requires exactly one SQL statement."
            raise ValueError(msg)
        expression = expressions[0]
        if not isinstance(expression, exp.Query) or expression.args.get("limit") is not None:
            return sql
        return expression.limit(n).sql(dialect="duckdb")

    @staticmethod
    def _literal(value: str) -> str:
        """Escape a metadata filter as a single-quoted SQL literal."""
        escaped = value.replace("'", "''")
        return f"'{escaped}'"

    def sql_list_tables(self) -> str:
        """List user tables from the selected file's current catalog."""
        return (
            "SELECT table_schema AS schema_name, table_name AS object_name "
            "FROM information_schema.tables "
            "WHERE table_catalog = current_database() AND table_type = 'BASE TABLE' "
            "AND table_schema NOT IN ('information_schema', 'pg_catalog') "
            "ORDER BY table_schema, table_name"
        )

    def sql_list_views(self) -> str:
        """List user views from the selected file's current catalog."""
        return (
            "SELECT table_schema AS schema_name, table_name AS object_name "
            "FROM information_schema.views "
            "WHERE table_catalog = current_database() "
            "AND table_schema NOT IN ('information_schema', 'pg_catalog') "
            "ORDER BY table_schema, table_name"
        )

    def sql_list_columns(self, schema: str, object_name: str) -> str:
        """List an object's columns in their declared order."""
        return (
            'SELECT column_name AS "COLUMN_NAME", data_type AS "DATA_TYPE", '  # noqa: S608 - literals are escaped
            'is_nullable AS "IS_NULLABLE" FROM information_schema.columns '
            "WHERE table_catalog = current_database() "
            "AND table_schema NOT IN ('information_schema', 'pg_catalog') "
            f"AND table_schema = {self._literal(schema)} AND table_name = {self._literal(object_name)} "
            "ORDER BY ordinal_position"
        )

    def sql_all_columns(self) -> str:
        """List all user columns in the existing bulk-cache result shape."""
        return (
            'SELECT table_schema AS "TABLE_SCHEMA", table_name AS "TABLE_NAME", '
            'column_name AS "COLUMN_NAME", data_type AS "DATA_TYPE", '
            'is_nullable AS "IS_NULLABLE", ordinal_position AS "ORDINAL_POSITION" '
            "FROM information_schema.columns "
            "WHERE table_catalog = current_database() "
            "AND table_schema NOT IN ('information_schema', 'pg_catalog') "
            "ORDER BY table_schema, table_name, ordinal_position"
        )
