"""MySQL dialect implementation."""

from __future__ import annotations

import re

from expo_jbm329.db.core.interfaces import DialectProtocol


class MySqlDialect(DialectProtocol):
    """MySQL/MariaDB dialect implementation.

    Note:
        In MySQL the concept of "schema" is equivalent to "database".
    """

    name = "mysql"  # We'll reuse for MariaDB as well via registry

    # Detect if a query already has a LIMIT clause (supports "LIMIT n" or "LIMIT offset, n")
    _LIMIT_RE = re.compile(r"(?is)\blimit\s+\d+(\s*,\s*\d+)?\b")

    def quote_ident(self, name: str) -> str:
        """Quote an identifier (e.g., table or column name) for MySQL.

        Args:
            name: The identifier to quote.

        Returns:
            The quoted identifier (e.g., `name`).
        """
        return f"`{name}`"

    def qualify(self, schema: str, object_name: str) -> str:
        """Qualify an object name with a schema for MySQL.

        Args:
            schema: The schema name.
            object_name: The object name (e.g., table name).

        Returns:
            The fully qualified name (e.g., `schema`.`table`).
        """
        return f"{self.quote_ident(schema)}.{self.quote_ident(object_name)}"

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
        """Apply a LIMIT clause to the given SQL query for MySQL.

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

    # ---------------- Metadata SQL (scoped to current database) ----------------
    def sql_list_tables(self) -> str:
        """Generate SQL for listing tables in the current MySQL database.

        Returns:
            A SQL query string to list tables from INFORMATION_SCHEMA.
        """
        return (
            "SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name "
            "FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE='BASE TABLE' AND TABLE_SCHEMA = DATABASE() "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )

    def sql_list_views(self) -> str:
        """Generate SQL for listing views in the current MySQL database.

        Returns:
            A SQL query string to list views from INFORMATION_SCHEMA.
        """
        return (
            "SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name "
            "FROM INFORMATION_SCHEMA.VIEWS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )

    def sql_list_columns(self, schema: str, object_name: str) -> str:
        """Generate SQL for listing columns of a table or view in MySQL.

        Args:
            schema: The schema (database) name.
            object_name: The table or view name.

        Returns:
            A SQL query string to list columns from INFORMATION_SCHEMA.
        """
        # Strong filter by provided schema (database) + table
        return (
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "  # noqa: S608 - deferred SQL construction refactor
            f"FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{object_name}' "
            "ORDER BY ORDINAL_POSITION"
        )

    def sql_all_columns(self) -> str | None:
        """Generate SQL for selecting all columns from the current MySQL database.

        Returns:
            A SQL query string to select all columns with metadata.
        """
        # Whole-db column map for the current database
        return (
            "SELECT "
            "  c.TABLE_SCHEMA       AS TABLE_SCHEMA, "
            "  c.TABLE_NAME         AS TABLE_NAME, "
            "  c.COLUMN_NAME        AS COLUMN_NAME, "
            "  c.DATA_TYPE          AS DATA_TYPE, "
            "  c.IS_NULLABLE        AS IS_NULLABLE, "
            "  c.ORDINAL_POSITION   AS ORDINAL_POSITION "
            "FROM INFORMATION_SCHEMA.COLUMNS AS c "
            "WHERE c.TABLE_SCHEMA = DATABASE() "
            "ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION"
        )
