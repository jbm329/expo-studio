"""Correlation analysis between numeric columns.

Computes a pairwise correlation matrix (Pearson, Spearman or Kendall's
tau-b) with a p-value, a 95% confidence interval and a Holm-adjusted
p-value per pair, plus a detailed view of a single pair (coefficient,
least-squares line and a deterministic scatterplot sample).

Missing values are handled by pairwise deletion: each pair uses every row
where both of its columns have a finite value, and reports its own `n`.
Statistics always use all of those rows; only the scatterplot sample is
capped at `SCATTER_SAMPLE_SIZE` points.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, norm, pearsonr, rankdata

from expo_jbm329.services.analysis.columns import numeric_columns

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

_NAN = float("nan")

MIN_SELECTED_COLUMNS = 2
MAX_SELECTED_COLUMNS = 30
DEFAULT_SELECTED_COLUMNS = 20

# Fewer observations than this make a correlation coefficient meaningless
# (two points always lie on a perfect line).
MIN_OBSERVATIONS = 3

CONFIDENCE_LEVEL = 0.95
SIGNIFICANCE_LEVEL = 0.05

SCATTER_SAMPLE_SIZE = 5_000
# A fixed seed keeps the plotted sample identical across runs.
_SCATTER_SEED = 0

# Cohen's (1988) conventional thresholds for |r|.
WEAK_THRESHOLD = 0.1
MODERATE_THRESHOLD = 0.3
STRONG_THRESHOLD = 0.5

# Fisher z standard errors per method. Spearman uses Bonett & Wright (2000),
# Kendall uses Fieller, Hartley & Pearson (1957). `offset` is subtracted from
# n; the CI is undefined unless n exceeds it.
_KENDALL_SE_NUMERATOR = 0.437
_SPEARMAN_OFFSET = 3
_PEARSON_OFFSET = 3
_KENDALL_OFFSET = 4

_MAX_PERCENT = 100


class CorrelationMethod(StrEnum):
    """Supported correlation coefficients."""

    PEARSON = "pearson"
    SPEARMAN = "spearman"
    KENDALL = "kendall"


class CorrelationStrength(StrEnum):
    """Conventional strength label for an absolute correlation coefficient."""

    NEGLIGIBLE = "negligible"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class CorrelationError(StrEnum):
    """Reasons a correlation analysis could not be computed.

    Kept UI-text-free (a plain reason code) so the GUI layer owns
    translation, matching the other analysis services.
    """

    NOT_ENOUGH_NUMERIC_COLUMNS = "not_enough_numeric_columns"
    NOT_ENOUGH_SELECTED_COLUMNS = "not_enough_selected_columns"
    TOO_MANY_SELECTED_COLUMNS = "too_many_selected_columns"
    INVALID_COLUMN = "invalid_column"
    NOT_ENOUGH_OBSERVATIONS = "not_enough_observations"
    CONSTANT_INPUT = "constant_input"


@dataclass(frozen=True, slots=True)
class CorrelationPair:
    """Correlation statistics for one pair of columns.

    Attributes:
        x_column: First column.
        y_column: Second column.
        coefficient: Correlation coefficient; NaN when undefined (fewer
            than `MIN_OBSERVATIONS` rows or a constant column).
        p_value: Two-sided p-value for "no correlation"; NaN when undefined.
        adjusted_p_value: Holm-adjusted p-value across every pair of the
            same matrix; NaN when undefined or not part of a matrix.
        ci_low: Lower bound of the `CONFIDENCE_LEVEL` confidence interval.
        ci_high: Upper bound of the `CONFIDENCE_LEVEL` confidence interval.
        n: Number of rows with a finite value in both columns.
    """

    x_column: str
    y_column: str
    coefficient: float
    p_value: float
    adjusted_p_value: float
    ci_low: float
    ci_high: float
    n: int


@dataclass(frozen=True, slots=True)
class CorrelationMatrixResult:
    """Pairwise correlations between the selected numeric columns.

    Attributes:
        method: The correlation coefficient used.
        columns: The analyzed columns, in matrix order.
        available_columns: Every numeric column in the dataset, for
            populating the configuration widget.
        coefficients: Symmetric, row-major coefficient matrix over
            `columns`; NaN where undefined, including the diagonal of
            columns that are constant or have too few values.
        pairs: Every distinct pair, sorted by descending absolute
            coefficient; undefined coefficients last.
        error: A structured reason no matrix could be computed, or `None`.
    """

    method: CorrelationMethod
    columns: tuple[str, ...]
    available_columns: tuple[str, ...]
    coefficients: tuple[tuple[float, ...], ...]
    pairs: tuple[CorrelationPair, ...]
    error: CorrelationError | None


@dataclass(frozen=True, slots=True)
class CorrelationPairDetail:
    """Detailed correlation of a single pair of columns.

    Attributes:
        method: The correlation coefficient used.
        pair: The pair's statistics (`adjusted_p_value` is NaN - a single
            pair involves no multiple testing). Coefficient-related fields
            are NaN when `error` is set.
        slope: Least-squares slope of y on x, using every valid row.
        intercept: Least-squares intercept of y on x.
        sample_x: x values of the scatterplot sample.
        sample_y: y values of the scatterplot sample.
        sampled: Whether the sample is smaller than `pair.n`.
        error: A structured reason the pair could not be analyzed, or `None`.
    """

    method: CorrelationMethod
    pair: CorrelationPair
    slope: float
    intercept: float
    sample_x: tuple[float, ...]
    sample_y: tuple[float, ...]
    sampled: bool
    error: CorrelationError | None


# ----------------------------------------------------------------------
# Public helpers
# ----------------------------------------------------------------------


def correlation_strength(coefficient: float) -> CorrelationStrength | None:
    """Classify an absolute correlation coefficient using Cohen's thresholds.

    Args:
        coefficient: A correlation coefficient in ``[-1, 1]``.

    Returns:
        The strength label, or `None` if `coefficient` is NaN.
    """
    if math.isnan(coefficient):
        return None
    magnitude = abs(coefficient)
    if magnitude >= STRONG_THRESHOLD:
        return CorrelationStrength.STRONG
    if magnitude >= MODERATE_THRESHOLD:
        return CorrelationStrength.MODERATE
    if magnitude >= WEAK_THRESHOLD:
        return CorrelationStrength.WEAK
    return CorrelationStrength.NEGLIGIBLE


def holm_adjust(p_values: Sequence[float]) -> tuple[float, ...]:
    """Apply the Holm-Bonferroni step-down adjustment to p-values.

    NaN p-values are passed through unchanged and do not count towards
    the number of tests.

    Args:
        p_values: Raw p-values, in any order.

    Returns:
        Adjusted p-values in the same order as `p_values`, capped at 1.
    """
    indexed = sorted(
        ((index, p) for index, p in enumerate(p_values) if not math.isnan(p)),
        key=lambda item: item[1],
    )
    m = len(indexed)
    adjusted = [_NAN] * len(p_values)
    running_max = 0.0
    for rank, (index, p) in enumerate(indexed):
        running_max = max(running_max, min(1.0, (m - rank) * p))
        adjusted[index] = running_max
    return tuple(adjusted)


def default_pair(result: CorrelationMatrixResult) -> tuple[str, str] | None:
    """Return the pair to show in detail by default: the strongest defined pair.

    Args:
        result: A computed correlation matrix.

    Returns:
        The ``(x, y)`` pair with the largest absolute coefficient, the
        first pair when none is defined, or `None` without any pair.
    """
    if not result.pairs:
        return None
    first = result.pairs[0]
    return first.x_column, first.y_column


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _column_values(df: pd.DataFrame, column: str) -> np.ndarray:
    """Return a column as float64 with missing and infinite values as NaN."""
    values = pd.to_numeric(df[column], errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
    values[~np.isfinite(values)] = np.nan
    return values


def _is_correlatable(values: np.ndarray) -> bool:
    """Return whether NaN-free values can yield a defined coefficient."""
    return len(values) >= MIN_OBSERVATIONS and not bool(np.all(values == values[0]))


def _fisher_ci(coefficient: float, n: int, method: CorrelationMethod) -> tuple[float, float]:
    """Return the Fisher z-transform confidence interval for a coefficient."""
    if math.isnan(coefficient):
        return _NAN, _NAN

    match method:
        case CorrelationMethod.PEARSON:
            offset = _PEARSON_OFFSET
            numerator = 1.0
        case CorrelationMethod.SPEARMAN:
            offset = _SPEARMAN_OFFSET
            numerator = 1.0 + coefficient**2 / 2.0
        case CorrelationMethod.KENDALL:
            offset = _KENDALL_OFFSET
            numerator = _KENDALL_SE_NUMERATOR

    if n <= offset:
        return _NAN, _NAN

    critical = float(norm.ppf(0.5 + CONFIDENCE_LEVEL / 2.0))
    standard_error = math.sqrt(numerator / (n - offset))
    with np.errstate(divide="ignore"):
        z = float(np.arctanh(coefficient))
    return math.tanh(z - critical * standard_error), math.tanh(z + critical * standard_error)


def _correlate(
    x: np.ndarray,
    y: np.ndarray,
    method: CorrelationMethod,
    *,
    x_ranks: np.ndarray | None = None,
    y_ranks: np.ndarray | None = None,
) -> tuple[float, float]:
    """Return ``(coefficient, p_value)`` for two NaN-free arrays of equal length.

    `x_ranks`/`y_ranks` may carry precomputed Spearman ranks of exactly
    these values, avoiding a re-rank per pair.
    """
    if not (_is_correlatable(x) and _is_correlatable(y)):
        return _NAN, _NAN

    with warnings.catch_warnings():
        # Degenerate inputs are reported as NaN rather than warnings.
        warnings.simplefilter("ignore")
        match method:
            case CorrelationMethod.PEARSON:
                result = pearsonr(x, y)
            case CorrelationMethod.SPEARMAN:
                # Spearman's rho is Pearson's r on (average) ranks, with the
                # same t-distribution p-value as scipy.stats.spearmanr.
                result = pearsonr(
                    rankdata(x) if x_ranks is None else x_ranks,
                    rankdata(y) if y_ranks is None else y_ranks,
                )
            case CorrelationMethod.KENDALL:
                result = kendalltau(x, y)
    return float(result.statistic), float(result.pvalue)  # pyright: ignore[reportAttributeAccessIssue]


def _pair_statistics(
    x_column: str,
    y_column: str,
    x: np.ndarray,
    y: np.ndarray,
    method: CorrelationMethod,
    *,
    x_ranks: np.ndarray | None = None,
    y_ranks: np.ndarray | None = None,
) -> CorrelationPair:
    """Compute one pair's statistics from NaN-free, equal-length arrays."""
    coefficient, p_value = _correlate(x, y, method, x_ranks=x_ranks, y_ranks=y_ranks)
    ci_low, ci_high = _fisher_ci(coefficient, len(x), method)
    return CorrelationPair(
        x_column=x_column,
        y_column=y_column,
        coefficient=coefficient,
        p_value=p_value,
        adjusted_p_value=_NAN,
        ci_low=ci_low,
        ci_high=ci_high,
        n=len(x),
    )


def _sort_key(pair: CorrelationPair) -> tuple[bool, float]:
    """Sort by descending |coefficient|, undefined coefficients last."""
    undefined = math.isnan(pair.coefficient)
    return undefined, 0.0 if undefined else -abs(pair.coefficient)


def _matrix_error(
    error: CorrelationError | None,
    method: CorrelationMethod,
    columns: tuple[str, ...],
    available: tuple[str, ...],
) -> CorrelationMatrixResult:
    """Build a `CorrelationMatrixResult` without coefficients.

    `error` is `None` only for the configuration-only result returned by
    `initialize_correlation`.
    """
    return CorrelationMatrixResult(
        method=method,
        columns=columns,
        available_columns=available,
        coefficients=(),
        pairs=(),
        error=error,
    )


# ----------------------------------------------------------------------
# Matrix
# ----------------------------------------------------------------------


def initialize_correlation(df: pd.DataFrame) -> CorrelationMatrixResult:
    """Return the default correlation configuration without computing coefficients.

    Only column metadata is inspected, so this is cheap enough for the GUI
    thread. It lets the configuration be shown before the user applies it.

    Args:
        df: The DataFrame to inspect. Never mutated.

    Returns:
        A result without coefficients, selecting the first
        `DEFAULT_SELECTED_COLUMNS` numeric columns with Pearson's method.
        Its `error` is `NOT_ENOUGH_NUMERIC_COLUMNS` when the dataset has too
        few numeric columns, and `None` otherwise.
    """
    available = numeric_columns(df)
    if len(available) < MIN_SELECTED_COLUMNS:
        return _matrix_error(CorrelationError.NOT_ENOUGH_NUMERIC_COLUMNS, CorrelationMethod.PEARSON, (), available)
    return _matrix_error(None, CorrelationMethod.PEARSON, available[:DEFAULT_SELECTED_COLUMNS], available)


def analyze_correlation_matrix(
    df: pd.DataFrame,
    columns: Sequence[str] | None = None,
    method: CorrelationMethod = CorrelationMethod.PEARSON,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> CorrelationMatrixResult | None:
    """Compute pairwise correlations between numeric columns.

    Args:
        df: The DataFrame to analyze. Never mutated.
        columns: Columns to analyze. Defaults to the first
            `DEFAULT_SELECTED_COLUMNS` numeric columns when `None`. An
            explicit selection is validated as given, never silently
            replaced.
        method: The correlation coefficient to compute.
        progress_cb: Optional callback receiving the completed percentage
            (0-100), called whenever it changes.
        cancel_cb: Optional cooperative cancellation check, polled between
            pairs.

    Returns:
        The populated result, a result with `error` set when the selection
        is unusable, or `None` if cancelled via `cancel_cb`.
    """
    available = numeric_columns(df)

    if len(available) < MIN_SELECTED_COLUMNS:
        return _matrix_error(CorrelationError.NOT_ENOUGH_NUMERIC_COLUMNS, method, (), available)

    selected = available[:DEFAULT_SELECTED_COLUMNS] if columns is None else tuple(columns)

    if len(set(selected)) != len(selected) or any(column not in available for column in selected):
        return _matrix_error(CorrelationError.INVALID_COLUMN, method, selected, available)
    if len(selected) < MIN_SELECTED_COLUMNS:
        return _matrix_error(CorrelationError.NOT_ENOUGH_SELECTED_COLUMNS, method, selected, available)
    if len(selected) > MAX_SELECTED_COLUMNS:
        return _matrix_error(CorrelationError.TOO_MANY_SELECTED_COLUMNS, method, selected, available)

    values = {column: _column_values(df, column) for column in selected}
    valid = {column: ~np.isnan(array) for column, array in values.items()}
    # Ranks of complete columns are valid for every pair they're part of,
    # so rank them once instead of once per pair.
    complete_ranks: dict[str, np.ndarray] = {}
    if method is CorrelationMethod.SPEARMAN:
        complete_ranks = {column: rankdata(values[column]) for column in selected if bool(valid[column].all())}

    size = len(selected)
    matrix = np.full((size, size), _NAN)
    for index, column in enumerate(selected):
        if _is_correlatable(values[column][valid[column]]):
            matrix[index, index] = 1.0
    pairs: list[CorrelationPair] = []

    total = size * (size - 1) // 2
    done = 0
    last_percent = -1

    for i in range(size):
        for j in range(i + 1, size):
            if cancel_cb is not None and cancel_cb():
                return None

            x_column, y_column = selected[i], selected[j]
            mask = valid[x_column] & valid[y_column]
            both_complete = x_column in complete_ranks and y_column in complete_ranks
            pair = _pair_statistics(
                x_column,
                y_column,
                values[x_column][mask],
                values[y_column][mask],
                method,
                x_ranks=complete_ranks[x_column] if both_complete else None,
                y_ranks=complete_ranks[y_column] if both_complete else None,
            )
            matrix[i, j] = matrix[j, i] = pair.coefficient
            pairs.append(pair)

            done += 1
            percent = done * _MAX_PERCENT // total
            if progress_cb is not None and percent != last_percent:
                progress_cb(percent)
                last_percent = percent

    adjusted = holm_adjust([pair.p_value for pair in pairs])
    adjusted_pairs = [
        CorrelationPair(
            x_column=pair.x_column,
            y_column=pair.y_column,
            coefficient=pair.coefficient,
            p_value=pair.p_value,
            adjusted_p_value=adjusted_p,
            ci_low=pair.ci_low,
            ci_high=pair.ci_high,
            n=pair.n,
        )
        for pair, adjusted_p in zip(pairs, adjusted, strict=True)
    ]

    return CorrelationMatrixResult(
        method=method,
        columns=selected,
        available_columns=available,
        coefficients=tuple(tuple(float(value) for value in row) for row in matrix),
        pairs=tuple(sorted(adjusted_pairs, key=_sort_key)),
        error=None,
    )


# ----------------------------------------------------------------------
# Single pair
# ----------------------------------------------------------------------


def _pair_error(
    error: CorrelationError,
    method: CorrelationMethod,
    x_column: str,
    y_column: str,
    n: int = 0,
) -> CorrelationPairDetail:
    """Build a `CorrelationPairDetail` carrying only a structured error."""
    return CorrelationPairDetail(
        method=method,
        pair=CorrelationPair(
            x_column=x_column,
            y_column=y_column,
            coefficient=_NAN,
            p_value=_NAN,
            adjusted_p_value=_NAN,
            ci_low=_NAN,
            ci_high=_NAN,
            n=n,
        ),
        slope=_NAN,
        intercept=_NAN,
        sample_x=(),
        sample_y=(),
        sampled=False,
        error=error,
    )


def analyze_correlation_pair(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    method: CorrelationMethod = CorrelationMethod.PEARSON,
) -> CorrelationPairDetail:
    """Analyze the correlation of a single pair of numeric columns in detail.

    Args:
        df: The DataFrame to analyze. Never mutated.
        x_column: Column plotted on the x axis.
        y_column: Column plotted on the y axis.
        method: The correlation coefficient to compute.

    Returns:
        The pair's statistics, least-squares line and scatterplot sample.
        `error` is set when either column is not numeric, both are the
        same, fewer than `MIN_OBSERVATIONS` rows are valid in both, or
        either column is constant over those rows.
    """
    available = numeric_columns(df)
    if x_column == y_column or x_column not in available or y_column not in available:
        return _pair_error(CorrelationError.INVALID_COLUMN, method, x_column, y_column)

    x_all = _column_values(df, x_column)
    y_all = _column_values(df, y_column)
    mask = ~np.isnan(x_all) & ~np.isnan(y_all)
    x = x_all[mask]
    y = y_all[mask]
    n = len(x)

    if n < MIN_OBSERVATIONS:
        return _pair_error(CorrelationError.NOT_ENOUGH_OBSERVATIONS, method, x_column, y_column, n)
    if not (_is_correlatable(x) and _is_correlatable(y)):
        return _pair_error(CorrelationError.CONSTANT_INPUT, method, x_column, y_column, n)

    pair = _pair_statistics(x_column, y_column, x, y, method)
    slope, intercept = (float(value) for value in np.polyfit(x, y, deg=1))

    if n > SCATTER_SAMPLE_SIZE:
        rng = np.random.default_rng(_SCATTER_SEED)
        indices = np.sort(rng.choice(n, size=SCATTER_SAMPLE_SIZE, replace=False))
        sample_x, sample_y = x[indices], y[indices]
    else:
        sample_x, sample_y = x, y

    return CorrelationPairDetail(
        method=method,
        pair=pair,
        slope=slope,
        intercept=intercept,
        sample_x=tuple(float(value) for value in sample_x),
        sample_y=tuple(float(value) for value in sample_y),
        sampled=len(sample_x) < n,
        error=None,
    )
