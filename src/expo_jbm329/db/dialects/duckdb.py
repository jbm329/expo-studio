"""DuckDB SQL syntax and selected-catalog metadata queries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from expo_jbm329.db.core.interfaces import DialectProtocol
from expo_jbm329.db.core.object_properties import ObjectPropertiesQueries, SchemaObjectKind

if TYPE_CHECKING:
    from expo_jbm329.db.core.object_properties import SchemaObjectIdentity


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

    def sql_object_properties(self, identity: SchemaObjectIdentity) -> ObjectPropertiesQueries:
        """Build native DuckDB catalog queries without reading object contents.

        Args:
            identity: Requested table/view in the selected file's catalog.

        Returns:
            Scoped comment, column and declared-constraint queries.
        """
        view = identity.kind == SchemaObjectKind.VIEW
        kind = "view" if view else "table"
        scope = (
            "database_name = current_database() "
            f"AND schema_name = {self._literal(identity.schema)} "
            f"AND {kind}_name = {self._literal(identity.name)} AND NOT internal"
        )
        if identity.catalog is not None:
            scope += f" AND database_name = {self._literal(identity.catalog)}"
        prefix = (
            f"WITH target AS (SELECT database_name, schema_name, {kind}_name AS object_name, "  # noqa: S608
            f"{kind}_oid AS object_id, comment, sql FROM duckdb_{kind}s() WHERE {scope}) "
        )
        object_sql = prefix + (  # noqa: S608 - scope uses escaped literals and a fixed table/view choice
            "SELECT database_name AS catalog_name, schema_name, object_name, object_id, "
            "comment AS description, sql AS modify_date FROM target"
        )
        columns_sql = prefix + (
            "SELECT o.object_id, c.column_index AS column_id, c.column_name, c.column_index AS ordinal_position, "
            "c.data_type, c.is_nullable AS nullable, c.comment AS description, "
            "(c.column_default IS NOT NULL AND NOT c.is_generated) AS default_present, "
            "CASE WHEN NOT c.is_generated THEN c.column_default END AS default_definition, "
            "'unsupported' AS identity_state, false AS identity_present, NULL AS identity_definition, "
            "c.is_generated AS generated_present, c.generation_expression AS generated_definition "
            "FROM target AS o JOIN duckdb_columns() AS c ON c.database_name = o.database_name "
            "AND c.schema_name = o.schema_name AND c.table_name = o.object_name AND c.table_oid = o.object_id "
            "ORDER BY c.column_index"
        )
        constraints_sql = prefix + (
            "SELECT o.object_id, k.constraint_index AS constraint_id, k.constraint_name, "
            "CASE k.constraint_type WHEN 'PRIMARY KEY' THEN 'primary_key' WHEN 'UNIQUE' THEN 'unique' "
            "WHEN 'FOREIGN KEY' THEN 'foreign_key' WHEN 'CHECK' THEN 'check' END AS constraint_kind, "
            "COALESCE(p.position, 1) AS column_position, k.constraint_column_names[p.position] AS column_name, "
            "k.constraint_text AS definition, "
            # DuckDB rejects foreign keys across schemas/catalogs.
            "CASE WHEN k.constraint_type = 'FOREIGN KEY' THEN o.schema_name END AS referenced_schema, "
            "k.referenced_table AS referenced_object, k.referenced_column_names[p.position] AS referenced_column "
            "FROM target AS o JOIN duckdb_constraints() AS k ON k.database_name = o.database_name "
            "AND k.schema_name = o.schema_name AND k.table_name = o.object_name AND k.table_oid = o.object_id "
            "LEFT JOIN LATERAL UNNEST(range(1, len(k.constraint_column_names) + 1)) AS p(position) ON true "
            "WHERE k.constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY', 'CHECK') "
            "ORDER BY k.constraint_index, p.position"
        )
        return ObjectPropertiesQueries(
            object_sql,
            columns_sql,
            constraints_sql,
            properties=None,
            description_property=None,
            verify_catalog_rows=True,
        )
