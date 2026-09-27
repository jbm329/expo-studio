from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis import clustering
from expo_jbm329.services.analysis.clustering import (
    DEFAULT_CLUSTER_COUNT,
    MAX_CLUSTER_COUNT,
    PLOT_SAMPLE_SIZE,
    ClusteringError,
    ClusteringMethod,
    analyze_clustering,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame({
        "x": [0.0, 0.1, -0.1, 10.0, 10.1, 9.9, np.nan],
        "y": [0.0, -0.1, 0.1, 10.0, 10.1, 9.9, 4.0],
        "text": list("abcdefg"),
    })


@pytest.mark.parametrize("method", list(ClusteringMethod))
def test_each_method_clusters_complete_cases(method):
    result = analyze_clustering(_frame(), method=method, cluster_count=2, dbscan_epsilon=0.5, dbscan_min_samples=2)

    assert result.error is None
    assert result.method is method
    assert result.columns == ("x", "y")
    assert result.available_columns == ("x", "y")
    assert result.standardize
    assert result.total_rows == 7
    assert result.rows_used == 6
    assert result.rows_dropped == 1
    assert sum(cluster.count for cluster in result.clusters) + result.noise_count == result.rows_used
    assert len(result.sample_pc1) == result.rows_used
    assert len(result.sample_pc2) == result.rows_used
    assert len(result.sample_labels) == result.rows_used


def test_k_means_uses_fixed_seed_and_reports_silhouette():
    first = analyze_clustering(_frame(), method=ClusteringMethod.K_MEANS, cluster_count=2)
    second = analyze_clustering(_frame(), method=ClusteringMethod.K_MEANS, cluster_count=2)

    assert first.error is None
    assert first.sample_labels == second.sample_labels
    assert first.silhouette_score is not None
    assert -1 <= first.silhouette_score <= 1
    assert first.noise_count == 0


def test_dbscan_reports_noise_and_has_no_silhouette_with_one_cluster():
    result = analyze_clustering(
        _frame(),
        method=ClusteringMethod.DBSCAN,
        dbscan_epsilon=100.0,
        dbscan_min_samples=2,
    )

    assert result.error is None
    assert len(result.clusters) == 1
    assert result.silhouette_score is None


def test_raw_scale_fit_is_supported():
    result = analyze_clustering(_frame(), standardize=False, cluster_count=2)

    assert result.error is None
    assert not result.standardize


@pytest.mark.parametrize(
    ("df", "columns", "kwargs", "error"),
    [
        (pd.DataFrame({"x": [1.0, 2.0]}), None, {}, ClusteringError.NOT_ENOUGH_NUMERIC_COLUMNS),
        (_frame(), ("x",), {}, ClusteringError.NOT_ENOUGH_SELECTED_COLUMNS),
        (_frame(), ("x", "missing"), {}, ClusteringError.INVALID_COLUMN),
        (_frame(), ("x", "x"), {}, ClusteringError.INVALID_COLUMN),
        (_frame(), None, {"cluster_count": 1}, ClusteringError.INVALID_CLUSTER_COUNT),
        (_frame(), None, {"cluster_count": MAX_CLUSTER_COUNT + 1}, ClusteringError.INVALID_CLUSTER_COUNT),
        (_frame(), None, {"dbscan_epsilon": 0.0}, ClusteringError.INVALID_DBSCAN_EPSILON),
        (_frame(), None, {"dbscan_min_samples": 1}, ClusteringError.INVALID_DBSCAN_MIN_SAMPLES),
    ],
)
def test_invalid_requests_return_structured_errors(df, columns, kwargs, error):
    result = analyze_clustering(df, columns, **kwargs)

    assert result.error is error
    assert result.clusters == ()
    assert result.sample_pc1 == ()


def test_fewer_than_two_complete_rows_returns_error():
    df = pd.DataFrame({"x": [1.0, np.nan], "y": [2.0, 4.0]})

    result = analyze_clustering(df)

    assert result.error is ClusteringError.NOT_ENOUGH_OBSERVATIONS
    assert result.rows_used == 1
    assert result.rows_dropped == 1


def test_too_many_requested_clusters_for_complete_rows_returns_error():
    result = analyze_clustering(_frame(), cluster_count=7)

    assert result.error is ClusteringError.INVALID_CLUSTER_COUNT
    assert result.rows_used == 6


def test_constant_features_return_no_variation():
    result = analyze_clustering(
        pd.DataFrame({"x": [1.0, 1.0, 1.0], "y": [2.0, 2.0, 2.0]}),
    )

    assert result.error is ClusteringError.NO_VARIATION


def test_infinite_values_are_excluded_as_incomplete():
    df = pd.DataFrame({"x": [1.0, np.inf, 10.0, 11.0], "y": [2.0, 3.0, 10.0, 11.0]})

    result = analyze_clustering(df, cluster_count=2)

    assert result.error is None
    assert result.rows_used == 3
    assert result.rows_dropped == 1


def test_plot_sample_is_deterministic():
    size = PLOT_SAMPLE_SIZE + 1
    values = np.arange(size, dtype=float)
    df = pd.DataFrame({"x": values, "y": values**2})

    first = analyze_clustering(df, cluster_count=2)
    second = analyze_clustering(df, cluster_count=2)

    assert first.sampled
    assert len(first.sample_pc1) == PLOT_SAMPLE_SIZE
    assert first.sample_pc1 == second.sample_pc1
    assert first.sample_labels == second.sample_labels


def test_analysis_does_not_mutate_the_dataframe():
    df = _frame()
    before = df.copy(deep=True)

    analyze_clustering(df)

    pd.testing.assert_frame_equal(df, before)


def test_model_fit_errors_are_not_silently_suppressed(monkeypatch):
    def _raise(*_args, **_kwargs):
        message = "intentional fitting failure"
        raise RuntimeError(message)

    monkeypatch.setattr(clustering, "_cluster_labels", _raise)

    with pytest.raises(RuntimeError, match="intentional fitting failure"):
        analyze_clustering(_frame())


def test_default_cluster_count_is_valid():
    result = analyze_clustering(_frame())

    assert result.error is None
    assert result.cluster_count == DEFAULT_CLUSTER_COUNT
