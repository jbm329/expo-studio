"""Dataset-wide descriptive summaries for continuous and categorical columns.

Aggregates per-column numeric statistics (mean/median/std/variance/min/max/
range/quartiles/IQR/skewness/kurtosis/count/missing) across every numeric
column in a DataFrame, and categorical level counts and percentages for
low-cardinality columns. Numeric columns also include histogram data for
distribution charts and a Shapiro-Wilk normality test. Reuses
`expo_jbm329.services.data_profile.column_data_profile.profile_series()`'s
existing per-column profiling instead of recomputing statistics from
scratch; `range`/`iqr`/`variance` are derived from that existing output, and
histogram bins/counts are the same ones `profile_series()` already computes
for the single-column "Column Properties" dialog. Boxplots need no extra
computation - they're drawn directly from the existing min/q1/median/q3/max
fields.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from expo_jbm329.services.analysis.columns import numeric_columns
from expo_jbm329.services.analysis.group_comparison import MAX_GROUPS
from expo_jbm329.services.analysis.normality import shapiro_normality
from expo_jbm329.services.data_operations.dtypes import SemanticDType, classify_series_dtype
from expo_jbm329.services.data_profile.column_data_profile import profile_series

if TYPE_CHECKING:
    import pandas as pd

_NAN = float("nan")
_NORMALITY_SIGNIFICANCE_LEVEL = 0.05
_CATEGORICAL_DTYPES = frozenset({SemanticDType.BOOL, SemanticDType.STRING, SemanticDType.CATEGORY})


class DescriptiveSummaryMethod(StrEnum):
    """Presentation method for one continuous variable in a baseline table."""

    MEAN_SD = "mean_sd"
    MEDIAN_IQR = "median_iqr"


@dataclass(frozen=True, slots=True)
class CategoryFrequency:
    """Frequency of one observed level in a categorical column."""

    value: str
    count: int
    fraction: float


@dataclass(frozen=True, slots=True)
class CategoricalColumnStatistics:
    """Frequency and missing-value summary for a categorical column."""

    column: str
    count: int
    missing_count: int
    missing_fraction: float
    frequencies: tuple[CategoryFrequency, ...]


def _as_int(value: object, default: int = 0) -> int:
    """Safely coerce a `ColumnProfile.stats` value (typed as `object`) to int."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return int(value)
    return default


def _as_float(value: object, default: float = _NAN) -> float:
    """Safely coerce a `ColumnProfile.stats` value (typed as `object`) to float."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return float(value)
    return default


@dataclass(frozen=True, slots=True)
class ColumnDescriptiveStatistics:
    """Descriptive statistics for a single numeric column.

    `missing_fraction` is stored as a fraction in the ``[0, 1]`` range,
    matching the input convention expected by
    `expo_jbm329.utils.format_utils.fmt_pct`. Statistic fields are NaN when
    a column has no non-null numeric values.

    Attributes:
        column: Column name.
        count: Non-null value count.
        missing_count: Number of missing (NaN/None) values.
        missing_fraction: Fraction of missing values.
        mean: Arithmetic mean.
        median: Median (50th percentile).
        std: Sample standard deviation.
        variance: Sample variance (``std ** 2``).
        minimum: Minimum value.
        maximum: Maximum value.
        range: ``maximum - minimum``.
        q1: 25th percentile.
        q3: 75th percentile.
        iqr: Interquartile range (``q3 - q1``).
        skewness: Sample skewness.
        kurtosis: Sample kurtosis.
        histogram_bins: Histogram bin edges (``len(histogram_bins) ==
            len(histogram_counts) + 1``). Empty when no histogram could be
            computed (e.g. a fully missing column).
        histogram_counts: Histogram bar heights, one per bin.
        shapiro_statistic: Shapiro-Wilk test statistic (W). NaN when it
            could not be computed (fewer than 3 valid values).
        shapiro_p_value: Shapiro-Wilk p-value for the null hypothesis that
            the data is normally distributed. May be inaccurate when
            `count` exceeds `SHAPIRO_LARGE_SAMPLE_THRESHOLD` (scipy's own
            documented limitation).
    """

    column: str
    count: int
    missing_count: int
    missing_fraction: float
    mean: float
    median: float
    std: float
    variance: float
    minimum: float
    maximum: float
    range: float
    q1: float
    q3: float
    iqr: float
    skewness: float
    kurtosis: float
    histogram_bins: tuple[float, ...]
    histogram_counts: tuple[int, ...]
    shapiro_statistic: float
    shapiro_p_value: float


@dataclass(frozen=True, slots=True)
class DescriptiveStatisticsResult:
    """Dataset-wide descriptive statistics and categorical frequencies.

    Attributes:
        columns: Per-column statistics, in the DataFrame's original column
            order. Empty when the DataFrame has no numeric columns.
        categorical_columns: Frequency summaries for eligible categorical
            columns, in the DataFrame's original column order.
    """

    columns: tuple[ColumnDescriptiveStatistics, ...]
    categorical_columns: tuple[CategoricalColumnStatistics, ...] = ()


def recommended_summary_method(stats: ColumnDescriptiveStatistics) -> DescriptiveSummaryMethod:
    """Choose a presentation default from the Shapiro-Wilk result.

    A non-significant result is only a guide, not proof of normality. When
    Shapiro-Wilk cannot provide a usable p-value, use the median/IQR
    presentation.

    Args:
        stats: Summary statistics for one numeric column.

    Returns:
        Mean/SD when Shapiro-Wilk does not reject normality; median/IQR when
        it does or when no usable p-value is available.
    """
    if math.isnan(stats.shapiro_p_value) or stats.shapiro_p_value < _NORMALITY_SIGNIFICANCE_LEVEL:
        return DescriptiveSummaryMethod.MEDIAN_IQR
    return DescriptiveSummaryMethod.MEAN_SD


def _safe_diff(minuend: float, subtrahend: float) -> float:
    """Return ``minuend - subtrahend``, or NaN if either operand is NaN."""
    if math.isnan(minuend) or math.isnan(subtrahend):
        return _NAN
    return minuend - subtrahend


def _column_statistics(df: pd.DataFrame, column: str) -> ColumnDescriptiveStatistics:
    """Compute descriptive statistics for a single numeric column."""
    profile = profile_series(df[column], name=column)
    stats = profile.stats

    total = _as_int(stats.get("count.n"))
    missing_count = _as_int(stats.get("missing.n"))

    minimum = _as_float(stats.get("num.min"))
    maximum = _as_float(stats.get("num.max"))
    q1 = _as_float(stats.get("num.q1"))
    q3 = _as_float(stats.get("num.q3"))
    std = _as_float(stats.get("num.std"))

    plot_bins = profile.plot.bins
    plot_counts = profile.plot.counts
    has_histogram = profile.plot.kind == "hist" and plot_bins is not None and plot_counts is not None

    shapiro_statistic, shapiro_p_value = shapiro_normality(df[column])

    return ColumnDescriptiveStatistics(
        column=column,
        count=total - missing_count,
        missing_count=missing_count,
        missing_fraction=_as_float(stats.get("missing.pct"), default=0.0),
        mean=_as_float(stats.get("num.mean")),
        median=_as_float(stats.get("num.median")),
        std=std,
        variance=_NAN if math.isnan(std) else std**2,
        minimum=minimum,
        maximum=maximum,
        range=_safe_diff(maximum, minimum),
        q1=q1,
        q3=q3,
        iqr=_safe_diff(q3, q1),
        skewness=_as_float(stats.get("num.skew")),
        kurtosis=_as_float(stats.get("num.kurtosis")),
        histogram_bins=tuple(plot_bins) if has_histogram and plot_bins is not None else (),
        histogram_counts=tuple(plot_counts) if has_histogram and plot_counts is not None else (),
        shapiro_statistic=shapiro_statistic,
        shapiro_p_value=shapiro_p_value,
    )


def _categorical_statistics(df: pd.DataFrame, column: str) -> CategoricalColumnStatistics:
    """Compute non-missing level frequencies for one eligible category."""
    series = df[column]
    count = int(series.count())
    frequencies = tuple(
        CategoryFrequency(
            value=str(value),
            count=int(value_count),
            fraction=float(value_count / count) if count else _NAN,
        )
        for value, value_count in series.value_counts(sort=False, dropna=True).items()
    )
    missing_count = len(series) - count
    return CategoricalColumnStatistics(
        column=column,
        count=count,
        missing_count=missing_count,
        missing_fraction=float(missing_count / len(series)) if len(series) else 0.0,
        frequencies=frequencies,
    )


def _categorical_columns(df: pd.DataFrame) -> tuple[str, ...]:
    """Return low-cardinality categorical and coded-numeric columns."""
    eligible: list[str] = []
    for column in df.columns:
        series = df[column]
        semantic_dtype = classify_series_dtype(series)
        is_categorical = semantic_dtype in _CATEGORICAL_DTYPES
        is_low_cardinality_numeric = semantic_dtype in {SemanticDType.INT, SemanticDType.FLOAT}
        if (is_categorical or is_low_cardinality_numeric) and int(series.nunique(dropna=True)) <= MAX_GROUPS:
            eligible.append(str(column))
    return tuple(eligible)


def analyze_descriptive_statistics(df: pd.DataFrame) -> DescriptiveStatisticsResult:
    """Compute continuous summaries and categorical frequencies for a DataFrame.

    Args:
        df: The DataFrame to analyze. Never mutated.

    Returns:
        A populated `DescriptiveStatisticsResult`, with numeric columns
        summarized as before and eligible low-cardinality columns summarized
        as frequencies. Low-cardinality numeric columns appear in both
        summaries so their continuous statistics remain available.
    """
    columns = tuple(_column_statistics(df, column) for column in numeric_columns(df))
    categorical_names = _categorical_columns(df)
    categorical_columns = tuple(_categorical_statistics(df, column) for column in categorical_names)
    return DescriptiveStatisticsResult(columns=columns, categorical_columns=categorical_columns)
