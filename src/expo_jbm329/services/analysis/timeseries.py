"""Time-series preparation, diagnostics and seasonal decomposition."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.stattools import acf

from expo_jbm329.services.analysis.columns import numeric_columns
from expo_jbm329.services.data_operations.dtypes import SemanticDType, classify_series_dtype

MIN_OBSERVATIONS = 3
MIN_SEASONAL_CYCLES = 2
MIN_SEASONAL_PERIOD = 2
MAX_ACF_LAGS = 40


class DecompositionModel(StrEnum):
    """Supported seasonal-decomposition models."""

    ADDITIVE = "additive"
    MULTIPLICATIVE = "multiplicative"


class TimeSeriesError(StrEnum):
    """Reasons a time-series result cannot be generated."""

    NO_DATETIME_COLUMN = "no_datetime_column"
    NO_NUMERIC_COLUMN = "no_numeric_column"
    INVALID_DATETIME_COLUMN = "invalid_datetime_column"
    INVALID_VALUE_COLUMN = "invalid_value_column"
    INVALID_FREQUENCY = "invalid_frequency"
    INVALID_SEASONAL_PERIOD = "invalid_seasonal_period"
    NOT_ENOUGH_OBSERVATIONS = "not_enough_observations"


@dataclass(frozen=True, slots=True)
class TimeSeriesResult:
    """Prepared series, diagnostics and optional seasonal decomposition."""

    datetime_column: str
    value_column: str
    available_datetime_columns: tuple[str, ...]
    available_value_columns: tuple[str, ...]
    resample_frequency: str | None
    detected_frequency: str | None
    seasonal_period: int | None
    decomposition_model: DecompositionModel
    source_rows: int
    invalid_rows: int
    duplicate_rows: int
    timestamps: tuple[pd.Timestamp, ...]
    values: tuple[float, ...]
    acf_values: tuple[float, ...]
    trend: tuple[float, ...]
    seasonal: tuple[float, ...]
    residual: tuple[float, ...]
    diagnostics_note: str | None
    decomposition_note: str | None
    error: TimeSeriesError | None


@dataclass(frozen=True, slots=True)
class _Configuration:
    """Requested series columns and processing controls."""

    datetime_column: str
    value_column: str
    available_datetime_columns: tuple[str, ...]
    available_value_columns: tuple[str, ...]
    resample_frequency: str | None
    seasonal_period: int | None
    decomposition_model: DecompositionModel
    source_rows: int


def datetime_columns(df: pd.DataFrame) -> tuple[str, ...]:
    """Return native datetime columns in DataFrame order."""
    return tuple(str(column) for column in df.columns if classify_series_dtype(df[column]) is SemanticDType.DATETIME)


def _default_period(frequency: str | None) -> int | None:
    """Return a conventional seasonal period for a pandas frequency."""
    if frequency is None:
        return None
    upper = frequency.upper()
    if upper.startswith(("H", "HOUR")):
        return 24
    if upper.startswith(("D", "B")):
        return 7
    if upper.startswith(("W",)):
        return 52
    if upper.startswith(("M", "ME")):
        return 12
    if upper.startswith(("Q", "QE")):
        return 4
    return None


def _unfitted_result(
    error: TimeSeriesError | None,
    *,
    configuration: _Configuration,
) -> TimeSeriesResult:
    """Build a result without series data, retaining the configuration context.

    `error` is `None` only for the configuration-only result returned by
    `initialize_time_series`.
    """
    return TimeSeriesResult(
        datetime_column=configuration.datetime_column,
        value_column=configuration.value_column,
        available_datetime_columns=configuration.available_datetime_columns,
        available_value_columns=configuration.available_value_columns,
        resample_frequency=configuration.resample_frequency,
        detected_frequency=None,
        seasonal_period=configuration.seasonal_period,
        decomposition_model=configuration.decomposition_model,
        source_rows=configuration.source_rows,
        invalid_rows=0,
        duplicate_rows=0,
        timestamps=(),
        values=(),
        acf_values=(),
        trend=(),
        seasonal=(),
        residual=(),
        diagnostics_note=None,
        decomposition_note=None,
        error=error,
    )


def _detect_frequency(index: pd.DatetimeIndex) -> str | None:
    """Infer a regular frequency without allowing pandas to raise for short input."""
    if len(index) < MIN_OBSERVATIONS:
        return None
    try:
        return pd.infer_freq(index)
    except ValueError:
        return None


def _prepared_series(
    df: pd.DataFrame,
    datetime_column: str,
    value_column: str,
    resample_frequency: str | None,
) -> tuple[pd.Series, int, int]:
    """Return an ordered mean-aggregated series and input row diagnostics."""
    raw_timestamps = pd.to_datetime(df[datetime_column], errors="coerce")
    raw_values = pd.to_numeric(df[value_column], errors="coerce")
    valid = raw_timestamps.notna() & raw_values.notna() & np.isfinite(raw_values)
    invalid_rows = int((~valid).sum())
    prepared = pd.DataFrame({"timestamp": raw_timestamps[valid], "value": raw_values[valid]})
    duplicate_rows = len(prepared) - prepared["timestamp"].nunique()
    series = prepared.groupby("timestamp", sort=True)["value"].mean()
    series.index = pd.DatetimeIndex(series.index)
    if resample_frequency is not None:
        series = series.resample(resample_frequency).mean()
    return series, invalid_rows, duplicate_rows


def _diagnostics(
    series: pd.Series,
    frequency: str | None,
) -> tuple[tuple[float, ...], str | None]:
    """Compute ACF only for a complete, regularly sampled series."""
    values = series.to_numpy(dtype=float)
    if frequency is None:
        return (), "The autocorrelation requires a regular time frequency."
    if bool(np.isnan(values).any()):
        return (), "The autocorrelation is unavailable while the series has gaps."
    lags = min(MAX_ACF_LAGS, len(values) // 2)
    coefficients = np.asarray(acf(values, nlags=lags, fft=True), dtype=float)
    return tuple(float(value) for value in coefficients[1:]), None


def _decomposition(
    series: pd.Series,
    frequency: str | None,
    seasonal_period: int | None,
    model: DecompositionModel,
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...], str | None]:
    """Decompose a complete regular series, otherwise return an explanation."""
    values = series.to_numpy(dtype=float)
    if frequency is None:
        return (), (), (), "Seasonal decomposition requires a regular time frequency."
    if bool(np.isnan(values).any()):
        return (), (), (), "Seasonal decomposition is unavailable while the series has gaps."
    if seasonal_period is None:
        return (), (), (), "No seasonal period could be detected; choose one to decompose the series."
    if len(values) < MIN_SEASONAL_CYCLES * seasonal_period:
        return (), (), (), "Seasonal decomposition needs at least two complete seasonal cycles."
    if model is DecompositionModel.MULTIPLICATIVE and bool(np.any(values <= 0)):
        return (), (), (), "Multiplicative decomposition requires all values to be greater than zero."

    result = seasonal_decompose(series, model=model.value, period=seasonal_period, extrapolate_trend=0)
    return (
        tuple(float(value) for value in result.trend.to_numpy(dtype=float)),
        tuple(float(value) for value in result.seasonal.to_numpy(dtype=float)),
        tuple(float(value) for value in result.resid.to_numpy(dtype=float)),
        None,
    )


def initialize_time_series(df: pd.DataFrame) -> TimeSeriesResult:
    """Return the default time-series configuration without analyzing a series.

    Only column metadata is inspected, so this is cheap enough for the GUI
    thread. It lets the configuration be shown before the user applies it.

    Args:
        df: DataFrame to inspect. Never mutated.

    Returns:
        A result without series data, selecting the first datetime and
        numeric columns. Its `error` is `NO_DATETIME_COLUMN` or
        `NO_NUMERIC_COLUMN` when the dataset lacks either, and `None`
        otherwise.
    """
    available_dates = datetime_columns(df)
    available_values = numeric_columns(df)
    configuration = _Configuration(
        datetime_column=available_dates[0] if available_dates else "",
        value_column=available_values[0] if available_values else "",
        available_datetime_columns=available_dates,
        available_value_columns=available_values,
        resample_frequency=None,
        seasonal_period=None,
        decomposition_model=DecompositionModel.ADDITIVE,
        source_rows=len(df),
    )
    error: TimeSeriesError | None = None
    if not available_dates:
        error = TimeSeriesError.NO_DATETIME_COLUMN
    elif not available_values:
        error = TimeSeriesError.NO_NUMERIC_COLUMN
    return _unfitted_result(error, configuration=configuration)


def analyze_time_series(
    df: pd.DataFrame,
    datetime_column: str | None = None,
    value_column: str | None = None,
    *,
    resample_frequency: str | None = None,
    seasonal_period: int | None = None,
    decomposition_model: DecompositionModel = DecompositionModel.ADDITIVE,
) -> TimeSeriesResult:
    """Prepare and analyze one numeric time series.

    Duplicate timestamps are averaged. The original timestamps are preserved
    unless an explicit resampling frequency is supplied. Resampling creates
    missing periods as gaps; diagnostics and decomposition deliberately do
    not impute them.

    Args:
        df: DataFrame to analyze. Never mutated.
        datetime_column: Native datetime column, defaulting to the first.
        value_column: Numeric value column, defaulting to the first.
        resample_frequency: Optional pandas offset alias to aggregate to.
        seasonal_period: Optional observations per seasonal cycle.
        decomposition_model: Additive or multiplicative decomposition.

    Returns:
        Prepared values and available diagnostics, or a structured error.
    """
    available_dates = datetime_columns(df)
    available_values = numeric_columns(df)
    date_column = datetime_column if datetime_column is not None else (available_dates[0] if available_dates else "")
    numeric_column = value_column if value_column is not None else (available_values[0] if available_values else "")
    configuration = _Configuration(
        datetime_column=date_column,
        value_column=numeric_column,
        available_datetime_columns=available_dates,
        available_value_columns=available_values,
        resample_frequency=resample_frequency,
        seasonal_period=seasonal_period,
        decomposition_model=decomposition_model,
        source_rows=len(df),
    )

    if not available_dates:
        return _unfitted_result(TimeSeriesError.NO_DATETIME_COLUMN, configuration=configuration)
    if not available_values:
        return _unfitted_result(TimeSeriesError.NO_NUMERIC_COLUMN, configuration=configuration)
    if date_column not in available_dates:
        return _unfitted_result(TimeSeriesError.INVALID_DATETIME_COLUMN, configuration=configuration)
    if numeric_column not in available_values:
        return _unfitted_result(TimeSeriesError.INVALID_VALUE_COLUMN, configuration=configuration)
    if seasonal_period is not None and seasonal_period < MIN_SEASONAL_PERIOD:
        return _unfitted_result(TimeSeriesError.INVALID_SEASONAL_PERIOD, configuration=configuration)

    try:
        series, invalid_rows, duplicate_rows = _prepared_series(df, date_column, numeric_column, resample_frequency)
    except ValueError:
        return _unfitted_result(TimeSeriesError.INVALID_FREQUENCY, configuration=configuration)
    if len(series) < MIN_OBSERVATIONS:
        return _unfitted_result(TimeSeriesError.NOT_ENOUGH_OBSERVATIONS, configuration=configuration)

    index = pd.DatetimeIndex(series.index)
    detected_frequency = resample_frequency if resample_frequency is not None else _detect_frequency(index)
    period = seasonal_period if seasonal_period is not None else _default_period(detected_frequency)
    acf_values, diagnostics_note = _diagnostics(series, detected_frequency)
    trend, seasonal, residual, decomposition_note = _decomposition(
        series,
        detected_frequency,
        period,
        decomposition_model,
    )
    return TimeSeriesResult(
        datetime_column=date_column,
        value_column=numeric_column,
        available_datetime_columns=available_dates,
        available_value_columns=available_values,
        resample_frequency=resample_frequency,
        detected_frequency=detected_frequency,
        seasonal_period=period,
        decomposition_model=decomposition_model,
        source_rows=len(df),
        invalid_rows=invalid_rows,
        duplicate_rows=duplicate_rows,
        timestamps=tuple(series.index),
        values=tuple(float(value) for value in series.to_numpy(dtype=float)),
        acf_values=acf_values,
        trend=trend,
        seasonal=seasonal,
        residual=residual,
        diagnostics_note=diagnostics_note,
        decomposition_note=decomposition_note,
        error=None,
    )
