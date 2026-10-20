"""Regression coverage for the documented analytical policy inventory."""

from __future__ import annotations

import importlib
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis import limits
from expo_jbm329.services.analysis.group_comparison import classify_grouping_columns
from expo_jbm329.services.analysis.outliers import DEFAULT_THRESHOLDS, OutlierMethod
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.pca import analyze_pca
from expo_jbm329.services.analysis.regression import (
    RegressionError,
    analyze_regression,
    classify_predictor_columns,
)
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
from expo_jbm329.services.analysis.timeseries import analyze_time_series


@pytest.mark.parametrize(
    ("owner", "legacy_name", "central_name", "expected"),
    [
        ("group_comparison", "MAX_GROUPS", "CATEGORICAL_MAX_DISTINCT_VALUES", 20),
        ("statistics", "MAX_GROUPS", "CATEGORICAL_MAX_DISTINCT_VALUES", 20),
        ("regression", "MAX_PREDICTORS", "REGRESSION_MAX_PREDICTORS", 20),
        ("regression", "MAX_MODEL_TERMS", "REGRESSION_MAX_MODEL_TERMS", 50),
        ("regression", "PLOT_SAMPLE_SIZE", "REGRESSION_PLOT_SAMPLE_SIZE", 5_000),
        ("regression_glm", "_CALIBRATION_MAX_BINS", "LOGISTIC_CALIBRATION_MAX_BINS", 10),
        ("correlation", "DEFAULT_SELECTED_COLUMNS", "CORRELATION_DEFAULT_SELECTED_COLUMNS", 20),
        ("correlation", "MAX_SELECTED_COLUMNS", "CORRELATION_MAX_SELECTED_COLUMNS", 30),
        ("correlation", "SCATTER_SAMPLE_SIZE", "CORRELATION_SCATTER_SAMPLE_SIZE", 5_000),
        ("correlation_charts", "MAX_ANNOTATED_COLUMNS", "CORRELATION_MAX_ANNOTATED_COLUMNS", 12),
        ("hypothesis_charts", "MAX_ANNOTATED_CELLS", "HYPOTHESIS_MAX_ANNOTATED_CELLS", 100),
        ("paired_comparison", "MAX_PAIRED_TRAJECTORIES", "PAIRED_MAX_TRAJECTORIES", 200),
        ("pca", "SCATTER_SAMPLE_SIZE", "PCA_SCATTER_SAMPLE_SIZE", 5_000),
        ("clustering", "PLOT_SAMPLE_SIZE", "CLUSTERING_PLOT_SAMPLE_SIZE", 5_000),
        ("clustering", "DEFAULT_CLUSTER_COUNT", "CLUSTERING_DEFAULT_CLUSTER_COUNT", 3),
        ("clustering", "MAX_CLUSTER_COUNT", "CLUSTERING_MAX_CLUSTER_COUNT", 100),
        ("clustering", "DEFAULT_DBSCAN_EPSILON", "CLUSTERING_DEFAULT_DBSCAN_EPSILON", 0.5),
        ("clustering", "MIN_DBSCAN_EPSILON", "CLUSTERING_MIN_DBSCAN_EPSILON", 0.01),
        ("clustering", "MAX_DBSCAN_EPSILON", "CLUSTERING_MAX_DBSCAN_EPSILON", 100.0),
        ("clustering", "DEFAULT_DBSCAN_MIN_SAMPLES", "CLUSTERING_DEFAULT_DBSCAN_MIN_SAMPLES", 5),
        ("clustering", "MAX_DBSCAN_MIN_SAMPLES", "CLUSTERING_MAX_DBSCAN_MIN_SAMPLES", 100),
        ("multivariate_outliers", "PLOT_SAMPLE_SIZE", "MULTIVARIATE_OUTLIERS_PLOT_SAMPLE_SIZE", 5_000),
        ("multivariate_outliers", "DEFAULT_CONTAMINATION", "MULTIVARIATE_OUTLIERS_DEFAULT_CONTAMINATION", 0.05),
        ("multivariate_outliers", "MIN_CONTAMINATION", "MULTIVARIATE_OUTLIERS_MIN_CONTAMINATION", 0.01),
        ("multivariate_outliers", "MAX_CONTAMINATION", "MULTIVARIATE_OUTLIERS_MAX_CONTAMINATION", 0.5),
        ("multivariate_outliers", "DEFAULT_LOF_NEIGHBORS", "MULTIVARIATE_OUTLIERS_DEFAULT_LOF_NEIGHBORS", 20),
        ("multivariate_outliers", "MAX_LOF_NEIGHBORS", "MULTIVARIATE_OUTLIERS_MAX_LOF_NEIGHBORS", 100),
        ("multivariate_outliers", "MAX_EXTREME_OBSERVATIONS", "MULTIVARIATE_OUTLIERS_MAX_EXTREME_OBSERVATIONS", 100),
        ("outliers", "MAX_EXTREME_OBSERVATIONS", "OUTLIERS_MAX_EXTREME_OBSERVATIONS", 100),
        ("outliers", "HISTOGRAM_BINS", "OUTLIERS_HISTOGRAM_BINS", 50),
        ("outliers", "MIN_THRESHOLD", "OUTLIERS_MIN_THRESHOLD", 0.1),
        ("outliers", "MAX_THRESHOLD", "OUTLIERS_MAX_THRESHOLD", 100.0),
        ("overview", "SAMPLE_ROW_LIMIT", "OVERVIEW_SAMPLE_ROW_LIMIT", 100),
        ("overview", "SAMPLE_DISPLAY_ROW_LIMIT", "OVERVIEW_SAMPLE_DISPLAY_ROW_LIMIT", 10),
        ("timeseries", "MAX_ACF_LAGS", "TIME_SERIES_MAX_ACF_LAGS", 40),
    ],
)
def test_central_values_and_existing_imports_preserve_policy(
    owner: str,
    legacy_name: str,
    central_name: str,
    expected: float,
) -> None:
    module = importlib.import_module(f"expo_jbm329.services.analysis.{owner}")

    assert getattr(limits, central_name) == expected
    assert getattr(module, legacy_name) == expected


def test_limits_can_be_imported_without_analysis_or_ui_dependencies() -> None:
    script = """
import sys
from expo_jbm329.services.analysis import limits
for name in ("pandas", "numpy", "matplotlib", "PyQt6",
             "expo_jbm329.services.analysis.regression",
             "expo_jbm329.services.analysis.outliers"):
    assert name not in sys.modules, name
assert limits.REGRESSION_MAX_MODEL_TERMS == 50
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)


def test_method_specific_outlier_defaults_keep_the_existing_enum_mapping() -> None:
    assert limits.OUTLIERS_DEFAULT_IQR_THRESHOLD == 1.5
    assert limits.OUTLIERS_DEFAULT_Z_SCORE_THRESHOLD == 3.0
    assert limits.OUTLIERS_DEFAULT_MODIFIED_Z_SCORE_THRESHOLD == 3.5
    assert DEFAULT_THRESHOLDS == {
        OutlierMethod.IQR: limits.OUTLIERS_DEFAULT_IQR_THRESHOLD,
        OutlierMethod.Z_SCORE: limits.OUTLIERS_DEFAULT_Z_SCORE_THRESHOLD,
        OutlierMethod.MODIFIED_Z_SCORE: limits.OUTLIERS_DEFAULT_MODIFIED_Z_SCORE_THRESHOLD,
    }


@pytest.mark.parametrize("level_count", [19, 20, 21])
def test_shared_category_boundary_keeps_all_levels_or_excludes_whole_column(level_count: int) -> None:
    city = [f"city-{index}" for index in range(level_count)] * 3
    df = pd.DataFrame({"city": city, "target": np.arange(len(city), dtype=float)})

    grouping = classify_grouping_columns(df[["city"]])
    predictors = classify_predictor_columns(df)
    statistics = analyze_descriptive_statistics(df[["city"]])
    fitted = analyze_regression(df, "target", ["city"])

    if level_count <= limits.CATEGORICAL_MAX_DISTINCT_VALUES:
        assert grouping.eligible == predictors.categorical == ("city",)
        assert len(statistics.categorical_columns[0].frequencies) == level_count
        assert fitted.error is None
        assert fitted.references[0].level_count == level_count
        assert fitted.n_used == len(df)
    else:
        assert grouping.eligible == predictors.categorical == ()
        assert grouping.excluded[0].name == predictors.excluded[0].name == "city"
        assert statistics.categorical_columns == ()
        assert fitted.error is RegressionError.INVALID_COLUMN


@pytest.mark.parametrize("level_count", [19, 20, 21])
@pytest.mark.parametrize("dtype", ["string", "category", "int64"])
def test_overview_dtype_counts_and_statistics_frequency_eligibility_are_distinct(
    level_count: int,
    dtype: str,
) -> None:
    source = pd.DataFrame({"value": pd.Series(list(range(level_count)) * 2, dtype=dtype)})

    overview = analyze_dataset_overview(source)
    statistics = analyze_descriptive_statistics(source)

    assert overview.columns[0].unique_count == level_count
    assert overview.categorical_column_count == (0 if dtype == "int64" else 1)
    assert overview.numeric_column_count == (1 if dtype == "int64" else 0)
    assert bool(statistics.categorical_columns) == (level_count <= limits.CATEGORICAL_MAX_DISTINCT_VALUES)
    assert bool(statistics.columns) == (dtype == "int64")


def test_overview_counts_booleans_separately_from_categorical_columns() -> None:
    source = pd.DataFrame({"flag": pd.Series([True, False, None], dtype="boolean")})

    overview = analyze_dataset_overview(source)
    statistics = analyze_descriptive_statistics(source)

    assert overview.boolean_column_count == 1
    assert overview.categorical_column_count == 0
    assert len(statistics.categorical_columns) == 1
    assert len(statistics.categorical_columns[0].frequencies) == 2


def test_category_eligibility_is_not_reclassified_after_complete_case_deletion() -> None:
    city = [f"city-{index}" for index in range(21)] * 3
    target = np.arange(len(city), dtype=float)
    df = pd.DataFrame({"city": city, "target": target})
    df.loc[df["city"] == "city-20", "target"] = np.nan

    assert df.dropna()["city"].nunique() == 20
    assert analyze_regression(df, "target", ["city"]).error is RegressionError.INVALID_COLUMN


@pytest.mark.parametrize(("last_levels", "expected_error"), [(17, None), (18, RegressionError.TOO_MANY_TERMS)])
def test_regression_expanded_term_boundary_excludes_intercept(
    last_levels: int,
    expected_error: RegressionError | None,
) -> None:
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "a": rng.choice([f"a-{index}" for index in range(18)], 500),
        "b": rng.choice([f"b-{index}" for index in range(18)], 500),
        "c": rng.choice([f"c-{index}" for index in range(last_levels)], 500),
        "y": rng.normal(size=500),
    })

    result = analyze_regression(df, "y", ["a", "b", "c"])

    assert result.error is expected_error
    assert result.n_used == 500
    if expected_error is None:
        assert result.df_model == limits.REGRESSION_MAX_MODEL_TERMS
        assert len(result.terms) == limits.REGRESSION_MAX_MODEL_TERMS + 1


@pytest.mark.parametrize("size", [4_999, 5_000, 5_001])
def test_ols_and_pca_sampling_boundaries_keep_full_fitted_cohorts(size: int) -> None:
    rng = np.random.default_rng(42)
    df = pd.DataFrame({"x": rng.normal(size=size), "y": rng.normal(size=size)})

    regression = analyze_regression(df, "y", ["x"])
    components = analyze_pca(df)

    assert regression.error is components.error is None
    assert regression.n_used == components.rows_used == size
    assert regression.plot is not None
    assert len(regression.plot.actual) == min(size, limits.REGRESSION_PLOT_SAMPLE_SIZE)
    assert len(components.sample_pc1) == min(size, limits.PCA_SCATTER_SAMPLE_SIZE)
    assert regression.plot.sampled == (size > limits.REGRESSION_PLOT_SAMPLE_SIZE)
    assert components.sampled == (size > limits.PCA_SCATTER_SAMPLE_SIZE)
    assert sum(components.explained_variance_ratio) == pytest.approx(1.0)


@pytest.mark.parametrize("size", [78, 80, 82])
def test_acf_limit_does_not_truncate_the_series(size: int) -> None:
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "when": pd.date_range("2025-01-01", periods=size, freq="D"),
        "value": rng.normal(size=size),
    })

    result = analyze_time_series(df)

    assert result.error is None
    assert len(result.values) == size
    assert len(result.acf_values) == min(limits.TIME_SERIES_MAX_ACF_LAGS, size // 2)
