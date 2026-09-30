"""Chi-square test of independence between two categorical columns.

Builds the observed contingency table of two columns, then runs Pearson's
chi-square test of independence (`scipy.stats.chi2_contingency`, which
applies Yates' continuity correction for 2x2 tables), CramÃ©r's V effect
size, and - for 2x2 tables only - Fisher's exact test as a small-sample
alternative. Adjusted standardized residuals are returned per cell so the
caller can show *which* cells drive a significant result, and Cochran's
rule of thumb for the chi-square approximation's validity is evaluated and
reported rather than silently ignored.

Column eligibility deliberately matches Group Comparison's grouping column
rule (`group_comparison.classify_grouping_columns`), so both hypothesis
tests agree on what counts as a categorical column.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, fisher_exact
from scipy.stats.contingency import association

from expo_jbm329.services.analysis.group_comparison import (
    MAX_GROUPS,
    MIN_GROUPS,
    ExcludedColumn,
    GroupingColumns,
    classify_grouping_columns,
)

_NAN = float("nan")

# Cochran's rule of thumb: the chi-square approximation is considered
# unreliable when more than 20% of expected counts are below 5, or when
# any expected count is below 1.
COCHRAN_LOW_EXPECTED_COUNT = 5.0
COCHRAN_MAX_LOW_EXPECTED_FRACTION = 0.2
COCHRAN_MIN_EXPECTED_COUNT = 1.0

_TWO_BY_TWO = (2, 2)

# A test of independence compares a pair of columns.
_COLUMNS_PER_TEST = 2


class ChiSquareError(StrEnum):
    """Reasons a chi-square test could not be computed.

    Kept UI-text-free (a plain reason code) so the GUI layer owns
    translation, matching `GroupComparisonError`.
    """

    NOT_ENOUGH_COLUMNS = "not_enough_columns"
    INVALID_COLUMN = "invalid_column"
    TOO_FEW_CATEGORIES = "too_few_categories"
    TOO_MANY_CATEGORIES = "too_many_categories"


@dataclass(frozen=True, slots=True)
class ChiSquareResult:
    """Result of a chi-square test of independence between two columns.

    Table-shaped fields (`observed`, `expected`, `adjusted_residuals`) are
    row-major: ``observed[i][j]`` is the count for ``row_labels[i]`` and
    ``column_labels[j]``. All table/statistic fields are empty/NaN when
    `error` is set.

    Attributes:
        row_column: Column whose categories form the table's rows.
        column_column: Column whose categories form the table's columns.
        available_columns: Every eligible categorical column, for
            populating the configuration widget.
        row_labels: Row category labels, in ascending order.
        column_labels: Column category labels, in ascending order.
        observed: Observed counts.
        expected: Expected counts under independence.
        adjusted_residuals: Adjusted standardized residuals per cell;
            ``|residual| > 1.96`` marks a cell that deviates significantly
            (at the 5% level) from independence.
        total: Number of rows with a non-missing value in both columns.
        chi2_statistic: Pearson chi-square statistic.
        p_value: p-value of the chi-square test.
        degrees_of_freedom: ``(rows - 1) * (columns - 1)``.
        yates_correction_applied: Whether Yates' continuity correction was
            applied (scipy does so for 2x2 tables only).
        cramers_v: CramÃ©r's V effect size in ``[0, 1]``.
        fisher_odds_ratio: Fisher's exact test odds ratio; `None` unless
            the table is 2x2.
        fisher_p_value: Fisher's exact test p-value; `None` unless the
            table is 2x2.
        low_expected_fraction: Fraction of cells with an expected count
            below `COCHRAN_LOW_EXPECTED_COUNT`.
        min_expected: Smallest expected count in the table.
        cochran_violated: Whether Cochran's rule of thumb is violated,
            i.e. the chi-square p-value may be unreliable.
        error: A structured reason no result could be computed, or `None`.
        excluded_columns: Every column *not* eligible as a categorical
            column, with the reason - lets the configuration widget show
            them as disabled choices instead of hiding them.
    """

    row_column: str
    column_column: str
    available_columns: tuple[str, ...]
    row_labels: tuple[str, ...]
    column_labels: tuple[str, ...]
    observed: tuple[tuple[int, ...], ...]
    expected: tuple[tuple[float, ...], ...]
    adjusted_residuals: tuple[tuple[float, ...], ...]
    total: int
    chi2_statistic: float
    p_value: float
    degrees_of_freedom: int
    yates_correction_applied: bool
    cramers_v: float
    fisher_odds_ratio: float | None
    fisher_p_value: float | None
    low_expected_fraction: float
    min_expected: float
    cochran_violated: bool
    error: ChiSquareError | None
    excluded_columns: tuple[ExcludedColumn, ...] = ()


def _unfitted_result(
    error: ChiSquareError | None,
    *,
    row_column: str,
    column_column: str,
    columns: GroupingColumns,
) -> ChiSquareResult:
    """Build a `ChiSquareResult` without table data, carrying `error` if any."""
    return ChiSquareResult(
        row_column=row_column,
        column_column=column_column,
        available_columns=columns.eligible,
        row_labels=(),
        column_labels=(),
        observed=(),
        expected=(),
        adjusted_residuals=(),
        total=0,
        chi2_statistic=_NAN,
        p_value=_NAN,
        degrees_of_freedom=0,
        yates_correction_applied=False,
        cramers_v=_NAN,
        fisher_odds_ratio=None,
        fisher_p_value=None,
        low_expected_fraction=_NAN,
        min_expected=_NAN,
        cochran_violated=False,
        error=error,
        excluded_columns=columns.excluded,
    )


def _adjusted_residuals(observed: np.ndarray, expected: np.ndarray) -> np.ndarray:
    """Compute adjusted standardized residuals for every contingency table cell.

    ``(O - E) / sqrt(E * (1 - row_total / n) * (1 - column_total / n))``.
    Cells whose denominator is zero get NaN.
    """
    n = observed.sum()
    row_share = observed.sum(axis=1, keepdims=True) / n
    column_share = observed.sum(axis=0, keepdims=True) / n
    denominator = np.sqrt(expected * (1.0 - row_share) * (1.0 - column_share))

    residuals = np.full(observed.shape, _NAN)
    np.divide(observed - expected, denominator, out=residuals, where=denominator > 0)
    return residuals


def _to_float_rows(table: np.ndarray) -> tuple[tuple[float, ...], ...]:
    """Convert a 2-D array into an immutable row-major tuple of floats."""
    return tuple(tuple(float(value) for value in row) for row in table)


def initialize_chi_square(df: pd.DataFrame) -> ChiSquareResult:
    """Return the default chi-square configuration without testing any columns.

    Only distinct-value counts are inspected, so the configuration can be
    shown before the user applies it.

    Args:
        df: The DataFrame to inspect. Never mutated.

    Returns:
        A result without table data, using the first two eligible
        categorical columns. Its `error` is `NOT_ENOUGH_COLUMNS` when fewer
        than two eligible columns exist, and `None` otherwise.
    """
    columns = classify_grouping_columns(df)
    available = columns.eligible
    enough = len(available) >= _COLUMNS_PER_TEST
    return _unfitted_result(
        None if enough else ChiSquareError.NOT_ENOUGH_COLUMNS,
        row_column=available[0] if enough else "",
        column_column=available[1] if enough else "",
        columns=columns,
    )


def analyze_chi_square(
    df: pd.DataFrame,
    row_column: str | None = None,
    column_column: str | None = None,
) -> ChiSquareResult:
    """Test two categorical columns for independence.

    Args:
        df: The DataFrame to analyze. Never mutated.
        row_column: Column forming the table's rows. Defaults to the
            first eligible column when `None`.
        column_column: Column forming the table's columns. Defaults to the
            first eligible column other than `row_column` when `None`.
            An explicitly given column pair is validated as given (never
            silently replaced), matching `analyze_group_comparison`.

    Returns:
        A populated `ChiSquareResult`. `error` is set when fewer than two
        eligible columns exist (`NOT_ENOUGH_COLUMNS`), an explicit column
        does not exist or both columns are the same (`INVALID_COLUMN`), or
        either column has fewer than `MIN_GROUPS` / more than `MAX_GROUPS`
        categories once rows missing either value are dropped.
    """
    columns = classify_grouping_columns(df)
    available = columns.eligible

    if row_column is None:
        row_column = available[0] if available else ""
    if column_column is None:
        others = tuple(column for column in available if column != row_column)
        column_column = others[0] if others else ""

    if row_column == "" or column_column == "":
        return _unfitted_result(
            ChiSquareError.NOT_ENOUGH_COLUMNS,
            row_column=row_column,
            column_column=column_column,
            columns=columns,
        )

    if row_column == column_column or row_column not in df.columns or column_column not in df.columns:
        return _unfitted_result(
            ChiSquareError.INVALID_COLUMN,
            row_column=row_column,
            column_column=column_column,
            columns=columns,
        )

    pair = df[[row_column, column_column]].dropna()
    crosstab = pd.crosstab(pair[row_column], pair[column_column])
    n_rows, n_columns = crosstab.shape

    if min(n_rows, n_columns) < MIN_GROUPS:
        return _unfitted_result(
            ChiSquareError.TOO_FEW_CATEGORIES,
            row_column=row_column,
            column_column=column_column,
            columns=columns,
        )
    if max(n_rows, n_columns) > MAX_GROUPS:
        return _unfitted_result(
            ChiSquareError.TOO_MANY_CATEGORIES,
            row_column=row_column,
            column_column=column_column,
            columns=columns,
        )

    observed = crosstab.to_numpy(dtype=np.int64)

    with warnings.catch_warnings():
        # Degenerate-input warnings from scipy are surfaced through NaN
        # results and the Cochran caveat instead.
        warnings.simplefilter("ignore")
        chi2_result = chi2_contingency(observed)
        cramers_v = float(association(observed, method="cramer"))

        fisher_odds_ratio: float | None = None
        fisher_p_value: float | None = None
        if observed.shape == _TWO_BY_TWO:
            fisher_result = fisher_exact(observed)
            fisher_odds_ratio = float(fisher_result.statistic)  # pyright: ignore[reportAttributeAccessIssue]
            fisher_p_value = float(fisher_result.pvalue)  # pyright: ignore[reportAttributeAccessIssue]

    expected = np.asarray(chi2_result.expected_freq, dtype=float)  # pyright: ignore[reportAttributeAccessIssue]
    degrees_of_freedom = int(chi2_result.dof)  # pyright: ignore[reportAttributeAccessIssue]
    low_expected_fraction = float(np.mean(expected < COCHRAN_LOW_EXPECTED_COUNT))
    min_expected = float(expected.min())

    return ChiSquareResult(
        row_column=row_column,
        column_column=column_column,
        available_columns=available,
        row_labels=tuple(str(label) for label in crosstab.index),
        column_labels=tuple(str(label) for label in crosstab.columns),
        observed=tuple(tuple(int(value) for value in row) for row in observed),
        expected=_to_float_rows(expected),
        adjusted_residuals=_to_float_rows(_adjusted_residuals(observed.astype(float), expected)),
        total=int(observed.sum()),
        chi2_statistic=float(chi2_result.statistic),  # pyright: ignore[reportAttributeAccessIssue]
        p_value=float(chi2_result.pvalue),  # pyright: ignore[reportAttributeAccessIssue]
        degrees_of_freedom=degrees_of_freedom,
        # scipy only applies the correction when there is exactly one
        # degree of freedom (i.e. a 2x2 table).
        yates_correction_applied=degrees_of_freedom == 1,
        cramers_v=cramers_v,
        fisher_odds_ratio=fisher_odds_ratio,
        fisher_p_value=fisher_p_value,
        low_expected_fraction=low_expected_fraction,
        min_expected=min_expected,
        cochran_violated=(
            low_expected_fraction > COCHRAN_MAX_LOW_EXPECTED_FRACTION or min_expected < COCHRAN_MIN_EXPECTED_COUNT
        ),
        error=None,
        excluded_columns=columns.excluded,
    )
