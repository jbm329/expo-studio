import pytest

from expo_jbm329.db.dialects.ansi import AnsiDialect
from expo_jbm329.db.dialects.duckdb import DuckDbDialect
from expo_jbm329.db.dialects.mssql import MssqlDialect
from expo_jbm329.db.dialects.mysql import MySqlDialect
from expo_jbm329.db.dialects.postgres import PostgresDialect
from expo_jbm329.db.dialects.sqlite import SqliteDialect


def test_mssql_dialect():
    dialect = MssqlDialect()
    assert dialect.name == "mssql"

    # Limit
    sql = "SELECT * FROM t"
    limited = dialect.apply_limit(sql, 10)
    assert "TOP 10" in limited

    # Quoting
    assert dialect.quote_ident("table") == "[table]"

    # Qualify
    assert dialect.qualify("dbo", "table") == "[dbo].[table]"

    # Metadata SQL
    assert "information_schema.tables" in dialect.sql_list_tables().lower()
    assert "information_schema.views" in dialect.sql_list_views().lower()
    assert "information_schema.columns" in dialect.sql_list_columns("dbo", "t").lower()


def test_mysql_dialect():
    dialect = MySqlDialect()
    assert dialect.name == "mysql"

    # Limit
    sql = "SELECT * FROM t"
    limited = dialect.apply_limit(sql, 10)
    assert "LIMIT 10" in limited

    # Quoting
    assert dialect.quote_ident("table") == "`table`"

    # Qualify
    assert dialect.qualify("db", "table") == "`db`.`table`"

    # Metadata SQL
    assert "information_schema.tables" in dialect.sql_list_tables().lower()
    assert "table_type='base table'" in dialect.sql_list_tables().lower()


def test_sqlite_dialect():
    dialect = SqliteDialect()
    assert dialect.name == "sqlite"

    # Limit
    sql = "SELECT * FROM t"
    limited = dialect.apply_limit(sql, 10)
    assert "LIMIT 10" in limited

    # Quoting
    assert dialect.quote_ident("table") == '"table"'

    # Qualify (schema is always included when present, like other dialects)
    assert dialect.qualify("main", "table") == '"main"."table"'
    assert dialect.qualify("", "table") == '"table"'

    # Metadata SQL
    assert "sqlite_master" in dialect.sql_list_tables().lower()
    assert "type='table'" in dialect.sql_list_tables().lower()


def test_postgres_dialect():
    dialect = PostgresDialect()
    assert dialect.name == "postgresql"

    # Limit
    sql = "SELECT * FROM t"
    limited = dialect.apply_limit(sql, 10)
    assert limited == "SELECT * FROM t LIMIT 10"

    # Limit with already limited
    assert dialect.apply_limit("SELECT * FROM t LIMIT 5", 10) == "SELECT * FROM t LIMIT 5"
    assert dialect.apply_limit("UPDATE t SET x = 1", 10) == "UPDATE t SET x = 1"
    assert dialect.apply_limit("SELECT * FROM t", 0) == "SELECT * FROM t"

    # Quoting
    assert dialect.quote_ident("table") == '"table"'
    assert dialect.quote_ident('tab"le') == '"tab""le"'

    # Qualify
    assert dialect.qualify("public", "table") == '"public"."table"'
    assert dialect.qualify("", "table") == '"table"'

    # Metadata SQL
    tables_sql = dialect.sql_list_tables().lower()
    assert "information_schema.tables" in tables_sql
    assert "pg_catalog" in tables_sql
    assert "information_schema" in tables_sql

    views_sql = dialect.sql_list_views().lower()
    assert "information_schema.views" in views_sql
    assert "pg_catalog" in views_sql

    cols_sql = dialect.sql_list_columns("public", "my_table")
    assert "information_schema.columns" in cols_sql.lower()
    assert "'public'" in cols_sql
    assert "'my_table'" in cols_sql
    assert 'COLUMN_NAME AS "COLUMN_NAME"' in cols_sql
    assert 'DATA_TYPE AS "DATA_TYPE"' in cols_sql
    assert 'IS_NULLABLE AS "IS_NULLABLE"' in cols_sql

    all_cols_sql = dialect.sql_all_columns()
    assert all_cols_sql is not None
    assert "information_schema.columns" in all_cols_sql.lower()
    assert "pg_catalog" in all_cols_sql.lower()
    assert 'TABLE_SCHEMA AS "TABLE_SCHEMA"' in all_cols_sql
    assert 'TABLE_NAME AS "TABLE_NAME"' in all_cols_sql
    assert 'COLUMN_NAME AS "COLUMN_NAME"' in all_cols_sql


@pytest.mark.parametrize(
    ("dialect", "expected_keyword"),
    [
        (MssqlDialect(), "TOP"),
        (MySqlDialect(), "LIMIT"),
        (PostgresDialect(), "LIMIT"),
        (SqliteDialect(), "LIMIT"),
        (DuckDbDialect(), "LIMIT"),
        (AnsiDialect(), "FETCH FIRST"),
    ],
)
def test_limit_keyword(dialect, expected_keyword):
    assert dialect.limit_keyword == expected_keyword


@pytest.mark.parametrize(
    ("dialect", "raw", "expected"),
    [
        (MssqlDialect(), "a]b", "[a]]b]"),
        (MySqlDialect(), "a`b", "`a``b`"),
        (PostgresDialect(), 'a"b', '"a""b"'),
        (SqliteDialect(), 'a"b', '"a""b"'),
        (DuckDbDialect(), 'a"b', '"a""b"'),
        (AnsiDialect(), 'a"b', '"a""b"'),
    ],
)
def test_quote_ident_escapes_closing_quote(dialect, raw, expected):
    assert dialect.quote_ident(raw) == expected


@pytest.mark.parametrize(
    ("dialect", "schema", "expected"),
    [
        (MssqlDialect(), "dbo", "[dbo].[T].[C]"),
        (MySqlDialect(), "db", "`db`.`T`.`C`"),
        (PostgresDialect(), "public", '"public"."T"."C"'),
        (PostgresDialect(), "", '"T"."C"'),
        (SqliteDialect(), "main", '"main"."T"."C"'),
        (SqliteDialect(), "aux", '"aux"."T"."C"'),
        (DuckDbDialect(), "sales", '"sales"."T"."C"'),
        (DuckDbDialect(), "", '"T"."C"'),
        (AnsiDialect(), "public", '"public"."T"."C"'),
        (AnsiDialect(), "", '"T"."C"'),
    ],
)
def test_qualify_column(dialect, schema, expected):
    assert dialect.qualify_column(schema, "T", "C") == expected


def test_ansi_dialect():
    dialect = AnsiDialect()
    assert dialect.name == "ansi"
    assert dialect.qualify("public", "t") == '"public"."t"'

    assert dialect.apply_limit("SELECT * FROM t;", 5) == "SELECT * FROM t\nFETCH FIRST 5 ROWS ONLY"
    assert dialect.apply_limit("SELECT * FROM t LIMIT 3", 5) == "SELECT * FROM t LIMIT 3"
    assert dialect.apply_limit("UPDATE t SET a = 1", 5) == "UPDATE t SET a = 1"
    assert dialect.apply_limit("SELECT 1", 0) == "SELECT 1"

    assert "information_schema.tables" in dialect.sql_list_tables().lower()
    assert "information_schema.views" in dialect.sql_list_views().lower()
    assert "TABLE_NAME='o''x'" in dialect.sql_list_columns("s", "o'x")
    assert dialect.sql_all_columns() is not None


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM t LIMIT 5;",
        "SELECT * FROM t LIMIT 10%;",
        "SELECT * FROM t FETCH FIRST 5 ROWS ONLY",
        "UPDATE t SET x = 1",
    ],
)
def test_duckdb_limit_preserves_existing_limits_and_nonqueries(sql):
    assert DuckDbDialect().apply_limit(sql, 10) == sql


def test_duckdb_limit_invalid_and_multiple_statements():
    dialect = DuckDbDialect()
    assert dialect.apply_limit("", 10) == ""
    assert dialect.apply_limit("SELECT 1", 0) == "SELECT 1"
    assert dialect.apply_limit("SELECT * FROM t LIMIT ALL", 10) == "SELECT * FROM t LIMIT 10"
    with pytest.raises(ValueError, match="exactly one"):
        dialect.apply_limit("SELECT 1; SELECT 2", 10)


def test_duckdb_metadata_filters_and_literal_escaping():
    dialect = DuckDbDialect()
    for sql in (dialect.sql_list_tables(), dialect.sql_list_views(), dialect.sql_all_columns()):
        assert "table_catalog = current_database()" in sql
        assert "table_schema NOT IN ('information_schema', 'pg_catalog')" in sql
    columns = dialect.sql_list_columns("it's", "o'x")
    assert "table_schema = 'it''s'" in columns
    assert "table_name = 'o''x'" in columns
