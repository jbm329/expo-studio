"""ANSI SQL fallback dialect implementation."""

from __future__ import annotations

import re

from expo_jbm329.db.core.interfaces import DialectProtocol


class AnsiDialect(DialectProtocol):
    """Standard SQL dialect used when no engine-specific dialect is available.

    Note:
        Used as a formatting fallback for engines without a registered dialect
        (e.g. PostgreSQL, Oracle or "Other"). Identifiers are quoted with
        double quotes and row limiting uses the SQL:2008
        ``FETCH FIRST n ROWS ONLY`` clause.
    """

    name = "ansi"
    limit_keyword = "FETCH FIRST"

    _LIMIT_RE = re.compile(r"(?is)\b(limit\s+\d+|fetch\s+first\s+\d+\s+rows?\s+only)\b")

    def quote_ident(self, name: str) -> str:
        """Quote an identifier using standard SQL double quotes.

        Args:
            name: The identifier to quote.

        Returns:
            The quoted identifier (e.g., "name"). Embedded double quotes are
            escaped by doubling them.
        """
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def qualify(self, schema: str, object_name: str) -> str:
        """Qualify an object name with a schema.

        Args:
            schema: The schema name. When empty, only the object name is used.
            object_name: The object name (e.g., table name).

        Returns:
            The qualified name (e.g., "schema"."object").
        """
        if not schema.strip():
            return self.quote_ident(object_name)
        return f"{self.quote_ident(schema)}.{self.quote_ident(object_name)}"

    def qualify_column(self, schema: str, object_name: str, column: str) -> str:
        """Qualify a column name with its schema and table/view.

        Args:
            schema: The schema name.
            object_name: The table or view name.
            column: The column name.

        Returns:
            The qualified column name (e.g., "schema"."table"."column").
        """
        return f"{self.qualify(schema, object_name)}.{self.quote_ident(column)}"

    def apply_limit(self, sql: str, n: int) -> str:
        """Append a standard ``FETCH FIRST n ROWS ONLY`` clause.

        Args:
            sql: The SQL query string.
            n: The number of rows to limit.

        Returns:
            The SQL query with a row limit, or the original query when it is
            not a SELECT/WITH statement or already limited.
        """
        if not sql or n <= 0:
            return sql

        stripped = sql.rstrip().rstrip(";").rstrip()
        if not stripped.lstrip().lower().startswith(("select", "with")):
            return stripped
        if self._LIMIT_RE.search(stripped):
            return stripped
        return f"{stripped}\nFETCH FIRST {int(n)} ROWS ONLY"

    @staticmethod
    def _literal(value: str) -> str:
        """Return a single-quoted SQL string literal.

        Args:
            value: Raw string value.

        Returns:
            The escaped string literal.
        """
        escaped = value.replace("'", "''")
        return f"'{escaped}'"

    def sql_list_tables(self) -> str:
        """Generate SQL for listing tables via INFORMATION_SCHEMA.

        Returns:
            A SQL query string to list tables.
        """
        return (
            "SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name "
            "FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )

    def sql_list_views(self) -> str:
        """Generate SQL for listing views via INFORMATION_SCHEMA.

        Returns:
            A SQL query string to list views.
        """
        return (
            "SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name "
            "FROM INFORMATION_SCHEMA.VIEWS ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )

    def sql_list_columns(self, schema: str, object_name: str) -> str:
        """Generate SQL for listing columns of a table or view.

        Args:
            schema: The schema name.
            object_name: The table or view name.

        Returns:
            A SQL query string to list columns.
        """
        return (
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "  # noqa: S608 - literals are escaped
            f"FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA={self._literal(schema)} "
            f"AND TABLE_NAME={self._literal(object_name)} ORDER BY ORDINAL_POSITION"
        )

    def sql_all_columns(self) -> str | None:
        """Generate SQL for selecting all columns via INFORMATION_SCHEMA.

        Returns:
            A SQL query string to select all columns with metadata.
        """
        return (
            "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, ORDINAL_POSITION "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
        )
