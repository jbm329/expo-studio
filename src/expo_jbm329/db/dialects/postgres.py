"""PostgreSQL dialect implementation."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from expo_jbm329.db.core.interfaces import DialectProtocol
from expo_jbm329.db.core.object_properties import ObjectPropertiesQueries, SchemaObjectKind

if TYPE_CHECKING:
    from expo_jbm329.db.core.object_properties import SchemaObjectIdentity


class PostgresDialect(DialectProtocol):
    """PostgreSQL dialect implementation."""

    name = "postgresql"
    limit_keyword = "LIMIT"

    _LIMIT_RE = re.compile(r"(?is)\b(limit\s+\d+|fetch\s+first\s+\d+\s+rows?\s+only)\b")

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
            'SELECT COLUMN_NAME AS "COLUMN_NAME", DATA_TYPE AS "DATA_TYPE", IS_NULLABLE AS "IS_NULLABLE" '  # noqa: S608
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
            '  TABLE_SCHEMA AS "TABLE_SCHEMA", '
            '  TABLE_NAME AS "TABLE_NAME", '
            '  COLUMN_NAME AS "COLUMN_NAME", '
            '  DATA_TYPE AS "DATA_TYPE", '
            '  IS_NULLABLE AS "IS_NULLABLE", '
            '  ORDINAL_POSITION AS "ORDINAL_POSITION" '
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
        )

    def sql_object_properties(self, identity: SchemaObjectIdentity) -> ObjectPropertiesQueries:
        """Build PostgreSQL catalog queries for native comments and constraints.

        Args:
            identity: Unquoted table or view identity in the current database.

        Returns:
            Common-shaped catalog queries without synthetic named properties.
        """

        def literal(value: str) -> str:
            # E literals are independent of standard_conforming_strings.
            return "E'" + value.replace("\\", "\\\\").replace("'", "''") + "'"

        kinds = "('r', 'p')" if identity.kind == SchemaObjectKind.TABLE else "('v')"
        scope = (
            "SELECT c.oid, c.relname, n.nspname, c.xmin::text AS catalog_version "  # noqa: S608 - escaped E literals
            "FROM pg_catalog.pg_class AS c "
            "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
            f"WHERE n.nspname = {literal(identity.schema)} AND c.relname = {literal(identity.name)} "
            f"AND c.relkind IN {kinds}"
        )
        if identity.catalog is not None:
            scope += f" AND pg_catalog.current_database() = {literal(identity.catalog)}"
        prefix = f"WITH target AS ({scope}) "
        object_sql = prefix + (  # noqa: S608 - scope contains only escaped E literals and fixed catalog SQL
            "SELECT pg_catalog.current_database() AS catalog_name, o.nspname AS schema_name, "
            "o.relname AS object_name, o.oid::bigint AS object_id, "
            "pg_catalog.obj_description(o.oid, 'pg_class') AS description, "
            "o.catalog_version || '|' || COALESCE(("
            "SELECT pg_catalog.string_agg(a.xmin::text, ',' ORDER BY a.attnum) "
            "FROM pg_catalog.pg_attribute AS a WHERE a.attrelid = o.oid), '') || '|' || COALESCE(("
            "SELECT pg_catalog.string_agg(d.xmin::text, ',' ORDER BY d.objsubid) "
            "FROM pg_catalog.pg_description AS d WHERE d.objoid = o.oid "
            "AND d.classoid = 'pg_catalog.pg_class'::regclass), '') || '|' || COALESCE(("
            "SELECT pg_catalog.string_agg(k.xmin::text, ',' ORDER BY k.oid) "
            "FROM pg_catalog.pg_constraint AS k WHERE k.conrelid = o.oid), '') || '|' || COALESCE(("
            "SELECT pg_catalog.string_agg(ad.xmin::text, ',' ORDER BY ad.adnum) "
            "FROM pg_catalog.pg_attrdef AS ad WHERE ad.adrelid = o.oid), '') AS modify_date FROM target AS o"
        )
        columns_sql = prefix + (
            "SELECT o.oid::bigint AS object_id, a.attnum AS column_id, a.attname AS column_name, "
            "a.attnum AS ordinal_position, pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type, "
            "NOT (a.attnotnull OR COALESCE(t.typnotnull, false)) AS nullable, "
            "pg_catalog.col_description(o.oid, a.attnum) AS description, "
            "(ad.oid IS NOT NULL AND COALESCE(to_jsonb(a)->>'attgenerated', '') = '') AS default_present, "
            "CASE WHEN COALESCE(to_jsonb(a)->>'attgenerated', '') = '' "
            "THEN pg_catalog.pg_get_expr(ad.adbin, ad.adrelid) END AS default_definition, "
            "(COALESCE(to_jsonb(a)->>'attidentity', '') <> '') AS identity_present, "
            "CASE to_jsonb(a)->>'attidentity' WHEN 'a' THEN 'GENERATED ALWAYS AS IDENTITY' "
            "WHEN 'd' THEN 'GENERATED BY DEFAULT AS IDENTITY' END AS identity_definition, "
            "(COALESCE(to_jsonb(a)->>'attgenerated', '') <> '') AS generated_present, "
            "CASE WHEN COALESCE(to_jsonb(a)->>'attgenerated', '') <> '' "
            "THEN pg_catalog.pg_get_expr(ad.adbin, ad.adrelid) END AS generated_definition "
            "FROM target AS o JOIN pg_catalog.pg_attribute AS a ON a.attrelid = o.oid "
            "JOIN pg_catalog.pg_type AS t ON t.oid = a.atttypid "
            "LEFT JOIN pg_catalog.pg_attrdef AS ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum "
            "WHERE a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum"
        )
        constraints_sql = prefix + (
            "SELECT o.oid::bigint AS object_id, k.oid::bigint AS constraint_id, k.conname AS constraint_name, "
            "CASE k.contype WHEN 'p' THEN 'primary_key' WHEN 'u' THEN 'unique' "
            "WHEN 'f' THEN 'foreign_key' WHEN 'c' THEN 'check' END AS constraint_kind, "
            "COALESCE(key.position, 1)::integer AS column_position, a.attname AS column_name, "
            "pg_catalog.pg_get_constraintdef(k.oid, true) AS definition, "
            "rn.nspname AS referenced_schema, rc.relname AS referenced_object, ra.attname AS referenced_column "
            "FROM target AS o JOIN pg_catalog.pg_constraint AS k ON k.conrelid = o.oid "
            "LEFT JOIN LATERAL unnest(k.conkey) WITH ORDINALITY AS key(attnum, position) ON true "
            "LEFT JOIN pg_catalog.pg_attribute AS a ON a.attrelid = o.oid AND a.attnum = key.attnum "
            "LEFT JOIN pg_catalog.pg_class AS rc ON rc.oid = k.confrelid "
            "LEFT JOIN pg_catalog.pg_namespace AS rn ON rn.oid = rc.relnamespace "
            "LEFT JOIN pg_catalog.pg_attribute AS ra ON ra.attrelid = k.confrelid "
            "AND ra.attnum = k.confkey[key.position::integer] "
            "WHERE k.contype IN ('p', 'u', 'f', 'c') ORDER BY k.oid, key.position"
        )
        return ObjectPropertiesQueries(
            object_sql,
            columns_sql,
            constraints_sql,
            properties=None,
            description_property=None,
            allows_zero_columns=True,
        )
