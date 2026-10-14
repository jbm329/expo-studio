"""PostgreSQL dialect implementation."""

from __future__ import annotations

import re

from expo_jbm329.db.core.interfaces import DialectProtocol


class PostgresDialect(DialectProtocol):
    """PostgreSQL dialect implementation."""

    name = "postgresql"
    limit_keyword = "LIMIT"

    _LIMIT_RE = re.compile(
        r"(?is)\b(limit\s+\d+|fetch\s+first\s+\d+\s+rows?\s+only)\b"
    )

    def quote_ident(self, name: str) -> str:
        """Quote an identifier (e.g., table or column name) for PostgreSQL.

        Args:
            name: The identifier to quote.

        Returns:
            The quoted identifier (e.g., "name"). Embedded double quotes are
            escaped by doubling them.
        """
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def qualify(self, schema: str, object_name: str) -> str:
        """Qualify an object name with a schema for PostgreSQL.

        Args:
            schema: The schema name. When empty, only the object name is used.
            object_name: The object name (e.g., table name).

        Returns:
            The fully qualified name (e.g., "schema"."table").
        """
        if not schema.strip():
            return self.quote_ident(object_name)
        return f"{self.quote_ident(schema)}.{self.quote_ident(object_name)}"

    def qualify_column(self, schema: str, object_name: str, column: str) -> str:
        """Qualify a column name with its schema and table/view for PostgreSQL.

        Args:
            schema: The schema name.
            object_name: The table or view name.
            column: The column name.

        Returns:
            The fully qualified column name (e.g., "schema"."table"."column").
        """
        return f"{self.qualify(schema, object_name)}.{self.quote_ident(column)}"

    @staticmethod
    def _strip_semicolon(sql: str) -> str:
        """Strip trailing semicolons and whitespace from a SQL query.

        Args:
            sql: The SQL query string.

        Returns:
            The SQL query string with trailing semicolons and whitespace removed.
        """
        return sql.rstrip().rstrip(";").rstrip()

    @staticmethod
    def _is_likely_select(sql: str) -> bool:
        """Check if a SQL query is likely a SELECT or WITH statement.

        Args:
            sql: The SQL query string.

        Returns:
            True if the query starts with 'SELECT' or 'WITH', False otherwise.
        """
        s = sql.lstrip().lower()
        return s.startswith(("select", "with"))

    def _already_limited(self, sql: str) -> bool:
        """Check if a SQL query already contains a LIMIT clause.

        Args:
            sql: The SQL query string.

        Returns:
            True if a LIMIT clause is found, False otherwise.
        """
        return bool(self._LIMIT_RE.search(sql))

    def apply_limit(self, sql: str, n: int) -> str:
        """Apply a LIMIT clause to the given SQL query for PostgreSQL.

        Args:
            sql: The SQL query string.
            n: The number of rows to limit.

        Returns:
            The modified SQL query with the LIMIT clause applied.
        """
        if not sql or n <= 0:
            return sql
        sql0 = self._strip_semicolon(sql)
        if not self._is_likely_select(sql0) or self._already_limited(sql0):
            return sql0
        return f"{sql0} LIMIT {int(n)}"

    @staticmethod
    def _literal(value: str) -> str:
        """Return a single-quoted SQL string literal with quotes escaped.

        Args:
            value: Raw string value.

        Returns:
            The escaped string literal.
        """
        escaped = value.replace("'", "''")
        return f"'{escaped}'"

    # ---------------- Metadata SQL (excluding internal schemas) ----------------
    def sql_list_tables(self) -> str:
        """Generate SQL for listing tables in PostgreSQL.

        Returns:
            A SQL query string to list tables from INFORMATION_SCHEMA.
        """
        return (
            "SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name "
            "FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE='BASE TABLE' "
            "AND TABLE_SCHEMA NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )

    def sql_list_views(self) -> str:
        """Generate SQL for listing views in PostgreSQL.

        Returns:
            A SQL query string to list views from INFORMATION_SCHEMA.
        """
        return (
            "SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name "
            "FROM INFORMATION_SCHEMA.VIEWS "
            "WHERE TABLE_SCHEMA NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )

    def sql_list_columns(self, schema: str, object_name: str) -> str:
        """Generate SQL for listing columns of a table or view in PostgreSQL.

        Args:
            schema: The schema name.
            object_name: The table or view name.

        Returns:
            A SQL query string to list columns from INFORMATION_SCHEMA.
        """
        return (
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "  # noqa: S608 - literals are escaped
            "FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_SCHEMA = {self._literal(schema)} AND TABLE_NAME = {self._literal(object_name)} "
            "ORDER BY ORDINAL_POSITION"
        )

    def sql_all_columns(self) -> str | None:
        """Generate SQL for selecting all columns from PostgreSQL.

        Returns:
            A SQL query string to select all columns with metadata.
        """
        return (
            "SELECT "
            "  TABLE_SCHEMA, "
            "  TABLE_NAME, "
            "  COLUMN_NAME, "
            "  DATA_TYPE, "
            "  IS_NULLABLE, "
            "  ORDINAL_POSITION "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
        )
