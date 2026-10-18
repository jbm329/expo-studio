"""Typed exports of a displayed clustering fit."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

import pandas as pd

from expo_jbm329.services.analysis.clustering import ClusteringMethod, ClusteringResult
from expo_jbm329.services.analysis.clustering_charts import ClusterProjectionLabels
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat

if TYPE_CHECKING:
    from collections.abc import Sequence


class ClusteringExportComponent(StrEnum):
    """Selectable displayed results; charts are Excel-only."""

    CLUSTER_SIZES = "cluster_sizes"
    MODEL_SUMMARY = "model_summary"
    CHARTS = "charts"


class ClusteringMetric(StrEnum):
    """Stable keys of the model summary, localized at the UI boundary."""

    FEATURES = "features"
    CLUSTER_COUNT = "cluster_count"
    DBSCAN_EPSILON = "dbscan_epsilon"
    DBSCAN_MIN_SAMPLES = "dbscan_min_samples"
    TOTAL_ROWS = "total_rows"
    ROWS_USED = "rows_used"
    ROWS_DROPPED = "rows_dropped"
    CLUSTERS_FOUND = "clusters_found"
    NOISE_ROWS = "noise_rows"
    SILHOUETTE = "silhouette"


CLUSTERING_COMPONENTS = tuple(ClusteringExportComponent)


@dataclass(frozen=True, slots=True)
class ClusteringExportSnapshot:
    """Own the displayed clustering fit, its comments and chart text.

    Attributes:
        result: The successful fit shown in the content pane.
        chart_labels: Translated projection text captured on the GUI thread.
        notes: Plain-text lines of the displayed model comments.
        capture_id: Stable provenance of this successful applied fit.
    """

    result: ClusteringResult
    chart_labels: ClusterProjectionLabels
    notes: tuple[str, ...] = ()
    capture_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        """Reject failed or unfitted results."""
        if not self.capture_id:
            message = "An applied clustering result requires a capture identifier."
            raise ValueError(message)
        result = self.result
        if not isinstance(result, ClusteringResult):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "A typed clustering result is required."
            raise TypeError(message)
        if result.error is not None:
            message = "A failed clustering result cannot be exported."
            raise ValueError(message)
        if result.rows_used == 0 or not result.sample_pc1:
            message = "An applied clustering result must be fitted."
            raise ValueError(message)
        if not isinstance(self.chart_labels, ClusterProjectionLabels):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Projection labels are required."
            raise TypeError(message)

    @property
    def components(self) -> tuple[ClusteringExportComponent, ...]:
        """Return the components offered for clustering."""
        return CLUSTERING_COMPONENTS


@dataclass(frozen=True, slots=True)
class ClusteringExportRequest:
    """Selected components from one immutable displayed snapshot."""

    snapshot: ClusteringExportSnapshot
    components: tuple[ClusteringExportComponent, ...]
    format: StatisticsExportFormat

    def __post_init__(self) -> None:
        """Validate the selection without altering retained dialog choices."""
        if not isinstance(self.snapshot, ClusteringExportSnapshot):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "A typed clustering export snapshot is required."
            raise TypeError(message)
        if not self.components or len(set(self.components)) != len(self.components):
            message = "Select distinct clustering components."
            raise ValueError(message)
        if any(
            not isinstance(item, ClusteringExportComponent)  # pyright: ignore[reportUnnecessaryIsInstance]
            for item in self.components
        ):
            message = "Unknown clustering export component."
            raise ValueError(message)
        if not isinstance(self.format, StatisticsExportFormat):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Unknown clustering export format."
            raise TypeError(message)
        if self.format is not StatisticsExportFormat.EXCEL and (
            ClusteringExportComponent.CHARTS in self.components or len(self.components) != 1
        ):
            message = "CSV and binary exports require exactly one table and no charts."
            raise ValueError(message)


def clustering_export_tables(
    snapshot: ClusteringExportSnapshot,
    components: Sequence[ClusteringExportComponent],
) -> dict[ClusteringExportComponent, pd.DataFrame]:
    """Build fresh tables for the selected non-chart components.

    Args:
        snapshot: The displayed clustering fit.
        components: Selected components; charts are ignored.

    Returns:
        Tables in selection order, keyed by component.
    """
    tables: dict[ClusteringExportComponent, pd.DataFrame] = {}
    for component in components:
        match component:
            case ClusteringExportComponent.CLUSTER_SIZES:
                tables[component] = cluster_sizes_table(snapshot)
            case ClusteringExportComponent.MODEL_SUMMARY:
                tables[component] = clustering_model_summary_table(snapshot)
            case ClusteringExportComponent.CHARTS:
                pass
    return tables


def cluster_sizes_table(snapshot: ClusteringExportSnapshot) -> pd.DataFrame:
    """Return the displayed cluster sizes with their share of the rows used.

    Clusters keep the displayed order and names; DBSCAN noise is the last
    row when present.

    Args:
        snapshot: The displayed clustering fit.

    Returns:
        Columns ``cluster`` (the displayed name), ``rows`` and ``share``.
    """
    result = snapshot.result
    labels = snapshot.chart_labels
    names = [labels.cluster_name(cluster.label) for cluster in result.clusters]
    counts = [cluster.count for cluster in result.clusters]
    if result.noise_count:
        names.append(labels.noise)
        counts.append(result.noise_count)
    return pd.DataFrame({
        "cluster": pd.Series(names, dtype=pd.StringDtype()),
        "rows": pd.Series(counts, dtype=pd.Int64Dtype()),
        "share": pd.Series([count / result.rows_used for count in counts], dtype="float64"),
    })


def clustering_model_summary_table(snapshot: ClusteringExportSnapshot) -> pd.DataFrame:
    """Return the fit's settings, row counts and silhouette with its displayed comments.

    The silhouette value is missing when the score is undefined for the fit;
    the comments explain why.

    Args:
        snapshot: The displayed clustering fit.

    Returns:
        Columns ``metric`` (a `ClusteringMetric` key), ``value`` and ``notes``.
    """
    result = snapshot.result
    values: list[tuple[ClusteringMetric, float]] = [(ClusteringMetric.FEATURES, len(result.columns))]
    if result.method is ClusteringMethod.DBSCAN:
        values += [
            (ClusteringMetric.DBSCAN_EPSILON, result.dbscan_epsilon),
            (ClusteringMetric.DBSCAN_MIN_SAMPLES, result.dbscan_min_samples),
        ]
    else:
        values.append((ClusteringMetric.CLUSTER_COUNT, result.cluster_count))
    values += [
        (ClusteringMetric.TOTAL_ROWS, result.total_rows),
        (ClusteringMetric.ROWS_USED, result.rows_used),
        (ClusteringMetric.ROWS_DROPPED, result.rows_dropped),
        (ClusteringMetric.CLUSTERS_FOUND, len(result.clusters)),
    ]
    if result.method is ClusteringMethod.DBSCAN:
        values.append((ClusteringMetric.NOISE_ROWS, result.noise_count))
    silhouette = float("nan") if result.silhouette_score is None else result.silhouette_score
    values.append((ClusteringMetric.SILHOUETTE, silhouette))

    notes = snapshot.notes
    row_count = max(len(values), len(notes))
    return pd.DataFrame({
        "metric": pd.Series([metric.value for metric, _ in values], dtype=pd.StringDtype()).reindex(range(row_count)),
        "value": pd.Series([float(value) for _, value in values], dtype="float64").reindex(range(row_count)),
        "notes": pd.Series(notes, dtype=pd.StringDtype()).reindex(range(row_count)),
    })
