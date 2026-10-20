"""Regression coverage for the documented analytical policy inventory."""

from __future__ import annotations

import importlib
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis import group_comparison as grouping_service
from expo_jbm329.services.analysis import limits
from expo_jbm329.services.analysis import multivariate_outliers as multivariate_service
from expo_jbm329.services.analysis import pca as pca_service
from expo_jbm329.services.analysis import regression as regression_service
from expo_jbm329.services.analysis import timeseries as timeseries_service
from expo_jbm329.services.analysis.clustering import MIN_CLUSTER_COUNT, MIN_DBSCAN_MIN_SAMPLES
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
    ("owner", "legacy_name", "central_name"),
    [
        ("group_comparison", "MAX_GROUPS", "CATEGORICAL_MAX_DISTINCT_VALUES"),
        ("statistics", "MAX_GROUPS", "CATEGORICAL_MAX_DISTINCT_VALUES"),
        ("regression", "MAX_PREDICTORS", "REGRESSION_MAX_PREDICTORS"),
        ("regression", "MAX_MODEL_TERMS", "REGRESSION_MAX_MODEL_TERMS"),
        ("regression", "PLOT_SAMPLE_SIZE", "REGRESSION_PLOT_SAMPLE_SIZE"),
        ("regression_glm", "_CALIBRATION_MAX_BINS", "LOGISTIC_CALIBRATION_MAX_BINS"),
        ("correlation", "DEFAULT_SELECTED_COLUMNS", "CORRELATION_DEFAULT_SELECTED_COLUMNS"),
        ("correlation", "MAX_SELECTED_COLUMNS", "CORRELATION_MAX_SELECTED_COLUMNS"),
        ("correlation", "SCATTER_SAMPLE_SIZE", "CORRELATION_SCATTER_SAMPLE_SIZE"),
        ("correlation_charts", "MAX_ANNOTATED_COLUMNS", "CORRELATION_MAX_ANNOTATED_COLUMNS"),
        ("hypothesis_charts", "MAX_ANNOTATED_CELLS", "HYPOTHESIS_MAX_ANNOTATED_CELLS"),
        ("paired_comparison", "MAX_PAIRED_TRAJECTORIES", "PAIRED_MAX_TRAJECTORIES"),
        ("pca", "SCATTER_SAMPLE_SIZE", "PCA_SCATTER_SAMPLE_SIZE"),
        ("clustering", "PLOT_SAMPLE_SIZE", "CLUSTERING_PLOT_SAMPLE_SIZE"),
        ("clustering", "DEFAULT_CLUSTER_COUNT", "CLUSTERING_DEFAULT_CLUSTER_COUNT"),
        ("clustering", "MAX_CLUSTER_COUNT", "CLUSTERING_MAX_CLUSTER_COUNT"),
        ("clustering", "DEFAULT_DBSCAN_EPSILON", "CLUSTERING_DEFAULT_DBSCAN_EPSILON"),
        ("clustering", "MIN_DBSCAN_EPSILON", "CLUSTERING_MIN_DBSCAN_EPSILON"),
        ("clustering", "MAX_DBSCAN_EPSILON", "CLUSTERING_MAX_DBSCAN_EPSILON"),
        ("clustering", "DEFAULT_DBSCAN_MIN_SAMPLES", "CLUSTERING_DEFAULT_DBSCAN_MIN_SAMPLES"),
        ("clustering", "MAX_DBSCAN_MIN_SAMPLES", "CLUSTERING_MAX_DBSCAN_MIN_SAMPLES"),
        ("multivariate_outliers", "PLOT_SAMPLE_SIZE", "MULTIVARIATE_OUTLIERS_PLOT_SAMPLE_SIZE"),
        ("multivariate_outliers", "DEFAULT_CONTAMINATION", "MULTIVARIATE_OUTLIERS_DEFAULT_CONTAMINATION"),
        ("multivariate_outliers", "MIN_CONTAMINATION", "MULTIVARIATE_OUTLIERS_MIN_CONTAMINATION"),
        ("multivariate_outliers", "MAX_CONTAMINATION", "MULTIVARIATE_OUTLIERS_MAX_CONTAMINATION"),
        ("multivariate_outliers", "DEFAULT_LOF_NEIGHBORS", "MULTIVARIATE_OUTLIERS_DEFAULT_LOF_NEIGHBORS"),
        ("multivariate_outliers", "MAX_LOF_NEIGHBORS", "MULTIVARIATE_OUTLIERS_MAX_LOF_NEIGHBORS"),
        ("multivariate_outliers", "MAX_EXTREME_OBSERVATIONS", "MULTIVARIATE_OUTLIERS_MAX_EXTREME_OBSERVATIONS"),
        ("outliers", "MAX_EXTREME_OBSERVATIONS", "OUTLIERS_MAX_EXTREME_OBSERVATIONS"),
        ("outliers", "HISTOGRAM_BINS", "OUTLIERS_HISTOGRAM_BINS"),
        ("outliers", "MIN_THRESHOLD", "OUTLIERS_MIN_THRESHOLD"),
        ("outliers", "MAX_THRESHOLD", "OUTLIERS_MAX_THRESHOLD"),
        ("overview", "SAMPLE_ROW_LIMIT", "OVERVIEW_SAMPLE_ROW_LIMIT"),
        ("overview", "SAMPLE_DISPLAY_ROW_LIMIT", "OVERVIEW_SAMPLE_DISPLAY_ROW_LIMIT"),
        ("timeseries", "MAX_ACF_LAGS", "TIME_SERIES_MAX_ACF_LAGS"),
    ],
)
def test_central_values_and_existing_imports_preserve_policy(
    owner: str,
    legacy_name: str,
    central_name: str,
) -> None:
    module = importlib.import_module(f"expo_jbm329.services.analysis.{owner}")

    assert getattr(module, legacy_name) == getattr(limits, central_name)


def test_limits_can_be_imported_without_analysis_or_ui_dependencies() -> None:
    script = """
import sys
from expo_jbm329.services.analysis import limits
for name in ("pandas", "numpy", "matplotlib", "PyQt6",
             "expo_jbm329.services.analysis.regression",
             "expo_jbm329.services.analysis.outliers"):
    assert name not in sys.modules, name
assert limits.REGRESSION_MAX_MODEL_TERMS > 0
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)


def test_method_specific_outlier_defaults_keep_the_existing_enum_mapping() -> None:
    assert DEFAULT_THRESHOLDS == {
        OutlierMethod.IQR: limits.OUTLIERS_DEFAULT_IQR_THRESHOLD,
        OutlierMethod.Z_SCORE: limits.OUTLIERS_DEFAULT_Z_SCORE_THRESHOLD,
        OutlierMethod.MODIFIED_Z_SCORE: limits.OUTLIERS_DEFAULT_MODIFIED_Z_SCORE_THRESHOLD,
    }


@pytest.mark.parametrize(
    ("minimum", "default", "maximum"),
    [
        (MIN_CLUSTER_COUNT, limits.CLUSTERING_DEFAULT_CLUSTER_COUNT, limits.CLUSTERING_MAX_CLUSTER_COUNT),
        (
            limits.CLUSTERING_MIN_DBSCAN_EPSILON,
            limits.CLUSTERING_DEFAULT_DBSCAN_EPSILON,
            limits.CLUSTERING_MAX_DBSCAN_EPSILON,
        ),
        (
            MIN_DBSCAN_MIN_SAMPLES,
            limits.CLUSTERING_DEFAULT_DBSCAN_MIN_SAMPLES,
            limits.CLUSTERING_MAX_DBSCAN_MIN_SAMPLES,
        ),
        (
            limits.MULTIVARIATE_OUTLIERS_MIN_CONTAMINATION,
            limits.MULTIVARIATE_OUTLIERS_DEFAULT_CONTAMINATION,
            limits.MULTIVARIATE_OUTLIERS_MAX_CONTAMINATION,
        ),
        (
            multivariate_service.MIN_LOF_NEIGHBORS,
            limits.MULTIVARIATE_OUTLIERS_DEFAULT_LOF_NEIGHBORS,
            limits.MULTIVARIATE_OUTLIERS_MAX_LOF_NEIGHBORS,
        ),
        (2, limits.CORRELATION_DEFAULT_SELECTED_COLUMNS, limits.CORRELATION_MAX_SELECTED_COLUMNS),
        *[
            (limits.OUTLIERS_MIN_THRESHOLD, threshold, limits.OUTLIERS_MAX_THRESHOLD)
            for threshold in DEFAULT_THRESHOLDS.values()
        ],
    ],
)
def test_parameter_defaults_remain_within_valid_bounds(minimum: float, default: float, maximum: float) -> None:
    assert minimum <= default <= maximum


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_shared_category_boundary_keeps_all_levels_or_excludes_whole_column(offset: int) -> None:
    level_count = limits.CATEGORICAL_MAX_DISTINCT_VALUES + offset
    city = [f"city-{index}" for index in range(level_count)] * 3
    df = pd.DataFrame({"city": city, "target": np.arange(len(city), dtype=float)})

    grouping = classify_grouping_columns(df[["city"]])
    predictors = classify_predictor_columns(df)
    statistics = analyze_descriptive_statistics(df[["city"]])
    fitted = analyze_regression(df, "target", ["city"])

    if level_count <= limits.CATEGORICAL_MAX_DISTINCT_VALUES:
        assert grouping.eligible == predictors.categorical == ("city",)
        assert len(statistics.categorical_columns[0].frequencies) == level_count
        if level_count - 1 <= limits.REGRESSION_MAX_MODEL_TERMS:
            assert fitted.error is None
            assert fitted.references[0].level_count == level_count
            assert fitted.n_used == len(df)
        else:
            assert fitted.error is RegressionError.TOO_MANY_TERMS
    else:
        assert grouping.eligible == predictors.categorical == ()
        assert grouping.excluded[0].name == predictors.excluded[0].name == "city"
        assert statistics.categorical_columns == ()
        assert fitted.error is RegressionError.INVALID_COLUMN


@pytest.mark.parametrize("offset", [-1, 0, 1])
@pytest.mark.parametrize("dtype", ["string", "category", "int64"])
def test_overview_dtype_counts_and_statistics_frequency_eligibility_are_distinct(
    offset: int,
    dtype: str,
) -> None:
    level_count = limits.CATEGORICAL_MAX_DISTINCT_VALUES + offset
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
    maximum = limits.CATEGORICAL_MAX_DISTINCT_VALUES
    city = [f"city-{index}" for index in range(maximum + 1)] * 3
    target = np.arange(len(city), dtype=float)
    df = pd.DataFrame({"city": city, "target": target})
    df.loc[df["city"] == f"city-{maximum}", "target"] = np.nan

    assert df.dropna()["city"].nunique() == maximum
    assert analyze_regression(df, "target", ["city"]).error is RegressionError.INVALID_COLUMN


@pytest.mark.parametrize(("last_levels", "expected_error"), [(17, None), (18, RegressionError.TOO_MANY_TERMS)])
def test_regression_expanded_term_boundary_excludes_intercept(
    last_levels: int,
    expected_error: RegressionError | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Isolate term-count behavior from independently tunable eligibility limits.
    monkeypatch.setattr(grouping_service, "MAX_GROUPS", 20)
    monkeypatch.setattr(regression_service, "MAX_PREDICTORS", 3)
    monkeypatch.setattr(regression_service, "MAX_MODEL_TERMS", 50)
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
        assert result.df_model == 50
        assert len(result.terms) == 51


@pytest.mark.parametrize("size", [29, 30, 31])
def test_ols_and_pca_sampling_boundaries_keep_full_fitted_cohorts(
    size: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(regression_service, "PLOT_SAMPLE_SIZE", 30)
    monkeypatch.setattr(pca_service, "SCATTER_SAMPLE_SIZE", 30)
    rng = np.random.default_rng(42)
    df = pd.DataFrame({"x": rng.normal(size=size), "y": rng.normal(size=size)})

    regression = analyze_regression(df, "y", ["x"])
    components = analyze_pca(df)

    assert regression.error is components.error is None
    assert regression.n_used == components.rows_used == size
    assert regression.plot is not None
    assert len(regression.plot.actual) == min(size, 30)
    assert len(components.sample_pc1) == min(size, 30)
    assert regression.plot.sampled == (size > 30)
    assert components.sampled == (size > 30)
    assert sum(components.explained_variance_ratio) == pytest.approx(1.0)


@pytest.mark.parametrize("size", [18, 20, 22])
def test_acf_limit_does_not_truncate_the_series(size: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timeseries_service, "MAX_ACF_LAGS", 10)
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "when": pd.date_range("2025-01-01", periods=size, freq="D"),
        "value": rng.normal(size=size),
    })

    result = analyze_time_series(df)

    assert result.error is None
    assert len(result.values) == size
    assert len(result.acf_values) == min(10, size // 2)
