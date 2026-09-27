"""Tests for the univariate outlier detection service."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis.outliers import (
    DEFAULT_THRESHOLDS,
    HISTOGRAM_BINS,
    MAX_EXTREME_OBSERVATIONS,
    MAX_THRESHOLD,
    MIN_THRESHOLD,
    ColumnOutlierStatus,
    ColumnOutlierSummary,
    OutlierError,
    OutlierMethod,
    OutlierSummaryResult,
    analyze_outlier_column,
    analyze_outlier_summary,
    default_column,
    max_possible_z_score,
)

_VALUES = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 100.0]


def _column(result: OutlierSummaryResult, name: str) -> ColumnOutlierSummary:
    return next(summary for summary in result.columns if summary.column == name)


# ----------------------------------------------------------------------
# Fences per method
# ----------------------------------------------------------------------


def test_iqr_fences_are_tukeys_fences():
    df = pd.DataFrame({"a": _VALUES})
    q1, q3 = np.quantile(_VALUES, [0.25, 0.75])

    summary = _column(analyze_outlier_summary(df, OutlierMethod.IQR), "a")

    assert summary.lower_fence == pytest.approx(q1 - 1.5 * (q3 - q1))
    assert summary.upper_fence == pytest.approx(q3 + 1.5 * (q3 - q1))
    assert (summary.outlier_count, summary.low_count, summary.high_count) == (1, 0, 1)


def test_z_score_fences_use_the_sample_standard_deviation():
    values = np.concatenate([np.zeros(50), [10.0]])
    df = pd.DataFrame({"a": values})
    mean, sd = values.mean(), values.std(ddof=1)

    summary = _column(analyze_outlier_summary(df, OutlierMethod.Z_SCORE), "a")

    assert summary.lower_fence == pytest.approx(mean - 3 * sd)
    assert summary.upper_fence == pytest.approx(mean + 3 * sd)
    assert summary.outlier_count == 1


def test_modified_z_score_fences_use_the_scaled_mad():
    df = pd.DataFrame({"a": _VALUES})
    median = np.median(_VALUES)
    mad = np.median(np.abs(np.array(_VALUES) - median))

    summary = _column(analyze_outlier_summary(df, OutlierMethod.MODIFIED_Z_SCORE), "a")

    assert summary.lower_fence == pytest.approx(median - 3.5 * mad / 0.6745)
    assert summary.upper_fence == pytest.approx(median + 3.5 * mad / 0.6745)
    assert summary.outlier_count == 1


def test_modified_z_score_falls_back_to_mean_absolute_deviation_when_mad_is_zero():
    values = [1.0] * 7 + [2.0, 3.0, 50.0]
    df = pd.DataFrame({"a": values})
    mean_ad = np.mean(np.abs(np.array(values) - 1.0))

    detail = analyze_outlier_column(df, "a", OutlierMethod.MODIFIED_Z_SCORE)

    assert detail.mad == 0.0
    assert detail.mad_fallback
    assert detail.scale == pytest.approx(1.253314 * mean_ad)
    assert detail.summary.outlier_count == 1
    assert detail.extremes[0].score == pytest.approx(49.0 / detail.scale)


def test_custom_threshold_moves_the_fences():
    df = pd.DataFrame({"a": _VALUES})

    default = _column(analyze_outlier_summary(df, OutlierMethod.IQR), "a")
    wide = _column(analyze_outlier_summary(df, OutlierMethod.IQR, 3.0), "a")

    assert wide.upper_fence > default.upper_fence
    assert analyze_outlier_summary(df, OutlierMethod.IQR, 3.0).threshold == 3.0


@pytest.mark.parametrize("method", list(OutlierMethod))
def test_default_threshold_is_used_when_none(method):
    result = analyze_outlier_summary(pd.DataFrame({"a": _VALUES}), method)

    assert result.threshold == DEFAULT_THRESHOLDS[method]
    assert result.method is method


def test_low_and_high_outliers_are_counted_separately():
    df = pd.DataFrame({"a": [-100.0, *_VALUES[:-1], 100.0, 200.0]})

    summary = _column(analyze_outlier_summary(df), "a")

    assert (summary.low_count, summary.high_count, summary.outlier_count) == (1, 2, 3)


# ----------------------------------------------------------------------
# Column status
# ----------------------------------------------------------------------


def test_missing_and_infinite_values_are_ignored():
    df = pd.DataFrame({"a": [*_VALUES, np.nan, np.inf, -np.inf]})

    summary = _column(analyze_outlier_summary(df), "a")

    assert summary.n == len(_VALUES)
    assert summary.missing == 3
    assert summary.outlier_fraction == pytest.approx(0.1)


def test_too_few_values_cannot_be_screened():
    df = pd.DataFrame({"a": [1.0, 2.0, np.nan]})

    summary = _column(analyze_outlier_summary(df), "a")

    assert summary.status is ColumnOutlierStatus.NOT_ENOUGH_OBSERVATIONS
    assert summary.outlier_count == 0
    assert math.isnan(summary.lower_fence)


def test_empty_column_has_undefined_outlier_fraction():
    df = pd.DataFrame({"a": [np.nan, np.nan]}, dtype="float64")

    summary = _column(analyze_outlier_summary(df), "a")

    assert summary.n == 0
    assert math.isnan(summary.outlier_fraction)


@pytest.mark.parametrize("method", [OutlierMethod.Z_SCORE, OutlierMethod.MODIFIED_Z_SCORE])
def test_constant_column_has_zero_spread_for_score_methods(method):
    df = pd.DataFrame({"a": [5.0] * 10})

    assert _column(analyze_outlier_summary(df, method), "a").status is ColumnOutlierStatus.ZERO_SPREAD


def test_constant_column_has_no_iqr_outliers():
    summary = _column(analyze_outlier_summary(pd.DataFrame({"a": [5.0] * 10})), "a")

    assert summary.status is None
    assert summary.outlier_count == 0
    assert summary.lower_fence == summary.upper_fence == 5.0


# ----------------------------------------------------------------------
# Summary result
# ----------------------------------------------------------------------


def test_summary_covers_numeric_columns_ranked_by_outlier_fraction():
    df = pd.DataFrame({
        "few": [*_VALUES],
        "none": [float(i) for i in range(10)],
        "many": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 30.0, 50.0],
        "short": [1.0, 2.0, *[np.nan] * 8],
        "text": list("abcdefghij"),
        "flag": [True, False] * 5,
    })

    result = analyze_outlier_summary(df)

    assert result.error is None
    assert result.available_columns == ("few", "none", "many", "short")
    assert [c.column for c in result.columns] == ["many", "few", "none", "short"]
    assert result.row_count == 10
    assert default_column(result) == "many"


def test_ties_keep_dataset_order():
    df = pd.DataFrame({"b": _VALUES, "a": _VALUES})

    assert [c.column for c in analyze_outlier_summary(df).columns] == ["b", "a"]


def test_rows_with_outliers_counts_each_row_once():
    df = pd.DataFrame({"a": _VALUES, "b": _VALUES, "c": [100.0, *_VALUES[:-1]]})

    result = analyze_outlier_summary(df)

    assert result.rows_with_outliers == 2  # row 10 (a and b) and row 1 (c)


def test_rows_with_outliers_is_positional_even_with_a_duplicate_index():
    df = pd.DataFrame({"a": _VALUES, "c": [100.0, *_VALUES[:-1]]}, index=[0] * 10)

    assert analyze_outlier_summary(df).rows_with_outliers == 2


def test_no_numeric_column_error():
    result = analyze_outlier_summary(pd.DataFrame({"t": ["a", "b", "c"]}))

    assert result.error is OutlierError.NO_NUMERIC_COLUMN
    assert result.columns == ()
    assert default_column(result) is None


@pytest.mark.parametrize("threshold", [MIN_THRESHOLD / 2, MAX_THRESHOLD * 2, math.nan, math.inf])
def test_invalid_threshold_error(threshold):
    df = pd.DataFrame({"a": _VALUES})

    assert analyze_outlier_summary(df, OutlierMethod.IQR, threshold).error is OutlierError.INVALID_THRESHOLD
    assert analyze_outlier_column(df, "a", OutlierMethod.IQR, threshold).error is OutlierError.INVALID_THRESHOLD


def test_input_frame_is_not_mutated():
    df = pd.DataFrame({"a": [*_VALUES, np.nan], "t": list("abcdefghijk")})
    before = df.copy()

    analyze_outlier_summary(df)
    analyze_outlier_column(df, "a")

    pd.testing.assert_frame_equal(df, before)


# ----------------------------------------------------------------------
# Column detail
# ----------------------------------------------------------------------


def test_detail_statistics():
    df = pd.DataFrame({"a": _VALUES})
    array = np.array(_VALUES)

    detail = analyze_outlier_column(df, "a", OutlierMethod.Z_SCORE)

    assert detail.error is None
    assert detail.mean == pytest.approx(array.mean())
    assert detail.std == pytest.approx(array.std(ddof=1))
    assert detail.scale == pytest.approx(array.std(ddof=1))
    assert detail.median == pytest.approx(np.median(array))
    assert detail.q1 == pytest.approx(np.quantile(array, 0.25))
    assert detail.q3 == pytest.approx(np.quantile(array, 0.75))
    assert detail.mad == pytest.approx(np.median(np.abs(array - np.median(array))))
    assert not detail.mad_fallback


def test_iqr_detail_scale_is_the_iqr():
    detail = analyze_outlier_column(pd.DataFrame({"a": _VALUES}), "a", OutlierMethod.IQR)

    assert detail.scale == pytest.approx(detail.q3 - detail.q1)


def test_histogram_splits_inliers_and_outliers_over_shared_bins():
    df = pd.DataFrame({"a": [*_VALUES, np.nan]})

    detail = analyze_outlier_column(df, "a")

    assert len(detail.histogram_edges) == HISTOGRAM_BINS + 1
    assert detail.histogram_edges[0] == 1.0
    assert detail.histogram_edges[-1] == 100.0
    assert sum(detail.inlier_counts) == 9
    assert sum(detail.outlier_counts) == 1
    assert detail.outlier_counts[-1] == 1


def test_extremes_list_flagged_rows_most_extreme_first_with_all_row_values():
    df = pd.DataFrame(
        {
            "t": list("abcdefghijklm"),
            "a": [-50.0, *_VALUES[:-1], 100.0, np.nan, 30.0],
        },
        index=[5] * 13,
    )

    detail = analyze_outlier_column(df, "a")

    assert detail.row_columns == ("t", "a")
    assert [(e.row_number, e.value) for e in detail.extremes] == [(11, 100.0), (1, -50.0), (13, 30.0)]
    assert detail.extremes[0].row_values == ("k", 100.0)
    assert detail.extremes[0].score == pytest.approx(100.0 - detail.summary.upper_fence)
    assert detail.extremes[1].score == pytest.approx(-50.0 - detail.summary.lower_fence)


def test_extremes_are_capped():
    values = np.concatenate([np.zeros(1_000), 1_000 + np.arange(MAX_EXTREME_OBSERVATIONS + 50, dtype=float)])
    df = pd.DataFrame({"a": values})

    detail = analyze_outlier_column(df, "a", OutlierMethod.IQR)

    assert detail.summary.outlier_count > MAX_EXTREME_OBSERVATIONS
    assert len(detail.extremes) == MAX_EXTREME_OBSERVATIONS
    assert detail.extremes[0].value == values.max()


def test_unscreenable_column_detail_has_no_extremes_but_a_histogram():
    detail = analyze_outlier_column(pd.DataFrame({"a": [5.0] * 10}), "a", OutlierMethod.Z_SCORE)

    assert detail.error is None
    assert detail.summary.status is ColumnOutlierStatus.ZERO_SPREAD
    assert detail.extremes == ()
    assert sum(detail.inlier_counts) == 10
    assert math.isnan(detail.scale)


def test_detail_of_an_empty_column():
    detail = analyze_outlier_column(pd.DataFrame({"a": [np.nan]}, dtype="float64"), "a")

    assert detail.summary.status is ColumnOutlierStatus.NOT_ENOUGH_OBSERVATIONS
    assert detail.histogram_edges == ()
    assert math.isnan(detail.mean)
    assert math.isnan(detail.std)


@pytest.mark.parametrize("column", ["missing", "t"])
def test_detail_invalid_column_error(column):
    detail = analyze_outlier_column(pd.DataFrame({"a": _VALUES, "t": list("abcdefghij")}), column)

    assert detail.error is OutlierError.INVALID_COLUMN
    assert detail.summary.column == column
    assert detail.extremes == ()


# ----------------------------------------------------------------------
# max_possible_z_score
# ----------------------------------------------------------------------


def test_max_possible_z_score():
    assert max_possible_z_score(10) == pytest.approx(9 / math.sqrt(10))
    assert math.isnan(max_possible_z_score(1))
    values = np.array([0.0] * 9 + [1.0])
    assert ((values - values.mean()) / values.std(ddof=1)).max() == pytest.approx(max_possible_z_score(10))
