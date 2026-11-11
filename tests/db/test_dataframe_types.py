from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import create_engine

from expo_jbm329.db.core.dataframe_types import read_sql_dataframe
from expo_jbm329.db.core.models import ConnectionConfig
from expo_jbm329.db.drivers.sa_duckdb import SqlAlchemyDuckDbDriver
from expo_jbm329.db.drivers.sa_mysql import SqlAlchemyMySqlDriver
from expo_jbm329.db.drivers.sa_postgres import SqlAlchemyPostgresDriver
from expo_jbm329.db.drivers.sa_sqlite import SqlAlchemySqliteDriver

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from expo_jbm329.db.core.interfaces import DriverProtocol


def raw_connection(rows: Sequence[Sequence[object]], labels: Sequence[str]) -> MagicMock:
    connection = MagicMock()
    result = connection.exec_driver_sql.return_value.__enter__.return_value
    result.keys.return_value = labels
    result.fetchall.return_value = rows
    return connection


def test_raw_sql_inference_preserves_exact_values_and_unrelated_types() -> None:
    rows = [
        [2**53 + 1, 2**64 - 1, True, 1, True, 1.0, "001", None],
        [None, None, None, 2, False, None, None, None],
    ]
    labels = ["integer", "unsigned", "boolean", "complete", "complete_bool", "float", "text", "unknown"]
    connection = raw_connection(rows, labels)
    result = read_sql_dataframe("SELECT values", connection)
    assert result.dtypes.astype(str).tolist() == [
        "Int64",
        "UInt64",
        "boolean",
        "int64",
        "bool",
        "float64",
        "object",
        "object",
    ]
    assert result["integer"].iloc[0] == 2**53 + 1
    assert result["unsigned"].iloc[0] == 2**64 - 1
    assert result["text"].tolist() == ["001", None]
    assert result["unknown"].tolist() == [None, None]
    connection.exec_driver_sql.assert_called_once_with("SELECT values")
    connection.exec_driver_sql.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "values",
    [
        [Decimal("1.25"), None],
        [Decimal(1), Decimal(2)],
        [Decimal("1.25"), "text", None],
        [datetime.fromisoformat("2025-01-01T00:00:00"), None],
        [datetime.fromisoformat("2025-01-01T00:00:00+02:00"), None],
        [datetime.fromisoformat("2025-01-01T00:00:00+02:00"), datetime.fromisoformat("2025-01-01T00:00:00+03:00")],
        [date(2025, 1, 1), None],
        [time(12, 30), None],
        [timedelta(days=1), None],
        [b"\x01", None],
        [1, "text", None],
        [True, 1, None],
        [{"key": 1}, ["item"], None],
        [1.0, None],
        [None, None],
        [],
    ],
)
def test_raw_sql_unrelated_values_match_records_inference(values: list[object]) -> None:
    rows = [(value,) for value in values]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.connect() as connection:
            result = MagicMock()
            result.keys.return_value = ["value"]
            result.fetchall.return_value = rows
            with patch.object(connection, "exec_driver_sql", return_value=result):
                expected = pd.read_sql_query("SELECT values", connection)
    finally:
        engine.dispose()
    actual = read_sql_dataframe("SELECT values", raw_connection(rows, ["value"]))
    pd.testing.assert_frame_equal(actual, expected)


def test_sql_duplicate_headers_and_empty_schema() -> None:
    result = read_sql_dataframe("SELECT values", raw_connection([[1, True], [None, None]], ["same", "same"]))
    assert result.columns.tolist() == ["same", "same"]
    assert result.dtypes.astype(str).tolist() == ["Int64", "boolean"]
    empty = read_sql_dataframe("SELECT empty", raw_connection([], ["same", "same"]))
    pd.testing.assert_frame_equal(empty, pd.DataFrame(columns=["same", "same"]))


@pytest.mark.parametrize("cancel_after", range(8))
def test_sql_preparation_cancellation_closes_result(cancel_after: int) -> None:
    checks = iter([False] * cancel_after)
    connection = raw_connection([[1, True], [None, None]], ["value", "flag"])
    with pytest.raises(RuntimeError, match="preparation cancelled"):
        read_sql_dataframe("SELECT values", connection, cancel_cb=lambda: next(checks, True))
    if cancel_after == 0:
        connection.exec_driver_sql.assert_not_called()
    else:
        connection.exec_driver_sql.return_value.__exit__.assert_called_once()


def test_sql_fetch_failure_closes_result() -> None:
    connection = raw_connection([], ["value"])
    connection.exec_driver_sql.return_value.__enter__.return_value.fetchall.side_effect = ValueError("fetch failed")
    with pytest.raises(ValueError, match="fetch failed"):
        read_sql_dataframe("SELECT values", connection)
    connection.exec_driver_sql.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize(
    ("driver", "engine_name", "protocol"),
    [
        (SqlAlchemySqliteDriver(), "sqlite", "sqlite"),
        (SqlAlchemyPostgresDriver(), "postgresql", "psycopg"),
        (SqlAlchemyMySqlDriver("pymysql"), "mysql", "pymysql"),
        (SqlAlchemyMySqlDriver("mysqlconnector"), "mariadb", "mysqlconnector"),
        (SqlAlchemyDuckDbDriver(), "duckdb", "duckdb"),
    ],
)
def test_sql_drivers_construct_raw_results(
    driver: DriverProtocol, engine_name: str, protocol: str, tmp_path: Path
) -> None:
    path = tmp_path / "existing.duckdb"
    path.touch()
    config = ConnectionConfig(name="test", engine=engine_name, protocol=protocol, database=str(path))
    engine = MagicMock()
    connection = raw_connection([[2**53 + 1, 1], [None, 2]], ["value", "complete"])
    engine.connect.return_value.__enter__.return_value = connection
    with patch.object(driver, "_get_engine", return_value=engine):
        result = driver.execute_df(config, "SELECT value, complete", cancel_cb=lambda: False)
    assert result["value"].iloc[0] == 2**53 + 1
    assert result.dtypes.astype(str).tolist() == ["Int64", "int64"]
    engine.connect.return_value.__exit__.assert_called_once()


def test_real_sqlite_result_inference(tmp_path: Path) -> None:
    driver = SqlAlchemySqliteDriver()
    config = ConnectionConfig(name="sqlite", engine="sqlite", protocol="sqlite", database=str(tmp_path / "data.db"))
    try:
        result = driver.execute_df(
            config,
            "SELECT 9007199254740993 AS integer_value, 1.0 AS measurement, 1 AS flag, '001' AS label "
            "UNION ALL SELECT NULL, NULL, NULL, NULL",
        )
        assert result.dtypes.astype(str).tolist() == ["Int64", "float64", "Int64", "object"]
        assert result["integer_value"].iloc[0] == 9007199254740993
        assert result["label"].tolist() == ["001", None]
    finally:
        driver.dispose()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1.0 AS value UNION ALL SELECT NULL",
        "SELECT '001' AS value UNION ALL SELECT NULL",
        "SELECT 1 AS value UNION ALL SELECT 'text' UNION ALL SELECT NULL",
        "SELECT x'0102' AS value UNION ALL SELECT NULL",
        "SELECT 1 AS value UNION ALL SELECT 2",
        "SELECT NULL AS value UNION ALL SELECT NULL",
        "SELECT 1 AS value WHERE 0",
        "SELECT 1 AS same, 'text' AS same UNION ALL SELECT 2, NULL",
    ],
)
def test_sqlite_unrelated_values_match_legacy_inference(sql: str) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.connect() as connection:
            expected = pd.read_sql(sql, connection)
            actual = read_sql_dataframe(sql, connection)
        pd.testing.assert_frame_equal(actual, expected)
    finally:
        engine.dispose()
