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

import pandas as pd

from expo_jbm329.services.analysis.columns import numeric_columns
from expo_jbm329.services.analysis.group_comparison import MAX_GROUPS
from expo_jbm329.services.analysis.normality import shapiro_normality
from expo_jbm329.services.data_operations.dtypes import SemanticDType, classify_series_dtype
from expo_jbm329.services.data_profile.column_data_profile import profile_series

_NAN = float("nan")
_NORMALITY_SIGNIFICANCE_LEVEL = 0.05
_MIN_SHAPIRO_OBSERVATIONS = 3
_CATEGORICAL_DTYPES = frozenset({SemanticDType.BOOL, SemanticDType.STRING, SemanticDType.CATEGORY})


class DescriptiveSummaryMethod(StrEnum):
    """Presentation method for one continuous variable in a baseline table."""

    MEAN_SD = "mean_sd"
    MEDIAN_IQR = "median_iqr"


class StatisticsExportTable(StrEnum):
    """Statistics tables available for export."""

    CONTINUOUS = "Continuous"
    CATEGORICAL = "Categorical"
    CHARTS = "Charts"


class StatisticsExportFormat(StrEnum):
    """File formats supported for Statistics exports."""

    CSV = "csv"
    EXCEL = "excel"
    BINARY = "binary"


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


@dataclass(frozen=True, slots=True)
class StatisticsExportRequest:
    """An export selection tied to the exact displayed Statistics result."""

    result: DescriptiveStatisticsResult
    tables: tuple[StatisticsExportTable, ...]
    format: StatisticsExportFormat


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


def has_summary_recommendation(stats: ColumnDescriptiveStatistics) -> bool:
    """Return whether the Shapiro-Wilk result supports a summary recommendation."""
    return (
        stats.count >= _MIN_SHAPIRO_OBSERVATIONS
        and stats.minimum < stats.maximum
        and math.isfinite(stats.shapiro_statistic)
        and math.isfinite(stats.shapiro_p_value)
        and 0 <= stats.shapiro_p_value <= 1
    )


def statistics_export_tables(
    result: DescriptiveStatisticsResult,
    tables: tuple[StatisticsExportTable, ...],
) -> dict[str, pd.DataFrame]:
    """Build independent, typed tables from a displayed Statistics snapshot.

    Args:
        result: The immutable statistics result currently displayed.
        tables: Distinct Continuous and/or Categorical table selections.
            Charts are rendered separately and are not DataFrame sheets.

    Returns:
        Ordered named frames containing raw numeric values and machine-readable
        recommendation fields.

    Raises:
        ValueError: If a table selection is empty, repeated, unsupported, or
            unavailable in the result.
    """
    if not tables or len(set(tables)) != len(tables):
        message = "Select distinct Statistics tables."
        raise ValueError(message)
    frames: dict[str, pd.DataFrame] = {}
    for table in tables:
        if table is StatisticsExportTable.CHARTS:
            message = "Charts are workbook content, not a Statistics table."
            raise ValueError(message)
        if table is StatisticsExportTable.CONTINUOUS:
            if not result.columns:
                message = "Continuous Statistics are unavailable."
                raise ValueError(message)
            frames[table.value] = _continuous_export_frame(result)
        elif table is StatisticsExportTable.CATEGORICAL:
            if not result.categorical_columns:
                message = "Categorical Statistics are unavailable."
                raise ValueError(message)
            frames[table.value] = _categorical_export_frame(result)
        else:
            message = "Unsupported Statistics table."
            raise ValueError(message)
    return frames


def _continuous_export_frame(result: DescriptiveStatisticsResult) -> pd.DataFrame:
    """Build the numeric, unformatted continuous summary table."""
    columns = (
        "column",
        "count",
        "missing_count",
        "missing_fraction",
        "mean",
        "median",
        "std",
        "variance",
        "minimum",
        "maximum",
        "range",
        "q1",
        "q3",
        "iqr",
        "skewness",
        "kurtosis",
        "mean_sd_summary",
        "median_iqr_summary",
        "shapiro_statistic",
        "shapiro_p_value",
        "recommended_summary_method",
    )
    rows: list[tuple[object, ...]] = []
    for stats in result.columns:
        recommendation = recommended_summary_method(stats).value if has_summary_recommendation(stats) else pd.NA
        mean_sd = f"{stats.mean:g} ± {stats.std:g}" if math.isfinite(stats.mean) and math.isfinite(stats.std) else ""
        median_iqr = (
            f"{stats.median:g} ({stats.q1:g} to {stats.q3:g})"
            if all(math.isfinite(value) for value in (stats.median, stats.q1, stats.q3))
            else ""
        )
        rows.append((
            stats.column,
            stats.count,
            stats.missing_count,
            stats.missing_fraction,
            stats.mean,
            stats.median,
            stats.std,
            stats.variance,
            stats.minimum,
            stats.maximum,
            stats.range,
            stats.q1,
            stats.q3,
            stats.iqr,
            stats.skewness,
            stats.kurtosis,
            mean_sd,
            median_iqr,
            stats.shapiro_statistic,
            stats.shapiro_p_value,
            recommendation,
        ))
    frame = pd.DataFrame(rows, columns=columns)
    return frame.astype({
        "column": pd.StringDtype(),
        "count": "int64",
        "missing_count": "int64",
        "missing_fraction": "float64",
        "mean": "float64",
        "median": "float64",
        "std": "float64",
        "variance": "float64",
        "minimum": "float64",
        "maximum": "float64",
        "range": "float64",
        "q1": "float64",
        "q3": "float64",
        "iqr": "float64",
        "skewness": "float64",
        "kurtosis": "float64",
        "mean_sd_summary": pd.StringDtype(),
        "median_iqr_summary": pd.StringDtype(),
        "shapiro_statistic": "float64",
        "shapiro_p_value": "float64",
        "recommended_summary_method": pd.StringDtype(),
    })


def _categorical_export_frame(result: DescriptiveStatisticsResult) -> pd.DataFrame:
    """Build one row per category, retaining denominator and missing data."""
    rows: list[tuple[object, ...]] = []
    for column in result.categorical_columns:
        if column.frequencies:
            rows.extend(
                (
                    column.column,
                    frequency.value,
                    frequency.count,
                    frequency.fraction,
                    column.count,
                    column.missing_count,
                    column.missing_fraction,
                )
                for frequency in column.frequencies
            )
        else:
            rows.append((
                column.column,
                pd.NA,
                0,
                math.nan,
                column.count,
                column.missing_count,
                column.missing_fraction,
            ))
    frame = pd.DataFrame(
        rows,
        columns=(
            "column",
            "value",
            "count",
            "fraction",
            "valid_count",
            "missing_count",
            "missing_fraction",
        ),
    )
    return frame.astype({
        "column": pd.StringDtype(),
        "value": pd.StringDtype(),
        "count": "int64",
        "fraction": "float64",
        "valid_count": "int64",
        "missing_count": "int64",
        "missing_fraction": "float64",
    })


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
