from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import friedmanchisquare, wilcoxon

from expo_jbm329.services.analysis.paired_comparison import (
    PairedComparisonError,
    PairedComparisonMethod,
    analyze_paired_comparison,
    initialize_paired_comparison,
)


def test_initializer_selects_first_two_numeric_columns_without_running_test():
    df = pd.DataFrame({
        "id": ["a", "b", "c"],
        "before": [1.0, 2.0, 3.0],
        "after": [2.0, 3.0, 4.0],
    })

    result = initialize_paired_comparison(df)

    assert result.columns == ("before", "after")
    assert result.available_numeric_columns == ("before", "after")
    assert result.method is PairedComparisonMethod.WILCOXON
    assert result.complete_subjects == 0
    assert result.error is None
    assert math.isnan(result.p_value)


def test_initializer_reports_when_fewer_than_two_numeric_columns_are_available():
    result = initialize_paired_comparison(pd.DataFrame({"id": ["a", "b"], "value": [1.0, 2.0]}))

    assert result.columns == ("value",)
    assert result.error is PairedComparisonError.NOT_ENOUGH_COLUMNS


def test_two_measurements_use_wilcoxon_on_complete_subjects():
    df = pd.DataFrame({
        "before": [1.0, 2.0, 3.0, None],
        "after": [2.0, 4.0, 5.0, 9.0],
    })

    result = analyze_paired_comparison(df, ("before", "after"))
    expected = wilcoxon(df.dropna()["before"], df.dropna()["after"])

    assert result.error is None
    assert result.method is PairedComparisonMethod.WILCOXON
    assert result.complete_subjects == 3
    assert result.excluded_subjects == 1
    assert result.statistic == pytest.approx(expected.statistic)
    assert result.p_value == pytest.approx(expected.pvalue)


def test_three_measurements_use_friedman_and_report_kendalls_w():
    df = pd.DataFrame({
        "baseline": [1.0, 2.0, 3.0, 4.0],
        "followup_1": [2.0, 2.0, 4.0, 5.0],
        "followup_2": [3.0, 4.0, 5.0, 6.0],
    })

    result = analyze_paired_comparison(df, ("baseline", "followup_1", "followup_2"))
    expected = friedmanchisquare(*(df[column] for column in result.columns))

    assert result.error is None
    assert result.method is PairedComparisonMethod.FRIEDMAN
    assert result.complete_subjects == 4
    assert result.excluded_subjects == 0
    assert result.statistic == pytest.approx(expected.statistic)
    assert result.p_value == pytest.approx(expected.pvalue)
    assert result.kendall_w == pytest.approx(expected.statistic / (4 * 2))


@pytest.mark.parametrize(
    "columns",
    [
        (),
        ("before",),
        ("before", "before"),
        ("before", "unknown"),
        ("group", "after"),
    ],
)
def test_invalid_column_selections_return_structured_errors(columns: tuple[str, ...]):
    df = pd.DataFrame({"before": [1.0, 2.0, 3.0], "after": [2.0, 3.0, 4.0], "group": ["a", "b", "c"]})

    result = analyze_paired_comparison(df, columns)

    expected_error = (
        PairedComparisonError.NOT_ENOUGH_COLUMNS if len(columns) < 2 else PairedComparisonError.INVALID_COLUMN
    )
    assert result.error is expected_error
    assert math.isnan(result.p_value)


def test_paired_tests_report_when_no_complete_subjects_are_available():
    df = pd.DataFrame({"before": [1.0, None, 3.0], "after": [None, 3.0, None]})

    result = analyze_paired_comparison(df, ("before", "after"))

    assert result.error is PairedComparisonError.NOT_ENOUGH_COMPLETE_SUBJECTS
    assert result.complete_subjects == 0
    assert result.excluded_subjects == 3


def test_friedman_requires_at_least_three_complete_subjects():
    df = pd.DataFrame({"a": [1.0, 2.0, None], "b": [2.0, 3.0, 4.0], "c": [3.0, 4.0, 5.0]})

    result = analyze_paired_comparison(df, ("a", "b", "c"))

    assert result.error is PairedComparisonError.NOT_ENOUGH_COMPLETE_SUBJECTS
    assert result.complete_subjects == 2
    assert result.excluded_subjects == 1


def test_wilcoxon_reports_no_differences_when_occasions_are_identical():
    result = analyze_paired_comparison(
        pd.DataFrame({"before": [1.0, 2.0, 3.0], "after": [1.0, 2.0, 3.0]}),
        ("before", "after"),
    )

    assert result.error is PairedComparisonError.NO_DIFFERENCES
    assert result.method is PairedComparisonMethod.WILCOXON
    assert result.complete_subjects == 3


def test_friedman_accepts_one_constant_measurement_column_when_others_vary():
    result = analyze_paired_comparison(
        pd.DataFrame({"a": [1.0, 1.0, 1.0, 1.0], "b": [1.0, 2.0, 3.0, 4.0], "c": [2.0, 3.0, 5.0, 7.0]}),
        ("a", "b", "c"),
    )

    assert result.error is None
    assert result.method is PairedComparisonMethod.FRIEDMAN


def test_friedman_reports_no_variation_when_all_measurement_columns_match():
    result = analyze_paired_comparison(
        pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0, 3.0], "c": [1.0, 2.0, 3.0]}),
        ("a", "b", "c"),
    )

    assert result.error is PairedComparisonError.NO_VARIATION


def test_non_finite_values_are_excluded_with_incomplete_subjects():
    df = pd.DataFrame({"before": [1.0, np.inf, 3.0], "after": [2.0, 4.0, 5.0]})

    result = analyze_paired_comparison(df, ("before", "after"))

    assert result.error is None
    assert result.complete_subjects == 2
    assert result.excluded_subjects == 1
