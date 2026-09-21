"""MSSQL dialect implementation."""

from __future__ import annotations

import re

from expo_jbm329.db.core.interfaces import DialectProtocol


class MssqlDialect(DialectProtocol):
    """MSSQL dialect: quoting, limit injection, metadata SQL builders."""

    name = "mssql"

    _LIMIT_RE = re.compile(
        r"(?is)\b("
        r"limit\s+\d+|top\s+\d+|fetch\s+first\s+\d+\s+rows\s+only|rownum\s*(?:<=|<|=)\s*\d+"
        r")\b"
    )

    def quote_ident(self, name: str) -> str:
        """Quote an identifier (e.g., table or column name) for MSSQL.

        Args:
            name: The identifier to quote.

        Returns:
            The quoted identifier (e.g., [name]).
        """
        return f"[{name}]"

    def qualify(self, schema: str, object_name: str) -> str:
        """Qualify an object name with a schema for MSSQL.

        Args:
            schema: The schema name.
            object_name: The object name (e.g., table name).

        Returns:
            The fully qualified name (e.g., [schema].[object]).
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
        """Check if a SQL query already contains a limit-like clause.

        Args:
            sql: The SQL query string.

        Returns:
            True if a limit-like clause is found, False otherwise.
        """
        return bool(self._LIMIT_RE.search(sql))

    @staticmethod
    def _find_top_level_select(sql: str) -> int:
        """Find the index of the top-level SELECT in a SQL query.

        This handles nested subqueries, comments, and strings.

        Args:
            sql: The SQL query string.

        Returns:
            The index of the top-level 'SELECT' keyword, or -1 if not found.
        """
        i, n = 0, len(sql)
        depth = 0
        in_sq = in_dq = in_br = in_line = in_block = False

        while i < n:
            ch = sql[i]
            ch2 = sql[i : i + 2]

            if not in_sq and not in_dq and not in_br:
                if not in_block and ch2 == "--":
                    in_line = True
                    i += 2
                    continue
                if not in_line and ch2 == "/*":
                    in_block = True
                    i += 2
                    continue

            if in_line:
                if ch == "\n":
                    in_line = False
                i += 1
                continue

            if in_block:
                if ch2 == "*/":
                    in_block = False
                    i += 2
                else:
                    i += 1
                continue

            if not in_dq and not in_br and ch == "'":
                in_sq = not in_sq
                i += 1
                continue

            if not in_sq and not in_br and ch == '"':
                in_dq = not in_dq
                i += 1
                continue

            if not in_sq and not in_dq:
                if ch == "[":
                    in_br = True
                    i += 1
                    continue
                if in_br and ch == "]":
                    in_br = False
                    i += 1
                    continue

            if in_sq or in_dq or in_br:
                i += 1
                continue

            if ch == "(":
                depth += 1
                i += 1
                continue

            if ch == ")":
                depth = max(0, depth - 1)
                i += 1
                continue

            if depth == 0 and sql[i : i + 6].lower() == "select":
                before = sql[i - 1] if i > 0 else " "
                after = sql[i + 6] if i + 6 < n else " "
                if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                    return i

            i += 1

        return -1

    def apply_limit(self, sql: str, n: int) -> str:
        """Apply a TOP clause to the given SQL query for MSSQL.

        Args:
            sql: The SQL query string.
            n: The number of rows to limit.

        Returns:
            The modified SQL query with the TOP clause applied.
        """
        if not sql or n <= 0:
            return sql

        sql0 = self._strip_semicolon(sql)
        if not self._is_likely_select(sql0) or self._already_limited(sql0):
            return sql0

        idx = self._find_top_level_select(sql0)
        if idx < 0:
            return sql0

        j = idx + 6
        while j < len(sql0) and sql0[j].isspace():
            j += 1

        token = []
        jj = j
        while jj < len(sql0) and (sql0[jj].isalpha() or sql0[jj] == "_"):
            token.append(sql0[jj])
            jj += 1

        t = "".join(token).lower()
        insert_pos = jj if t in ("distinct", "all") else (idx + 6)
        return sql0[:insert_pos] + f" TOP {int(n)}" + sql0[insert_pos:]

    def sql_list_tables(self) -> str:
        """Generate SQL for listing tables in MSSQL.

        Returns:
            A SQL query string to list tables from INFORMATION_SCHEMA.
        """
        return (
            "SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name "
            "FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )

    def sql_list_views(self) -> str:
        """Generate SQL for listing views in MSSQL.

        Returns:
            A SQL query string to list views from INFORMATION_SCHEMA.
        """
        return (
            "SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name "
            "FROM INFORMATION_SCHEMA.VIEWS ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )

    def sql_list_columns(self, schema: str, object_name: str) -> str:
        """Generate SQL for listing columns of a table or view in MSSQL.

        Args:
            schema: The schema name.
            object_name: The table or view name.

        Returns:
            A SQL query string to list columns from INFORMATION_SCHEMA.
        """
        return (
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "  # noqa: S608 - deferred SQL construction refactor
            f"FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='{schema}' "
            f"AND TABLE_NAME='{object_name}' ORDER BY ORDINAL_POSITION"
        )

    def sql_all_columns(self) -> str | None:
        """Generate SQL for selecting all columns from all tables/views in MSSQL.

        Returns:
            A SQL query string to select all columns with metadata.
        """
        return (
            "SELECT "
            "  c.TABLE_SCHEMA   AS TABLE_SCHEMA, "
            "  c.TABLE_NAME     AS TABLE_NAME, "
            "  c.COLUMN_NAME    AS COLUMN_NAME, "
            "  c.DATA_TYPE      AS DATA_TYPE, "
            "  c.IS_NULLABLE    AS IS_NULLABLE, "
            "  c.ORDINAL_POSITION AS ORDINAL_POSITION "
            "FROM INFORMATION_SCHEMA.COLUMNS AS c "
            "ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION"
        )
