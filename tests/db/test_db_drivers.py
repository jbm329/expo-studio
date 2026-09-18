from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from expo_jbm329.db.core.di import ServiceRegistry
from expo_jbm329.db.core.models import ConnectionConfig
from expo_jbm329.db.drivers.sa_mysql import SqlAlchemyMySqlDriver
from expo_jbm329.db.drivers.sa_odbc import SqlAlchemyOdbcDriver
from expo_jbm329.db.drivers.sa_sqlite import SqlAlchemySqliteDriver


def test_service_registry_register_and_create():
    registry = ServiceRegistry()

    registry.register_driver("sqlite", lambda: "driver")
    registry.register_dialect("sqlite", lambda: "dialect")

    assert registry.create_driver("sqlite") == "driver"
    assert registry.create_dialect("sqlite") == "dialect"


def test_service_registry_rejects_invalid_registration():
    registry = ServiceRegistry()

    with pytest.raises(ValueError):
        registry.register_driver("", lambda: "driver")

    with pytest.raises(ValueError):
        registry.register_dialect("sqlite", None)  # type: ignore[arg-type]


def test_sqlite_driver_reuses_engine_and_executes_df():
    driver = SqlAlchemySqliteDriver()
    driver.initialize(timeouts={"login_timeout_s": 7})
    cfg = ConnectionConfig(name="db", engine="sqlite", protocol="sqlite", database=":memory:")
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = object()

    with patch("expo_jbm329.db.drivers.sa_sqlite.create_engine", return_value=engine) as mock_create, \
         patch("expo_jbm329.db.drivers.sa_sqlite.pd.read_sql", return_value=pd.DataFrame({"x": [1]})) as mock_read:
        df = driver.execute_df(cfg, "SELECT 1")
        df2 = driver.execute_df(cfg, "SELECT 1")

    assert len(df) == 1
    assert df.equals(df2)
    mock_create.assert_called_once()
    mock_read.assert_called()


def test_mysql_driver_builds_url_and_connect_args():
    driver = SqlAlchemyMySqlDriver("pymysql")
    driver.initialize(timeouts={"login_timeout_s": 5})
    driver.set_query_timeout(9)
    cfg = ConnectionConfig(
        name="db",
        engine="mysql",
        protocol="pymysql",
        server="localhost",
        port=3307,
        database="sample",
        user="user",
        password="secret",
    )
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = object()

    with patch("expo_jbm329.db.drivers.sa_mysql.create_engine", return_value=engine) as mock_create, \
         patch("expo_jbm329.db.drivers.sa_mysql.pd.read_sql", return_value=pd.DataFrame({"x": [1]})):
        driver.execute_df(cfg, "SELECT 1")

    _, kwargs = mock_create.call_args
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["connect_args"]["connect_timeout"] == 5
    assert kwargs["connect_args"]["read_timeout"] == 9
    assert kwargs["connect_args"]["write_timeout"] == 9


def test_odbc_driver_cancels_and_executes_df():
    driver = SqlAlchemyOdbcDriver()
    driver.set_query_timeout(3)
    cfg = ConnectionConfig(name="db", engine="mssql", protocol="odbc")
    cursor = MagicMock()
    cursor.description = [("id",)]
    cursor.fetchall.return_value = [(1,)]
    raw_conn = MagicMock()
    raw_conn.cursor.return_value = cursor
    engine = MagicMock()
    engine.raw_connection.return_value = raw_conn

    with patch("expo_jbm329.db.drivers.sa_odbc.create_engine", return_value=engine), \
         patch("expo_jbm329.db.drivers.sa_odbc.time.sleep", side_effect=RuntimeError("stop")):
        df = driver.execute_df(cfg, "SELECT 1", job_id="job-1")

    assert list(df.columns) == ["id"]
    assert driver.cancel_execution("job-1") is False

