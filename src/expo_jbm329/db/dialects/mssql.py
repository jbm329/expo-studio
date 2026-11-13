"""MSSQL dialect implementation."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from expo_jbm329.db.core.interfaces import DialectProtocol
from expo_jbm329.db.core.object_properties import ObjectPropertiesQueries, SchemaObjectKind

if TYPE_CHECKING:
    from expo_jbm329.db.core.object_properties import SchemaObjectIdentity


class MssqlDialect(DialectProtocol):
    """MSSQL dialect: quoting, limit injection, metadata SQL builders."""

    name = "mssql"
    limit_keyword = "TOP"

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
            The quoted identifier (e.g., [name]). Embedded closing brackets
            are escaped by doubling them.
        """
        escaped = name.replace("]", "]]")
        return f"[{escaped}]"

    def qualify(self, schema: str, object_name: str) -> str:
        """Qualify an object name with a schema for MSSQL.

        Args:
            schema: The schema name.
            object_name: The object name (e.g., table name).

        Returns:
            The fully qualified name (e.g., [schema].[object]).
        """
        return f"{self.quote_ident(schema)}.{self.quote_ident(object_name)}"

    def qualify_column(self, schema: str, object_name: str, column: str) -> str:
        """Qualify a column name with its schema and table/view for MSSQL.

        Args:
            schema: The schema name.
            object_name: The table or view name.
            column: The column name.

        Returns:
            The fully qualified column name (e.g., [schema].[table].[column]).
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

    def sql_object_properties(self, identity: SchemaObjectIdentity) -> ObjectPropertiesQueries:
        """Build scoped catalog queries for table/view properties.

        Args:
            identity: Unquoted identity within the current database.

        Returns:
            Queries with a shared object scope and normalized metadata aliases.
        """

        def literal(value: str) -> str:
            return "N'" + value.replace("'", "''") + "'"

        object_type = "U" if identity.kind == SchemaObjectKind.TABLE else "V"
        scope = (
            "SELECT o.object_id, o.name, o.type, o.modify_date, s.name AS schema_name "  # noqa: S608 - escaped Unicode literals
            "FROM sys.objects AS o JOIN sys.schemas AS s ON s.schema_id = o.schema_id "
            f"WHERE s.name = {literal(identity.schema)} AND o.name = {literal(identity.name)} "
            f"AND o.type = {literal(object_type)}"
        )
        if identity.catalog is not None:
            scope += f" AND DB_NAME() = {literal(identity.catalog)}"
        prefix = f"WITH target AS ({scope}) "
        object_sql = prefix + (  # noqa: S608 - prefix contains only escaped catalog filters
            "SELECT DB_NAME() AS catalog_name, schema_name, name AS object_name, object_id, modify_date FROM target"
        )
        columns_sql = prefix + (
            "SELECT o.object_id, c.column_id, c.name AS column_name, "
            "c.column_id AS ordinal_position, "
            "CASE WHEN t.user_type_id IS NULL THEN NULL "
            "WHEN t.is_user_defined = 1 OR t.is_assembly_type = 1 "
            "THEN QUOTENAME(ts.name) + N'.' + QUOTENAME(t.name) "
            "ELSE t.name + CASE "
            "WHEN t.name IN (N'varchar', N'char', N'varbinary', N'binary', N'nvarchar', N'nchar') "
            "THEN N'(' + CASE WHEN c.max_length = -1 THEN N'max' "
            "ELSE CONVERT(nvarchar(10), CASE WHEN t.name IN (N'nvarchar', N'nchar') "
            "THEN c.max_length / 2 ELSE c.max_length END) END + N')' "
            "WHEN t.name IN (N'decimal', N'numeric') THEN N'(' + CONVERT(nvarchar(10), c.precision) "
            "+ N', ' + CONVERT(nvarchar(10), c.scale) + N')' "
            "WHEN t.name IN (N'datetime2', N'datetimeoffset', N'time') "
            "THEN N'(' + CONVERT(nvarchar(10), c.scale) + N')' "
            "WHEN t.name = N'float' THEN N'(' + CONVERT(nvarchar(10), c.precision) + N')' "
            "WHEN t.name = N'xml' AND c.xml_collection_id <> 0 "
            "THEN N'(' + CASE WHEN c.is_xml_document = 1 THEN N'DOCUMENT ' ELSE N'CONTENT ' END "
            "+ QUOTENAME(xs.name) + N'.' + QUOTENAME(xc.name) + N')' "
            "ELSE N'' END END AS data_type, "
            "c.is_nullable AS nullable, "
            "CASE WHEN c.default_object_id <> 0 THEN 1 ELSE 0 END AS default_present, "
            "OBJECT_DEFINITION(c.default_object_id) AS default_definition, "
            "c.is_identity AS identity_present, "
            "CASE WHEN ic.object_id IS NOT NULL THEN N'IDENTITY(' "
            "+ CONVERT(nvarchar(100), ic.seed_value) + N', ' "
            "+ CONVERT(nvarchar(100), ic.increment_value) + N')' END AS identity_definition, "
            "c.is_computed AS generated_present, cc.definition AS generated_definition "
            "FROM target AS o JOIN sys.columns AS c ON c.object_id = o.object_id "
            "LEFT JOIN sys.types AS t ON t.user_type_id = c.user_type_id "
            "LEFT JOIN sys.schemas AS ts ON ts.schema_id = t.schema_id "
            "LEFT JOIN sys.identity_columns AS ic ON ic.object_id = c.object_id AND ic.column_id = c.column_id "
            "LEFT JOIN sys.computed_columns AS cc ON cc.object_id = c.object_id AND cc.column_id = c.column_id "
            "LEFT JOIN sys.xml_schema_collections AS xc ON xc.xml_collection_id = c.xml_collection_id "
            "LEFT JOIN sys.schemas AS xs ON xs.schema_id = xc.schema_id "
            "ORDER BY c.column_id"
        )
        constraints_sql = prefix + (
            "SELECT o.object_id, k.object_id AS constraint_id, k.name AS constraint_name, "
            "CASE k.type WHEN 'PK' THEN 'primary_key' ELSE 'unique' END AS constraint_kind, "
            "ic.key_ordinal AS column_position, c.name AS column_name, "
            "CAST(NULL AS nvarchar(max)) AS definition, "
            "CAST(NULL AS sysname) AS referenced_schema, CAST(NULL AS sysname) AS referenced_object, "
            "CAST(NULL AS sysname) AS referenced_column "
            "FROM target AS o JOIN sys.key_constraints AS k ON k.parent_object_id = o.object_id "
            "JOIN sys.index_columns AS ic ON ic.object_id = o.object_id "
            "AND ic.index_id = k.unique_index_id AND ic.key_ordinal > 0 "
            "JOIN sys.columns AS c ON c.object_id = o.object_id AND c.column_id = ic.column_id "
            "UNION ALL "
            "SELECT o.object_id, fk.object_id, fk.name, 'foreign_key', fc.constraint_column_id, c.name, "
            "NULL, rs.name, rt.name, rc.name "
            "FROM target AS o JOIN sys.foreign_keys AS fk ON fk.parent_object_id = o.object_id "
            "JOIN sys.foreign_key_columns AS fc ON fc.constraint_object_id = fk.object_id "
            "JOIN sys.columns AS c ON c.object_id = o.object_id AND c.column_id = fc.parent_column_id "
            "LEFT JOIN sys.objects AS rt ON rt.object_id = fk.referenced_object_id "
            "LEFT JOIN sys.schemas AS rs ON rs.schema_id = rt.schema_id "
            "LEFT JOIN sys.columns AS rc ON rc.object_id = rt.object_id AND rc.column_id = fc.referenced_column_id "
            "UNION ALL "
            "SELECT o.object_id, ck.object_id, ck.name, 'check', 1, c.name, ck.definition, NULL, NULL, NULL "
            "FROM target AS o JOIN sys.check_constraints AS ck ON ck.parent_object_id = o.object_id "
            "LEFT JOIN sys.columns AS c ON c.object_id = o.object_id AND c.column_id = ck.parent_column_id "
            "ORDER BY constraint_id, column_position"
        )
        properties_sql = prefix + (  # noqa: S608 - prefix contains only escaped catalog filters
            "SELECT o.object_id, ep.minor_id AS column_id, ep.name AS property_name, "
            "CASE WHEN SQL_VARIANT_PROPERTY(ep.value, 'BaseType') IN ('binary', 'varbinary') "
            "THEN CONVERT(nvarchar(max), CONVERT(varbinary(8000), ep.value), 1) "
            "ELSE CONVERT(nvarchar(max), ep.value) END AS property_value "
            "FROM target AS o JOIN sys.extended_properties AS ep "
            "ON ep.class = 1 AND ep.major_id = o.object_id "
            "WHERE ep.minor_id = 0 OR EXISTS "
            "(SELECT 1 FROM sys.columns AS c WHERE c.object_id = o.object_id AND c.column_id = ep.minor_id) "
            "ORDER BY ep.minor_id, ep.name"
        )
        return ObjectPropertiesQueries(object_sql, columns_sql, constraints_sql, properties_sql)
