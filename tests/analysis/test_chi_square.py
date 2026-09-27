from __future__ import annotations

import math

import pandas as pd
import pytest

from expo_jbm329.services.analysis.chi_square import ChiSquareError, analyze_chi_square
from expo_jbm329.services.analysis.group_comparison import MAX_GROUPS, ColumnExclusionReason, ExcludedColumn


def _table_df(counts: dict[tuple[str, str], int], row: str = "r", column: str = "c") -> pd.DataFrame:
    """Expand a ``{(row_label, column_label): count}`` mapping into raw rows."""
    records = [pair for pair, n in counts.items() for _ in range(n)]
    return pd.DataFrame(records, columns=[row, column])


def _two_by_three_df() -> pd.DataFrame:
    return _table_df({
        ("x", "a"): 10,
        ("x", "b"): 20,
        ("x", "c"): 30,
        ("y", "a"): 25,
        ("y", "b"): 15,
        ("y", "c"): 5,
    })


def _two_by_two_df() -> pd.DataFrame:
    return _table_df({("x", "p"): 8, ("x", "q"): 2, ("y", "p"): 1, ("y", "q"): 5})


# ----------------------------------------------------------------------
# Column defaulting / structured errors
# ----------------------------------------------------------------------


def test_defaults_to_the_first_two_eligible_columns():
    result = analyze_chi_square(_two_by_three_df())

    assert result.error is None
    assert (result.row_column, result.column_column) == ("r", "c")
    assert result.available_columns == ("r", "c")


def test_high_cardinality_columns_are_not_eligible():
    df = _two_by_three_df()
    df["id"] = [str(i) for i in range(len(df))]

    result = analyze_chi_square(df)

    assert "id" not in result.available_columns


def test_fewer_than_two_eligible_columns_is_not_enough_columns():
    result = analyze_chi_square(pd.DataFrame({"a": ["x", "y", "x"]}))

    assert result.error is ChiSquareError.NOT_ENOUGH_COLUMNS
    assert result.observed == ()
    assert math.isnan(result.chi2_statistic)


def test_same_column_twice_is_invalid():
    result = analyze_chi_square(_two_by_three_df(), "r", "r")

    assert result.error is ChiSquareError.INVALID_COLUMN


def test_nonexistent_column_is_invalid_not_substituted():
    result = analyze_chi_square(_two_by_three_df(), "r", "does_not_exist")

    assert result.error is ChiSquareError.INVALID_COLUMN
    assert result.column_column == "does_not_exist"


def test_too_few_categories_after_dropping_missing_values():
    df = pd.DataFrame({"a": ["x", "y", "x", "y"], "b": ["p", "p", None, None]})

    result = analyze_chi_square(df, "a", "b")

    assert result.error is ChiSquareError.TOO_FEW_CATEGORIES


def test_explicit_column_with_too_many_categories_is_validated_as_given():
    df = pd.DataFrame({"a": ["x", "y"] * 30, "id": [str(i) for i in range(60)]})

    result = analyze_chi_square(df, "a", "id")

    assert result.error is ChiSquareError.TOO_MANY_CATEGORIES
    assert len(set(df["id"])) > MAX_GROUPS


# ----------------------------------------------------------------------
# Contingency table
# ----------------------------------------------------------------------


def test_observed_table_is_row_major_with_sorted_labels():
    result = analyze_chi_square(_two_by_three_df())

    assert result.row_labels == ("x", "y")
    assert result.column_labels == ("a", "b", "c")
    assert result.observed == ((10, 20, 30), (25, 15, 5))
    assert result.total == 105


def test_expected_counts_follow_the_independence_model():
    result = analyze_chi_square(_two_by_three_df())

    # Row totals 60/45, column totals 35/35/35, n = 105.
    assert result.expected[0] == pytest.approx((20.0, 20.0, 20.0))
    assert result.expected[1] == pytest.approx((15.0, 15.0, 15.0))


def test_rows_missing_either_value_are_excluded():
    df = _two_by_three_df()
    extra = pd.DataFrame({"r": ["x", None], "c": [None, "a"]})

    result = analyze_chi_square(pd.concat([df, extra], ignore_index=True))

    assert result.total == 105


# ----------------------------------------------------------------------
# Test statistics (reference values verified directly against scipy)
# ----------------------------------------------------------------------


def test_chi_square_statistics_match_scipy_reference_values():
    result = analyze_chi_square(_two_by_three_df())

    assert result.chi2_statistic == pytest.approx(23.333333333333336)
    assert result.p_value == pytest.approx(8.57493910267228e-06)
    assert result.degrees_of_freedom == 2
    assert result.cramers_v == pytest.approx(0.4714045207910317)
    assert result.yates_correction_applied is False


def test_adjusted_residuals_match_hand_computed_values():
    result = analyze_chi_square(_two_by_three_df())

    # Cell (x, a): (10 - 20) / sqrt(20 * (1 - 60/105) * (1 - 35/105)).
    assert result.adjusted_residuals[0][0] == pytest.approx(-4.183300132670377)
    assert result.adjusted_residuals[0][1] == pytest.approx(0.0)
    assert result.adjusted_residuals[1][2] == pytest.approx(-4.183300132670378)


def test_non_two_by_two_table_has_no_fisher_result():
    result = analyze_chi_square(_two_by_three_df())

    assert result.fisher_odds_ratio is None
    assert result.fisher_p_value is None


def test_two_by_two_table_applies_yates_and_adds_fisher_exact():
    result = analyze_chi_square(_two_by_two_df())

    assert result.yates_correction_applied is True
    assert result.degrees_of_freedom == 1
    assert result.chi2_statistic == pytest.approx(3.8095238095238093)
    assert result.p_value == pytest.approx(0.050961936967763424)
    assert result.cramers_v == pytest.approx(0.6180700462007377)
    assert result.fisher_odds_ratio == pytest.approx(20.0)
    assert result.fisher_p_value == pytest.approx(0.034965034965034975)


def test_perfectly_independent_columns_yield_zero_effect_size():
    df = _table_df({("x", "p"): 10, ("x", "q"): 20, ("y", "p"): 10, ("y", "q"): 20})

    result = analyze_chi_square(df)

    assert result.p_value == pytest.approx(1.0)
    assert result.cramers_v == pytest.approx(0.0)


# ----------------------------------------------------------------------
# Cochran's rule
# ----------------------------------------------------------------------


def test_cochran_rule_is_satisfied_with_large_expected_counts():
    result = analyze_chi_square(_two_by_three_df())

    assert result.low_expected_fraction == pytest.approx(0.0)
    assert result.min_expected == pytest.approx(15.0)
    assert result.cochran_violated is False


def test_cochran_rule_is_violated_with_small_expected_counts():
    result = analyze_chi_square(_two_by_two_df())

    assert result.low_expected_fraction == pytest.approx(0.75)
    assert result.min_expected == pytest.approx(2.625)
    assert result.cochran_violated is True


def test_cochran_rule_is_violated_when_any_expected_count_is_below_one():
    # 2x5 table, n = 201: column "e" (total 1) yields two expected counts of
    # ~0.5. That's exactly 2 of 10 cells (20%) below 5 - *not* over the 20%
    # threshold - so only the "any expected count below 1" branch applies.
    counts: dict[tuple[str, str], int] = {}
    for row in ("x", "y"):
        for column in ("a", "b", "c", "d"):
            counts[row, column] = 25
    counts["x", "e"] = 1
    df = _table_df(counts)

    result = analyze_chi_square(df)

    assert result.low_expected_fraction == pytest.approx(0.2)
    assert result.min_expected < 1.0
    assert result.cochran_violated is True


def test_result_reports_excluded_columns_on_success_and_on_error():
    df = pd.DataFrame({
        "id": list(range(24)),
        "grp": ["A", "B"] * 12,
        "color": ["r", "g", "b"] * 8,
    })

    success = analyze_chi_square(df)
    error = analyze_chi_square(df, "grp", "grp")

    expected = (ExcludedColumn("id", 24, ColumnExclusionReason.TOO_MANY_VALUES),)
    assert success.error is None
    assert success.excluded_columns == expected
    assert error.error is ChiSquareError.INVALID_COLUMN
    assert error.excluded_columns == expected
