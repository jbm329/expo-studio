"""Qt-free clustering PCA projection and its Excel image."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from expo_jbm329.services.analysis.chart_export import render_chart_png
from expo_jbm329.services.analysis.chart_layout import ChartFigure as Figure
from expo_jbm329.services.analysis.chart_presentation import (
    DEFAULT_WORKSHEET_HEADING,
    ChartPresentationMetadata,
)
from expo_jbm329.services.analysis.chart_profiles import (
    CLUSTERING_LEGEND_FONT_SIZE,
    CLUSTERING_PROJECTION_PROFILE,
)
from expo_jbm329.services.analysis.statistics_charts import STATISTICS_CHART_LOCK
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage

if TYPE_CHECKING:
    from collections.abc import Callable

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.clustering import ClusteringResult
    from expo_jbm329.services.analysis.clustering_export import ClusteringExportSnapshot

_NOISE_LABEL = -1


@dataclass(frozen=True, slots=True)
class ClusterProjectionLabels:
    """Translated projection semantics and output metadata captured before rendering.

    Attributes:
        metadata: Worksheet, accessibility, and sampling caption metadata.
        pc1_axis: X-axis label.
        pc2_axis: Y-axis label.
        cluster: Legend template of a cluster, formatted with its 1-based ``number``.
        noise: Legend label of DBSCAN noise.
    """

    metadata: ChartPresentationMetadata
    pc1_axis: str
    pc2_axis: str
    cluster: str
    noise: str

    def cluster_name(self, label: int) -> str:
        """Return the displayed name of a fitted cluster label, or noise for ``-1``."""
        return self.noise if label == _NOISE_LABEL else self.cluster.format(number=label + 1)


def build_cluster_projection_labels(
    result: ClusteringResult,
    translate: Callable[[str, str], str],
    *,
    count_format: Callable[[int], str] = str,
) -> ClusterProjectionLabels:
    """Capture the shared projection labels, accessibility, and sampling note.

    Args:
        result: Applied clustering fit with its existing projection sample.
        translate: Explicit translation callback used only during capture.
        count_format: Locale-aware count formatter used only during capture.

    Returns:
        Frozen projection labels requiring no Qt or formatter in a worker.
    """
    title = translate("ClusteringPresentation", "Cluster projection (internal PCA)")
    captions = (
        (
            translate("ClusteringPresentation", "The plot shows a deterministic sample of {count} rows.").format(
                count=count_format(len(result.sample_labels))
            ),
        )
        if result.sampled and result.error is None
        else ()
    )
    return ClusterProjectionLabels(
        metadata=ChartPresentationMetadata(
            worksheet_heading=DEFAULT_WORKSHEET_HEADING, accessible_name=title, captions=captions
        ),
        pc1_axis=translate("ClusteringPresentation", "PC1"),
        pc2_axis=translate("ClusteringPresentation", "PC2"),
        cluster=translate("ClusteringView", "Cluster {number}"),
        noise=translate("ClusteringView", "Noise"),
    )


def draw_cluster_projection(ax: Axes, result: ClusteringResult, labels: ClusterProjectionLabels) -> None:
    """Draw the internal two-component PCA projection colored by cluster label.

    Args:
        ax: Target axes.
        result: Successful clustering fit with its projected sample.
        labels: Captured title, axis and legend text.
    """
    cluster_labels = np.asarray(result.sample_labels)
    x = np.asarray(result.sample_pc1)
    y = np.asarray(result.sample_pc2)
    for label in sorted(set(cluster_labels.tolist())):
        mask = cluster_labels == label
        color = "0.5" if label == _NOISE_LABEL else None
        ax.scatter(x[mask], y[mask], s=8, alpha=0.5, label=labels.cluster_name(label), color=color)
    ax.axhline(0, color="0.8", linewidth=0.8)
    ax.axvline(0, color="0.8", linewidth=0.8)
    ax.set_title(labels.metadata.accessible_name)
    ax.set_xlabel(labels.pc1_axis)
    ax.set_ylabel(labels.pc2_axis)
    ax.legend(fontsize=CLUSTERING_LEGEND_FONT_SIZE)


def render_clustering_charts(
    snapshot: ClusteringExportSnapshot,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render the displayed cluster projection as one image.

    Args:
        snapshot: Successful fit with its projected sample and chart text.
        progress_cb: Optional image preparation progress.
        cancel_cb: Optional cancellation callback.

    Returns:
        One PNG image owned by the worker, never a live Qt canvas.

    Raises:
        ExcelChartCancelledError: If cancellation is requested before or after drawing.
    """
    if cancel_cb is not None and cancel_cb():
        raise ExcelChartCancelledError
    labels = snapshot.chart_labels
    with STATISTICS_CHART_LOCK:
        geometry = CLUSTERING_PROJECTION_PROFILE.geometry
        figure = Figure(
            figsize=geometry.figsize,
            dpi=geometry.dpi,
            constrained_layout=geometry.constrained_layout,
        )
        draw_cluster_projection(figure.add_subplot(111), snapshot.result, labels)
        raster = render_chart_png(figure)
    if cancel_cb is not None and cancel_cb():
        raise ExcelChartCancelledError
    if progress_cb is not None:
        progress_cb(100)
    return (
        ExcelChartImage(
            labels.metadata.worksheet_heading,
            raster.image_data,
            raster.width_px,
            raster.height_px,
            labels.metadata.captions,
            accessible_name=labels.metadata.accessible_name,
        ),
    )
