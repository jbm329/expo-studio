"""MySQL dialect implementation."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from expo_jbm329.db.core.interfaces import DialectProtocol
from expo_jbm329.db.core.object_properties import MetadataState, ObjectPropertiesQueries, SchemaObjectKind

if TYPE_CHECKING:
    import pandas as pd

    from expo_jbm329.db.core.object_properties import SchemaObjectIdentity


class MySqlDialect(DialectProtocol):
    """MySQL/MariaDB dialect implementation.

    Note:
        In MySQL the concept of "schema" is equivalent to "database".
    """

    name = "mysql"  # We'll reuse for MariaDB as well via registry
    limit_keyword = "LIMIT"

    # Detect if a query already has a LIMIT clause (supports "LIMIT n" or "LIMIT offset, n")
    _LIMIT_RE = re.compile(r"(?is)\blimit\s+\d+(\s*,\s*\d+)?\b")

    def quote_ident(self, name: str) -> str:
        """Quote an identifier (e.g., table or column name) for MySQL.

        Args:
            name: The identifier to quote.

        Returns:
            The quoted identifier (e.g., `name`). Embedded backticks are
            escaped by doubling them.
        """
        escaped = name.replace("`", "``")
        return f"`{escaped}`"

    def qualify(self, schema: str, object_name: str) -> str:
        """Qualify an object name with a schema for MySQL.

        Args:
            schema: The schema name.
            object_name: The object name (e.g., table name).

        Returns:
            The fully qualified name (e.g., `schema`.`table`).
        """
        return f"{self.quote_ident(schema)}.{self.quote_ident(object_name)}"

    def qualify_column(self, schema: str, object_name: str, column: str) -> str:
        """Qualify a column name with its schema and table/view for MySQL.

        Args:
            schema: The schema (database) name.
            object_name: The table or view name.
            column: The column name.

        Returns:
            The fully qualified column name (e.g., `schema`.`table`.`column`).
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

    def sql_object_properties_capabilities(self) -> str:
        """Discover catalog shape and default representation without probing by failure.

        Returns:
            A read-only catalog-column query including the server version.
        """
        return (
            "SELECT VERSION() AS server_version, TABLE_NAME AS table_name, COLUMN_NAME AS column_name "
            "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'information_schema' "
            "AND TABLE_NAME IN ('COLUMNS', 'TABLES', 'TABLE_CONSTRAINTS', 'KEY_COLUMN_USAGE', "
            "'CHECK_CONSTRAINTS', 'STATISTICS') "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION"
        )

    def sql_discovered_object_properties(
        self, identity: SchemaObjectIdentity, capabilities: pd.DataFrame
    ) -> ObjectPropertiesQueries:
        """Build queries for the discovered MySQL/MariaDB catalog capabilities.

        Args:
            identity: Requested database, object name and kind.
            capabilities: Successful result of the catalog-column discovery query.

        Returns:
            Scoped queries using only available optional catalog columns.

        Raises:
            ValueError: Discovery is empty or lacks required catalog metadata.
        """
        if not {"server_version", "table_name", "column_name"}.issubset(capabilities.columns):
            message = "Required object properties discovery fields are missing."
            raise ValueError(message)
        names: set[tuple[str, str]] = set()
        versions: set[str] = set()
        for version, table, column in capabilities[["server_version", "table_name", "column_name"]].itertuples(
            index=False, name=None
        ):
            if not all(isinstance(value, str) and value for value in (version, table, column)):
                message = "Invalid object properties catalog capabilities."
                raise ValueError(message)
            names.add((str(table).upper(), str(column).upper()))
            versions.add(str(version))
        required = {
            "TABLES": {"TABLE_CATALOG", "TABLE_SCHEMA", "TABLE_NAME", "TABLE_TYPE", "TABLE_COMMENT", "CREATE_TIME"},
            "COLUMNS": {
                "TABLE_SCHEMA",
                "TABLE_NAME",
                "COLUMN_NAME",
                "ORDINAL_POSITION",
                "COLUMN_TYPE",
                "IS_NULLABLE",
                "COLUMN_DEFAULT",
                "COLUMN_COMMENT",
                "EXTRA",
                "DATA_TYPE",
            },
            "TABLE_CONSTRAINTS": {
                "CONSTRAINT_SCHEMA",
                "TABLE_SCHEMA",
                "TABLE_NAME",
                "CONSTRAINT_NAME",
                "CONSTRAINT_TYPE",
            },
            "KEY_COLUMN_USAGE": {
                "CONSTRAINT_SCHEMA",
                "TABLE_SCHEMA",
                "TABLE_NAME",
                "CONSTRAINT_NAME",
                "COLUMN_NAME",
                "ORDINAL_POSITION",
                "REFERENCED_TABLE_SCHEMA",
                "REFERENCED_TABLE_NAME",
                "REFERENCED_COLUMN_NAME",
            },
            "STATISTICS": {
                "INDEX_SCHEMA",
                "TABLE_SCHEMA",
                "TABLE_NAME",
                "INDEX_NAME",
                "COLUMN_NAME",
                "SEQ_IN_INDEX",
                "SUB_PART",
            },
        }
        if len(versions) != 1 or any((table, col) not in names for table, cols in required.items() for col in cols):
            message = "Required object properties catalog capabilities are unavailable."
            raise ValueError(message)
        checks = any(table == "CHECK_CONSTRAINTS" for table, _ in names)
        if checks and any(
            ("CHECK_CONSTRAINTS", col) not in names for col in ("CONSTRAINT_SCHEMA", "CONSTRAINT_NAME", "CHECK_CLAUSE")
        ):
            message = "Required CHECK catalog columns are unavailable."
            raise ValueError(message)
        version = next(iter(versions))
        maria = "mariadb" in version.lower()
        if maria and checks and ("CHECK_CONSTRAINTS", "TABLE_NAME") not in names:
            message = "MariaDB CHECK catalog does not expose table identity."
            raise ValueError(message)
        match = re.match(r"(?:5\.5\.5-)?(\d+)\.(\d+)\.(\d+)", version)
        if match is None:
            message = "Cannot determine catalog default representation."
            raise ValueError(message)
        quoted_defaults = maria and tuple(int(part) for part in match.groups()) >= (10, 2, 7)
        return self._object_properties_queries(
            identity,
            checks=checks,
            table_checks=("CHECK_CONSTRAINTS", "TABLE_NAME") in names,
            generated=("COLUMNS", "GENERATION_EXPRESSION") in names,
            quoted_defaults=quoted_defaults,
            ambiguous_defaults=maria and not quoted_defaults,
            key_expressions=("STATISTICS", "EXPRESSION") in names,
        )

    def sql_object_properties(self, identity: SchemaObjectIdentity) -> ObjectPropertiesQueries:
        """Build conservative queries; the service refines them after discovery.

        Args:
            identity: Requested database, object name and kind.

        Returns:
            Queries with optional CHECK and generated-expression metadata unsupported.
        """
        return self._object_properties_queries(identity)

    def _object_properties_queries(
        self,
        identity: SchemaObjectIdentity,
        *,
        checks: bool = False,
        table_checks: bool = False,
        generated: bool = False,
        quoted_defaults: bool = False,
        ambiguous_defaults: bool = False,
        key_expressions: bool = False,
    ) -> ObjectPropertiesQueries:
        def literal(value: str) -> str:
            # Hex-encoded UTF-8 is independent of NO_BACKSLASH_ESCAPES and ANSI_QUOTES.
            return f"_utf8mb4 X'{value.encode('utf-8').hex()}'"

        kind = "'BASE TABLE'" if identity.kind == SchemaObjectKind.TABLE else "'VIEW'"
        scope = (
            f"t.TABLE_SCHEMA = {literal(identity.schema)} AND t.TABLE_NAME = {literal(identity.name)} "
            f"AND t.TABLE_TYPE = {kind}"
        )
        if identity.catalog is not None:
            scope += f" AND t.TABLE_CATALOG = {literal(identity.catalog)}"
        target = f"INFORMATION_SCHEMA.TABLES AS t WHERE {scope}"
        object_sql = (
            "SELECT t.TABLE_CATALOG AS catalog_name, t.TABLE_SCHEMA AS schema_name, "  # noqa: S608 - hex literals
            "t.TABLE_NAME AS object_name, 1 AS object_id, t.CREATE_TIME AS modify_date, "
            f"NULLIF(t.TABLE_COMMENT, '') AS description FROM {target}"
        )
        column_scope = "c.TABLE_SCHEMA = t.TABLE_SCHEMA AND c.TABLE_NAME = t.TABLE_NAME"
        generated_present = "c.EXTRA LIKE '%GENERATED%' AND c.EXTRA NOT LIKE '%DEFAULT_GENERATED%'"
        expression = "c.GENERATION_EXPRESSION" if generated else "NULL"
        default = "c.COLUMN_DEFAULT"
        if ambiguous_defaults:
            # Older MariaDB cannot distinguish a literal from an expression reliably.
            default = "NULL"
        elif not quoted_defaults:
            default = (
                "CASE WHEN c.EXTRA LIKE '%DEFAULT_GENERATED%' "
                "OR (c.DATA_TYPE IN ('timestamp', 'datetime') AND "
                "UPPER(c.COLUMN_DEFAULT) REGEXP '^CURRENT_TIMESTAMP([(][0-9]*[)])?$') "
                "OR (c.DATA_TYPE = 'bit' AND c.COLUMN_DEFAULT REGEXP '^b''[01]+''$') "
                "OR c.DATA_TYPE IN ('tinyint', 'smallint', 'mediumint', 'int', 'bigint', "
                "'decimal', 'float', 'double', 'year') THEN c.COLUMN_DEFAULT "
                "WHEN FIND_IN_SET('NO_BACKSLASH_ESCAPES', @@sql_mode) > 0 THEN "
                "CONCAT(CHAR(39), REPLACE(c.COLUMN_DEFAULT, CHAR(39), CONCAT(CHAR(39), CHAR(39))), CHAR(39)) "
                "ELSE QUOTE(c.COLUMN_DEFAULT) END"
            )
        columns_sql = (
            "SELECT 1 AS object_id, c.ORDINAL_POSITION AS column_id, c.COLUMN_NAME AS column_name, "  # noqa: S608
            "c.ORDINAL_POSITION AS ordinal_position, c.COLUMN_TYPE AS data_type, "
            "(c.IS_NULLABLE = 'YES') AS nullable, NULLIF(c.COLUMN_COMMENT, '') AS description, "
            "(c.COLUMN_DEFAULT IS NOT NULL) AS default_present, "
            f"{default} AS default_definition, (c.EXTRA LIKE '%auto_increment%') AS identity_present, "
            "CASE WHEN c.EXTRA LIKE '%auto_increment%' THEN 'AUTO_INCREMENT' END AS identity_definition, "
            f"({generated_present}) AS generated_present, {expression} AS generated_definition "
            "FROM INFORMATION_SCHEMA.TABLES AS t JOIN INFORMATION_SCHEMA.COLUMNS AS c "
            f"ON {column_scope} WHERE {scope} ORDER BY c.ORDINAL_POSITION"
        )
        key_expression = "CONCAT('(', s.EXPRESSION, ')')" if key_expressions else "NULL"
        key_part = (
            "CASE WHEN s.COLUMN_NAME IS NOT NULL THEN "
            "CONCAT('`', REPLACE(s.COLUMN_NAME, '`', '``'), '`', "
            "CASE WHEN s.SUB_PART IS NULL THEN '' ELSE CONCAT('(', s.SUB_PART, ')') END) "
            f"ELSE {key_expression} END"
        )
        constraints_sql = (
            "SELECT 1 AS object_id, tc.CONSTRAINT_NAME AS constraint_id, "  # noqa: S608 - hex literals
            "tc.CONSTRAINT_NAME AS constraint_name, "
            "CASE tc.CONSTRAINT_TYPE WHEN 'PRIMARY KEY' THEN 'primary_key' WHEN 'UNIQUE' THEN 'unique' "
            "WHEN 'FOREIGN KEY' THEN 'foreign_key' WHEN 'CHECK' THEN 'check' END AS constraint_kind, "
            "COALESCE(s.SEQ_IN_INDEX, k.ORDINAL_POSITION, 1) AS column_position, "
            "COALESCE(s.COLUMN_NAME, k.COLUMN_NAME) AS column_name, "
            "NULL AS definition, k.REFERENCED_TABLE_SCHEMA AS referenced_schema, "
            "k.REFERENCED_TABLE_NAME AS referenced_object, k.REFERENCED_COLUMN_NAME AS referenced_column, "
            f"{key_part} AS key_part "
            "FROM INFORMATION_SCHEMA.TABLES AS t JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc "
            "ON tc.TABLE_SCHEMA = t.TABLE_SCHEMA AND tc.TABLE_NAME = t.TABLE_NAME "
            "LEFT JOIN INFORMATION_SCHEMA.STATISTICS AS s ON tc.CONSTRAINT_TYPE IN ('PRIMARY KEY', 'UNIQUE') "
            "AND s.INDEX_SCHEMA = tc.CONSTRAINT_SCHEMA AND s.TABLE_SCHEMA = tc.TABLE_SCHEMA "
            "AND s.TABLE_NAME = tc.TABLE_NAME AND s.INDEX_NAME = tc.CONSTRAINT_NAME "
            "LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS k ON tc.CONSTRAINT_TYPE = 'FOREIGN KEY' "
            "AND k.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA "
            "AND k.TABLE_SCHEMA = tc.TABLE_SCHEMA AND k.TABLE_NAME = tc.TABLE_NAME "
            "AND k.CONSTRAINT_NAME = tc.CONSTRAINT_NAME "
            f"WHERE {scope} AND tc.CONSTRAINT_TYPE IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY'"
            + (")" if checks else ", 'CHECK')")
        )
        if checks:
            check_scope = "cc.CONSTRAINT_SCHEMA = t.TABLE_SCHEMA"
            if table_checks:
                check_scope += " AND cc.TABLE_NAME = t.TABLE_NAME"
            else:
                check_scope += (
                    " AND EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS ct "
                    "WHERE ct.TABLE_SCHEMA = t.TABLE_SCHEMA AND ct.TABLE_NAME = t.TABLE_NAME "
                    "AND ct.CONSTRAINT_SCHEMA = cc.CONSTRAINT_SCHEMA AND ct.CONSTRAINT_NAME = cc.CONSTRAINT_NAME "
                    "AND ct.CONSTRAINT_TYPE = 'CHECK')"
                )
            constraints_sql += (
                " UNION ALL SELECT 1, cc.CONSTRAINT_NAME, cc.CONSTRAINT_NAME, 'check', 1, NULL, "  # noqa: S608
                "cc.CHECK_CLAUSE, NULL, NULL, NULL, NULL FROM INFORMATION_SCHEMA.TABLES AS t "
                f"JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc ON {check_scope} WHERE {scope}"
            )
        constraints_sql += " ORDER BY constraint_kind, constraint_name, column_position"
        view = identity.kind == SchemaObjectKind.VIEW
        return ObjectPropertiesQueries(
            object_sql,
            columns_sql,
            constraints_sql,
            properties=None,
            description_property=None,
            object_description_state=MetadataState.UNSUPPORTED if view else None,
            column_description_state=MetadataState.UNSUPPORTED if view else None,
            check_constraints_state=MetadataState.AVAILABLE if checks else MetadataState.UNSUPPORTED,
            verify_catalog_rows=True,
        )
