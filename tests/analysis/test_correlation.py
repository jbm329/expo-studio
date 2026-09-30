"""Tests for the correlation analysis service."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import pytest
from scipy.stats import kendalltau, pearsonr, spearmanr

from expo_jbm329.services.analysis.correlation import (
    DEFAULT_SELECTED_COLUMNS,
    MAX_SELECTED_COLUMNS,
    SCATTER_SAMPLE_SIZE,
    CorrelationError,
    CorrelationMatrixResult,
    CorrelationMethod,
    CorrelationPair,
    CorrelationStrength,
    analyze_correlation_matrix,
    analyze_correlation_pair,
    correlation_strength,
    default_pair,
    holm_adjust,
    initialize_correlation,
)


def _frame(size: int = 50, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = rng.normal(size=size)
    return pd.DataFrame({
        "a": base,
        "b": 2.0 * base + rng.normal(scale=0.5, size=size),
        "c": rng.normal(size=size),
        "text": ["x"] * size,
    })


def _matrix(df: pd.DataFrame, **kwargs: object) -> CorrelationMatrixResult:
    result = analyze_correlation_matrix(df, **kwargs)  # type: ignore[arg-type]
    assert result is not None
    return result


def _statistic_and_p(scipy_result: Any) -> tuple[float, float]:  # noqa: ANN401
    """Read ``(statistic, pvalue)`` from a scipy result object, which pyright can't type."""
    return float(scipy_result.statistic), float(scipy_result.pvalue)


def _pair(result: CorrelationMatrixResult, x: str, y: str) -> CorrelationPair:
    return next(p for p in result.pairs if {p.x_column, p.y_column} == {x, y})


# ----------------------------------------------------------------------
# correlation_strength
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("coefficient", "expected"),
    [
        (0.0, CorrelationStrength.NEGLIGIBLE),
        (0.09, CorrelationStrength.NEGLIGIBLE),
        (0.1, CorrelationStrength.WEAK),
        (-0.29, CorrelationStrength.WEAK),
        (0.3, CorrelationStrength.MODERATE),
        (-0.5, CorrelationStrength.STRONG),
        (1.0, CorrelationStrength.STRONG),
    ],
)
def test_correlation_strength_uses_cohen_thresholds(coefficient: float, expected: CorrelationStrength) -> None:
    assert correlation_strength(coefficient) is expected


def test_correlation_strength_of_nan_is_none() -> None:
    assert correlation_strength(float("nan")) is None


# ----------------------------------------------------------------------
# holm_adjust
# ----------------------------------------------------------------------


def test_holm_adjust_matches_hand_computed_values() -> None:
    # Sorted: 0.01*4=0.04, 0.02*3=0.06, 0.03*2=0.06, 0.04*1=0.04 -> running max.
    adjusted = holm_adjust([0.04, 0.01, 0.03, 0.02])

    assert adjusted == pytest.approx((0.06, 0.04, 0.06, 0.06))


def test_holm_adjust_caps_at_one() -> None:
    assert holm_adjust([0.5, 0.6]) == pytest.approx((1.0, 1.0))


def test_holm_adjust_passes_nan_through_and_excludes_it_from_the_count() -> None:
    adjusted = holm_adjust([0.01, float("nan"), 0.04])

    assert adjusted[0] == pytest.approx(0.02)
    assert math.isnan(adjusted[1])
    assert adjusted[2] == pytest.approx(0.04)


def test_holm_adjust_of_empty_is_empty() -> None:
    assert holm_adjust([]) == ()


# ----------------------------------------------------------------------
# analyze_correlation_matrix: statistics
# ----------------------------------------------------------------------


def test_pearson_matches_scipy_including_confidence_interval() -> None:
    df = _frame()
    result = _matrix(df)
    pair = _pair(result, "a", "b")
    scipy_result = pearsonr(df["a"], df["b"])
    expected_r, expected_p = _statistic_and_p(scipy_result)
    ci = scipy_result.confidence_interval()

    assert pair.coefficient == pytest.approx(expected_r)
    assert pair.p_value == pytest.approx(expected_p)
    assert pair.ci_low == pytest.approx(ci.low)
    assert pair.ci_high == pytest.approx(ci.high)
    assert pair.n == len(df)


def test_spearman_matches_scipy_with_ties() -> None:
    df = pd.DataFrame({"a": [1, 2, 2, 3, 4, 4, 5, 6], "b": [2, 1, 3, 3, 5, 4, 6, 6]})
    pair = _pair(_matrix(df, method=CorrelationMethod.SPEARMAN), "a", "b")
    expected_r, expected_p = _statistic_and_p(spearmanr(df["a"], df["b"]))

    assert pair.coefficient == pytest.approx(expected_r)
    assert pair.p_value == pytest.approx(expected_p)
    assert pair.ci_low < pair.coefficient < pair.ci_high


def test_spearman_with_missing_values_uses_pairwise_ranks() -> None:
    df = _frame()
    df.loc[[0, 5, 9], "b"] = np.nan
    pair = _pair(_matrix(df, method=CorrelationMethod.SPEARMAN), "a", "b")
    complete = df[["a", "b"]].dropna()
    expected_r, expected_p = _statistic_and_p(spearmanr(complete["a"], complete["b"]))

    assert pair.n == len(df) - 3
    assert pair.coefficient == pytest.approx(expected_r)
    assert pair.p_value == pytest.approx(expected_p)


def test_kendall_matches_scipy() -> None:
    df = _frame()
    pair = _pair(_matrix(df, method=CorrelationMethod.KENDALL), "a", "c")
    expected_r, expected_p = _statistic_and_p(kendalltau(df["a"], df["c"]))

    assert pair.coefficient == pytest.approx(expected_r)
    assert pair.p_value == pytest.approx(expected_p)
    assert pair.ci_low < pair.coefficient < pair.ci_high


def test_pairwise_deletion_reports_each_pairs_own_n() -> None:
    df = _frame(size=20)
    df.loc[[0, 1], "a"] = np.nan
    df.loc[[1, 2, 3], "c"] = np.nan
    result = _matrix(df)

    assert _pair(result, "a", "b").n == 18
    assert _pair(result, "b", "c").n == 17
    assert _pair(result, "a", "c").n == 16


def test_infinite_values_are_treated_as_missing() -> None:
    df = _frame(size=20)
    df.loc[0, "a"] = np.inf

    assert _pair(_matrix(df), "a", "b").n == 19


def test_matrix_is_symmetric_with_unit_diagonal() -> None:
    result = _matrix(_frame())
    matrix = np.array(result.coefficients)

    assert result.columns == ("a", "b", "c")
    assert matrix.shape == (3, 3)
    np.testing.assert_allclose(matrix, matrix.T)
    np.testing.assert_allclose(np.diag(matrix), 1.0)
    assert matrix[0, 1] == pytest.approx(_pair(result, "a", "b").coefficient)


def test_constant_column_yields_nan_including_diagonal() -> None:
    df = _frame(size=10)
    df["k"] = 3.0
    result = _matrix(df)
    matrix = np.array(result.coefficients)
    pair = _pair(result, "a", "k")

    assert np.isnan(matrix[3, 3])
    assert math.isnan(pair.coefficient)
    assert math.isnan(pair.p_value)
    assert math.isnan(pair.adjusted_p_value)
    assert math.isnan(pair.ci_low)
    assert math.isnan(pair.ci_high)


def test_too_few_overlapping_rows_yield_nan() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, np.nan, np.nan, 5.0], "b": [np.nan, 1.0, 2.0, 3.0, 4.0]})

    assert math.isnan(_pair(_matrix(df), "a", "b").coefficient)


def test_perfect_correlation_has_degenerate_confidence_interval() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0], "b": [2.0, 4.0, 6.0, 8.0, 10.0]})
    pair = _pair(_matrix(df), "a", "b")

    assert pair.coefficient == pytest.approx(1.0)
    assert pair.ci_low == pytest.approx(1.0)
    assert pair.ci_high == pytest.approx(1.0)


def test_kendall_confidence_interval_needs_more_than_four_rows() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [1.0, 3.0, 2.0, 4.0]})
    pair = _pair(_matrix(df, method=CorrelationMethod.KENDALL), "a", "b")

    assert not math.isnan(pair.coefficient)
    assert math.isnan(pair.ci_low)
    assert math.isnan(pair.ci_high)


def test_pairs_are_sorted_by_absolute_coefficient_with_nan_last() -> None:
    df = _frame()
    df["k"] = 1.0
    df["neg"] = -df["a"] + np.random.default_rng(3).normal(scale=0.1, size=len(df))
    result = _matrix(df)
    coefficients = [p.coefficient for p in result.pairs]
    defined = [abs(c) for c in coefficients if not math.isnan(c)]

    assert defined == sorted(defined, reverse=True)
    assert all(math.isnan(c) for c in coefficients[len(defined) :])
    assert len(result.pairs) == 10


def test_adjusted_p_values_are_holm_of_raw_p_values() -> None:
    result = _matrix(_frame())
    expected = holm_adjust([p.p_value for p in result.pairs])

    assert tuple(p.adjusted_p_value for p in result.pairs) == pytest.approx(expected)
    assert all(p.adjusted_p_value >= p.p_value for p in result.pairs)


def test_input_frame_is_not_mutated() -> None:
    df = _frame()
    df.loc[0, "a"] = np.nan
    before = df.copy()

    _matrix(df, method=CorrelationMethod.SPEARMAN)

    pd.testing.assert_frame_equal(df, before)


# ----------------------------------------------------------------------
# analyze_correlation_matrix: column selection and errors
# ----------------------------------------------------------------------


def test_default_selection_takes_first_default_count_numeric_columns() -> None:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({f"n{i}": rng.normal(size=10) for i in range(DEFAULT_SELECTED_COLUMNS + 2)})
    df.insert(0, "text", ["x"] * 10)
    result = _matrix(df)

    assert result.columns == tuple(f"n{i}" for i in range(DEFAULT_SELECTED_COLUMNS))
    assert result.available_columns == tuple(f"n{i}" for i in range(DEFAULT_SELECTED_COLUMNS + 2))


def test_explicit_selection_is_used_in_given_order() -> None:
    result = _matrix(_frame(), columns=["c", "a"])

    assert result.columns == ("c", "a")
    assert result.available_columns == ("a", "b", "c")
    assert len(result.pairs) == 1


def test_not_enough_numeric_columns_error() -> None:
    result = _matrix(pd.DataFrame({"a": [1.0, 2.0, 3.0], "t": ["x", "y", "z"]}))

    assert result.error is CorrelationError.NOT_ENOUGH_NUMERIC_COLUMNS
    assert result.columns == ()
    assert result.available_columns == ("a",)
    assert result.pairs == ()
    assert result.coefficients == ()


def test_not_enough_selected_columns_error() -> None:
    result = _matrix(_frame(), columns=["a"])

    assert result.error is CorrelationError.NOT_ENOUGH_SELECTED_COLUMNS
    assert result.columns == ("a",)
    assert result.available_columns == ("a", "b", "c")


def test_too_many_selected_columns_error() -> None:
    rng = np.random.default_rng(0)
    names = [f"n{i}" for i in range(MAX_SELECTED_COLUMNS + 1)]
    df = pd.DataFrame({name: rng.normal(size=5) for name in names})

    assert _matrix(df, columns=names).error is CorrelationError.TOO_MANY_SELECTED_COLUMNS
    assert _matrix(df, columns=names[:MAX_SELECTED_COLUMNS]).error is None


@pytest.mark.parametrize("columns", [["a", "text"], ["a", "missing"], ["a", "a"]])
def test_invalid_column_error(columns: list[str]) -> None:
    assert _matrix(_frame(), columns=columns).error is CorrelationError.INVALID_COLUMN


# ----------------------------------------------------------------------
# analyze_correlation_matrix: progress and cancellation
# ----------------------------------------------------------------------


def test_progress_reports_increasing_percentages_ending_at_100() -> None:
    reported: list[int] = []

    _matrix(_frame(), progress_cb=reported.append)

    assert reported == [33, 66, 100]


def test_progress_deduplicates_equal_percentages() -> None:
    rng = np.random.default_rng(0)
    df = pd.DataFrame({f"n{i}": rng.normal(size=5) for i in range(MAX_SELECTED_COLUMNS)})
    reported: list[int] = []

    _matrix(df, columns=list(df.columns), progress_cb=reported.append)

    assert reported == sorted(set(reported))
    assert reported[-1] == 100


def test_cancel_returns_none() -> None:
    calls: list[None] = []

    def cancel() -> bool:
        calls.append(None)
        return len(calls) > 1

    assert analyze_correlation_matrix(_frame(), cancel_cb=cancel) is None
    assert len(calls) == 2


def test_not_cancelled_returns_result() -> None:
    assert analyze_correlation_matrix(_frame(), cancel_cb=lambda: False) is not None


# ----------------------------------------------------------------------
# default_pair
# ----------------------------------------------------------------------


def test_default_pair_is_strongest_pair() -> None:
    assert default_pair(_matrix(_frame())) == ("a", "b")


def test_default_pair_of_error_result_is_none() -> None:
    assert default_pair(_matrix(_frame(), columns=["a"])) is None


# ----------------------------------------------------------------------
# analyze_correlation_pair
# ----------------------------------------------------------------------


def test_pair_detail_matches_matrix_statistics_and_least_squares_line() -> None:
    df = _frame()
    detail = analyze_correlation_pair(df, "a", "b", CorrelationMethod.SPEARMAN)
    matrix_pair = _pair(_matrix(df, method=CorrelationMethod.SPEARMAN), "a", "b")
    slope, intercept = np.polyfit(df["a"], df["b"], deg=1)

    assert detail.error is None
    assert detail.method is CorrelationMethod.SPEARMAN
    assert detail.pair.x_column == "a"
    assert detail.pair.y_column == "b"
    assert detail.pair.coefficient == pytest.approx(matrix_pair.coefficient)
    assert detail.pair.ci_low == pytest.approx(matrix_pair.ci_low)
    assert math.isnan(detail.pair.adjusted_p_value)
    assert detail.slope == pytest.approx(slope)
    assert detail.intercept == pytest.approx(intercept)


def test_small_pair_is_not_sampled() -> None:
    df = _frame(size=30)
    df.loc[0, "a"] = np.nan
    detail = analyze_correlation_pair(df, "a", "b")

    assert not detail.sampled
    assert detail.pair.n == 29
    assert detail.sample_x == tuple(df["a"].iloc[1:])
    assert detail.sample_y == tuple(df["b"].iloc[1:])


def test_large_pair_is_sampled_deterministically_in_row_order() -> None:
    size = SCATTER_SAMPLE_SIZE + 1_000
    df = pd.DataFrame({"a": np.arange(size, dtype=float), "b": np.arange(size, dtype=float) * 2.0})
    first = analyze_correlation_pair(df, "a", "b")
    second = analyze_correlation_pair(df, "a", "b")

    assert first.sampled
    assert first.pair.n == size
    assert len(first.sample_x) == SCATTER_SAMPLE_SIZE
    assert first.sample_x == second.sample_x
    assert list(first.sample_x) == sorted(first.sample_x)
    assert first.sample_y == tuple(2.0 * x for x in first.sample_x)
    assert first.slope == pytest.approx(2.0)


@pytest.mark.parametrize(("x", "y"), [("a", "a"), ("a", "text"), ("missing", "b")])
def test_pair_invalid_column_error(x: str, y: str) -> None:
    detail = analyze_correlation_pair(_frame(), x, y)

    assert detail.error is CorrelationError.INVALID_COLUMN
    assert detail.pair.x_column == x
    assert detail.pair.y_column == y
    assert detail.pair.n == 0
    assert math.isnan(detail.slope)
    assert detail.sample_x == ()
    assert not detail.sampled


def test_pair_not_enough_observations_error() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, np.nan], "b": [1.0, 2.0, 3.0]})
    detail = analyze_correlation_pair(df, "a", "b")

    assert detail.error is CorrelationError.NOT_ENOUGH_OBSERVATIONS
    assert detail.pair.n == 2


def test_pair_constant_input_error() -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [5.0, 5.0, 5.0, 5.0]})
    detail = analyze_correlation_pair(df, "a", "b")

    assert detail.error is CorrelationError.CONSTANT_INPUT
    assert detail.pair.n == 4
    assert math.isnan(detail.pair.coefficient)


def test_initialize_correlation_selects_default_columns_without_coefficients() -> None:
    df = pd.DataFrame({f"n{i}": [float(i), float(i + 1)] for i in range(DEFAULT_SELECTED_COLUMNS + 2)})
    df["text"] = ["x", "y"]

    result = initialize_correlation(df)

    assert result.error is None
    assert result.method is CorrelationMethod.PEARSON
    assert result.available_columns == tuple(f"n{i}" for i in range(DEFAULT_SELECTED_COLUMNS + 2))
    assert result.columns == result.available_columns[:DEFAULT_SELECTED_COLUMNS]
    assert result.coefficients == ()
    assert result.pairs == ()


def test_initialize_correlation_reports_too_few_numeric_columns() -> None:
    result = initialize_correlation(pd.DataFrame({"a": [1.0, 2.0], "text": ["x", "y"]}))

    assert result.error is CorrelationError.NOT_ENOUGH_NUMERIC_COLUMNS
    assert result.columns == ()
    assert result.available_columns == ("a",)
