"""SQLite dialect implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from expo_jbm329.db.core.interfaces import DialectProtocol
from expo_jbm329.db.core.object_properties import MetadataState, ObjectPropertiesQueries

if TYPE_CHECKING:
    from expo_jbm329.db.core.object_properties import SchemaObjectIdentity


class SqliteDialect(DialectProtocol):
    """SQLite dialect implementation.

    Note:
        Uses double-quotes for identifiers (SQLite accepts backticks too).
        LIMIT injection via '... LIMIT n'.
        Metadata via sqlite_master and PRAGMA table_info.
        No whole-database one-shot column SQL (returns None to force batch).
    """

    name = "sqlite"
    limit_keyword = "LIMIT"

    def quote_ident(self, name: str) -> str:
        """Quote an identifier (e.g., table or column name) for SQLite.

        Args:
            name: The identifier to quote.

        Returns:
            The quoted identifier (e.g., "name"). Embedded double quotes are
            escaped by doubling them.
        """
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def qualify(self, schema: str, object_name: str) -> str:
        """Qualify an object name with a schema for SQLite.

        Args:
            schema: The schema name (typically 'main' or 'temp').
            object_name: The object name (e.g., table name).

        Returns:
            The qualified name (e.g., "main"."table"). If schema is empty,
            returns just the quoted table.
        """
        s = (schema or "").strip()
        if not s:
            return self.quote_ident(object_name)
        return f"{self.quote_ident(s)}.{self.quote_ident(object_name)}"

    def qualify_column(self, schema: str, object_name: str, column: str) -> str:
        """Qualify a column name with its schema and table for SQLite.

        Args:
            schema: The schema name (typically 'main' or 'temp').
            object_name: The table or view name.
            column: The column name.

        Returns:
            The qualified column name (e.g., "main"."table"."column").
        """
        return f"{self.qualify(schema, object_name)}.{self.quote_ident(column)}"

    def apply_limit(self, sql: str, n: int) -> str:
        """Apply a LIMIT clause to the given SQL query for SQLite.

        Args:
            sql: The SQL query string.
            n: The number of rows to limit.

        Returns:
            The modified SQL query with the LIMIT clause applied.
        """
        if not sql or n <= 0:
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
        _ = schema  # unused, but kept for signature consistency
        tbl = object_name.replace('"', '""')
        return (
            "SELECT "  # noqa: S608 - deferred SQL construction refactor
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

    def sql_object_properties(self, identity: SchemaObjectIdentity) -> ObjectPropertiesQueries:
        """Build read-only SQLite schema and table-valued PRAGMA queries.

        Args:
            identity: Requested table/view in main, temp or an attached schema.

        Returns:
            Native declared metadata without parsing SQL for comments or expressions.
        """
        schema = identity.schema or "main"

        def literal(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"

        schema_literal = literal(schema)
        name_literal = literal(identity.name)
        target = (
            f"SELECT rowid AS object_id, name, sql FROM {self.quote_ident(schema)}.sqlite_master "  # noqa: S608
            f"WHERE name = {name_literal} AND type = {literal(identity.kind.value)}"
        )
        if identity.catalog is not None:
            target += f" AND {literal(identity.catalog)} = {schema_literal}"
        prefix = f"WITH target AS ({target}) "
        object_sql = prefix + (  # noqa: S608 - quoted identifiers and escaped string literals
            f"SELECT {schema_literal} AS catalog_name, {schema_literal} AS schema_name, "  # noqa: S608
            "name AS object_name, object_id, sql AS modify_date FROM target"
        )
        table_info = f"pragma_table_xinfo({name_literal}, {schema_literal})"
        indexes = f"pragma_index_list({name_literal}, {schema_literal})"
        # A true INTEGER PRIMARY KEY rowid alias has no separate primary-key index.
        rowid_alias = (
            "c.pk > 0 AND UPPER(c.type) = 'INTEGER' "  # noqa: S608 - escaped PRAGMA arguments
            f"AND (SELECT COUNT(*) FROM {table_info} WHERE pk > 0) = 1 "
            f"AND NOT EXISTS (SELECT 1 FROM {indexes} WHERE origin = 'pk')"
        )
        columns_sql = prefix + (
            "SELECT o.object_id, c.cid AS column_id, c.name AS column_name, c.cid + 1 AS ordinal_position, "  # noqa: S608
            f'c.type AS data_type, NOT (c."notnull" OR ({rowid_alias})) AS nullable, '
            "(c.dflt_value IS NOT NULL) AS default_present, c.dflt_value AS default_definition, "
            "'unsupported' AS identity_state, 0 AS identity_present, NULL AS identity_definition, "
            "(c.hidden IN (2, 3)) AS generated_present, NULL AS generated_definition "
            f"FROM target AS o JOIN {table_info} AS c ORDER BY c.cid"
        )
        constraints_sql = prefix + (
            "SELECT o.object_id, 0 AS constraint_id, NULL AS constraint_name, 'primary_key' AS constraint_kind, "  # noqa: S608
            "c.pk AS column_position, c.name AS column_name, NULL AS definition, "
            "NULL AS referenced_schema, NULL AS referenced_object, NULL AS referenced_column, "
            "NULL AS referenced_columns_state "
            f"FROM target AS o JOIN {table_info} AS c WHERE c.pk > 0 "
            "UNION ALL SELECT o.object_id, i.name, i.name, 'unique', k.seqno + 1, k.name, NULL, NULL, NULL, NULL, NULL "
            f"FROM target AS o JOIN {indexes} AS i "
            f"JOIN pragma_index_xinfo(i.name, {schema_literal}) AS k "
            "WHERE i.origin = 'u' AND k.key = 1 "
            "UNION ALL SELECT o.object_id, f.id, NULL, 'foreign_key', f.seq + 1, f.\"from\", NULL, "
            f'{schema_literal}, f."table", COALESCE(f."to", p.name), '
            "CASE WHEN COALESCE(f.\"to\", p.name) IS NULL THEN 'unavailable' END "
            f"FROM target AS o JOIN pragma_foreign_key_list({name_literal}, {schema_literal}) AS f "
            f'LEFT JOIN pragma_table_xinfo(f."table", {schema_literal}) AS p '
            'ON f."to" IS NULL AND p.pk = f.seq + 1 '
            "ORDER BY constraint_kind, constraint_id, column_position"
        )
        return ObjectPropertiesQueries(
            object_sql,
            columns_sql,
            constraints_sql,
            properties=None,
            description_property=None,
            object_description_state=MetadataState.UNSUPPORTED,
            column_description_state=MetadataState.UNSUPPORTED,
            check_constraints_state=MetadataState.UNAVAILABLE,
            verify_catalog_rows=True,
        )
