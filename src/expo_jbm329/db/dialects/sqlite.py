"""SQLite dialect implementation."""

from __future__ import annotations

from expo_jbm329.db.core.interfaces import DialectProtocol


class SqliteDialect(DialectProtocol):
    """SQLite dialect implementation.

    Note:
        Uses double-quotes for identifiers (SQLite accepts backticks too).
        LIMIT injection via '... LIMIT n'.
        Metadata via sqlite_master and PRAGMA table_info.
        No whole-database one-shot column SQL (returns None to force batch).
    """

    name = "sqlite"

    def quote_ident(self, name: str) -> str:
        """Quote an identifier (e.g., table or column name) for SQLite.

        Args:
            name: The identifier to quote.

        Returns:
            The quoted identifier (e.g., "name").
        """
        return f'"{name}"'

    def qualify(self, schema: str, object_name: str) -> str:
        """Qualify an object name with a schema for SQLite.

        Args:
            schema: The schema name (typically 'main' or 'temp').
            object_name: The object name (e.g., table name).

        Returns:
            The qualified name. If schema is falsy or 'main', returns just the quoted table.
        """
        s = (schema or "").strip()
        if not s or s.lower() == "main":
            return self.quote_ident(object_name)
        return f"{self.quote_ident(s)}.{self.quote_ident(object_name)}"

    def apply_limit(self, sql: str, n: int) -> str:
        """Apply a LIMIT clause to the given SQL query for SQLite.

        Args:
            sql: The SQL query string.
            n: The number of rows to limit.

        Returns:
            The modified SQL query with the LIMIT clause applied.
        """
        if not sql or not isinstance(n, int) or n <= 0:
            return sql
        s = sql.rstrip().rstrip(";")
        # Naive but safe: SQLite supports simple '... LIMIT n'
        # We deliberately don't try to parse existing LIMIT to keep it simple.
        lower = s.lower()
        if " limit " in lower or lower.endswith(" limit") or " limit\n" in lower:
            return s  # already limited (best effort)
        return f"{s} LIMIT {int(n)}"

    # ---------------- Metadata SQL ----------------
    def sql_list_tables(self) -> str:
        """Generate SQL for listing tables in the SQLite database.

        Returns:
            A SQL query string to list tables from sqlite_master.
        """
        return (
            "SELECT "
            "  COALESCE(NULL, 'main') AS schema_name, "
            "  name AS object_name "
            "FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )

    def sql_list_views(self) -> str:
        """Generate SQL for listing views in the SQLite database.

        Returns:
            A SQL query string to list views from sqlite_master.
        """
        return (
            "SELECT "
            "  COALESCE(NULL, 'main') AS schema_name, "
            "  name AS object_name "
            "FROM sqlite_master "
            "WHERE type='view' "
            "ORDER BY name"
        )

    def sql_list_columns(self, schema: str, object_name: str) -> str:
        """Generate SQL for listing columns of a table or view in SQLite.

        Note:
            We use PRAGMA_TABLE_INFO which is interpolated into the SQL.

        Args:
            schema: The schema name.
            object_name: The table or view name.

        Returns:
            A SQL query string to list columns.
        """
        # We must use PRAGMA; we return a SELECT that wraps pragma for consistency.
        # Note: PRAGMA does not support parameters. We interpolate object_name safely.
        tbl = object_name.replace('"', '""')
        return (
            "SELECT "
            "  name AS COLUMN_NAME, "
            "  LOWER(type) AS DATA_TYPE, "
            "  CASE WHEN \"notnull\" = 0 THEN 'YES' ELSE 'NO' END AS IS_NULLABLE "
            f'FROM PRAGMA_TABLE_INFO("{tbl}") '
            "ORDER BY cid"
        )

    def sql_all_columns(self) -> str | None:
        """Generate SQL for selecting all columns from all tables in SQLite.

        Note:
            Not feasible in a single SQL across all tables in SQLite.

        Returns:
            None as it is not supported for SQLite.
        """
        # Not feasible in a single SQL across all tables in SQLite (needs per-table PRAGMA).
        return None
