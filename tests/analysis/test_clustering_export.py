from __future__ import annotations

import dataclasses
import math

import pandas as pd
import pytest

from expo_jbm329.services.analysis.clustering import ClusteringMethod, ClusteringResult, analyze_clustering
from expo_jbm329.services.analysis.clustering_charts import ClusterProjectionLabels
from expo_jbm329.services.analysis.clustering_export import (
    CLUSTERING_COMPONENTS,
    ClusteringExportComponent,
    ClusteringExportRequest,
    ClusteringExportSnapshot,
    ClusteringMetric,
    cluster_sizes_table,
    clustering_export_tables,
    clustering_model_summary_table,
)
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat

PROJECTION_LABELS = ClusterProjectionLabels(
    heading="Cluster projection",
    title="Cluster projection (internal PCA)",
    pc1_axis="PC1",
    pc2_axis="PC2",
    cluster="Cluster {number}",
    noise="Noise",
    captions=("Sampled",),
)
NOTES = ("K-Means on 2 features.", "Silhouette score: 0.9", "Features: x, y")


def clustering_frame() -> pd.DataFrame:
    """Return two tight groups, one far point, one incomplete row and a text column."""
    return pd.DataFrame({
        "x": [0.0, 0.1, 0.2, 0.1, 10.0, 10.1, 10.2, 10.1, 50.0, None],
        "y": [0.0, 0.2, 0.1, 0.1, 10.0, 10.2, 10.1, 10.1, 50.0, 1.0],
        "name": list("abcdefghij"),
    })


def clustering_result(method: ClusteringMethod = ClusteringMethod.K_MEANS, **kwargs: object) -> ClusteringResult:
    """Return a successful fit of `clustering_frame` on unscaled features."""
    parameters: dict[str, object] = {"standardize": False, "cluster_count": 3, "dbscan_epsilon": 1.0}
    parameters.update(kwargs)
    result = analyze_clustering(clustering_frame(), ("x", "y"), method=method, **parameters)  # type: ignore[arg-type]
    assert result.error is None
    return result


def clustering_snapshot(
    method: ClusteringMethod = ClusteringMethod.K_MEANS,
    *,
    notes: tuple[str, ...] = NOTES,
    **kwargs: object,
) -> ClusteringExportSnapshot:
    return ClusteringExportSnapshot(clustering_result(method, **kwargs), PROJECTION_LABELS, notes)


# ----------------------------------------------------------------------
# Snapshot
# ----------------------------------------------------------------------


def test_snapshot_offers_every_component():
    snapshot = clustering_snapshot()

    assert snapshot.components == CLUSTERING_COMPONENTS
    assert CLUSTERING_COMPONENTS == (
        ClusteringExportComponent.CLUSTER_SIZES,
        ClusteringExportComponent.MODEL_SUMMARY,
        ClusteringExportComponent.CHARTS,
    )


def test_clustering_capture_provenance_survives_presentation_edits_but_not_new_fits():
    snapshot = clustering_snapshot()
    assert dataclasses.replace(snapshot, notes=("Edited",)).capture_id == snapshot.capture_id
    assert clustering_snapshot().capture_id != snapshot.capture_id
    with pytest.raises(ValueError, match="capture identifier"):
        dataclasses.replace(snapshot, capture_id="")


def test_snapshot_requires_a_typed_result_and_labels():
    with pytest.raises(TypeError, match="clustering result"):
        ClusteringExportSnapshot(object(), PROJECTION_LABELS)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Projection labels"):
        ClusteringExportSnapshot(clustering_result(), object())  # type: ignore[arg-type]


def test_snapshot_rejects_failed_and_unfitted_results():
    failed = analyze_clustering(clustering_frame(), ("x",))
    assert failed.error is not None
    with pytest.raises(ValueError, match="failed"):
        ClusteringExportSnapshot(failed, PROJECTION_LABELS)
    unfitted = dataclasses.replace(clustering_result(), sample_pc1=())
    with pytest.raises(ValueError, match="fitted"):
        ClusteringExportSnapshot(unfitted, PROJECTION_LABELS)
    unused = dataclasses.replace(clustering_result(), rows_used=0)
    with pytest.raises(ValueError, match="fitted"):
        ClusteringExportSnapshot(unused, PROJECTION_LABELS)


def test_projection_labels_name_clusters_one_based_and_noise():
    assert PROJECTION_LABELS.cluster_name(0) == "Cluster 1"
    assert PROJECTION_LABELS.cluster_name(4) == "Cluster 5"
    assert PROJECTION_LABELS.cluster_name(-1) == "Noise"


# ----------------------------------------------------------------------
# Request
# ----------------------------------------------------------------------


@pytest.mark.parametrize("fmt", list(StatisticsExportFormat))
@pytest.mark.parametrize(
    "component", [ClusteringExportComponent.CLUSTER_SIZES, ClusteringExportComponent.MODEL_SUMMARY]
)
def test_request_accepts_one_table_in_every_format(fmt, component):
    request = ClusteringExportRequest(clustering_snapshot(), (component,), fmt)

    assert request.components == (component,)


def test_excel_request_accepts_tables_with_charts_and_charts_only():
    snapshot = clustering_snapshot()

    assert ClusteringExportRequest(snapshot, CLUSTERING_COMPONENTS, StatisticsExportFormat.EXCEL)
    assert ClusteringExportRequest(snapshot, (ClusteringExportComponent.CHARTS,), StatisticsExportFormat.EXCEL)


@pytest.mark.parametrize("fmt", [StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY])
@pytest.mark.parametrize(
    "components",
    [
        (ClusteringExportComponent.CHARTS,),
        (ClusteringExportComponent.CLUSTER_SIZES, ClusteringExportComponent.MODEL_SUMMARY),
    ],
)
def test_non_excel_request_requires_exactly_one_table_without_charts(fmt, components):
    with pytest.raises(ValueError, match="exactly one table"):
        ClusteringExportRequest(clustering_snapshot(), components, fmt)


@pytest.mark.parametrize(
    "components",
    [
        (),
        (ClusteringExportComponent.CLUSTER_SIZES, ClusteringExportComponent.CLUSTER_SIZES),
    ],
)
def test_request_rejects_empty_or_duplicate_components(components):
    with pytest.raises(ValueError, match="distinct"):
        ClusteringExportRequest(clustering_snapshot(), components, StatisticsExportFormat.EXCEL)


def test_request_rejects_untyped_values():
    snapshot = clustering_snapshot()
    with pytest.raises(TypeError, match="snapshot"):
        ClusteringExportRequest(
            object(),  # type: ignore[arg-type]
            (ClusteringExportComponent.CLUSTER_SIZES,),
            StatisticsExportFormat.EXCEL,
        )
    with pytest.raises(ValueError, match="Unknown clustering export component"):
        ClusteringExportRequest(snapshot, ("cluster_sizes",), StatisticsExportFormat.EXCEL)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="format"):
        ClusteringExportRequest(snapshot, (ClusteringExportComponent.CLUSTER_SIZES,), "excel")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------


def test_export_tables_follow_selection_order_and_skip_charts():
    tables = clustering_export_tables(
        clustering_snapshot(),
        (
            ClusteringExportComponent.CHARTS,
            ClusteringExportComponent.MODEL_SUMMARY,
            ClusteringExportComponent.CLUSTER_SIZES,
        ),
    )

    assert list(tables) == [ClusteringExportComponent.MODEL_SUMMARY, ClusteringExportComponent.CLUSTER_SIZES]


def test_cluster_sizes_use_displayed_names_counts_and_shares():
    snapshot = clustering_snapshot()
    result = snapshot.result

    table = cluster_sizes_table(snapshot)

    assert table.columns.tolist() == ["cluster", "rows", "share"]
    assert table["cluster"].tolist() == [f"Cluster {cluster.label + 1}" for cluster in result.clusters]
    assert table["rows"].tolist() == [cluster.count for cluster in result.clusters]
    assert table["rows"].sum() == result.rows_used == 9
    assert table["share"].sum() == pytest.approx(1.0)
    assert isinstance(table["cluster"].dtype, pd.StringDtype)
    assert isinstance(table["rows"].dtype, pd.Int64Dtype)
    assert table["share"].dtype == "float64"


def test_dbscan_cluster_sizes_end_with_the_noise_row():
    snapshot = clustering_snapshot(ClusteringMethod.DBSCAN, dbscan_min_samples=3)
    result = snapshot.result
    assert result.noise_count == 1

    table = cluster_sizes_table(snapshot)

    assert table["cluster"].tolist() == ["Cluster 1", "Cluster 2", "Noise"]
    assert table["rows"].tolist() == [4, 4, 1]
    assert table["share"].iloc[-1] == pytest.approx(1 / 9)


def test_dbscan_without_noise_has_no_noise_row():
    snapshot = clustering_snapshot(ClusteringMethod.DBSCAN, dbscan_epsilon=100.0, dbscan_min_samples=2)

    table = cluster_sizes_table(snapshot)

    assert "Noise" not in table["cluster"].tolist()


@pytest.mark.parametrize("method", [ClusteringMethod.K_MEANS, ClusteringMethod.AGGLOMERATIVE])
def test_partitioning_model_summary_lists_requested_clusters_and_notes(method):
    snapshot = clustering_snapshot(method)
    result = snapshot.result

    table = clustering_model_summary_table(snapshot)

    assert table.columns.tolist() == ["metric", "value", "notes"]
    assert table["metric"].tolist() == [
        ClusteringMetric.FEATURES,
        ClusteringMetric.CLUSTER_COUNT,
        ClusteringMetric.TOTAL_ROWS,
        ClusteringMetric.ROWS_USED,
        ClusteringMetric.ROWS_DROPPED,
        ClusteringMetric.CLUSTERS_FOUND,
        ClusteringMetric.SILHOUETTE,
    ]
    assert table["value"].tolist()[:-1] == [2.0, 3.0, 10.0, 9.0, 1.0, 3.0]
    assert result.silhouette_score is not None
    assert table["value"].iloc[-1] == pytest.approx(result.silhouette_score)
    assert table["notes"].tolist()[: len(NOTES)] == list(NOTES)
    assert table["notes"].iloc[len(NOTES) :].isna().all()
    assert isinstance(table["metric"].dtype, pd.StringDtype)
    assert isinstance(table["notes"].dtype, pd.StringDtype)
    assert table["value"].dtype == "float64"


def test_dbscan_model_summary_lists_its_parameters_and_noise():
    snapshot = clustering_snapshot(ClusteringMethod.DBSCAN, dbscan_min_samples=3)

    table = clustering_model_summary_table(snapshot)

    values = dict(zip(table["metric"], table["value"], strict=True))
    assert ClusteringMetric.CLUSTER_COUNT not in values
    assert values[ClusteringMetric.DBSCAN_EPSILON] == 1.0
    assert values[ClusteringMetric.DBSCAN_MIN_SAMPLES] == 3.0
    assert values[ClusteringMetric.CLUSTERS_FOUND] == 2.0
    assert values[ClusteringMetric.NOISE_ROWS] == 1.0


def test_undefined_silhouette_is_missing():
    snapshot = clustering_snapshot(ClusteringMethod.DBSCAN, dbscan_epsilon=100.0, dbscan_min_samples=2)
    assert snapshot.result.silhouette_score is None

    table = clustering_model_summary_table(snapshot)

    assert table["metric"].iloc[-1] == ClusteringMetric.SILHOUETTE
    assert math.isnan(table["value"].iloc[-1])


def test_more_notes_than_metrics_extend_the_table():
    notes = tuple(f"Line {index}" for index in range(10))
    snapshot = clustering_snapshot(notes=notes)

    table = clustering_model_summary_table(snapshot)

    assert len(table) == 10
    assert table["notes"].tolist() == list(notes)
    assert table["metric"].iloc[7:].isna().all()
    assert table["value"].iloc[7:].isna().all()
