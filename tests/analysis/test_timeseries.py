from __future__ import annotations

import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis import timeseries
from expo_jbm329.services.analysis.timeseries import (
    DecompositionModel,
    TimeSeriesError,
    analyze_time_series,
    datetime_columns,
)


def _daily_frame(size: int = 28) -> pd.DataFrame:
    timestamps = pd.date_range("2025-01-01", periods=size, freq="D")
    return pd.DataFrame({
        "when": timestamps,
        "value": 10 + np.arange(size, dtype=float) * 0.1 + np.sin(np.arange(size) * 2 * np.pi / 7),
        "other": np.arange(size, dtype=float),
        "text": ["a"] * size,
    })


def _result_values(result) -> tuple[float, ...]:
    return dataclasses.asdict(result)["values"]


def test_datetime_columns_returns_only_native_datetime_columns():
    df = _daily_frame()
    df["as_text"] = df["when"].astype(str)

    assert datetime_columns(df) == ("when",)


def test_default_analysis_uses_first_datetime_and_numeric_columns():
    result = analyze_time_series(_daily_frame())

    assert result.error is None
    assert result.datetime_column == "when"
    assert result.value_column == "value"
    assert result.available_datetime_columns == ("when",)
    assert result.available_value_columns == ("value", "other")
    assert result.detected_frequency == "D"
    assert result.seasonal_period == 7
    assert len(result.timestamps) == 28
    assert len(result.values) == 28
    assert len(result.acf_values) > 0
    assert result.diagnostics_note is None


def test_additive_decomposition_returns_every_component():
    result = analyze_time_series(_daily_frame())

    assert result.error is None
    assert result.decomposition_model is DecompositionModel.ADDITIVE
    assert len(result.trend) == 28
    assert len(result.seasonal) == 28
    assert len(result.residual) == 28
    assert result.decomposition_note is None


def test_multiplicative_decomposition_is_available_for_positive_values():
    result = analyze_time_series(_daily_frame(), decomposition_model=DecompositionModel.MULTIPLICATIVE)

    assert result.error is None
    assert result.decomposition_note is None
    assert len(result.trend) == 28


def test_multiplicative_decomposition_explains_non_positive_values():
    df = _daily_frame()
    df["value"] = df["value"] - 20

    result = analyze_time_series(df, decomposition_model=DecompositionModel.MULTIPLICATIVE)

    assert result.error is None
    assert result.trend == ()
    assert "greater than zero" in result.decomposition_note


def test_duplicate_timestamps_are_averaged():
    df = _daily_frame(3)
    duplicate = df.iloc[[1]].copy()
    duplicate["value"] = 100.0
    df = pd.concat([df, duplicate], ignore_index=True)

    result = analyze_time_series(df)

    assert result.error is None
    assert result.duplicate_rows == 1
    assert len(result.timestamps) == 3
    result_values = _result_values(result)
    assert result_values[1] == pytest.approx((10.1 + np.sin(2 * np.pi / 7) + 100.0) / 2)


def test_invalid_rows_are_dropped_from_original_frequency():
    df = _daily_frame(4)
    df.loc[1, "value"] = np.inf
    df.loc[2, "when"] = pd.NaT

    result = analyze_time_series(df)

    assert result.error is TimeSeriesError.NOT_ENOUGH_OBSERVATIONS


def test_explicit_resample_aggregates_and_preserves_missing_bins_as_gaps():
    df = _daily_frame(21).drop(index=range(7, 14))

    result = analyze_time_series(df, resample_frequency="7D", seasonal_period=2)

    assert result.error is None
    assert result.detected_frequency == "7D"
    assert len(result.values) == 3
    result_values = _result_values(result)
    assert math.isnan(result_values[1])
    assert result.acf_values == ()
    assert "gaps" in result.diagnostics_note
    assert result.trend == ()
    assert "gaps" in result.decomposition_note


def test_irregular_original_frequency_skips_diagnostics_and_decomposition():
    df = _daily_frame(10).drop(index=[3, 6])

    result = analyze_time_series(df)

    assert result.error is None
    assert result.detected_frequency is None
    assert result.acf_values == ()
    assert "regular" in result.diagnostics_note
    assert result.trend == ()
    assert "regular" in result.decomposition_note


def test_explicit_seasonal_period_overrides_detected_default():
    result = analyze_time_series(_daily_frame(), seasonal_period=3)

    assert result.error is None
    assert result.seasonal_period == 3
    assert result.decomposition_note is None


@pytest.mark.parametrize(
    ("df", "datetime_column", "value_column", "kwargs", "error"),
    [
        (pd.DataFrame({"value": [1.0, 2.0, 3.0]}), None, None, {}, TimeSeriesError.NO_DATETIME_COLUMN),
        (
            pd.DataFrame({"when": pd.date_range("2025-01-01", periods=3)}),
            None,
            None,
            {},
            TimeSeriesError.NO_NUMERIC_COLUMN,
        ),
        (_daily_frame(), "missing", None, {}, TimeSeriesError.INVALID_DATETIME_COLUMN),
        (_daily_frame(), None, "missing", {}, TimeSeriesError.INVALID_VALUE_COLUMN),
        (_daily_frame(), None, None, {"resample_frequency": "invalid"}, TimeSeriesError.INVALID_FREQUENCY),
        (_daily_frame(), None, None, {"seasonal_period": 1}, TimeSeriesError.INVALID_SEASONAL_PERIOD),
    ],
)
def test_invalid_configuration_returns_structured_error(df, datetime_column, value_column, kwargs, error):
    result = analyze_time_series(df, datetime_column, value_column, **kwargs)

    assert result.error is error
    assert result.timestamps == ()


def test_fewer_than_three_valid_observations_returns_an_error():
    df = _daily_frame(3)
    df.loc[0, "value"] = np.nan

    result = analyze_time_series(df)

    assert result.error is TimeSeriesError.NOT_ENOUGH_OBSERVATIONS


def test_analysis_does_not_mutate_the_dataframe():
    df = _daily_frame()
    before = df.copy(deep=True)

    analyze_time_series(df)

    pd.testing.assert_frame_equal(df, before)


@pytest.mark.parametrize(
    ("frequency", "period"),
    [
        (None, None),
        ("H", 24),
        ("D", 7),
        ("W", 52),
        ("ME", 12),
        ("QE", 4),
        ("YS", None),
    ],
)
def test_default_seasonal_period_by_frequency(frequency, period):
    assert timeseries._default_period(frequency) == period  # noqa: SLF001


def test_short_series_has_no_inferred_frequency():
    index = pd.date_range("2025-01-01", periods=2, freq="D")

    assert timeseries._detect_frequency(index) is None  # noqa: SLF001


def test_frequency_inference_errors_are_treated_as_unavailable(monkeypatch):
    def _raise(_index):
        raise ValueError

    monkeypatch.setattr(timeseries.pd, "infer_freq", _raise)

    assert timeseries._detect_frequency(pd.date_range("2025-01-01", periods=3, freq="D")) is None  # noqa: SLF001


def test_invalid_rows_are_counted_when_enough_rows_remain():
    df = _daily_frame(4)
    df.loc[0, "value"] = np.nan

    result = analyze_time_series(df)

    assert result.error is None
    assert result.invalid_rows == 1
    assert result.detected_frequency == "D"


def test_decomposition_needs_an_detected_or_selected_period():
    result = analyze_time_series(_daily_frame(10).drop(index=[3]))

    assert result.decomposition_note is not None
    assert "regular" in result.decomposition_note


def test_decomposition_explains_a_missing_seasonal_period():
    series = pd.Series(range(10), index=pd.date_range("2025-01-01", periods=10, freq="D"), dtype=float)

    _trend, _seasonal, _residual, note = timeseries._decomposition(  # noqa: SLF001
        series,
        "D",
        None,
        DecompositionModel.ADDITIVE,
    )

    assert note == "No seasonal period could be detected; choose one to decompose the series."


def test_initialize_time_series_selects_first_columns_without_analyzing() -> None:
    df = pd.DataFrame({
        "when": pd.date_range("2025-01-01", periods=3, freq="D"),
        "later": pd.date_range("2025-02-01", periods=3, freq="D"),
        "value": [1.0, 2.0, 3.0],
        "other": [4.0, 5.0, 6.0],
    })

    result = timeseries.initialize_time_series(df)

    assert result.error is None
    assert result.datetime_column == "when"
    assert result.value_column == "value"
    assert result.available_datetime_columns == ("when", "later")
    assert result.available_value_columns == ("value", "other")
    assert result.resample_frequency is None
    assert result.seasonal_period is None
    assert result.decomposition_model is timeseries.DecompositionModel.ADDITIVE
    assert result.source_rows == 3
    assert result.timestamps == ()
    assert result.acf_values == ()


@pytest.mark.parametrize(
    ("df", "error"),
    [
        (pd.DataFrame({"value": [1.0, 2.0]}), timeseries.TimeSeriesError.NO_DATETIME_COLUMN),
        (pd.DataFrame({}), timeseries.TimeSeriesError.NO_DATETIME_COLUMN),
        (
            pd.DataFrame({"when": pd.date_range("2025-01-01", periods=2, freq="D"), "text": ["a", "b"]}),
            timeseries.TimeSeriesError.NO_NUMERIC_COLUMN,
        ),
    ],
)
def test_initialize_time_series_reports_missing_columns(df: pd.DataFrame, error: timeseries.TimeSeriesError) -> None:
    result = timeseries.initialize_time_series(df)

    assert result.error is error
