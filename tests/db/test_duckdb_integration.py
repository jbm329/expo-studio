from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import duckdb
import pandas as pd
import pytest
from sqlalchemy import event
from sqlalchemy.exc import DBAPIError

from expo_jbm329.db import base
from expo_jbm329.db.core.errors import (
    TR_INVALID_CONFIG_DUCKDB,
    TR_LOCKED_HINT_DUCKDB,
    classify_duckdb,
)
from expo_jbm329.db.core.models import ConnectionConfig
from expo_jbm329.db.dialects.duckdb import DuckDbDialect
from expo_jbm329.db.drivers.sa_duckdb import SqlAlchemyDuckDbDriver
from expo_jbm329.db.service import DbService
from expo_jbm329.db.sql_analysis import format_sql, lint_syntax
from expo_jbm329.gui.autocomplete.engine import SqlAutoCompleter
from expo_jbm329.services import schema_cache
from expo_jbm329.services.schema_cache import SchemaCacheManager
from expo_jbm329.services.schema_model import build_schema_dict


@pytest.fixture
def duckdb_file(tmp_path):
    path = tmp_path / "sample # café.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute("""
            CREATE SCHEMA sales;
            CREATE SCHEMA "it's";
            CREATE TABLE main.orders (other_id INTEGER);
            CREATE TABLE sales.orders (
                id INTEGER NOT NULL,
                label VARCHAR,
                amount DECIMAL(10, 2),
                created DATE,
                enabled BOOLEAN
            );
            INSERT INTO sales.orders VALUES
                (1, 'first', 12.50, DATE '2025-01-02', true),
                (2, NULL, NULL, NULL, false),
                (3, 'third', 0.75, DATE '2025-01-03', NULL);
            CREATE VIEW sales.order_view AS SELECT id, label FROM sales.orders;
            CREATE TABLE "it's"."o'x" ("a""b" INTEGER);
            INSERT INTO "it's"."o'x" VALUES (7);
        """)
    return path


@pytest.fixture
def duckdb_connection(duckdb_file):
    name = f"duck-{duckdb_file}"
    config = {"db_type": "duckdb", "database": str(duckdb_file)}
    with patch("expo_jbm329.db.base.read_connections", return_value={name: config}):
        try:
            yield name
        finally:
            base.close_connection(name)


def test_facade_reads_real_file_and_preserves_result_values(duckdb_connection):
    result = base.execute_sql_safe(duckdb_connection, "SELECT * FROM sales.orders ORDER BY id", corr_id="test")

    assert result.ok and not result.cancelled
    assert result.rows == 3
    assert result.error is None
    frame = result.data
    assert list(frame.columns) == ["id", "label", "amount", "created", "enabled"]
    assert pd.api.types.is_integer_dtype(frame["id"])
    assert frame["id"].tolist() == [1, 2, 3]
    assert frame.loc[0, "label"] == "first"
    assert frame.loc[0, "amount"] == 12.5
    assert str(frame.loc[0, "created"]) == "2025-01-02"
    assert frame.loc[0, "enabled"]
    assert pd.isna(frame.loc[1, "label"])
    assert pd.isna(frame.loc[1, "amount"])
    assert pd.isna(frame.loc[1, "created"])
    assert pd.isna(frame.loc[2, "enabled"])
    assert base.get_db_name(duckdb_connection).endswith(".duckdb")
    first, cfg = base._get_service_with_config(duckdb_connection)
    second, cached_cfg = base._get_service_with_config(duckdb_connection)
    assert first is second and cfg is cached_cfg


def test_metadata_and_select_builders_use_real_file(duckdb_connection):
    assert base.list_tables(duckdb_connection) == [
        {"schema": "it's", "name": "o'x"},
        {"schema": "main", "name": "orders"},
        {"schema": "sales", "name": "orders"},
    ]
    assert base.list_views(duckdb_connection) == [{"schema": "sales", "name": "order_view"}]
    columns = base.list_columns(duckdb_connection, "sales", "orders")
    assert [column["COLUMN_NAME"] for column in columns] == ["id", "label", "amount", "created", "enabled"]
    assert columns[0] == {"COLUMN_NAME": "id", "DATA_TYPE": "INTEGER", "IS_NULLABLE": "NO"}
    assert columns[1] == {"COLUMN_NAME": "label", "DATA_TYPE": "VARCHAR", "IS_NULLABLE": "YES"}
    assert base.supports_bulk_column_listing(duckdb_connection)
    bulk = base.list_all_columns_map(duckdb_connection)
    assert set(bulk) == {("it's", "o'x"), ("main", "orders"), ("sales", "orders"), ("sales", "order_view")}
    for (schema, table), metadata in bulk.items():
        assert metadata == base.list_columns(duckdb_connection, schema, table)
    assert base.list_columns(duckdb_connection, "missing", "orders") == []
    sql = base.build_select_columns_auto(duckdb_connection, "sales", "orders", top_n=2)
    result = base.execute_sql_safe(duckdb_connection, sql)
    assert result.ok and result.rows == 2
    assert list(result.data.columns) == [column["COLUMN_NAME"] for column in columns]
    star = base.build_select_star(duckdb_connection, "it's", "o'x", top_n=1)
    assert base.execute_sql_safe(duckdb_connection, star).data.iloc[0, 0] == 7
    distinct = base.build_select_distinct(duckdb_connection, "it's", "o'x", 'a"b')
    assert base.execute_sql_safe(duckdb_connection, distinct).data.iloc[0, 0] == 7


@pytest.mark.parametrize(
    ("sql", "expected_rows"),
    [
        ("SELECT * FROM sales.orders;", 2),
        ("SELECT * FROM sales.orders -- trailing comment", 2),
        ("SELECT ' limit 1 ' AS label FROM sales.orders", 2),
        ("SELECT * FROM (SELECT * FROM sales.orders LIMIT 3) AS nested", 2),
        ("WITH limited AS (SELECT * FROM sales.orders LIMIT 3) SELECT * FROM limited", 2),
        ("SELECT * FROM sales.orders LIMIT 1", 1),
        ("SELECT * FROM sales.orders FETCH FIRST 1 ROWS ONLY", 1),
        ("SELECT * FROM sales.orders LIMIT ALL", 2),
        ("SELECT * FROM sales.orders UNION ALL SELECT * FROM sales.orders", 2),
        ("SELECT * FROM sales.orders OFFSET 1", 2),
    ],
)
def test_server_and_service_limits(duckdb_connection, sql, expected_rows):
    limited = DuckDbDialect().apply_limit(sql, 2)
    driver_service, cfg = base._get_service_with_config(duckdb_connection)
    server_frame = driver_service.driver.execute_df(cfg, limited)
    assert len(server_frame) == expected_rows
    result = base.execute_sql_safe(duckdb_connection, sql, top_n=2)
    assert result.ok and result.rows == expected_rows


def test_limit_parser_failure_keeps_valid_sql_and_client_row_cap(duckdb_connection, caplog):
    # sqlglot's DuckDB parser currently rejects the valid singular ROW spelling.
    sql = "SELECT * FROM sales.orders FETCH FIRST 3 ROW ONLY"
    with caplog.at_level("DEBUG", logger="applogger.db"):
        result = base.execute_sql_safe(duckdb_connection, sql, top_n=2)
    assert result.ok and result.rows == 2
    assert "limit injection failed" in caplog.text


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (
            "SELECT id, row_number() OVER (ORDER BY id) AS rn FROM sales.orders QUALIFY rn = 1",
            [(1, 1)],
        ),
        ("SELECT id FROM sales.orders WHERE label ILIKE 'F%' ORDER BY id", [(1,)]),
        ("SELECT id::VARCHAR AS text_id FROM sales.orders ORDER BY id", [("1",), ("2",), ("3",)]),
        ("SELECT [1, 2, 3] AS items", [([1, 2, 3],)]),
        ("SELECT {'name': 'a', 'value': 1} AS record", [({"name": "a", "value": 1},)]),
        ("SELECT * EXCLUDE (label, amount, created, enabled) FROM sales.orders ORDER BY id", [(1,), (2,), (3,)]),
        (
            "SELECT * EXCLUDE (label, amount, created, enabled) REPLACE (id * 2 AS id) FROM sales.orders ORDER BY id",
            [(2,), (4,), (6,)],
        ),
        ("WITH c AS (SELECT id FROM sales.orders) SELECT id FROM c ORDER BY id", [(1,), (2,), (3,)]),
    ],
)
def test_duckdb_formatted_queries_keep_real_results(duckdb_connection, duckdb_file, sql, expected):
    formatted = format_sql(sql, "duckdb")
    with duckdb.connect(str(duckdb_file), read_only=True) as connection:
        original_rows = connection.execute(sql).fetchall()
        assert connection.execute(formatted).fetchall() == original_rows
        assert original_rows == expected
    original = base.execute_sql_safe(duckdb_connection, sql)
    formatted_result = base.execute_sql_safe(duckdb_connection, formatted)
    assert original.ok and formatted_result.ok
    pd.testing.assert_frame_equal(original.data, formatted_result.data)


@pytest.mark.parametrize(
    ("sql", "category"),
    [
        ("SELECT * FROM absent", "missing_object"),
        ("SELECT missing FROM sales.orders", "syntax"),
        ("SELECT o.missing FROM sales.orders AS o", "syntax"),
        ("SELECT FROM", "syntax"),
        ("SELECT id FROM sales.orders a JOIN sales.orders b ON a.id = b.id", "ambiguous_column"),
        ("SELECT * FROM absent_function()", "missing_proc"),
        ("SELECT sum(label) FROM sales.orders", "syntax"),
    ],
)
def test_real_wrapped_errors_are_classified(duckdb_connection, sql, category):
    service, cfg = base._get_service_with_config(duckdb_connection)
    with pytest.raises(DBAPIError) as failure:
        service.driver.execute_df(cfg, sql)
    error = classify_duckdb(failure.value)
    assert error.category == category
    result = base.execute_sql_safe(duckdb_connection, sql)
    assert not result.ok and result.data is None
    assert result.error == error


def test_read_only_is_enforced_by_driver(duckdb_connection, duckdb_file):
    service, cfg = base._get_service_with_config(duckdb_connection)
    with pytest.raises(DBAPIError) as failure:
        service.driver.execute_df(cfg, "INSERT INTO sales.orders (id) VALUES (99)")
    assert classify_duckdb(failure.value).category == "permission"
    assert base.execute_sql_safe(duckdb_connection, "SELECT * FROM sales.orders").rows == 3
    for extra in ({"read_only": False}, {"config": {"access_mode": "READ_WRITE"}}, {"unknown": 1}):
        with pytest.raises(ValueError, match="extra options"):
            service.driver.execute_df(replace(cfg, extra=extra), "SELECT 1")
    base.close_connection(duckdb_connection)
    # No pooled reader remains to prevent a subsequent writable connection.
    with duckdb.connect(str(duckdb_file)) as connection:
        assert connection.execute("SELECT count(*) FROM sales.orders").fetchone() == (3,)


@pytest.mark.parametrize(
    "database", [None, "", " ", ":memory:", ":memory:shared", "md:remote", "https://host/db", "duckdb:///db"]
)
def test_invalid_paths_are_rejected_without_creating_databases(database, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    initial_paths = set(tmp_path.rglob("*"))
    config = ConnectionConfig(name="invalid", engine="duckdb", protocol="duckdb", database=database)
    service = DbService(SqlAlchemyDuckDbDriver(), DuckDbDialect())
    result = service.execute_sql(config, "SELECT 1")
    assert not result.ok
    assert result.error.message == TR_INVALID_CONFIG_DUCKDB
    assert set(tmp_path.rglob("*")) == initial_paths


def test_nonexistent_directory_and_invalid_files_fail_explicitly(tmp_path):
    driver = SqlAlchemyDuckDbDriver()
    cfg = ConnectionConfig(name="invalid", engine="duckdb", protocol="duckdb")
    missing = tmp_path / "missing.duckdb"
    service = DbService(driver, DuckDbDialect())
    result = service.execute_sql(replace(cfg, database=str(missing)), "SELECT 1")
    assert not result.ok and result.error.category == "connection"
    assert not missing.exists()
    with pytest.raises(IsADirectoryError):
        driver.execute_df(replace(cfg, database=str(tmp_path)), "SELECT 1")
    bad = tmp_path / "bad.duckdb"
    bad.write_bytes(b"not a DuckDB database")
    result = service.execute_sql(replace(cfg, database=str(bad)), "SELECT 1")
    assert not result.ok and result.error.category == "connection"
    assert bad.read_bytes() == b"not a DuckDB database"
    driver.dispose()


def test_concurrent_worker_queries_use_independent_connections(duckdb_file):
    driver = SqlAlchemyDuckDbDriver()
    cfg = ConnectionConfig(name="workers", engine="duckdb", protocol="duckdb", database=str(duckdb_file))
    engine = driver._get_engine(cfg)
    barrier = Barrier(2)
    native_connections = []

    def before_execute(connection, cursor, statement, parameters, context, executemany):
        if statement != "SELECT id FROM sales.orders ORDER BY id":
            return
        native_connections.append(connection.connection.driver_connection)
        barrier.wait(timeout=15)

    event.listen(engine, "before_cursor_execute", before_execute)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(driver.execute_df, cfg, "SELECT id FROM sales.orders ORDER BY id") for _ in range(2)
            ]
            frames = [future.result() for future in futures]
        assert frames[0].equals(frames[1])
        assert len(native_connections) == 2
        assert native_connections[0] is not native_connections[1]
    finally:
        driver.dispose()


def test_metadata_excludes_attached_and_temporary_catalogs(duckdb_file, tmp_path):
    other = tmp_path / "other.duckdb"
    with duckdb.connect(str(other)) as connection:
        connection.execute("CREATE TABLE alien (id INTEGER)")
    dialect = DuckDbDialect()
    with duckdb.connect(str(duckdb_file)) as connection:
        connection.execute(f"ATTACH '{other.as_posix()}' AS attached")
        connection.execute("CREATE TEMP TABLE ephemeral (id INTEGER)")
        tables = connection.execute(dialect.sql_list_tables()).fetchall()
        views = connection.execute(dialect.sql_list_views()).fetchall()
        columns = connection.execute(dialect.sql_all_columns()).fetchall()
        assert ("main", "alien") not in tables
        assert ("main", "ephemeral") not in tables
        assert tables == [("it's", "o'x"), ("main", "orders"), ("sales", "orders")]
        assert views == [("sales", "order_view")]
        assert not any(column[1] in ("alien", "ephemeral") for column in columns)
        assert connection.execute(dialect.sql_list_columns("it's", "o'x")).fetchall() == [('a"b', "INTEGER", "YES")]


def test_file_lock_from_another_process_has_useful_error(duckdb_file):
    script = """
import json
import sys
from expo_jbm329.db.core.models import ConnectionConfig
from expo_jbm329.db.dialects.duckdb import DuckDbDialect
from expo_jbm329.db.drivers.sa_duckdb import SqlAlchemyDuckDbDriver
from expo_jbm329.db.service import DbService
driver = SqlAlchemyDuckDbDriver()
result = DbService(driver, DuckDbDialect()).execute_sql(
    ConnectionConfig(name="locked", engine="duckdb", protocol="duckdb", database=sys.argv[1]),
    "SELECT 1",
)
print(json.dumps({"ok": result.ok, "category": result.error.category, "hint": result.error.hint}))
driver.dispose()
"""
    with duckdb.connect(str(duckdb_file)):
        process = subprocess.run(
            [sys.executable, "-c", script, str(duckdb_file)],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    payload = json.loads(process.stdout)
    assert payload == {"ok": False, "category": "connection", "hint": TR_LOCKED_HINT_DUCKDB}


def test_cancellation_and_disposal_follow_existing_service_contract(duckdb_connection):
    cancelled = base.execute_sql_safe(duckdb_connection, "SELECT 1", cancel_cb=lambda: True)
    assert cancelled.cancelled and not cancelled.ok
    assert duckdb_connection not in base._services
    checks = iter([False, False, False, True])
    cancelled = base.execute_sql_safe(duckdb_connection, "SELECT 1", cancel_cb=lambda: next(checks))
    assert cancelled.cancelled and not cancelled.ok
    base.close_connection(duckdb_connection)
    assert duckdb_connection not in base._services


@pytest.mark.parametrize("prefetch", ["bulk", "fallback"])
def test_real_schema_cache_drives_completion_lint_and_reconnect(
    duckdb_connection, duckdb_file, tmp_path, monkeypatch, prefetch
):
    # Other cache unit tests replace these module aliases directly.
    for name in [
        "get_db_name",
        "list_tables",
        "list_views",
        "list_columns",
        "list_all_columns_map",
        "supports_bulk_column_listing",
    ]:
        monkeypatch.setattr(schema_cache, name, getattr(base, name))
    rebuilt = []
    manager = SchemaCacheManager(autocomplete_cb=rebuilt.append)
    monkeypatch.setattr(manager, "_invoke_ui", lambda callback: callback())
    jobs = []

    def runner(_parent, function, connection, *args, **kwargs):
        jobs.append(function.__name__)
        if prefetch == "fallback" and function.__name__ == "_load_all_columns":
            return SimpleNamespace(
                result=MagicMock(),
                error=SimpleNamespace(connect=lambda callback: callback("bulk unavailable")),
            )
        payload = function(connection, *args)
        return SimpleNamespace(
            result=SimpleNamespace(connect=lambda callback: callback(payload)),
            error=MagicMock(),
        )

    manager.set_job_runner(runner)
    entry = manager.load_schema(duckdb_connection)
    manager.prefetch_columns_async(duckdb_connection)
    assert entry.columns == base.list_all_columns_map(duckdb_connection)
    assert rebuilt and set(rebuilt) == {duckdb_connection}
    assert jobs[0] == "_load_all_columns"
    assert len(jobs) == (1 if prefetch == "bulk" else 2)
    schema = build_schema_dict(asdict(entry))
    completer = SqlAutoCompleter()
    completer.set_schema(schema)
    assert completer.get_suggestions("sales.") == ["orders", "order_view"]
    assert completer.get_suggestions("sales.orders.") == ["id", "label", "amount", "created", "enabled"]
    assert completer.get_suggestions("main.orders.") == ["other_id"]
    assert completer.get_suggestions("sales.order_view.") == ["id", "label"]
    assert "sales" in completer.get_suggestions("sa")
    for table, column in [("sales.orders", "label"), ("main.orders", "other_id"), ("sales.order_view", "label")]:
        sql = f"SELECT o. FROM {table} o"
        assert column in completer.get_contextual_suggestions(sql, len("SELECT o."), "o.", dialect="duckdb")
    assert lint_syntax("SELECT id FROM sales.orders", "duckdb", schema=schema) == []
    assert lint_syntax("WITH c AS (SELECT id FROM sales.orders) SELECT id FROM c", "duckdb", schema=schema) == []
    assert any(
        "Unknown column 'other_id'" in diagnostic.message
        for diagnostic in lint_syntax("SELECT s.other_id FROM sales.orders s", "duckdb", schema=schema)
    )

    other_file = tmp_path / "isolated.duckdb"
    with duckdb.connect(str(other_file)) as connection:
        connection.execute("CREATE TABLE isolated (unique_column INTEGER)")
    configs = {
        duckdb_connection: {"db_type": "duckdb", "database": str(duckdb_file)},
        "other-duck": {"db_type": "duckdb", "database": str(other_file)},
    }
    with patch("expo_jbm329.db.base.read_connections", return_value=configs):
        try:
            other = manager.load_schema("other-duck")
            manager.prefetch_columns_async("other-duck")
            other_schema = build_schema_dict(asdict(other))
            completer.set_schema(other_schema)
            assert completer.get_suggestions("main.isolated.") == ["unique_column"]
            assert completer.get_suggestions("sales.") == []
            assert manager.get_cache_for(duckdb_connection) is entry

            manager.clear_for(duckdb_connection)
            base.close_connection(duckdb_connection)
            assert manager.get_cache_for(duckdb_connection) is None
            with duckdb.connect(str(duckdb_file)) as connection:
                connection.execute("ALTER TABLE sales.orders ADD COLUMN refreshed INTEGER")
            refreshed = manager.load_schema(duckdb_connection, force_refresh=True)
            manager.prefetch_columns_async(duckdb_connection)
            assert refreshed is not entry
            assert manager.get_cache_for("other-duck") is other
            completer.set_schema(build_schema_dict(asdict(refreshed)))
            assert "refreshed" in completer.get_suggestions("sales.orders.")
            assert "unique_column" not in completer.get_all_objects()
            assert (
                lint_syntax("SELECT refreshed FROM sales.orders", "duckdb", schema=build_schema_dict(asdict(refreshed)))
                == []
            )
        finally:
            base.close_connection("other-duck")
            manager.clear_all()
