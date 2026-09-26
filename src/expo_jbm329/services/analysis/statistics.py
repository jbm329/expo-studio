"""Dataset-wide Descriptive Statistics analysis.

Aggregates per-column numeric statistics (mean/median/std/variance/min/max/
range/quartiles/IQR/skewness/kurtosis/count/missing) across every numeric
column in a DataFrame, plus per-column histogram data for distribution
charts and a Shapiro-Wilk normality test. Reuses
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
import warnings
from dataclasses import dataclass

import pandas as pd
from scipy.stats import shapiro

from expo_jbm329.services.data_operations.dtypes import SemanticDType, classify_series_dtype
from expo_jbm329.services.data_profile.column_data_profile import profile_series

_NUMERIC_DTYPES = frozenset({SemanticDType.INT, SemanticDType.FLOAT})
_NAN = float("nan")

# scipy.stats.shapiro's own documented threshold beyond which its computed
# p-value may not be accurate. Surfaced explicitly as a UI caveat (see
# gui/dialogs/analysis/statistics_view.py) instead of scipy's internal
# warning, which we deliberately suppress in `_shapiro_normality`.
SHAPIRO_LARGE_SAMPLE_THRESHOLD = 5000


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


def _shapiro_normality(series: pd.Series) -> tuple[float, float]:
    """Run the Shapiro-Wilk normality test on a column's numeric values.

    Args:
        series: The raw column values (any dtype coercible to numeric).

    Returns:
        A ``(statistic, p_value)`` tuple. Both are NaN when scipy cannot
        compute a result (e.g. fewer than 3 valid values).
    """
    values = pd.to_numeric(series, errors="coerce").replace([float("inf"), float("-inf")], _NAN).dropna()

    with warnings.catch_warnings():
        # scipy warns about reduced accuracy for large samples and about
        # degenerate (zero-range) input. Both are surfaced explicitly as UI
        # caveats (see StatisticsView) instead of as noisy warnings here.
        warnings.simplefilter("ignore")
        result = shapiro(values)

    return float(result.statistic), float(result.pvalue)


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
    """Dataset-wide descriptive statistics for every numeric column.

    Attributes:
        columns: Per-column statistics, in the DataFrame's original column
            order. Empty when the DataFrame has no numeric columns.
    """

    columns: tuple[ColumnDescriptiveStatistics, ...]


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

    shapiro_statistic, shapiro_p_value = _shapiro_normality(df[column])

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


def analyze_descriptive_statistics(df: pd.DataFrame) -> DescriptiveStatisticsResult:
    """Compute dataset-wide descriptive statistics for every numeric column.

    Args:
        df: The DataFrame to analyze. Never mutated.

    Returns:
        A populated `DescriptiveStatisticsResult`, with one entry per
        numeric column (int or float), in the DataFrame's original column
        order. Empty if the DataFrame has no numeric columns.
    """
    columns = tuple(
        _column_statistics(df, str(column))
        for column in df.columns
        if classify_series_dtype(df[column]) in _NUMERIC_DTYPES
    )
    return DescriptiveStatisticsResult(columns=columns)
