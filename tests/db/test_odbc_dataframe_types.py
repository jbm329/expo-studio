from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from expo_jbm329.db.core.models import ConnectionConfig
from expo_jbm329.db.drivers.sa_odbc import SqlAlchemyOdbcDriver
from expo_jbm329.utils.dataframe_construction import dataframe_from_raw_values

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def execute_rows(
    rows: Sequence[Sequence[object]],
    columns: Sequence[str],
    *,
    cancel_cb: Callable[[], bool] | None = None,
    fail_fetch: bool = False,
) -> pd.DataFrame:
    driver = SqlAlchemyOdbcDriver()
    config = ConnectionConfig(name="odbc", engine="mssql", protocol="odbc")
    engine = MagicMock()
    raw = engine.raw_connection.return_value
    cursor = raw.cursor.return_value
    cursor.description = [(column,) for column in columns]
    cursor.fetchall.return_value = rows
    if fail_fetch:
        cursor.fetchall.side_effect = ValueError("fetch failed")

    def execute(sql: str) -> None:
        assert sql == "SELECT values"
        assert driver._active_cursors == {"job": cursor}

    cursor.execute.side_effect = execute
    with (
        patch.object(driver, "_get_engine", return_value=engine),
        patch("expo_jbm329.db.drivers.sa_odbc.threading.Thread") as thread,
    ):
        try:
            return driver.execute_df(config, "SELECT values", job_id="job", cancel_cb=cancel_cb)
        finally:
            assert driver._active_cursors == {}
            if raw.cursor.called:
                cursor.close.assert_called_once()
                raw.close.assert_called_once()
            else:
                engine.raw_connection.assert_not_called()
            if cancel_cb is not None and raw.cursor.called:
                thread.return_value.start.assert_called_once()
                thread.return_value.join.assert_called_once_with(timeout=0.2)


def test_odbc_missing_only_nullable_values_are_exact() -> None:
    result = execute_rows(
        [
            [2**53 + 1, 2**64 - 1, True, 1, True, 1.0, "001", None],
            [None, None, None, 2, False, None, None, None],
        ],
        ["integer", "unsigned", "boolean", "complete", "complete_bool", "float", "text", "unknown"],
    )
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
    assert result["boolean"].isna().tolist() == [False, True]
    assert result["text"].tolist() == ["001", None]
    assert result["unknown"].tolist() == [None, None]


@pytest.mark.parametrize(
    "values",
    [
        [Decimal("1.25"), None],
        [Decimal(1), Decimal(2)],
        [Decimal("1.25"), "text", None],
        [datetime.fromisoformat("2025-01-01T00:00:00"), None],
        [datetime.fromisoformat("2025-01-01T00:00:00+02:00"), None],
        [date(2025, 1, 1), None],
        [time(12, 30), None],
        [timedelta(days=1), None],
        [b"\x01", None],
        [1, "text", None],
        [True, 1, None],
        [1.0, None],
        [None, None],
        [],
    ],
)
def test_odbc_unrelated_values_retain_records_inference(values: list[object]) -> None:
    rows = [(value,) for value in values]
    expected = pd.DataFrame.from_records(rows, columns=["value"])
    pd.testing.assert_frame_equal(execute_rows(rows, ["value"]), expected)


def test_odbc_duplicate_labels_and_empty_schema() -> None:
    result = execute_rows([[1, True], [None, None]], ["same", "same"])
    assert result.columns.tolist() == ["same", "same"]
    assert result.dtypes.astype(str).tolist() == ["Int64", "boolean"]
    pd.testing.assert_frame_equal(execute_rows([], ["same", "same"]), pd.DataFrame(columns=["same", "same"]))


@pytest.mark.parametrize("cancel_after", range(7))
def test_odbc_cancellation_releases_cursor_and_connection(cancel_after: int) -> None:
    checks = iter([False] * cancel_after)
    with pytest.raises(RuntimeError, match="cancelled"):
        execute_rows([[1, True], [None, None]], ["value", "flag"], cancel_cb=lambda: next(checks, True))


def test_odbc_fetch_failure_releases_cursor_and_connection() -> None:
    with pytest.raises(ValueError, match="fetch failed"):
        execute_rows([], ["value"], cancel_cb=lambda: False, fail_fetch=True)


def test_odbc_cursor_remains_cancellable_during_dataframe_preparation() -> None:
    driver = SqlAlchemyOdbcDriver()
    config = ConnectionConfig(name="odbc", engine="mssql", protocol="odbc")
    engine = MagicMock()
    raw = engine.raw_connection.return_value
    cursor = raw.cursor.return_value
    cursor.description = [("value",)]
    cursor.fetchall.return_value = [(1,), (None,)]

    def prepare(
        data: Sequence[Sequence[object]], header: Sequence[object], *, check_cancel: Callable[[], None]
    ) -> pd.DataFrame:
        assert driver.cancel_execution("job")
        cursor.cancel.assert_called_once()
        cursor.close.assert_not_called()
        raw.close.assert_not_called()
        return dataframe_from_raw_values(data, header, check_cancel=check_cancel)

    with (
        patch.object(driver, "_get_engine", return_value=engine),
        patch("expo_jbm329.db.drivers.sa_odbc.dataframe_from_raw_values", side_effect=prepare),
    ):
        result = driver.execute_df(config, "SELECT value", job_id="job")
    assert str(result["value"].dtype) == "Int64"
    assert driver._active_cursors == {}
    assert not driver.cancel_execution("job")
    cursor.close.assert_called_once()
    raw.close.assert_called_once()
