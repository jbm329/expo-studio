from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from expo_jbm329.db.core.interfaces import DialectProtocol, DriverProtocol
from expo_jbm329.db.core.models import ConnectionConfig, SqlError, TimeoutConfig
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


def test_list_tables(db_service, mock_driver, mock_dialect, conn_config):
    df_tables = pd.DataFrame({"schema_name": ["dbo", "dbo"], "object_name": ["t1", "t2"]})
    mock_driver.execute_df.return_value = df_tables

    tables = db_service.list_tables(conn_config)

    assert tables == [{"schema": "dbo", "name": "t1"}, {"schema": "dbo", "name": "t2"}]


def test_list_columns(db_service, mock_driver, conn_config):
    df_cols = pd.DataFrame(
        {
            "COLUMN_NAME": ["id", "name"],
            "DATA_TYPE": ["int", "varchar"],
            "IS_NULLABLE": ["NO", "YES"],
        }
    )
    mock_driver.execute_df.return_value = df_cols

    columns = db_service.list_columns(conn_config, "dbo", "table1")

    assert columns[0]["COLUMN_NAME"] == "id"
    assert columns[1]["IS_NULLABLE"] == "YES"


def test_list_tables_sql_failure(db_service, mock_driver):
    mock_driver.execute_df.side_effect = Exception("Login failed")
    db_service._classify_error = MagicMock(return_value=SqlError("connection", 18456, "Login failed", "Check credentials"))

    with pytest.raises(RuntimeError, match="Login failed"):
        db_service.list_tables(ConnectionConfig(name="test", engine="sqlite", protocol="sqlite"))


def test_build_select_columns_auto(db_service, mock_driver, conn_config):
    df_cols = pd.DataFrame(
        {
            "COLUMN_NAME": ["id", "name"],
            "DATA_TYPE": ["int", "varchar"],
            "IS_NULLABLE": ["NO", "YES"],
        }
    )
    mock_driver.execute_df.return_value = df_cols

    sql = db_service.build_select_columns_auto(conn_config, "dbo", "table1")

    assert "SELECT" in sql
    assert "[id]" in sql
    assert "[name]" in sql
    assert "FROM dbo.table1" in sql
