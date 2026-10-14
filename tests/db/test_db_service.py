from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from expo_jbm329.db.core.errors import BulkColumnListingNotSupportedError
from expo_jbm329.db.core.interfaces import DialectProtocol, DriverProtocol
from expo_jbm329.db.core.models import ConnectionConfig, SqlError, TimeoutConfig
from expo_jbm329.db.dialects.postgres import PostgresDialect
from expo_jbm329.db.service import DbService


@pytest.fixture
def mock_driver():
    return MagicMock(spec=DriverProtocol)


@pytest.fixture
def mock_dialect():
    dialect = MagicMock(spec=DialectProtocol)
    dialect.name = "test_dialect"
    dialect.apply_limit.side_effect = lambda sql, n: f"{sql} LIMIT {n}"
    dialect.qualify.side_effect = lambda schema, obj: f"{schema}.{obj}"
    dialect.quote_ident.side_effect = lambda ident: f"[{ident}]"
    dialect.sql_list_tables.return_value = "SELECT * FROM sys.tables"
    dialect.sql_list_views.return_value = "SELECT * FROM sys.views"
    dialect.sql_list_columns.return_value = "SELECT * FROM sys.columns"
    return dialect


@pytest.fixture
def conn_config():
    return ConnectionConfig(name="test_conn", engine="sqlite", protocol="sqlite")


@pytest.fixture
def db_service(mock_driver, mock_dialect):
    return DbService(driver=mock_driver, dialect=mock_dialect)


def test_db_service_init(mock_driver, mock_dialect):
    timeouts = TimeoutConfig(login_timeout_s=5, query_timeout_s=10)

    service = DbService(driver=mock_driver, dialect=mock_dialect, timeouts=timeouts)

    mock_driver.initialize.assert_called_once_with(timeouts={"login_timeout_s": 5})
    mock_driver.set_query_timeout.assert_called_once_with(10)
    assert service.allow_exec is True


def test_execute_sql_success(db_service, mock_driver, conn_config):
    df_expected = pd.DataFrame({"col1": [1, 2]})
    mock_driver.execute_df.return_value = df_expected

    result = db_service.execute_sql(conn_config, "SELECT * FROM table")

    assert result.ok is True
    assert result.data.equals(df_expected)
    assert result.rows == 2
    assert result.error is None
    mock_driver.execute_df.assert_called_once()


def test_execute_sql_empty_query(db_service, conn_config):
    result = db_service.execute_sql(conn_config, "")

    assert result.ok is False
    assert result.error.category == "syntax"


def test_execute_sql_unsupported_kind(db_service, conn_config):
    result = db_service.execute_sql(conn_config, "DROP TABLE x")

    assert result.ok is False
    assert result.error.category == "unsupported"


def test_execute_sql_exec_disabled(mock_driver, mock_dialect, conn_config):
    service = DbService(driver=mock_driver, dialect=mock_dialect, allow_exec=False)

    result = service.execute_sql(conn_config, "EXEC my_proc")

    assert result.ok is False
    assert result.error.category == "unsupported"


def test_execute_sql_with_limit(db_service, mock_driver, mock_dialect, conn_config):
    df_expected = pd.DataFrame({"col1": [1]})
    mock_driver.execute_df.return_value = df_expected

    result = db_service.execute_sql(conn_config, "SELECT * FROM table", top_n=1)

    mock_dialect.apply_limit.assert_called_once_with("SELECT * FROM table", 1)
    mock_driver.execute_df.assert_called_once_with(
        conn_config,
        "SELECT * FROM table LIMIT 1",
        job_id=None,
        cancel_cb=None,
        corr_id=None,
    )
    assert result.ok is True


def test_execute_sql_fallback_limit(db_service, mock_driver, mock_dialect, conn_config):
    mock_dialect.apply_limit.side_effect = lambda sql, n: sql
    mock_driver.execute_df.return_value = pd.DataFrame({"col1": [1, 2, 3]})

    result = db_service.execute_sql(conn_config, "SELECT * FROM table", top_n=2)

    assert result.ok is True
    assert len(result.data) == 2
    assert result.rows == 2


def test_execute_sql_failure(db_service, mock_driver, conn_config):
    mock_driver.execute_df.side_effect = Exception("DB Error")
    db_service._classify_error = MagicMock(return_value=SqlError("unknown", None, "Fel"))

    result = db_service.execute_sql(conn_config, "SELECT * FROM table")

    assert result.ok is False
    assert result.error.category == "unknown"


@pytest.mark.parametrize(
    ("engine", "message", "expected_code"),
    [
        ("mssql", "Ambiguous column name 'id'. (209)", 209),
        ("mysql", "(1052, \"Column 'id' in field list is ambiguous\")", 1052),
        ("mariadb", "(1052, \"Column 'id' in field list is ambiguous\")", 1052),
        ("sqlite", "ambiguous column name: id", None),
        ("postgresql", 'column reference "id" is ambiguous SQLSTATE 42702', 42702),
        ("oracle", "ORA-00918: column ambiguously defined", 918),
    ],
)
def test_execute_sql_classifies_ambiguity_by_connection_engine(
    mock_driver,
    mock_dialect,
    engine,
    message,
    expected_code,
):
    mock_dialect.name = "ansi"
    mock_driver.execute_df.side_effect = Exception(message)
    service = DbService(driver=mock_driver, dialect=mock_dialect)
    connection = ConnectionConfig(name="test", engine=engine, protocol="odbc")

    result = service.execute_sql(connection, "SELECT id FROM a JOIN b ON a.id = b.id")

    assert result.ok is False
    assert result.error is not None
    assert result.error.category == "ambiguous_column"
    assert result.error.code == expected_code


def test_list_tables(db_service, mock_driver, mock_dialect, conn_config):
    df_tables = pd.DataFrame({"schema_name": ["dbo", "dbo"], "object_name": ["t1", "t2"]})
    mock_driver.execute_df.return_value = df_tables

    tables = db_service.list_tables(conn_config)

    assert tables == [{"schema": "dbo", "name": "t1"}, {"schema": "dbo", "name": "t2"}]


def test_list_columns(db_service, mock_driver, conn_config):
    df_cols = pd.DataFrame({
        "COLUMN_NAME": ["id", "name"],
        "DATA_TYPE": ["int", "varchar"],
        "IS_NULLABLE": ["NO", "YES"],
    })
    mock_driver.execute_df.return_value = df_cols

    columns = db_service.list_columns(conn_config, "dbo", "table1")

    assert columns[0]["COLUMN_NAME"] == "id"
    assert columns[1]["IS_NULLABLE"] == "YES"


def test_list_tables_sql_failure(db_service, mock_driver):
    mock_driver.execute_df.side_effect = Exception("Login failed")
    db_service._classify_error = MagicMock(
        return_value=SqlError("connection", 18456, "Login failed", "Check credentials")
    )

    with pytest.raises(RuntimeError, match="Login failed"):
        db_service.list_tables(ConnectionConfig(name="test", engine="sqlite", protocol="sqlite"))


def test_build_select_columns_auto(db_service, mock_driver, conn_config):
    df_cols = pd.DataFrame({
        "COLUMN_NAME": ["id", "name"],
        "DATA_TYPE": ["int", "varchar"],
        "IS_NULLABLE": ["NO", "YES"],
    })
    mock_driver.execute_df.return_value = df_cols

    sql = db_service.build_select_columns_auto(conn_config, "dbo", "table1")

    assert "SELECT" in sql
    assert "[id]" in sql
    assert "[name]" in sql
    assert "FROM dbo.table1" in sql
    assert "    [id],\n    [name]" in sql


@pytest.mark.parametrize("stmt", [None, ""])
def test_list_all_columns_map_unsupported_dialect_runs_no_sql(db_service, mock_driver, mock_dialect, conn_config, stmt):
    mock_dialect.sql_all_columns.return_value = stmt

    with pytest.raises(BulkColumnListingNotSupportedError):
        db_service.list_all_columns_map(conn_config)

    mock_driver.execute_df.assert_not_called()


def test_list_all_columns_map_unsupported_error_is_attribute_error():
    assert issubclass(BulkColumnListingNotSupportedError, AttributeError)


@pytest.mark.parametrize(
    "columns",
    [
        {"COLUMN_NAME": ["id", "name"], "DATA_TYPE": ["int", "text"], "IS_NULLABLE": ["NO", "YES"]},
        {"column_name": ["id", "name"], "data_type": ["int", "text"], "is_nullable": ["NO", "YES"]},
        {"Column_Name": ["id", "name"], "Data_Type": ["int", "text"], "Is_Nullable": ["NO", "YES"]},
    ],
)
def test_list_columns_case_resilient(db_service, mock_driver, conn_config, columns):
    mock_driver.execute_df.return_value = pd.DataFrame(columns)

    cols = db_service.list_columns(conn_config, "public", "users")

    assert len(cols) == 2
    assert cols[0]["COLUMN_NAME"] == "id"
    assert cols[0]["DATA_TYPE"] == "int"
    assert cols[0]["IS_NULLABLE"] == "NO"
    assert cols[1]["COLUMN_NAME"] == "name"
    assert cols[1]["DATA_TYPE"] == "text"
    assert cols[1]["IS_NULLABLE"] == "YES"


@pytest.mark.parametrize(
    "columns",
    [
        {
            "TABLE_SCHEMA": ["public"],
            "TABLE_NAME": ["users"],
            "COLUMN_NAME": ["id"],
            "DATA_TYPE": ["int"],
            "IS_NULLABLE": ["NO"],
        },
        {
            "table_schema": ["public"],
            "table_name": ["users"],
            "column_name": ["id"],
            "data_type": ["int"],
            "is_nullable": ["NO"],
        },
    ],
)
def test_list_all_columns_map_case_resilient(mock_driver, columns):
    dialect = PostgresDialect()
    service = DbService(driver=mock_driver, dialect=dialect)
    mock_driver.execute_df.return_value = pd.DataFrame(columns)
    conn = ConnectionConfig(name="pg", engine="postgresql", protocol="psycopg")

    cols_map = service.list_all_columns_map(conn)

    assert ("public", "users") in cols_map
    assert cols_map[("public", "users")][0]["COLUMN_NAME"] == "id"


def test_build_select_columns_auto_postgres(mock_driver):
    dialect = PostgresDialect()
    service = DbService(driver=mock_driver, dialect=dialect)
    mock_driver.execute_df.return_value = pd.DataFrame({
        "column_name": ["id", "username"],
        "data_type": ["integer", "text"],
        "is_nullable": ["NO", "YES"],
    })
    conn = ConnectionConfig(name="pg", engine="postgresql", protocol="psycopg")

    # Double-click style (with_schema=False, top_n=1000)
    sql_double_click = service.build_select_columns_auto(conn, "public", "users", top_n=1000, with_schema=False)
    assert sql_double_click == 'SELECT\n    "id",\n    "username"\nFROM "public"."users" LIMIT 1000'

    # Context menu style (with_schema=True, top_n=1000)
    sql_with_schema = service.build_select_columns_auto(conn, "public", "users", top_n=1000, with_schema=True)
    assert sql_with_schema == (
        'SELECT\n    "public"."users"."id",\n    "public"."users"."username"\nFROM "public"."users" LIMIT 1000'
    )

    # Context menu SELECT *
    sql_star = service.build_select_star("public", "users", top_n=1000)
    assert sql_star == 'SELECT *\nFROM "public"."users" LIMIT 1000'
