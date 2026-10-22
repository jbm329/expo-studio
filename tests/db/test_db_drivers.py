from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from expo_jbm329.db.core.di import ServiceRegistry
from expo_jbm329.db.core.models import ConnectionConfig
from expo_jbm329.db.drivers.sa_duckdb import SqlAlchemyDuckDbDriver
from expo_jbm329.db.drivers.sa_mysql import SqlAlchemyMySqlDriver
from expo_jbm329.db.drivers.sa_odbc import SqlAlchemyOdbcDriver
from expo_jbm329.db.drivers.sa_postgres import SqlAlchemyPostgresDriver
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
        registry.register_dialect("sqlite", None)


def test_sqlite_driver_reuses_engine_and_executes_df():
    driver = SqlAlchemySqliteDriver()
    driver.initialize(timeouts={"login_timeout_s": 7})
    cfg = ConnectionConfig(name="db", engine="sqlite", protocol="sqlite", database=":memory:")
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = object()

    with (
        patch("expo_jbm329.db.drivers.sa_sqlite.create_engine", return_value=engine) as mock_create,
        patch("expo_jbm329.db.drivers.sa_sqlite.pd.read_sql", return_value=pd.DataFrame({"x": [1]})) as mock_read,
    ):
        df = driver.execute_df(cfg, "SELECT 1")
        df2 = driver.execute_df(cfg, "SELECT 1")

    assert len(df) == 1
    assert df.equals(df2)
    mock_create.assert_called_once()
    mock_read.assert_called()


@pytest.mark.parametrize("driver_name", ["pymysql", "mysqlconnector"])
def test_mysql_driver_builds_url_and_connect_args(driver_name):
    driver = SqlAlchemyMySqlDriver(driver_name)
    driver.initialize(timeouts={"login_timeout_s": 5})
    driver.set_query_timeout(9)
    cfg = ConnectionConfig(
        name="db",
        engine="mysql",
        protocol=driver_name,
        server="localhost",
        port=3307,
        database="sample",
        user="user",
        password="secret",
    )
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = object()

    with (
        patch("expo_jbm329.db.drivers.sa_mysql.create_engine", return_value=engine) as mock_create,
        patch("expo_jbm329.db.drivers.sa_mysql.pd.read_sql", return_value=pd.DataFrame({"x": [1]})),
    ):
        df = driver.execute_df(cfg, "SELECT 1")

    assert len(df) == 1
    call_args, kwargs = mock_create.call_args
    url = call_args[0]
    assert url.drivername == f"mysql+{driver_name}"
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["connect_args"]["connect_timeout"] == 5
    assert kwargs["connect_args"]["read_timeout"] == 9
    assert kwargs["connect_args"]["write_timeout"] == 9
    if driver_name == "mysqlconnector":
        assert kwargs["connect_args"]["use_pure"] is True
    else:
        assert "use_pure" not in kwargs["connect_args"]


@pytest.mark.parametrize(
    ("extra_val", "expected_pure"),
    [
        (False, False),
        ("false", False),
        ("0", False),
        (True, True),
        ("true", True),
    ],
)
def test_mysql_driver_use_pure_extra_override(extra_val, expected_pure):
    driver = SqlAlchemyMySqlDriver("mysqlconnector")
    cfg = ConnectionConfig(
        name="db",
        engine="mysql",
        protocol="mysqlconnector",
        extra={"use_pure": extra_val},
    )
    engine = MagicMock()
    with patch("expo_jbm329.db.drivers.sa_mysql.create_engine", return_value=engine) as mock_create:
        driver._get_engine(cfg)
    _, kwargs = mock_create.call_args
    assert kwargs["connect_args"]["use_pure"] is expected_pure


def test_mysql_driver_pymysql_ignores_use_pure_extra():
    driver = SqlAlchemyMySqlDriver("pymysql")
    cfg = ConnectionConfig(
        name="db",
        engine="mysql",
        protocol="pymysql",
        extra={"use_pure": True},
    )
    engine = MagicMock()
    with patch("expo_jbm329.db.drivers.sa_mysql.create_engine", return_value=engine) as mock_create:
        driver._get_engine(cfg)
    _, kwargs = mock_create.call_args
    assert "use_pure" not in kwargs["connect_args"]


def test_mysql_driver_mariadb_url_dialect():
    driver = SqlAlchemyMySqlDriver("mysqlconnector")
    cfg = ConnectionConfig(
        name="mariadb_conn",
        engine="mariadb",
        protocol="mysqlconnector",
        server="127.0.0.1",
        port=3306,
        database="testdb",
    )
    url = driver._url_for(cfg)
    assert url.drivername == "mariadb+mysqlconnector"
    assert url.host == "127.0.0.1"


def test_mysql_driver_create_engine_failure_logs_and_raises():
    driver = SqlAlchemyMySqlDriver("pymysql")
    cfg = ConnectionConfig(
        name="failed_db",
        engine="mysql",
        protocol="pymysql",
    )
    with (
        patch(
            "expo_jbm329.db.drivers.sa_mysql.create_engine",
            side_effect=ModuleNotFoundError("No module named 'pymysql'"),
        ),
        pytest.raises(ModuleNotFoundError, match="No module named 'pymysql'"),
    ):
        driver._get_engine(cfg)


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

    with (
        patch("expo_jbm329.db.drivers.sa_odbc.create_engine", return_value=engine),
        patch("expo_jbm329.db.drivers.sa_odbc.time.sleep", side_effect=RuntimeError("stop")),
    ):
        df = driver.execute_df(cfg, "SELECT 1", job_id="job-1")

    assert list(df.columns) == ["id"]
    assert driver.cancel_execution("job-1") is False


def test_postgres_driver_builds_url_and_connect_args():
    driver = SqlAlchemyPostgresDriver()
    driver.initialize(timeouts={"login_timeout_s": 5})
    driver.set_query_timeout(9)
    cfg = ConnectionConfig(
        name="pg_db",
        engine="postgresql",
        protocol="psycopg",
        server="localhost",
        port=5432,
        database="sample",
        user="user",
        password="secret",
    )
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = object()

    with (
        patch("expo_jbm329.db.drivers.sa_postgres.create_engine", return_value=engine) as mock_create,
        patch("expo_jbm329.db.drivers.sa_postgres.pd.read_sql", return_value=pd.DataFrame({"x": [1]})),
    ):
        df = driver.execute_df(cfg, "SELECT 1")

    assert len(df) == 1
    call_args, kwargs = mock_create.call_args
    url = call_args[0]
    assert url.drivername == "postgresql+psycopg"
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["connect_args"]["connect_timeout"] == 5
    assert kwargs["connect_args"]["options"] == "-c statement_timeout=9000"


def test_postgres_driver_reuses_engine_and_disposes():
    driver = SqlAlchemyPostgresDriver()
    cfg = ConnectionConfig(name="pg_db", engine="postgresql", protocol="psycopg", database="sample")
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = object()

    with (
        patch("expo_jbm329.db.drivers.sa_postgres.create_engine", return_value=engine) as mock_create,
        patch("expo_jbm329.db.drivers.sa_postgres.pd.read_sql", return_value=pd.DataFrame({"x": [1]})),
    ):
        df1 = driver.execute_df(cfg, "SELECT 1")
        df2 = driver.execute_df(cfg, "SELECT 1")

    assert len(df1) == 1
    assert df1.equals(df2)
    mock_create.assert_called_once()

    driver.dispose()
    engine.dispose.assert_called_once()
    assert len(driver._engines) == 0


def test_postgres_driver_create_engine_failure_logs_and_raises():
    driver = SqlAlchemyPostgresDriver()
    cfg = ConnectionConfig(name="failed_pg", engine="postgresql", protocol="psycopg")
    with (
        patch(
            "expo_jbm329.db.drivers.sa_postgres.create_engine",
            side_effect=ModuleNotFoundError("No module named 'psycopg'"),
        ),
        pytest.raises(ModuleNotFoundError, match="No module named 'psycopg'"),
    ):
        driver._get_engine(cfg)


def test_postgres_driver_cancel_execution():
    driver = SqlAlchemyPostgresDriver()
    assert driver.cancel_execution("job-pg-1") is False


def test_duckdb_driver_reuses_engine_enforces_read_only_and_disposes(tmp_path):
    from sqlalchemy.pool import NullPool

    path = tmp_path / "existing.duckdb"
    path.touch()
    cfg = ConnectionConfig(name="duck", engine="duckdb", protocol="duckdb", database=str(path))
    driver = SqlAlchemyDuckDbDriver()
    driver.initialize(timeouts={"login_timeout_s": 5})
    driver.set_query_timeout(9)
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = object()

    with (
        patch("expo_jbm329.db.drivers.sa_duckdb.create_engine", return_value=engine) as create,
        patch("expo_jbm329.db.drivers.sa_duckdb.pd.read_sql", return_value=pd.DataFrame({"x": [1]})),
    ):
        first = driver.execute_df(cfg, "SELECT 1", job_id="job", corr_id="correlation")
        second = driver.execute_df(cfg, "SELECT 1")

    assert first.equals(second)
    create.assert_called_once()
    args, kwargs = create.call_args
    assert args[0].drivername == "duckdb"
    assert args[0].database == str(path.resolve())
    assert kwargs["connect_args"] == {"read_only": True}
    assert kwargs["poolclass"] is NullPool
    assert driver.cancel_execution("job") is False
    driver.dispose()
    engine.dispose.assert_called_once()
    assert driver._engines == {}


def test_duckdb_driver_does_not_hide_engine_creation_failure(tmp_path):
    path = tmp_path / "existing.duckdb"
    path.touch()
    cfg = ConnectionConfig(name="duck", engine="duckdb", protocol="duckdb", database=str(path))
    with (
        patch("expo_jbm329.db.drivers.sa_duckdb.create_engine", side_effect=ModuleNotFoundError("duckdb_engine")),
        pytest.raises(ModuleNotFoundError, match="duckdb_engine"),
    ):
        SqlAlchemyDuckDbDriver().execute_df(cfg, "SELECT 1")
