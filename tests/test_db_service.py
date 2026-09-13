import pytest
import pandas as pd
from unittest.mock import MagicMock
from expo_jbm329.db.service import DbService
from expo_jbm329.db.core.models import ConnectionConfig, TimeoutConfig, SqlResult, SqlError
from expo_jbm329.db.core.interfaces import DriverProtocol, DialectProtocol

@pytest.fixture
def mock_driver():
    driver = MagicMock(spec=DriverProtocol)
    return driver

@pytest.fixture
def mock_dialect():
    dialect = MagicMock(spec=DialectProtocol)
    dialect.name = "test_dialect"
    dialect.apply_limit.side_effect = lambda sql, n: f"{sql} LIMIT {n}"
    return dialect

@pytest.fixture
def db_service(mock_driver, mock_dialect):
    return DbService(driver=mock_driver, dialect=mock_dialect)

@pytest.fixture
def conn_config():
    return ConnectionConfig(name="test_conn", engine="sqlite", protocol="sqlite")

def test_db_service_init(mock_driver, mock_dialect):
    timeouts = TimeoutConfig(login_timeout_s=5, query_timeout_s=10)
    service = DbService(driver=mock_driver, dialect=mock_dialect, timeouts=timeouts)
    
    mock_driver.initialize.assert_called_once_with(timeouts={"login_timeout_s": 5})
    mock_driver.set_query_timeout.assert_called_once_with(10)
    assert service.allow_exec is True

def test_execute_sql_success(db_service, mock_driver, mock_dialect, conn_config):
    # Setup
    sql = "SELECT * FROM table"
    df_expected = pd.DataFrame({"col1": [1, 2]})
    mock_driver.execute_df.return_value = df_expected
    
    # Execute
    result = db_service.execute_sql(conn_config, sql)
    
    # Verify
    assert result.ok is True
    assert result.data.equals(df_expected)
    assert result.rows == 2
    assert result.error is None
    mock_driver.execute_df.assert_called_once_with(conn_config, sql)

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
    sql = "SELECT * FROM table"
    df_expected = pd.DataFrame({"col1": [1]})
    mock_driver.execute_df.return_value = df_expected
    
    # Execute with top_n
    result = db_service.execute_sql(conn_config, sql, top_n=1)
    
    # Verify limit injection
    mock_dialect.apply_limit.assert_called_once_with(sql, 1)
    mock_driver.execute_df.assert_called_once_with(conn_config, f"{sql} LIMIT 1")
    assert result.ok is True

def test_execute_sql_fallback_limit(db_service, mock_driver, mock_dialect, conn_config):
    # Dialect fails to apply limit (returns same SQL)
    mock_dialect.apply_limit.side_effect = lambda sql, n: sql
    sql = "SELECT * FROM table"
    df_full = pd.DataFrame({"col1": [1, 2, 3]})
    mock_driver.execute_df.return_value = df_full
    
    result = db_service.execute_sql(conn_config, sql, top_n=2)
    
    assert result.ok is True
    assert len(result.data) == 2  # Client-side limited
    assert result.rows == 2

def test_execute_sql_failure(db_service, mock_driver, conn_config):
    sql = "SELECT * FROM table"
    mock_driver.execute_df.side_effect = Exception("DB Error")
    
    # We need to mock _classify_error or ensure it doesn't crash
    db_service._classify_error = MagicMock(return_value=SqlError("unknown", None, "Fel"))
    
    result = db_service.execute_sql(conn_config, sql)
    
    assert result.ok is False
    assert result.error.category == "unknown"

def test_list_tables(db_service, mock_driver, mock_dialect, conn_config):
    mock_dialect.sql_list_tables.return_value = "SELECT * FROM sys.tables"
    df_tables = pd.DataFrame({"schema_name": ["dbo", "dbo"], "object_name": ["t1", "t2"]})
    mock_driver.execute_df.return_value = df_tables
    
    tables = db_service.list_tables(conn_config)
    
    assert len(tables) == 2
    assert tables[0] == {"schema": "dbo", "name": "t1"}
    assert tables[1] == {"schema": "dbo", "name": "t2"}

def test_list_columns(db_service, mock_driver, mock_dialect, conn_config):
    mock_dialect.sql_list_columns.return_value = "SELECT * FROM sys.columns"
    df_cols = pd.DataFrame({
        "COLUMN_NAME": ["id", "name"],
        "DATA_TYPE": ["int", "varchar"],
        "IS_NULLABLE": ["NO", "YES"]
    })
    mock_driver.execute_df.return_value = df_cols
    
    columns = db_service.list_columns(conn_config, "dbo", "table1")
    
    assert len(columns) == 2
    assert columns[0]["COLUMN_NAME"] == "id"
    assert columns[1]["IS_NULLABLE"] == "YES"

def test_list_tables_sql_failure(db_service, mock_driver, mock_dialect, conn_config):
    mock_dialect.sql_list_tables.return_value = "SELECT 1"
    db_service._classify_error = MagicMock(return_value=SqlError("connection", 18456, "Login failed", "Check credentials"))
    mock_driver.execute_df.side_effect = Exception("Login failed")
    
    with pytest.raises(RuntimeError) as excinfo:
        db_service.list_tables(conn_config)
    
    assert "Login failed" in str(excinfo.value)
    assert "Check credentials" in str(excinfo.value)

def test_build_select_columns_auto(db_service, mock_driver, mock_dialect, conn_config):
    # Mock list_columns to return some columns
    mock_dialect.sql_list_columns.return_value = "SELECT * FROM metadata"
    df_cols = pd.DataFrame({
        "COLUMN_NAME": ["id", "name"],
        "DATA_TYPE": ["int", "varchar"],
        "IS_NULLABLE": ["NO", "YES"]
    })
    mock_driver.execute_df.return_value = df_cols
    mock_dialect.qualify.side_effect = lambda s, o: f"{s}.{o}"
    mock_dialect.quote_ident.side_effect = lambda i: f"[{i}]"
    
    sql = db_service.build_select_columns_auto(conn_config, "dbo", "table1")
    
    assert "SELECT" in sql
    assert "[id]" in sql
    assert "[name]" in sql
    assert "FROM dbo.table1" in sql
