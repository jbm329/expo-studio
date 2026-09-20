"""Pure-logic SQL autocomplete engine.

This module provides the core logic for generating SQL autocomplete suggestions
based on a provided database schema. It is designed to be independent of the
UI framework.
"""

from __future__ import annotations

import logging
from typing import Self

from expo_jbm329.db.sql_analysis import TableRef, extract_table_refs

MIN_QUOTED_IDENTIFIER_LENGTH = 2
SCHEMA_TABLE_PARTS = 2
SCHEMA_TABLE_COLUMN_PARTS = 3


class SqlAutoCompleter:
    """Pure-logic SQL autocomplete engine (Qt-free).

    Supports various completion patterns:
      - schema.
      - schema.table.
      - table.
      - table.colprefix
      - schema.table.colprefix
      - alias.
      - alias.colprefix
      - global prefix (no dot)

    Attributes:
        _schema: The database schema metadata.
    """

    def __init__(self) -> None:
        """Initialize the autocompleter."""
        self._schema: dict[str, dict[str, list[str]]] = {}
        self._log = logging.getLogger("applogger.ui.autocomplete")

    # ------------------------------------------------------------------ #
    def set_schema(self, schema_dict: dict[str, object] | None) -> None:
        """Set the schema metadata used for generating suggestions.

        Args:
            schema_dict: Schema metadata. The preferred internal shape is:

                {
                    "schema_name": {
                        "table_name": ["column_a", "column_b"]
                    }
                }

            For compatibility, this method also accepts richer schema dictionaries
            containing a "by_schema" key.
        """
        raw_keys = list(schema_dict.keys()) if schema_dict is not None else []
        self._schema = self._normalize_schema_dict(schema_dict or {})

        non_empty_column_tables = 0
        for tables in self._schema.values():
            for columns in tables.values():
                if columns:
                    non_empty_column_tables += 1

        self._log.debug(
            "SqlAutoCompleter: schema loaded raw_keys=%s schemas=%s table_count=%s non_empty_column_tables=%s",
            raw_keys,
            list(self._schema.keys()),
            sum(len(tables) for tables in self._schema.values()),
            non_empty_column_tables,
        )

    # ------------------------------------------------------------------ #
    def get_contextual_suggestions(
        self,
        sql: str,
        cursor_pos: int,
        prefix: str,
        *,
        dialect: str | None = None,
    ) -> list[str]:
        """Get SQL-aware suggestions using the current query context.

        This method first tries context-aware completions, such as resolving
        table aliases. If no contextual suggestions are found, it falls back to
        the existing prefix-based completion behavior.

        Args:
            sql: Full SQL editor text.
            cursor_pos: Current cursor position in the editor text.
            prefix: Prefix/token immediately before the cursor.
            dialect: Optional internal engine name or sqlglot dialect name.

        Returns:
            A list of matching suggestions.
        """
        safe_sql = sql
        safe_cursor_pos = max(0, min(int(cursor_pos), len(safe_sql)))
        safe_prefix = (prefix or "").strip()

        self._log.debug(
            "SqlAutoCompleter: contextual request prefix=%r cursor_pos=%s dialect=%r schema_count=%s",
            safe_prefix,
            safe_cursor_pos,
            dialect,
            len(self._schema),
        )

        if not safe_prefix:
            self._log.debug("SqlAutoCompleter: no prefix; returning empty suggestions.")
            return []

        contextual = self._get_alias_column_suggestions(
            safe_sql,
            safe_cursor_pos,
            safe_prefix,
            dialect=dialect,
        )
        if contextual:
            self._log.debug(
                "SqlAutoCompleter: using contextual suggestions count=%s preview=%s",
                len(contextual),
                contextual[:10],
            )
            return contextual

        fallback = self.get_suggestions(safe_prefix)
        self._log.debug(
            "SqlAutoCompleter: using fallback suggestions count=%s preview=%s",
            len(fallback),
            fallback[:10],
        )
        return fallback

    # ------------------------------------------------------------------ #
    def get_suggestions(self, text: str) -> list[str]:
        """Get autocomplete suggestions based on the provided text.

        Parses the text to determine if it's a schema, table, or column prefix
        and returns matching objects from the schema.

        Args:
            text: The text prefix to get suggestions for.

        Returns:
            A list of matching object names.
        """
        text = (text or "").strip()
        if not text:
            return []

        if "." in text:
            parts = text.split(".")

            # schema. OR table.
            if len(parts) == SCHEMA_TABLE_PARTS:
                first, second = parts
                if text.endswith("."):
                    schema_key = self._resolve_schema_ci(first)
                    if schema_key:
                        return self._list_tables(schema_key)

                    table = first
                    schema_for_table = self._find_schema_for_table(table)
                    return self._list_columns(schema_for_table, table) if schema_for_table else []

                schema_key = self._resolve_schema_ci(first)
                if schema_key:
                    return self._filter_starts_with(self._list_tables(schema_key), second)

                table = first
                colprefix = second
                schema_for_table = self._find_schema_for_table(table)
                if schema_for_table:
                    return self._filter_starts_with(self._list_columns(schema_for_table, table), colprefix)
                return []

            # schema.table. OR schema.table.colprefix
            if len(parts) == SCHEMA_TABLE_COLUMN_PARTS:
                schema, table, colprefix = parts
                if text.endswith("."):
                    return self._list_columns(schema, table)
                return self._filter_starts_with(self._list_columns(schema, table), colprefix)

        # table. (no schema)
        if text.endswith("."):
            table = text[:-1]
            table_schema = self._find_schema_for_table(table)
            return self._list_columns(table_schema, table) if table_schema else []

        # table.prefix (no schema)
        if "." in text:
            table, colprefix = text.split(".", 1)
            table_schema = self._find_schema_for_table(table)
            if table_schema:
                return self._filter_starts_with(self._list_columns(table_schema, table), colprefix)

        # fallback → global prefix
        return self.get_global_suggestions(text)

    # ------------------------------------------------------------------ #
    def get_global_suggestions(self, prefix: str) -> list[str]:
        """Get suggestions from all schemas, tables, and columns matching the prefix.

        Args:
            prefix: The prefix to search for across all object types.

        Returns:
            A list of matching schema, table, and column names.
        """
        if not prefix:
            return []

        pref = prefix.lower()
        col_set = set()
        tables: list[str] = []
        schemas: list[str] = []

        for schema_name, tbls in self._schema.items():
            if schema_name.lower().startswith(pref):
                schemas.append(schema_name)
            for table_name, cols in tbls.items():
                if table_name.lower().startswith(pref):
                    tables.append(table_name)
                for col in cols:
                    if col.lower().startswith(pref):
                        col_set.add(col)

        col_list = sorted(col_set, key=str.lower)
        tables.sort(key=str.lower)
        schemas.sort(key=str.lower)
        return col_list + tables + schemas

    # ------------------------------------------------------------------ #
    def get_all_objects(self) -> list[str]:
        """Distinct columns + all tables + all schemas."""
        col_set: set[str] = set()
        tables: list[str] = []
        schemas: list[str] = []

        for schema_name, tbls in self._schema.items():
            schemas.append(schema_name)
            for table_name, cols in tbls.items():
                tables.append(table_name)
                for col in cols:
                    col_set.add(col)

        col_list = sorted(col_set, key=str.lower)
        tables.sort(key=str.lower)
        schemas.sort(key=str.lower)
        return col_list + tables + schemas

    # ------------------------------------------------------------------ #
    def _get_alias_column_suggestions(
        self,
        sql: str,
        cursor_pos: int,
        prefix: str,
        *,
        dialect: str | None = None,
    ) -> list[str]:
        """Return column suggestions for alias-qualified prefixes.

        Examples:
            c.      -> columns from the table aliased as c
            c.na    -> matching columns from the table aliased as c

        Args:
            sql: Full SQL editor text.
            cursor_pos: Current cursor position in the editor text.
            prefix: Current token/prefix before the cursor.
            dialect: Optional internal engine name or sqlglot dialect name.

        Returns:
            Matching column suggestions, or an empty list when no alias context
            can be resolved.
        """
        if "." not in prefix:
            self._log.debug("SqlAutoCompleter: prefix has no dot; not alias-qualified: %r", prefix)
            return []

        qualifier, col_prefix = prefix.rsplit(".", 1)
        qualifier = qualifier.strip()
        if not qualifier:
            self._log.debug("SqlAutoCompleter: empty qualifier for prefix=%r", prefix)
            return []

        parse_sql = self._sql_with_completion_placeholder(
            sql,
            cursor_pos,
            prefix,
            qualifier,
        )

        self._log.debug(
            "SqlAutoCompleter: alias completion qualifier=%r col_prefix=%r parse_sql=%r",
            qualifier,
            col_prefix,
            parse_sql,
        )

        parse_dialect = self._dialect_for_completion_parse(parse_sql, dialect)
        refs = extract_table_refs(parse_sql, parse_dialect)

        self._log.debug(
            "SqlAutoCompleter: extracted table refs=%s using parse_dialect=%r",
            refs,
            parse_dialect,
        )

        if not refs and parse_dialect != "tsql":
            refs = extract_table_refs(parse_sql, "tsql")
            self._log.debug(
                "SqlAutoCompleter: retry extracted table refs=%s using parse_dialect='tsql'",
                refs,
            )

        ref = self._resolve_ref_for_qualifier(refs, qualifier)
        self._log.debug("SqlAutoCompleter: resolved qualifier=%r to ref=%s", qualifier, ref)

        if ref is None:
            return []

        schema = ref.schema or self._find_schema_for_table(ref.name)
        self._log.debug(
            "SqlAutoCompleter: resolved table=%r schema_from_sql=%r schema_used=%r available_schemas=%s",
            ref.name,
            ref.schema,
            schema,
            list(self._schema.keys()),
        )

        if not schema:
            return []

        columns = self._list_columns(schema, ref.name)
        self._log.debug(
            "SqlAutoCompleter: resolved columns for %s.%s count=%s preview=%s",
            schema,
            ref.name,
            len(columns),
            columns[:10],
        )

        return self._filter_starts_with(columns, col_prefix)

    def _resolve_ref_for_qualifier(
        self,
        refs: list[TableRef],
        qualifier: str,
    ) -> TableRef | None:
        """Resolve a table reference by alias or table name."""
        qualifier_l = qualifier.lower()

        for ref in reversed(refs):
            alias = ref.alias
            if alias and alias.lower() == qualifier_l:
                return ref

        for ref in reversed(refs):
            if ref.name.lower() == qualifier_l:
                return ref

        return None

    # ------------------------------------------------------------------ #
    @classmethod
    def _normalize_identifier(cls: type[Self], value: str | None) -> str:
        """Normalize an SQL identifier for lookup.

        Removes common SQL quoting styles used by supported dialects:
        - [identifier] for SQL Server
        - "identifier" for PostgreSQL/SQLite/Oracle
        - `identifier` for MySQL/MariaDB

        Args:
            value: Identifier text.

        Returns:
            Unquoted identifier text.
        """
        text = (value or "").strip()

        if len(text) >= MIN_QUOTED_IDENTIFIER_LENGTH:
            if text.startswith("[") and text.endswith("]"):
                return text[1:-1].replace("]]", "]")

            if text.startswith('"') and text.endswith('"'):
                return text[1:-1].replace('""', '"')

            if text.startswith("`") and text.endswith("`"):
                return text[1:-1].replace("``", "`")

        return text

    @classmethod
    def _normalize_qualified_identifier(cls: type[Self], value: str | None) -> str:
        """Normalize a possibly qualified SQL identifier.

        Examples:
            [dbo].[Table] -> dbo.Table
            "public"."users" -> public.users
            `db`.`users` -> db.users

        Args:
            value: Identifier text.

        Returns:
            Normalized identifier text.
        """
        text = (value or "").strip()
        if "." not in text:
            return cls._normalize_identifier(text)

        return ".".join(cls._normalize_identifier(part) for part in text.split("."))

    def _resolve_schema_ci(self, schema: str | None) -> str | None:
        s = self._normalize_identifier(schema).lower()
        for k in self._schema:
            if self._normalize_identifier(k).lower() == s:
                return k
        return None

    def _find_schema_for_table(self, table: str | None) -> str | None:
        table_l = self._normalize_identifier(table).lower()
        for schema, tbls in self._schema.items():
            for t in tbls:
                if self._normalize_identifier(t).lower() == table_l:
                    return schema
        return None

    def _list_tables(self, schema: str | None) -> list[str]:
        key = self._resolve_schema_ci(schema)
        if key is None:
            self._log.debug(
                "SqlAutoCompleter: no schema match while listing tables schema=%r normalized=%r available=%s",
                schema,
                self._normalize_identifier(schema),
                list(self._schema.keys()),
            )
            return []
        return list(self._schema.get(key, {}).keys())

    def _list_columns(self, schema: str | None, table: str | None) -> list[str]:
        skey = self._resolve_schema_ci(schema)
        if skey is None:
            self._log.debug(
                "SqlAutoCompleter: no schema match for schema=%r normalized=%r available=%s",
                schema,
                self._normalize_identifier(schema),
                list(self._schema.keys()),
            )
            return []

        t = self._normalize_identifier(table).lower()
        available_tables = list(self._schema.get(skey, {}).keys())

        for tbl_name, cols in self._schema.get(skey, {}).items():
            if self._normalize_identifier(tbl_name).lower() == t:
                self._log.debug(
                    "SqlAutoCompleter: table match schema=%r table=%r columns_count=%s",
                    skey,
                    tbl_name,
                    len(cols),
                )
                return cols

        self._log.debug(
            "SqlAutoCompleter: no table match for schema=%r table=%r normalized_table=%r available_tables=%s",
            skey,
            table,
            self._normalize_identifier(table),
            available_tables[:25],
        )
        return []

    @staticmethod
    def _filter_starts_with(items: list[str], prefix: str) -> list[str]:
        pref = (prefix or "").lower()
        return [i for i in items if i.lower().startswith(pref)]

    @staticmethod
    def _dialect_for_completion_parse(
        sql: str,
        dialect: str | None,
    ) -> str | None:
        """Return the best dialect to use for autocomplete context parsing.

        Args:
            sql: SQL text being parsed for autocomplete.
            dialect: Currently configured dialect, if any.

        Returns:
            The configured dialect, or a best-effort inferred dialect.
        """
        if dialect:
            return dialect

        # SQL Server / T-SQL bracket quoted identifiers:
        #   [dbo].[SomeTable]
        if "[" in sql and "]" in sql:
            return "tsql"

        return None

    @staticmethod
    def _sql_with_completion_placeholder(
        sql: str,
        cursor_pos: int,
        prefix: str,
        qualifier: str,
    ) -> str:
        """Return SQL with the active incomplete completion token replaced.

        This makes SQL like this parseable for context extraction:

            SELECT c.
            FROM customers c

        It becomes:

            SELECT c.__expo_dummy_col
            FROM customers c

        Args:
            sql: Full SQL editor text.
            cursor_pos: Current cursor position.
            prefix: Current token/prefix before the cursor.
            qualifier: Alias/table qualifier before the dot.

        Returns:
            SQL text that is more likely to parse successfully.
        """
        safe_sql = sql
        safe_cursor_pos = max(0, min(int(cursor_pos), len(safe_sql)))
        start = max(0, safe_cursor_pos - len(prefix))

        if start > safe_cursor_pos:
            return safe_sql

        placeholder = f"{qualifier}.__expo_dummy_col"
        return f"{safe_sql[:start]}{placeholder}{safe_sql[safe_cursor_pos:]}"

        # ------------------------------------------------------------------ #

    def _normalize_schema_dict(self, schema_dict: dict[str, object]) -> dict[str, dict[str, list[str]]]:
        """Normalize supported schema-cache shapes into the autocomplete shape.

        The autocomplete engine internally expects:

            {
                "schema_name": {
                    "table_name": ["column_a", "column_b"]
                }
            }

        Args:
            schema_dict: Raw schema dictionary from the workbench/schema cache.

        Returns:
            Normalized schema -> table -> columns mapping.
        """
        by_schema = schema_dict.get("by_schema")
        if isinstance(by_schema, dict):
            normalized = self._normalize_by_schema_shape(by_schema)
            if normalized:
                return normalized

        return self._normalize_direct_schema_shape(schema_dict)

    def _normalize_direct_schema_shape(self, schema_dict: dict[str, object]) -> dict[str, dict[str, list[str]]]:
        """Normalize a direct schema -> table -> columns mapping."""
        normalized: dict[str, dict[str, list[str]]] = {}

        for schema_name, tables in schema_dict.items():
            # Ignore richer top-level metadata keys if they reached this path.
            if schema_name in {"tables", "views", "columns", "loaded_at", "db_name", "by_schema"}:
                continue

            if not isinstance(tables, dict):
                continue

            normalized_tables: dict[str, list[str]] = {}

            for table_name, columns in tables.items():
                if not isinstance(table_name, str):
                    continue

                normalized_columns = self._normalize_columns(columns)
                normalized_tables[table_name] = normalized_columns

            if normalized_tables:
                normalized[schema_name] = normalized_tables

        return normalized

    def _normalize_by_schema_shape(self, by_schema: dict[object, object]) -> dict[str, dict[str, list[str]]]:
        """Normalize a by_schema mapping into schema -> table -> columns."""
        normalized: dict[str, dict[str, list[str]]] = {}

        for schema_name, tables in by_schema.items():
            if not isinstance(schema_name, str) or not isinstance(tables, dict):
                continue

            normalized_tables: dict[str, list[str]] = {}

            for table_name, value in tables.items():
                if not isinstance(table_name, str):
                    continue

                columns = self._extract_columns_from_table_payload(value)
                normalized_tables[table_name] = columns

            if normalized_tables:
                normalized[schema_name] = normalized_tables

        return normalized

    def _extract_columns_from_table_payload(self, value: object) -> list[str]:
        """Extract column names from a table payload in supported cache shapes."""
        if isinstance(value, list | tuple):
            return self._normalize_columns(value)

        if isinstance(value, dict):
            for key in ("columns", "cols", "fields"):
                columns = value.get(key)
                if isinstance(columns, list | tuple):
                    return self._normalize_columns(columns)

        return []

    @staticmethod
    def _normalize_columns(columns: object) -> list[str]:
        """Normalize supported column payloads into a list of column names."""
        if not isinstance(columns, list | tuple):
            return []

        out: list[str] = []

        for column in columns:
            if isinstance(column, str):
                out.append(column)
                continue

            if isinstance(column, dict):
                for key in ("name", "column_name", "COLUMN_NAME", "COLUMN", "ColumnName"):
                    value = column.get(key)
                    if isinstance(value, str) and value:
                        out.append(value)
                        break

        return out
