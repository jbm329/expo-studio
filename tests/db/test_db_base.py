from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from expo_jbm329.db import base
from expo_jbm329.db.core.models import ConnectionConfig, SqlError, SqlResult


@pytest.fixture(autouse=True)
def clear_base_cache():
    with patch.dict(base._services, {}, clear=True):
        yield


def test_configure_timeouts():
    base.configure_timeouts(login_timeout_s=15, query_timeout_s=45)

    assert base._login_timeout_s == 15
    assert base._query_timeout_s == 45

    with pytest.raises(ValueError):
        base.configure_timeouts(login_timeout_s=-1)


def test_build_connection_config_sqlite():
    with patch("expo_jbm329.db.base.read_connections") as mock_read:
        mock_read.return_value = {"my_sqlite": {"name": "my_sqlite", "db_type": "sqlite", "database": "test.db"}}

        cfg = base._build_connection_config("my_sqlite")

    assert cfg.name == "my_sqlite"
    assert cfg.engine == "sqlite"
    assert cfg.protocol == "sqlite"
    assert cfg.database == "test.db"


def test_build_connection_config_duckdb():
    with patch(
        "expo_jbm329.db.base.read_connections", return_value={"duck": {"db_type": "DuCkDb", "database": "data.duckdb"}}
    ):
        cfg = base._build_connection_config("duck")

    assert cfg.engine == "duckdb"
    assert cfg.protocol == "duckdb"
    assert cfg.database == "data.duckdb"
    assert cfg.odbc_connect is None
    assert base._registry.create_driver("duckdb") is not None


def test_duckdb_form_validation_does_not_open_file(tmp_path):
    path = tmp_path / "data.duckdb"
    path.touch()
    with patch("expo_jbm329.db.drivers.sa_duckdb.create_engine") as create:
        assert base.validate_duckdb_connection(str(path)) is None
        assert base.validate_duckdb_connection(str(path), protocol="sqlite").message == base.TR_INVALID_CONFIG_DUCKDB
        assert (
            base.validate_duckdb_connection(str(path), extra={"read_only": False}).message
            == base.TR_INVALID_CONFIG_DUCKDB
        )
        assert base.validate_duckdb_connection(str(tmp_path / "missing.duckdb")).category == "connection"
    create.assert_not_called()


@pytest.mark.parametrize(
    ("engine", "protocol"),
    [("duckdb", "sqlite"), ("duckdb", "odbc"), ("sqlite", "duckdb")],
)
def test_duckdb_rejects_mismatched_protocol(engine, protocol):
    with patch(
        "expo_jbm329.db.base.read_connections",
        return_value={"duck": {"db_type": engine, "protocol": protocol}},
    ):
        result = base.execute_sql_safe("duck", "SELECT 1")

    assert not result.ok
    assert result.error.category == "connection"
    assert result.error.hint == base.TR_INVALID_CONFIG_DUCKDB


def test_build_connection_config_mysql():
    with patch("expo_jbm329.db.base.read_connections") as mock_read:
        mock_read.return_value = {
            "my_mysql": {
                "name": "my_mysql",
                "db_type": "mysql",
                "protocol": "pymysql",
                "server": "localhost",
                "user": "root",
            }
        }

        cfg = base._build_connection_config("my_mysql")

    assert cfg.engine == "mysql"
    assert cfg.protocol == "pymysql"
    assert cfg.server == "localhost"


def test_build_connection_config_postgresql():
    with patch("expo_jbm329.db.base.read_connections") as mock_read:
        mock_read.return_value = {
            "my_pg": {
                "name": "my_pg",
                "db_type": "postgresql",
                "server": "localhost",
                "port": "5432",
                "database": "test_db",
                "user": "postgres",
                "password": "secret",
            }
        }

        cfg = base._build_connection_config("my_pg")

    assert cfg.engine == "postgresql"
    assert cfg.protocol == "psycopg"
    assert cfg.server == "localhost"
    assert cfg.port == 5432
    assert cfg.database == "test_db"


def test_build_connection_config_postgresql_legacy_fallback():
    with patch("expo_jbm329.db.base.read_connections") as mock_read:
        mock_read.return_value = {
            "legacy_pg": {
                "name": "legacy_pg",
                "db_type": "postgresql",
                "protocol": "psycopg2",
                "server": "localhost",
            }
        }

        cfg = base._build_connection_config("legacy_pg")

    assert cfg.engine == "postgresql"
    assert cfg.protocol == "psycopg"


def test_driver_registry_postgresql_psycopg_only():
    assert base._registry.create_driver("psycopg") is not None
    with pytest.raises(KeyError):
        base._registry.create_driver("psycopg2")


@patch("expo_jbm329.db.base.read_connections")
def test_get_service_caching(mock_read_connections):
    mock_read_connections.return_value = {
        "test_conn": {"name": "test_conn", "db_type": "sqlite", "database": ":memory:"}
    }

    service1, cfg1 = base._get_service_with_config("test_conn")
    service2, cfg2 = base._get_service_with_config("test_conn")

    assert "test_conn" in base._services
    assert service1 is service2
    assert cfg1 is cfg2


@patch("expo_jbm329.db.base.read_connections")
def test_close_connection(mock_read_connections):
    mock_read_connections.return_value = {
        "test_conn": {"name": "test_conn", "db_type": "sqlite", "database": ":memory:"}
    }

    service, _ = base._get_service_with_config("test_conn")
    service.dispose = MagicMock()

    base.close_connection("test_conn")

    assert "test_conn" not in base._services
    service.dispose.assert_called_once()


@patch("expo_jbm329.db.base._get_service_with_config")
def test_execute_sql_safe(mock_get_svc_cfg):
    mock_service = MagicMock()
    mock_cfg = ConnectionConfig(name="test", engine="sqlite", protocol="sqlite")
    expected_result = SqlResult(ok=True)
    mock_service.execute_sql.return_value = expected_result
    mock_get_svc_cfg.return_value = (mock_service, mock_cfg)

    result = base.execute_sql_safe("test", "SELECT 1")

    assert result == expected_result
    mock_service.execute_sql.assert_called_once_with(
        mock_cfg,
        "SELECT 1",
        top_n=None,
        corr_id=None,
        cancel_cb=None,
        job_id=None,
    )


def test_execute_sql_safe_initialization_failure():
    with patch("expo_jbm329.db.base._build_connection_config", side_effect=RuntimeError("Config missing")):
        result = base.execute_sql_safe("nonexistent", "SELECT 1")

    assert result.ok is False
    assert result.error == SqlError(
        category="connection",
        code=None,
        message=base.TR_COULD_NOT_INIT_CONN,
        hint="Config missing",
    )


def test_list_tables_failure():
    with (
        patch("expo_jbm329.db.base._get_service_with_config", side_effect=Exception("Service fail")),
        pytest.raises(Exception, match="Service fail"),
    ):
        base.list_tables("broken_conn")


def test_fetch_df_returns_none_on_failure():
    with patch("expo_jbm329.db.base.execute_sql_safe", return_value=SqlResult(ok=False, data=None)):
        assert base.fetch_df("conn", "SELECT 1") is None


@pytest.mark.parametrize(
    ("db_type", "expected_name"),
    [
        ("mssql", "mssql"),
        ("mysql", "mysql"),
        ("mariadb", "mysql"),
        ("sqlite", "sqlite"),
        ("duckdb", "duckdb"),
        ("postgresql", "postgresql"),
        ("postgres", "postgresql"),
        ("oracle", "ansi"),
    ],
)
def test_get_dialect_resolves_from_config(db_type, expected_name):
    with patch("expo_jbm329.db.base.read_connections", return_value={"c": {"db_type": db_type}}):
        dialect = base.get_dialect("c")

    assert dialect.name == expected_name
    assert "c" not in base._services


def test_get_dialect_falls_back_to_ansi_for_missing_config():
    with patch("expo_jbm329.db.base.read_connections", return_value={}):
        dialect = base.get_dialect("missing")

    assert dialect.name == "ansi"
    assert dialect.qualify("dbo", "T") == '"dbo"."T"'


def test_get_dialect_falls_back_to_ansi_when_config_unreadable():
    with patch("expo_jbm329.db.base.read_connections", side_effect=OSError("locked")):
        assert base.get_dialect("c").name == "ansi"


def test_get_dialect_prefers_cached_service_dialect():
    service = MagicMock()
    base._services["cached"] = (service, MagicMock())

    with patch("expo_jbm329.db.base.read_connections") as mock_read:
        assert base.get_dialect("cached") is service.dialect

    mock_read.assert_not_called()


@pytest.mark.parametrize(
    ("db_type", "expected_star", "expected_distinct"),
    [
        ("mysql", "SELECT * FROM `s`.`t`", "SELECT DISTINCT `c`\nFROM `s`.`t`"),
        ("postgresql", 'SELECT * FROM "s"."t"', 'SELECT DISTINCT "c"\nFROM "s"."t"'),
        ("duckdb", 'SELECT * FROM "s"."t"', 'SELECT DISTINCT "c"\nFROM "s"."t"'),
    ],
)
def test_select_builders_fallback_is_dialect_aware(db_type, expected_star, expected_distinct):
    with (
        patch("expo_jbm329.db.base._get_service_with_config", side_effect=RuntimeError("init failed")),
        patch("expo_jbm329.db.base.read_connections", return_value={"c": {"db_type": db_type}}),
    ):
        assert base.build_select_star("c", "s", "t") == expected_star
        assert base.build_select_distinct("c", "s", "t", "c") == expected_distinct


@pytest.mark.parametrize(
    ("db_type", "expected"),
    [("mssql", True), ("mysql", True), ("postgresql", True), ("sqlite", False)],
)
def test_supports_bulk_column_listing(db_type, expected):
    with patch("expo_jbm329.db.base.read_connections", return_value={"c": {"db_type": db_type}}):
        assert base.supports_bulk_column_listing("c") is expected

    assert "c" not in base._services
