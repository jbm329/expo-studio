"""Paired comparisons for repeated measurements stored in wide form.

Each row represents one subject and each selected numeric column represents
one measurement occasion. Rows missing any selected measurement are excluded
as complete subjects before applying a paired test.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd
from scipy.stats import friedmanchisquare, wilcoxon

from expo_jbm329.services.analysis.columns import numeric_columns

_NAN = float("nan")
_MIN_OCCASIONS = 2
_MIN_FRIEDMAN_SUBJECTS = 3
MAX_PAIRED_TRAJECTORIES = 200
_PLOT_SEED = 0


class PairedComparisonError(StrEnum):
    """Reasons a paired comparison could not be computed."""

    NOT_ENOUGH_COLUMNS = "not_enough_columns"
    INVALID_COLUMN = "invalid_column"
    NOT_ENOUGH_COMPLETE_SUBJECTS = "not_enough_complete_subjects"
    NO_DIFFERENCES = "no_differences"
    NO_VARIATION = "no_variation"


class PairedComparisonMethod(StrEnum):
    """Paired test selected from the number of measurement occasions."""

    WILCOXON = "wilcoxon"
    FRIEDMAN = "friedman"


@dataclass(frozen=True, slots=True)
class PairedOccasionSummary:
    """Full complete-case distribution for one occasion; whiskers are min/max."""

    column: str
    count: int
    mean: float
    median: float
    std: float
    q1: float
    q3: float
    minimum: float
    maximum: float


@dataclass(frozen=True, slots=True)
class PairedPlotData:
    """Aligned subject trajectories in selected occasion order, capped for display."""

    trajectories: tuple[tuple[float, ...], ...]
    sampled: bool


@dataclass(frozen=True, slots=True)
class PairedComparisonResult:
    """Result of a Wilcoxon signed-rank or Friedman repeated-measures test."""

    columns: tuple[str, ...]
    available_numeric_columns: tuple[str, ...]
    method: PairedComparisonMethod | None
    total_subjects: int
    complete_subjects: int
    excluded_subjects: int
    statistic: float
    p_value: float
    kendall_w: float
    error: PairedComparisonError | None
    summaries: tuple[PairedOccasionSummary, ...] = ()
    plot_data: PairedPlotData | None = None


def _empty_result(
    *,
    columns: tuple[str, ...],
    available: tuple[str, ...],
    error: PairedComparisonError,
    total_subjects: int,
) -> PairedComparisonResult:
    """Build a structured result for a comparison that could not be computed."""
    return PairedComparisonResult(
        columns=columns,
        available_numeric_columns=available,
        method=None,
        total_subjects=total_subjects,
        complete_subjects=0,
        excluded_subjects=total_subjects,
        statistic=_NAN,
        p_value=_NAN,
        kendall_w=_NAN,
        error=error,
    )


def initialize_paired_comparison(df: pd.DataFrame) -> PairedComparisonResult:
    """Return default paired-test column metadata without running a test.

    The first two numeric columns are selected when available. This metadata
    initializer is intentionally inexpensive for use by the GUI thread.

    Args:
        df: DataFrame whose numeric columns should populate the configuration.

    Returns:
        An unfitted result. `error` is set when fewer than two numeric columns
        are available.
    """
    available = numeric_columns(df)
    selected = available[:_MIN_OCCASIONS]
    if len(selected) < _MIN_OCCASIONS:
        return _empty_result(
            columns=selected,
            available=available,
            error=PairedComparisonError.NOT_ENOUGH_COLUMNS,
            total_subjects=len(df),
        )
    return PairedComparisonResult(
        columns=selected,
        available_numeric_columns=available,
        method=PairedComparisonMethod.WILCOXON,
        total_subjects=len(df),
        complete_subjects=0,
        excluded_subjects=0,
        statistic=_NAN,
        p_value=_NAN,
        kendall_w=_NAN,
        error=None,
    )


def analyze_paired_comparison(
    df: pd.DataFrame,
    columns: tuple[str, ...] | list[str],
) -> PairedComparisonResult:
    """Compare repeated measurements from selected wide-form numeric columns.

    The test is selected by the number of measurement occasions: Wilcoxon
    signed-rank for two columns and Friedman for three or more. Subjects with
    missing or non-finite values in any selected occasion are excluded.

    Args:
        df: DataFrame with one subject per row. Never mutated.
        columns: Ordered numeric measurement columns, from earliest to latest
            or in the desired comparison order.

    Returns:
        Paired test results and complete/excluded subject counts, or a
        structured error for invalid or insufficient data.
    """
    selected = tuple(columns)
    available = numeric_columns(df)
    if len(selected) < _MIN_OCCASIONS:
        return _empty_result(
            columns=selected,
            available=available,
            error=PairedComparisonError.NOT_ENOUGH_COLUMNS,
            total_subjects=len(df),
        )
    if len(set(selected)) != len(selected) or any(column not in available for column in selected):
        return _empty_result(
            columns=selected,
            available=available,
            error=PairedComparisonError.INVALID_COLUMN,
            total_subjects=len(df),
        )

    measurements = df.loc[:, list(selected)].apply(pd.to_numeric, errors="coerce")
    measurements = measurements.replace([np.inf, -np.inf], _NAN)
    complete = measurements.dropna()
    complete_count = len(complete)
    excluded_count = len(df) - complete_count
    method = PairedComparisonMethod.WILCOXON if len(selected) == _MIN_OCCASIONS else PairedComparisonMethod.FRIEDMAN

    if method is PairedComparisonMethod.FRIEDMAN and complete_count < _MIN_FRIEDMAN_SUBJECTS:
        return _result_with_error(
            selected,
            available,
            method,
            total_subjects=len(df),
            complete_subjects=complete_count,
            excluded_subjects=excluded_count,
            error=PairedComparisonError.NOT_ENOUGH_COMPLETE_SUBJECTS,
        )
    if complete_count == 0:
        return _result_with_error(
            selected,
            available,
            method,
            total_subjects=len(df),
            complete_subjects=0,
            excluded_subjects=excluded_count,
            error=PairedComparisonError.NOT_ENOUGH_COMPLETE_SUBJECTS,
        )

    arrays = [complete[column].to_numpy(dtype=np.float64) for column in selected]
    if method is PairedComparisonMethod.WILCOXON:
        differences = arrays[0] - arrays[1]
        if not np.any(differences):
            return _result_with_error(
                selected,
                available,
                method,
                total_subjects=len(df),
                complete_subjects=complete_count,
                excluded_subjects=excluded_count,
                error=PairedComparisonError.NO_DIFFERENCES,
            )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            test_result = wilcoxon(arrays[0], arrays[1], alternative="two-sided")
        statistic = float(test_result.statistic)  # pyright: ignore[reportAttributeAccessIssue]
        p_value = float(test_result.pvalue)  # pyright: ignore[reportAttributeAccessIssue]
        kendall_w = _NAN
    else:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            test_result = friedmanchisquare(*arrays)
        statistic = float(test_result.statistic)  # pyright: ignore[reportAttributeAccessIssue]
        p_value = float(test_result.pvalue)  # pyright: ignore[reportAttributeAccessIssue]
        kendall_w = statistic / (complete_count * (len(selected) - 1))
        if math.isnan(statistic) or math.isnan(p_value):
            return _result_with_error(
                selected,
                available,
                method,
                total_subjects=len(df),
                complete_subjects=complete_count,
                excluded_subjects=excluded_count,
                error=PairedComparisonError.NO_VARIATION,
            )

    return PairedComparisonResult(
        columns=selected,
        available_numeric_columns=available,
        method=method,
        total_subjects=len(df),
        complete_subjects=complete_count,
        excluded_subjects=excluded_count,
        statistic=statistic,
        p_value=p_value,
        kendall_w=kendall_w,
        error=None,
        summaries=tuple(_occasion_summary(column, complete[column]) for column in selected),
        plot_data=_plot_data(complete),
    )


def _occasion_summary(column: str, values: pd.Series) -> PairedOccasionSummary:
    """Summarize all complete subjects, with sample SD unavailable for one subject."""
    return PairedOccasionSummary(
        column=column,
        count=len(values),
        mean=float(values.mean()),
        median=float(values.median()),
        std=float(values.std(ddof=1)) if len(values) > 1 else _NAN,
        q1=float(values.quantile(0.25)),
        q3=float(values.quantile(0.75)),
        minimum=float(values.min()),
        maximum=float(values.max()),
    )


def _plot_data(complete: pd.DataFrame) -> PairedPlotData:
    """Sample rows, never occasions independently, without changing test statistics."""
    count = len(complete)
    if count > MAX_PAIRED_TRAJECTORIES:
        rng = np.random.default_rng(_PLOT_SEED)
        indices = np.sort(rng.choice(count, size=MAX_PAIRED_TRAJECTORIES, replace=False))
        plotted = complete.iloc[indices]
    else:
        plotted = complete
    return PairedPlotData(
        trajectories=tuple(tuple(float(value) for value in row) for row in plotted.itertuples(index=False, name=None)),
        sampled=count > MAX_PAIRED_TRAJECTORIES,
    )


def _result_with_error(
    columns: tuple[str, ...],
    available: tuple[str, ...],
    method: PairedComparisonMethod,
    *,
    total_subjects: int,
    complete_subjects: int,
    excluded_subjects: int,
    error: PairedComparisonError,
) -> PairedComparisonResult:
    """Build a failed-fit result while preserving complete-case counts."""
    return PairedComparisonResult(
        columns=columns,
        available_numeric_columns=available,
        method=method,
        total_subjects=total_subjects,
        complete_subjects=complete_subjects,
        excluded_subjects=excluded_subjects,
        statistic=_NAN,
        p_value=_NAN,
        kendall_w=_NAN,
        error=error,
    )
