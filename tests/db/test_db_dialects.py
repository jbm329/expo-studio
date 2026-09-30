import pytest

from expo_jbm329.db.dialects.ansi import AnsiDialect
from expo_jbm329.db.dialects.mssql import MssqlDialect
from expo_jbm329.db.dialects.mysql import MySqlDialect
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


@pytest.mark.parametrize(
    ("dialect", "expected_keyword"),
    [
        (MssqlDialect(), "TOP"),
        (MySqlDialect(), "LIMIT"),
        (SqliteDialect(), "LIMIT"),
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
        (SqliteDialect(), 'a"b', '"a""b"'),
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
        (SqliteDialect(), "main", '"main"."T"."C"'),
        (SqliteDialect(), "aux", '"aux"."T"."C"'),
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
