"""Univariate outlier detection (IQR fences, Z-score, modified Z-score).

Each numeric column is screened on its own. Every method reduces to a
pair of fences in the column's own units; values strictly outside them
are flagged as *potential* outliers. Flagging never implies that a value
is an error - that judgement is left to the user.

- IQR (Tukey's fences): ``Q1 - k * IQR`` and ``Q3 + k * IQR``.
- Z-score: ``|x - mean| / sd > t`` (sample standard deviation).
- Modified Z-score (Iglewicz & Hoaglin): ``0.6745 * |x - median| / MAD > t``.
  When the MAD is zero (more than half the values are identical), the
  mean absolute deviation is used instead, scaled by 1.253314 - the IBM
  SPSS convention - so the score stays defined.

Missing and infinite values are ignored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from expo_jbm329.services.analysis.columns import numeric_columns

if TYPE_CHECKING:
    from collections.abc import Callable

_NAN = float("nan")


class OutlierMethod(StrEnum):
    """How potential outliers are identified."""

    IQR = "iqr"
    Z_SCORE = "z_score"
    MODIFIED_Z_SCORE = "modified_z_score"


# Conventional defaults: Tukey's 1.5 IQR fences, |z| > 3 and the
# Iglewicz-Hoaglin |modified z| > 3.5.
DEFAULT_THRESHOLDS: dict[OutlierMethod, float] = {
    OutlierMethod.IQR: 1.5,
    OutlierMethod.Z_SCORE: 3.0,
    OutlierMethod.MODIFIED_Z_SCORE: 3.5,
}
MIN_THRESHOLD = 0.1
MAX_THRESHOLD = 100.0

# Fewer values than this give no meaningful spread estimate.
MIN_OBSERVATIONS = 3
# The most extreme flagged rows listed in a column's detail.
MAX_EXTREME_OBSERVATIONS = 100
HISTOGRAM_BINS = 50

# 0.6745 is the 0.75 quantile of the standard normal distribution, making
# MAD / 0.6745 a consistent estimator of the standard deviation.
_MAD_CONSISTENCY = 0.6745
# sqrt(pi / 2): scales the mean absolute deviation to the standard
# deviation of a normal distribution (fallback when the MAD is zero).
_MEAN_AD_CONSISTENCY = 1.253314


class OutlierError(StrEnum):
    """Reasons an outlier analysis could not be computed.

    Kept UI-text-free (a plain reason code) so the GUI layer owns
    translation, matching the other analysis services.
    """

    NO_NUMERIC_COLUMN = "no_numeric_column"
    INVALID_COLUMN = "invalid_column"
    INVALID_THRESHOLD = "invalid_threshold"


class ColumnOutlierStatus(StrEnum):
    """Reasons a single column could not be screened."""

    NOT_ENOUGH_OBSERVATIONS = "not_enough_observations"
    ZERO_SPREAD = "zero_spread"


@dataclass(frozen=True, slots=True)
class ColumnOutlierSummary:
    """Outlier counts and fences for one numeric column.

    Attributes:
        column: The column name.
        n: Number of finite values screened.
        missing: Number of missing or infinite values (ignored).
        outlier_count: Values outside the fences.
        low_count: Values below the lower fence.
        high_count: Values above the upper fence.
        lower_fence: The lower fence, in the column's units (NaN when
            `status` is set).
        upper_fence: The upper fence, in the column's units (NaN when
            `status` is set).
        status: Why the column could not be screened, or `None`.
    """

    column: str
    n: int
    missing: int
    outlier_count: int
    low_count: int
    high_count: int
    lower_fence: float
    upper_fence: float
    status: ColumnOutlierStatus | None

    @property
    def outlier_fraction(self) -> float:
        """Return the share of screened values that are outliers (NaN without values)."""
        return self.outlier_count / self.n if self.n else _NAN


@dataclass(frozen=True, slots=True)
class OutlierSummaryResult:
    """Outlier screening of every numeric column.

    Attributes:
        method: The detection method.
        threshold: The method's threshold (IQR multiplier or score limit).
        available_columns: Every numeric column, in dataset order.
        columns: One summary per numeric column, ranked by outlier
            fraction (highest first; unscreenable columns last), ties in
            dataset order.
        row_count: Rows in the dataset.
        rows_with_outliers: Rows with an outlier in at least one column.
        error: A structured reason nothing was computed, or `None`.
    """

    method: OutlierMethod
    threshold: float
    available_columns: tuple[str, ...]
    columns: tuple[ColumnOutlierSummary, ...]
    row_count: int
    rows_with_outliers: int
    error: OutlierError | None


@dataclass(frozen=True, slots=True)
class ExtremeObservation:
    """One flagged row of a column's detail.

    Attributes:
        row_number: 1-based position of the row in the dataset.
        value: The column's value in that row.
        score: Z or modified Z score; for IQR, the signed distance past
            the nearest fence in the column's units.
        row_values: The row's value in every column of `OutlierColumnDetail.row_columns`.
    """

    row_number: int
    value: float
    score: float
    row_values: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class OutlierColumnDetail:
    """Detailed outlier screening of one column.

    Attributes:
        method: The detection method.
        threshold: The method's threshold.
        summary: The column's counts and fences.
        mean: Mean of the screened values.
        std: Sample standard deviation.
        median: Median.
        q1: First quartile.
        q3: Third quartile.
        mad: Median absolute deviation (unscaled).
        scale: The spread the score divides by (sd for Z-score, scaled
            MAD or mean absolute deviation for modified Z, IQR for IQR).
        mad_fallback: Whether the modified Z-score used the mean absolute
            deviation because the MAD is zero.
        histogram_edges: `HISTOGRAM_BINS + 1` bin edges over all values.
        inlier_counts: Per-bin count of values inside the fences.
        outlier_counts: Per-bin count of values outside the fences.
        row_columns: Every dataset column, for `ExtremeObservation.row_values`.
        extremes: Up to `MAX_EXTREME_OBSERVATIONS` flagged rows, most
            extreme first.
        error: A structured reason nothing was computed, or `None`.
    """

    method: OutlierMethod
    threshold: float
    summary: ColumnOutlierSummary
    mean: float
    std: float
    median: float
    q1: float
    q3: float
    mad: float
    scale: float
    mad_fallback: bool
    histogram_edges: tuple[float, ...]
    inlier_counts: tuple[int, ...]
    outlier_counts: tuple[int, ...]
    row_columns: tuple[str, ...]
    extremes: tuple[ExtremeObservation, ...]
    error: OutlierError | None


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Screening:
    """Fences and per-row scores of one column."""

    finite: np.ndarray  # finite values only
    positions: np.ndarray  # their 0-based row positions in the dataset
    lower: float
    upper: float
    scores: np.ndarray
    scale: float
    mad_fallback: bool
    status: ColumnOutlierStatus | None


def _finite_values(series: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Return the column's finite values as float64 and their row positions."""
    raw = pd.to_numeric(series, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
    positions = np.flatnonzero(np.isfinite(raw))
    return raw[positions], positions


def _unscreened(values: np.ndarray, positions: np.ndarray, status: ColumnOutlierStatus) -> _Screening:
    return _Screening(values, positions, _NAN, _NAN, np.zeros(len(values)), _NAN, mad_fallback=False, status=status)


def _screen(series: pd.Series, method: OutlierMethod, threshold: float) -> _Screening:
    """Compute a column's fences and scores with `method`."""
    array, positions = _finite_values(series)
    if len(array) < MIN_OBSERVATIONS:
        return _unscreened(array, positions, ColumnOutlierStatus.NOT_ENOUGH_OBSERVATIONS)

    match method:
        case OutlierMethod.IQR:
            q1, q3 = (float(q) for q in np.quantile(array, [0.25, 0.75]))
            iqr = q3 - q1
            lower, upper = q1 - threshold * iqr, q3 + threshold * iqr
            scores = np.where(array < lower, array - lower, np.where(array > upper, array - upper, 0.0))
            return _Screening(array, positions, lower, upper, scores, iqr, mad_fallback=False, status=None)
        case OutlierMethod.Z_SCORE:
            center = float(array.mean())
            scale = float(array.std(ddof=1))
            fallback = False
        case OutlierMethod.MODIFIED_Z_SCORE:
            center = float(np.median(array))
            deviations = np.abs(array - center)
            mad = float(np.median(deviations))
            fallback = mad == 0.0
            scale = _MEAN_AD_CONSISTENCY * float(deviations.mean()) if fallback else mad / _MAD_CONSISTENCY

    if not scale > 0.0:
        return _unscreened(array, positions, ColumnOutlierStatus.ZERO_SPREAD)
    scores = (array - center) / scale
    return _Screening(
        array, positions, center - threshold * scale, center + threshold * scale, scores, scale, fallback, status=None
    )


def _summary(column: str, series: pd.Series, screening: _Screening) -> ColumnOutlierSummary:
    """Summarize a column's screening."""
    array = screening.finite
    if screening.status is not None:
        low = high = 0
    else:
        low = int((array < screening.lower).sum())
        high = int((array > screening.upper).sum())
    return ColumnOutlierSummary(
        column=column,
        n=len(array),
        missing=len(series) - len(array),
        outlier_count=low + high,
        low_count=low,
        high_count=high,
        lower_fence=screening.lower,
        upper_fence=screening.upper,
        status=screening.status,
    )


def _outlier_mask(screening: _Screening) -> np.ndarray:
    """Return which screened values lie outside the fences."""
    if screening.status is not None:
        return np.zeros(len(screening.finite), dtype=bool)
    return (screening.finite < screening.lower) | (screening.finite > screening.upper)


def _valid_threshold(threshold: float) -> bool:
    return math.isfinite(threshold) and MIN_THRESHOLD <= threshold <= MAX_THRESHOLD


def _rank_key(summary: ColumnOutlierSummary) -> tuple[bool, float]:
    """Sort key: screenable columns first, then by descending outlier fraction."""
    if summary.status is not None:
        return True, 0.0
    return False, -summary.outlier_fraction


def max_possible_z_score(n: int) -> float:
    """Return the largest |z| any of `n` values can reach, ``(n - 1) / sqrt(n)``.

    With few values the sample standard deviation is inflated by the
    outlier itself, so a Z-score threshold above this bound can never
    flag anything.

    Args:
        n: Number of values.

    Returns:
        The bound, or NaN for fewer than two values.
    """
    if n < 2:  # noqa: PLR2004 - a standard deviation needs two values
        return _NAN
    return (n - 1) / math.sqrt(n)


def default_column(result: OutlierSummaryResult) -> str | None:
    """Return the column to detail by default: the top-ranked one, if any.

    Args:
        result: A computed outlier summary.

    Returns:
        The first ranked column, or `None` when there is none.
    """
    return result.columns[0].column if result.columns else None


# ----------------------------------------------------------------------
# Analysis
# ----------------------------------------------------------------------


def analyze_outlier_summary(
    df: pd.DataFrame,
    method: OutlierMethod = OutlierMethod.IQR,
    threshold: float | None = None,
) -> OutlierSummaryResult:
    """Screen every numeric column for potential outliers.

    Args:
        df: The DataFrame to analyze. Never mutated.
        method: The detection method.
        threshold: The method's threshold, or `None` for its default.
            Must be within [`MIN_THRESHOLD`, `MAX_THRESHOLD`].

    Returns:
        Per-column counts and fences, or a result with `error` set.
    """
    chosen_threshold = DEFAULT_THRESHOLDS[method] if threshold is None else threshold
    available = numeric_columns(df)

    def _error(error: OutlierError) -> OutlierSummaryResult:
        return OutlierSummaryResult(method, chosen_threshold, available, (), len(df), 0, error)

    if not available:
        return _error(OutlierError.NO_NUMERIC_COLUMN)
    if not _valid_threshold(chosen_threshold):
        return _error(OutlierError.INVALID_THRESHOLD)

    summaries: list[ColumnOutlierSummary] = []
    flagged_rows = np.zeros(len(df), dtype=bool)
    for column in available:
        series = df[column]
        screening = _screen(series, method, chosen_threshold)
        summaries.append(_summary(column, series, screening))
        mask = _outlier_mask(screening)
        if mask.any():
            flagged_rows[screening.positions[mask]] = True

    ranked = sorted(summaries, key=_rank_key)
    return OutlierSummaryResult(
        method=method,
        threshold=chosen_threshold,
        available_columns=available,
        columns=tuple(ranked),
        row_count=len(df),
        rows_with_outliers=int(flagged_rows.sum()),
        error=None,
    )


def _histogram(screening: _Screening, mask: np.ndarray) -> tuple[tuple[float, ...], tuple[int, ...], tuple[int, ...]]:
    """Return shared bin edges and the inlier/outlier counts per bin."""
    array = screening.finite
    if len(array) == 0:
        return (), (), ()
    edges = np.histogram_bin_edges(array, bins=HISTOGRAM_BINS)
    inliers, _ = np.histogram(array[~mask], bins=edges)
    outliers, _ = np.histogram(array[mask], bins=edges)
    return tuple(float(e) for e in edges), tuple(int(c) for c in inliers), tuple(int(c) for c in outliers)


def _extremes(df: pd.DataFrame, screening: _Screening, mask: np.ndarray) -> tuple[ExtremeObservation, ...]:
    """Return the most extreme flagged rows, most extreme first."""
    flagged = np.flatnonzero(mask)
    if len(flagged) == 0:
        return ()
    scores = screening.scores[flagged]
    # Stable sort keeps dataset order among equally extreme values.
    order = flagged[np.argsort(-np.abs(scores), kind="stable")][:MAX_EXTREME_OBSERVATIONS]
    positions = screening.positions[order]
    rows = df.iloc[positions]
    values = screening.finite
    return tuple(
        ExtremeObservation(
            row_number=int(position) + 1,
            value=float(values[index]),
            score=float(screening.scores[index]),
            row_values=tuple(row),
        )
        for position, index, row in zip(positions, order, rows.itertuples(index=False, name=None), strict=True)
    )


def _statistic(array: np.ndarray, compute: Callable[[np.ndarray], float]) -> float:
    return compute(array) if len(array) else _NAN


def analyze_outlier_column(
    df: pd.DataFrame,
    column: str,
    method: OutlierMethod = OutlierMethod.IQR,
    threshold: float | None = None,
) -> OutlierColumnDetail:
    """Screen one numeric column in detail.

    Args:
        df: The DataFrame to analyze. Never mutated.
        column: The numeric column to screen.
        method: The detection method.
        threshold: The method's threshold, or `None` for its default.

    Returns:
        The column's statistics, histogram and most extreme flagged rows,
        or a result with `error` set.
    """
    chosen_threshold = DEFAULT_THRESHOLDS[method] if threshold is None else threshold
    row_columns = tuple(str(c) for c in df.columns)

    def _error(error: OutlierError) -> OutlierColumnDetail:
        return OutlierColumnDetail(
            method=method,
            threshold=chosen_threshold,
            summary=ColumnOutlierSummary(column, 0, 0, 0, 0, 0, _NAN, _NAN, None),
            mean=_NAN,
            std=_NAN,
            median=_NAN,
            q1=_NAN,
            q3=_NAN,
            mad=_NAN,
            scale=_NAN,
            mad_fallback=False,
            histogram_edges=(),
            inlier_counts=(),
            outlier_counts=(),
            row_columns=row_columns,
            extremes=(),
            error=error,
        )

    if column not in numeric_columns(df):
        return _error(OutlierError.INVALID_COLUMN)
    if not _valid_threshold(chosen_threshold):
        return _error(OutlierError.INVALID_THRESHOLD)

    series = df[column]
    screening = _screen(series, method, chosen_threshold)
    mask = _outlier_mask(screening)
    array = screening.finite
    edges, inliers, outliers = _histogram(screening, mask)
    median = _statistic(array, lambda a: float(np.median(a)))

    return OutlierColumnDetail(
        method=method,
        threshold=chosen_threshold,
        summary=_summary(column, series, screening),
        mean=_statistic(array, lambda a: float(a.mean())),
        std=float(array.std(ddof=1)) if len(array) > 1 else _NAN,
        median=median,
        q1=_statistic(array, lambda a: float(np.quantile(a, 0.25))),
        q3=_statistic(array, lambda a: float(np.quantile(a, 0.75))),
        mad=_statistic(array, lambda a: float(np.median(np.abs(a - median)))),
        scale=screening.scale,
        mad_fallback=screening.mad_fallback,
        histogram_edges=edges,
        inlier_counts=inliers,
        outlier_counts=outliers,
        row_columns=row_columns,
        extremes=_extremes(df, screening, mask),
        error=None,
    )
