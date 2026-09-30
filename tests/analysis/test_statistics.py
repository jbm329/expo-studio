from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis.normality import SHAPIRO_LARGE_SAMPLE_THRESHOLD
from expo_jbm329.services.analysis.statistics import (
    ColumnDescriptiveStatistics,
    analyze_descriptive_statistics,
)


def _get(result, column: str) -> ColumnDescriptiveStatistics:
    matches = [c for c in result.columns if c.column == column]
    assert len(matches) == 1, f"expected exactly one column named {column!r}"
    return matches[0]


def test_analyze_descriptive_statistics_matches_known_reference_values():
    df = pd.DataFrame({"nums": [1.0, 2.0, 3.0, 4.0, 5.0]})

    result = analyze_descriptive_statistics(df)

    stats = _get(result, "nums")
    assert stats.count == 5
    assert stats.missing_count == 0
    assert stats.missing_fraction == 0.0
    assert stats.mean == 3.0
    assert stats.median == 3.0
    assert stats.std == pytest.approx(1.5811388300841898)
    assert stats.variance == pytest.approx(2.5)
    assert stats.minimum == 1.0
    assert stats.maximum == 5.0
    assert stats.range == 4.0
    assert stats.q1 == 2.0
    assert stats.q3 == 4.0
    assert stats.iqr == 2.0
    assert stats.skewness == 0.0
    assert stats.kurtosis == pytest.approx(-1.2)
    assert len(stats.histogram_bins) == len(stats.histogram_counts) + 1
    assert sum(stats.histogram_counts) == stats.count
    assert stats.shapiro_statistic == pytest.approx(0.986762155211559)
    assert stats.shapiro_p_value == pytest.approx(0.9671739349728582)


def test_analyze_descriptive_statistics_counts_missing_values():
    df = pd.DataFrame({"col": [1.0, None, 3.0, None, 5.0]})

    result = analyze_descriptive_statistics(df)

    stats = _get(result, "col")
    assert stats.count == 3
    assert stats.missing_count == 2
    assert stats.missing_fraction == 0.4
    # Shapiro-Wilk must only see the 3 non-null values, not the missing ones.
    assert stats.shapiro_statistic == pytest.approx(1.0)
    assert stats.shapiro_p_value == pytest.approx(1.0)


def test_analyze_descriptive_statistics_excludes_non_numeric_columns():
    df = pd.DataFrame({
        "nums": [1, 2, 3],
        "text": ["a", "b", "c"],
        "flag": [True, False, True],
        "cat": pd.Categorical(["x", "y", "x"]),
    })

    result = analyze_descriptive_statistics(df)

    assert [c.column for c in result.columns] == ["nums"]


def test_analyze_descriptive_statistics_preserves_original_column_order():
    df = pd.DataFrame({"c": [1, 2], "a": [3, 4], "b": [5, 6]})

    result = analyze_descriptive_statistics(df)

    assert [c.column for c in result.columns] == ["c", "a", "b"]


def test_analyze_descriptive_statistics_includes_fully_missing_numeric_column():
    """A numeric column with no non-null values must still appear (with
    NaN statistics), not be silently dropped.
    """
    df = pd.DataFrame({"all_nan": pd.Series([np.nan] * 5, dtype="float64")})

    result = analyze_descriptive_statistics(df)

    stats = _get(result, "all_nan")
    assert stats.count == 0
    assert stats.missing_count == 5
    assert stats.missing_fraction == 1.0
    assert math.isnan(stats.mean)
    assert math.isnan(stats.std)
    assert math.isnan(stats.variance)
    assert math.isnan(stats.range)
    assert math.isnan(stats.iqr)
    assert stats.histogram_bins == ()
    assert stats.histogram_counts == ()
    assert math.isnan(stats.shapiro_statistic)
    assert math.isnan(stats.shapiro_p_value)


def test_analyze_descriptive_statistics_handles_dataframe_with_no_numeric_columns():
    df = pd.DataFrame({"text": ["a", "b", "c"]})

    result = analyze_descriptive_statistics(df)

    assert result.columns == ()


def test_analyze_descriptive_statistics_handles_completely_empty_dataframe():
    result = analyze_descriptive_statistics(pd.DataFrame())

    assert result.columns == ()


def test_variance_is_derived_from_squared_standard_deviation():
    df = pd.DataFrame({"col": [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]})

    result = analyze_descriptive_statistics(df)

    stats = _get(result, "col")
    assert stats.variance == pytest.approx(stats.std**2)


def test_range_and_iqr_are_derived_from_min_max_quartiles():
    df = pd.DataFrame({"col": [10.0, 20.0, 30.0, 40.0, 50.0]})

    result = analyze_descriptive_statistics(df)

    stats = _get(result, "col")
    assert stats.range == stats.maximum - stats.minimum
    assert stats.iqr == stats.q3 - stats.q1


def test_histogram_bin_edges_span_the_full_value_range():
    df = pd.DataFrame({"col": list(range(1, 21))})  # 1..20

    result = analyze_descriptive_statistics(df)

    stats = _get(result, "col")
    assert stats.histogram_bins[0] == pytest.approx(stats.minimum)
    assert stats.histogram_bins[-1] == pytest.approx(stats.maximum)
    assert sum(stats.histogram_counts) == stats.count


def test_shapiro_wilk_flags_clearly_non_normal_data():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({"uniform": rng.uniform(0, 100, size=200)})

    result = analyze_descriptive_statistics(df)

    stats = _get(result, "uniform")
    # Uniformly distributed data should be clearly rejected as non-normal.
    assert stats.shapiro_p_value < 0.001


def test_shapiro_wilk_does_not_reject_clearly_normal_data():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({"normal": rng.normal(loc=50, scale=10, size=200)})

    result = analyze_descriptive_statistics(df)

    stats = _get(result, "normal")
    assert stats.shapiro_p_value > 0.05


def test_shapiro_wilk_handles_a_constant_column():
    df = pd.DataFrame({"col": [5.0] * 50})

    result = analyze_descriptive_statistics(df)

    stats = _get(result, "col")
    assert stats.shapiro_statistic == pytest.approx(1.0)
    assert stats.shapiro_p_value == pytest.approx(1.0)


def test_shapiro_wilk_handles_large_samples_without_raising():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({"col": rng.normal(size=10_000)})

    result = analyze_descriptive_statistics(df)

    stats = _get(result, "col")
    assert stats.count > SHAPIRO_LARGE_SAMPLE_THRESHOLD
    assert not math.isnan(stats.shapiro_statistic)
    assert not math.isnan(stats.shapiro_p_value)
