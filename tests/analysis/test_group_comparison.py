from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis.group_comparison import (
    MAX_GROUPS,
    MIN_GROUPS,
    GroupComparisonError,
    GroupWarningReason,
    analyze_group_comparison,
)


def _two_group_df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "value": np.concatenate([rng.normal(10, 2, 30), rng.normal(12, 2, 30)]),
        "grp": ["A"] * 30 + ["B"] * 30,
    })


def _three_group_df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "value": np.concatenate([rng.normal(10, 2, 20), rng.normal(12, 2, 20), rng.normal(11, 2, 20)]),
        "grp": ["A"] * 20 + ["B"] * 20 + ["C"] * 20,
    })


# ----------------------------------------------------------------------
# Column defaulting / eligibility
# ----------------------------------------------------------------------


def test_defaults_to_first_numeric_and_first_eligible_grouping_column():
    df = _two_group_df()

    result = analyze_group_comparison(df)

    assert result.numeric_column == "value"
    assert result.grouping_column == "grp"
    assert result.error is None


def test_available_numeric_columns_lists_every_numeric_column_in_order():
    df = pd.DataFrame({"a": [1.0, 2.0], "b": ["x", "y"], "c": [3, 4]})

    result = analyze_group_comparison(df)

    assert result.available_numeric_columns == ("a", "c")


def test_available_grouping_columns_excludes_columns_outside_the_group_count_range():
    # "const" has 1 distinct value (< MIN_GROUPS), "id" has 60 (> MAX_GROUPS).
    df = pd.DataFrame({
        "value": range(60),
        "const": [1] * 60,
        "grp": (["A"] * 30 + ["B"] * 30),
        "id": range(60),
    })

    result = analyze_group_comparison(df)

    assert result.available_grouping_columns == ("grp",)


def test_grouping_candidate_columns_allow_any_dtype_including_numeric_flags():
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0], "flag": [0, 0, 1, 1]})

    result = analyze_group_comparison(df)

    assert "flag" in result.available_grouping_columns


def test_grouping_column_defaults_exclude_the_selected_numeric_column():
    # "flag" is both numeric (0/1) and a valid grouping candidate; since
    # it's picked as the numeric column, it must not also default as the
    # grouping column (comparing a column to itself is meaningless).
    df = pd.DataFrame({"flag": [0, 0, 1, 1], "other_flag": [1, 0, 1, 0]})

    result = analyze_group_comparison(df, numeric_column="flag")

    assert result.grouping_column == "other_flag"


# ----------------------------------------------------------------------
# Structured errors
# ----------------------------------------------------------------------


def test_no_numeric_column_available():
    df = pd.DataFrame({"a": ["x", "y"], "b": ["p", "q"]})

    result = analyze_group_comparison(df)

    assert result.error is GroupComparisonError.NO_NUMERIC_COLUMN
    assert result.groups == ()
    assert result.pairwise is None
    assert result.multi_group is None


def test_no_eligible_grouping_column_available():
    df = pd.DataFrame({"value": range(60), "id": range(60)})

    result = analyze_group_comparison(df)

    assert result.error is GroupComparisonError.NO_GROUPING_COLUMN


def test_explicit_numeric_column_that_is_not_numeric_is_reported_not_substituted():
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0], "grp": ["A", "A", "B", "B"], "text": ["x", "y", "z", "w"]})

    result = analyze_group_comparison(df, numeric_column="text", grouping_column="grp")

    assert result.error is GroupComparisonError.NO_NUMERIC_COLUMN
    assert result.numeric_column == "text"


def test_explicit_grouping_column_equal_to_numeric_column_is_reported_not_substituted():
    df = _two_group_df()

    result = analyze_group_comparison(df, numeric_column="value", grouping_column="value")

    assert result.error is GroupComparisonError.NO_GROUPING_COLUMN
    assert result.grouping_column == "value"


def test_explicit_grouping_column_that_does_not_exist_is_reported_not_substituted():
    df = _two_group_df()

    result = analyze_group_comparison(df, numeric_column="value", grouping_column="does_not_exist")

    assert result.error is GroupComparisonError.NO_GROUPING_COLUMN


def test_explicit_grouping_column_with_too_many_distinct_values_is_validated_as_given():
    """An explicitly requested column is validated as-is, never silently
    swapped for a different (more suitable) column - the caller gets an
    honest answer about the exact column it asked for."""
    df = pd.DataFrame({"value": range(MAX_GROUPS + 5), "id": range(MAX_GROUPS + 5)})

    result = analyze_group_comparison(df, numeric_column="value", grouping_column="id")

    assert result.error is GroupComparisonError.TOO_MANY_GROUPS
    assert result.grouping_column == "id"


def test_too_few_groups_after_dropping_missing_numeric_values():
    """A grouping column can be eligible in general (2..MAX_GROUPS raw
    distinct values) yet still resolve to fewer valid groups once rows
    with a missing numeric value are dropped."""
    df = pd.DataFrame({"value": [1.0] * 30 + [np.nan] * 30, "grp": ["A"] * 30 + ["B"] * 30})

    result = analyze_group_comparison(df, numeric_column="value", grouping_column="grp")

    assert result.error is GroupComparisonError.TOO_FEW_GROUPS


def test_single_remaining_group_after_dropping_missing_values_is_too_few_groups():
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0], "grp": ["A", "A", "A"]})

    result = analyze_group_comparison(df, numeric_column="value", grouping_column="grp")

    assert result.error is GroupComparisonError.TOO_FEW_GROUPS


# ----------------------------------------------------------------------
# Per-group summaries
# ----------------------------------------------------------------------


def test_group_summaries_report_count_mean_and_quartiles():
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0, 10.0, 20.0, 30.0, 40.0], "grp": ["A"] * 4 + ["B"] * 4})

    result = analyze_group_comparison(df, "value", "grp")

    a, b = result.groups
    assert a.label == "A"
    assert a.count == 4
    assert a.mean == pytest.approx(2.5)
    assert a.minimum == pytest.approx(1.0)
    assert a.maximum == pytest.approx(4.0)
    assert a.median == pytest.approx(2.5)
    assert b.mean == pytest.approx(25.0)


def test_groups_are_ordered_by_ascending_label():
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], "grp": ["C", "C", "A", "A", "B", "B"]})

    result = analyze_group_comparison(df, "value", "grp")

    assert [g.label for g in result.groups] == ["A", "B", "C"]


def test_group_with_a_single_observation_warns_about_variance_and_normality():
    df = pd.DataFrame({"value": [5.0, 1.0, 2.0, 3.0, 4.0], "grp": ["A", "B", "B", "B", "B"]})

    result = analyze_group_comparison(df, "value", "grp")

    a = next(g for g in result.groups if g.label == "A")
    assert a.count == 1
    assert math.isnan(a.std)
    assert math.isnan(a.shapiro_statistic)

    reasons = {(w.group_label, w.reason) for w in result.warnings}
    assert ("A", GroupWarningReason.TOO_FEW_FOR_VARIANCE) in reasons
    assert ("A", GroupWarningReason.TOO_FEW_FOR_NORMALITY) in reasons


def test_group_with_two_observations_only_warns_about_normality():
    df = pd.DataFrame({"value": [5.0, 6.0, 1.0, 2.0, 3.0, 4.0], "grp": ["A", "A", "B", "B", "B", "B"]})

    result = analyze_group_comparison(df, "value", "grp")

    a = next(g for g in result.groups if g.label == "A")
    assert a.count == 2
    assert not math.isnan(a.std)

    reasons = {(w.group_label, w.reason) for w in result.warnings}
    assert ("A", GroupWarningReason.TOO_FEW_FOR_VARIANCE) not in reasons
    assert ("A", GroupWarningReason.TOO_FEW_FOR_NORMALITY) in reasons


def test_no_warnings_when_every_group_has_enough_observations():
    result = analyze_group_comparison(_two_group_df(), "value", "grp")

    assert result.warnings == ()


def test_non_numeric_and_infinite_values_are_dropped_before_grouping():
    df = pd.DataFrame({
        "value": [1.0, 2.0, 3.0, np.nan, float("inf"), 10.0, 20.0, 30.0],
        "grp": ["A", "A", "A", "A", "A", "B", "B", "B"],
    })

    result = analyze_group_comparison(df, "value", "grp")

    a = next(g for g in result.groups if g.label == "A")
    assert a.count == 3  # NaN and inf dropped


# ----------------------------------------------------------------------
# Pairwise comparison (2 groups)
# ----------------------------------------------------------------------


def test_two_groups_populate_pairwise_and_not_multi_group():
    result = analyze_group_comparison(_two_group_df(), "value", "grp")

    assert result.pairwise is not None
    assert result.multi_group is None


def test_pairwise_statistics_match_known_scipy_reference_values():
    """Cross-checked directly against scipy in isolation (see session
    notes): ttest_ind(a, b, equal_var=False) and mannwhitneyu(a, b) with
    this exact seeded data give these exact values."""
    result = analyze_group_comparison(_two_group_df(), "value", "grp")

    pairwise = result.pairwise
    assert pairwise is not None
    assert pairwise.t_statistic == pytest.approx(-5.371949870025589)
    assert pairwise.t_p_value == pytest.approx(1.442996693360877e-06)
    assert pairwise.t_degrees_of_freedom == pytest.approx(57.92758039371246)
    assert pairwise.mean_difference_ci_low == pytest.approx(-3.0114014973635843)
    assert pairwise.mean_difference_ci_high == pytest.approx(-1.376369257419432)
    assert pairwise.cohens_d == pytest.approx(-1.387031492218014)
    assert pairwise.u_statistic == pytest.approx(150.0)
    assert pairwise.u_p_value == pytest.approx(9.513937913202741e-06)
    assert pairwise.rank_biserial_correlation == pytest.approx(0.6666666666666667)


def test_mean_difference_is_first_group_minus_second_group():
    df = pd.DataFrame({"value": [10.0, 10.0, 4.0, 4.0], "grp": ["A", "A", "B", "B"]})

    result = analyze_group_comparison(df, "value", "grp")

    assert result.pairwise is not None
    assert result.pairwise.mean_difference == pytest.approx(6.0)


def test_cohens_d_is_nan_when_a_group_has_fewer_than_two_observations():
    df = pd.DataFrame({"value": [5.0, 1.0, 2.0, 3.0, 4.0], "grp": ["A", "B", "B", "B", "B"]})

    result = analyze_group_comparison(df, "value", "grp")

    assert result.pairwise is not None
    assert math.isnan(result.pairwise.cohens_d)


def test_two_fully_constant_groups_do_not_crash_and_report_no_difference():
    """Unlike Kruskal-Wallis (3+ groups), Mann-Whitney U handles fully
    constant, identical-value groups without raising - verified directly
    against scipy - but this is still worth locking in as a regression
    test given the closely related Kruskal-Wallis crash found next to it."""
    df = pd.DataFrame({"value": [5.0, 5.0, 5.0, 5.0], "grp": ["A", "A", "B", "B"]})

    result = analyze_group_comparison(df, "value", "grp")

    assert result.pairwise is not None
    assert result.pairwise.mean_difference == pytest.approx(0.0)
    assert result.pairwise.u_p_value == pytest.approx(1.0)


def test_identical_groups_yield_a_high_p_value_and_near_zero_effect_size():
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0], "grp": ["A"] * 4 + ["B"] * 4})

    result = analyze_group_comparison(df, "value", "grp")

    assert result.pairwise is not None
    assert result.pairwise.t_p_value == pytest.approx(1.0)
    assert result.pairwise.mean_difference == pytest.approx(0.0)


# ----------------------------------------------------------------------
# Multi-group comparison (3+ groups)
# ----------------------------------------------------------------------


def test_three_groups_populate_multi_group_and_not_pairwise():
    result = analyze_group_comparison(_three_group_df(), "value", "grp")

    assert result.multi_group is not None
    assert result.pairwise is None


def test_multi_group_statistics_match_known_scipy_reference_values():
    result = analyze_group_comparison(_three_group_df(), "value", "grp")

    multi = result.multi_group
    assert multi is not None
    assert multi.f_statistic == pytest.approx(10.364581080972242)
    assert multi.f_p_value == pytest.approx(0.00014480707177904137)
    assert multi.eta_squared == pytest.approx(0.26668449247859394)
    assert multi.h_statistic == pytest.approx(13.574098360655768)
    assert multi.h_p_value == pytest.approx(0.0011282932567261627)
    assert multi.epsilon_squared == pytest.approx(0.20305435720448714)


def test_all_constant_values_yield_undefined_eta_squared_and_h_statistic():
    """`ss_total` is zero only when every single value across all groups is
    identical (not merely when every group's *mean* matches). scipy's
    kruskal() raises rather than returning NaN in this exact situation
    (no rank variation at all) - verified this must be caught, not left
    to crash the whole analysis."""
    df = pd.DataFrame({"value": [5.0] * 6, "grp": ["A"] * 2 + ["B"] * 2 + ["C"] * 2})

    result = analyze_group_comparison(df, "value", "grp")

    assert result.multi_group is not None
    assert math.isnan(result.multi_group.eta_squared)  # ss_total == 0
    assert math.isnan(result.multi_group.f_statistic)
    assert math.isnan(result.multi_group.h_statistic)
    assert math.isnan(result.multi_group.h_p_value)
    assert math.isnan(result.multi_group.epsilon_squared)


def test_identical_group_means_yield_zero_eta_squared_despite_within_group_variance():
    df = pd.DataFrame({"value": [1.0, 2.0] * 3, "grp": ["A"] * 2 + ["B"] * 2 + ["C"] * 2})

    result = analyze_group_comparison(df, "value", "grp")

    assert result.multi_group is not None
    assert result.multi_group.f_p_value == pytest.approx(1.0)
    assert result.multi_group.eta_squared == pytest.approx(0.0)


def test_maximum_allowed_group_count_is_accepted():
    values = list(range(MAX_GROUPS * 3))
    groups = [str(i % MAX_GROUPS) for i in range(MAX_GROUPS * 3)]
    df = pd.DataFrame({"value": values, "grp": groups})

    result = analyze_group_comparison(df, "value", "grp")

    assert result.error is None
    assert len(result.groups) == MAX_GROUPS


def test_minimum_allowed_group_count_is_accepted():
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0], "grp": ["A", "A", "B", "B"]})

    result = analyze_group_comparison(df, "value", "grp")

    assert result.error is None
    assert len(result.groups) == MIN_GROUPS
