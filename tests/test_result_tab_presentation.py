"""Tests for exact, whole-column result-tab datetime metadata."""

from __future__ import annotations

import pandas as pd
import pytest
from pytest import MonkeyPatch

from expo_jbm329.services import result_tab_presentation
from expo_jbm329.services.result_tab_presentation import build_datetime_date_only_columns


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["2026-01-01", "2026-01-02"], True),
        (["2026-01-01", None, "2026-01-02"], True),
        (["2026-01-01", "2026-01-02 01:00:00"], False),
        (["2026-01-01", "2026-01-02 00:01:00"], False),
        (["2026-01-01", "2026-01-02 00:00:01"], False),
        (["2026-01-01", "2026-01-02 00:00:00.001"], False),
        (["2026-01-01", "2026-01-02 00:00:00.000001"], False),
        (["2026-01-01", "2026-01-02 00:00:00.000000001"], False),
        ([None, None], False),
        ([], False),
    ],
)
def test_datetime_date_only_metadata(values: list[str | None], expected: bool) -> None:
    df = pd.DataFrame({"date": pd.to_datetime(pd.Series(values, dtype=object), format="mixed")})
    original = df.copy(deep=True)

    assert build_datetime_date_only_columns(df) == {0: expected}
    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_datetime_metadata_supports_storage_units(unit: str) -> None:
    df = pd.DataFrame({"date": pd.Series(["2026-01-01", "2026-01-02"], dtype=f"datetime64[{unit}]")})

    assert build_datetime_date_only_columns(df) == {0: True}
    df.iloc[1, 0] = pd.Timestamp("2026-01-02 00:00:01")
    assert build_datetime_date_only_columns(df) == {0: False}


@pytest.mark.parametrize("zone", ["UTC", "Europe/Stockholm", "America/New_York", "Asia/Kolkata"])
def test_datetime_metadata_uses_stored_wall_clock_time(zone: str) -> None:
    df = pd.DataFrame({
        "date": pd.DatetimeIndex(["2026-03-28", None, "2026-03-30", "2026-10-26"]).tz_localize(zone),
    })
    original = df.copy(deep=True)

    assert build_datetime_date_only_columns(df) == {0: True}
    pd.testing.assert_frame_equal(df, original)
    df.iloc[-1, 0] = pd.Timestamp("2026-10-26 00:00:00.000000001", tz=zone)
    assert build_datetime_date_only_columns(df) == {0: False}


def test_datetime_metadata_handles_midnight_during_dst_transition() -> None:
    # Midnight is ambiguous on this date; inspecting components must not
    # normalize/relocalize it and trigger pandas' ambiguous-time error.
    dates = pd.DatetimeIndex(["2020-11-01"]).tz_localize("America/Havana", ambiguous=True)
    df = pd.DataFrame({"date": dates})

    assert build_datetime_date_only_columns(df) == {0: True}


def test_datetime_metadata_checks_beyond_first_chunk_and_visible_sample(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(result_tab_presentation, "DATETIME_SCAN_CHUNK_ROWS", 128)
    dates = pd.Series(pd.Timestamp("2026-01-01"), index=range(1001), dtype="datetime64[ns]")
    df = pd.DataFrame({"date": dates})

    assert build_datetime_date_only_columns(df) == {0: True}
    df.iloc[-1, 0] = pd.Timestamp("2026-01-01 00:00:00.000000001")
    assert build_datetime_date_only_columns(df) == {0: False}


def test_datetime_metadata_ignores_empty_chunks(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(result_tab_presentation, "DATETIME_SCAN_CHUNK_ROWS", 2)
    df = pd.DataFrame({"date": pd.Series([None, None, "2026-01-01", None, None], dtype="datetime64[ns]")})

    assert build_datetime_date_only_columns(df) == {0: True}


def test_datetime_metadata_checks_across_production_chunk_boundary() -> None:
    rows = result_tab_presentation.DATETIME_SCAN_CHUNK_ROWS + 1
    df = pd.DataFrame({
        "date": pd.Series(pd.Timestamp("2026-01-01"), index=range(rows), dtype="datetime64[ns]"),
    })

    assert build_datetime_date_only_columns(df) == {0: True}
    df.iloc[-1, 0] = pd.Timestamp("2026-01-01 00:00:00.000000001")
    assert build_datetime_date_only_columns(df) == {0: False}


def test_datetime_metadata_is_positional_and_does_not_parse_other_columns() -> None:
    df = pd.DataFrame({
        "date": pd.Series(["2026-01-01", None], dtype="datetime64[ns]"),
        "time": pd.Series(["2026-01-01 01:00:00", None], dtype="datetime64[ns]"),
        "text": ["2026-01-01", None],
        "object": pd.Series([pd.Timestamp("2026-01-01"), None], dtype=object),
        "integer": pd.Series([2026, pd.NA], dtype="Int64"),
        "float": pd.Series([2026.0, pd.NA], dtype="Float64"),
        "bool": pd.Series([True, pd.NA], dtype="boolean"),
        "category": pd.Series(["2026-01-01", None], dtype="category"),
        "duration": pd.Series([0, None], dtype="timedelta64[ns]"),
    })
    df.columns = ["value"] * df.shape[1]
    original = df.copy(deep=True)

    assert build_datetime_date_only_columns(df) == {0: True, 1: False}
    pd.testing.assert_frame_equal(df, original)


def test_datetime_metadata_supports_dates_outside_nanosecond_range() -> None:
    df = pd.DataFrame({"date": pd.Series(["1500-01-01", "2500-01-01"], dtype="datetime64[s]")})

    assert build_datetime_date_only_columns(df) == {0: True}
