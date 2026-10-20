"""Qt-free PCA scree and score plots and their Excel images."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from expo_jbm329.services.analysis.chart_export import chart_render_batch, render_chart_png
from expo_jbm329.services.analysis.chart_layout import ChartFigure as Figure
from expo_jbm329.services.analysis.chart_presentation import (
    DEFAULT_WORKSHEET_HEADING,
    ChartPresentationMetadata,
)
from expo_jbm329.services.analysis.chart_profiles import PCA_CHART_PROFILE, PCA_LEGEND_FONT_SIZE
from expo_jbm329.services.analysis.statistics_charts import STATISTICS_CHART_LOCK
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage

if TYPE_CHECKING:
    from collections.abc import Callable

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.pca import PCAResult
    from expo_jbm329.services.analysis.pca_export import PCAExportSnapshot


@dataclass(frozen=True, slots=True)
class PCAChartLabels:
    """Translated PCA plot text captured on the GUI thread.

    Attributes:
        scree_metadata: Scree title, accessibility, and output metadata.
        explained: Legend label of the per-component bars.
        cumulative: Legend label of the cumulative line.
        component_axis: Scree x-axis label.
        variance_axis: Scree y-axis label.
        scatter_metadata: Score title, accessibility, and sampling caption metadata.
        pc1_axis: Score plot x-axis label, including PC1's explained share.
        pc2_axis: Score plot y-axis label, including PC2's explained share.
    """

    scree_metadata: ChartPresentationMetadata
    explained: str
    cumulative: str
    component_axis: str
    variance_axis: str
    scatter_metadata: ChartPresentationMetadata
    pc1_axis: str
    pc2_axis: str


def build_pca_chart_labels(
    result: PCAResult,
    translate: Callable[[str, str], str],
    *,
    percent_format: Callable[[float], str],
    count_format: Callable[[int], str] = str,
) -> PCAChartLabels:
    """Capture shared PCA semantics without retaining translators or formatters.

    Args:
        result: Applied fit with its existing ordered components and score sample.
        translate: Explicit translation callback used only during capture.
        percent_format: Percentage formatter used only during capture.
        count_format: Count formatter used only during capture.

    Returns:
        Frozen labels safe to draw in the app or a background renderer.
    """
    ratios = result.explained_variance_ratio
    captions = (
        (
            translate("PCAView", "The PC1-vs-PC2 plot shows a deterministic sample of {count} rows.").format(
                count=count_format(len(result.sample_pc1))
            ),
        )
        if result.sampled and result.error is None
        else ()
    )
    return PCAChartLabels(
        scree_metadata=ChartPresentationMetadata(
            worksheet_heading=DEFAULT_WORKSHEET_HEADING, accessible_name=translate("PCAView", "Scree plot")
        ),
        explained=translate("PCAPresentation", "Explained variance"),
        cumulative=translate("PCAView", "Cumulative"),
        component_axis=translate("PCAView", "Component"),
        variance_axis=translate("PCAView", "Explained variance (%)"),
        scatter_metadata=ChartPresentationMetadata(
            worksheet_heading=DEFAULT_WORKSHEET_HEADING,
            accessible_name=translate("PCAView", "PC1 vs PC2"),
            captions=captions,
        ),
        pc1_axis=(
            translate("PCAView", "PC1 ({variance})").format(variance=percent_format(ratios[0])) if ratios else "PC1"
        ),
        pc2_axis=(
            translate("PCAView", "PC2 ({variance})").format(variance=percent_format(ratios[1]))
            if len(ratios) > 1
            else "PC2"
        ),
    )


def draw_scree_plot(ax: Axes, result: PCAResult, labels: PCAChartLabels) -> None:
    """Draw per-component explained variance bars and the cumulative line.

    Args:
        ax: Target axes.
        result: Successful PCA fit.
        labels: Translated title, axis and legend text.
    """
    positions = np.arange(1, len(result.explained_variance_ratio) + 1)
    percentages = np.asarray(result.explained_variance_ratio) * 100
    cumulative = np.asarray(result.cumulative_variance_ratio) * 100
    ax.bar(positions, percentages, label=labels.explained)
    ax.plot(positions, cumulative, color="tab:red", marker="o", label=labels.cumulative)
    ax.set_title(labels.scree_metadata.accessible_name)
    ax.set_xlabel(labels.component_axis)
    ax.set_ylabel(labels.variance_axis)
    ax.set_xticks(positions)
    ax.set_ylim(0, 105)
    ax.legend(fontsize=PCA_LEGEND_FONT_SIZE)


def draw_score_plot(ax: Axes, result: PCAResult, labels: PCAChartLabels) -> None:
    """Draw the sampled PC1 and PC2 scores.

    Args:
        ax: Target axes.
        result: Successful PCA fit with its score sample.
        labels: Translated title and axis text.
    """
    ax.scatter(result.sample_pc1, result.sample_pc2, s=6, alpha=0.4)
    ax.axhline(0, color="0.7", linewidth=0.8)
    ax.axvline(0, color="0.7", linewidth=0.8)
    ax.set_title(labels.scatter_metadata.accessible_name)
    ax.set_xlabel(labels.pc1_axis)
    ax.set_ylabel(labels.pc2_axis)


def render_pca_charts(
    snapshot: PCAExportSnapshot,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
    corr_id: str | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render a PCA chart batch with bounded diagnostics."""
    with chart_render_batch("pca", 2, corr_id):
        return _render_pca_charts(
            snapshot,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
            corr_id=corr_id,
        )


def _render_pca_charts(
    snapshot: PCAExportSnapshot,
    *,
    progress_cb: Callable[[int], None] | None,
    cancel_cb: Callable[[], bool] | None,
    corr_id: str | None,
) -> tuple[ExcelChartImage, ...]:
    """Render the displayed scree plot and PC1-vs-PC2 plot as two images.

    Args:
        snapshot: Successful fit with its score sample and chart text.
        progress_cb: Optional per-image progress (50, then 100).
        cancel_cb: Optional cancellation callback, checked before each image and at the end.
        corr_id: Optional operation correlation identifier used only for diagnostics.

    Returns:
        PNG images owned by the worker, never live Qt canvases.

    Raises:
        ExcelChartCancelledError: If cancellation is requested.
    """
    labels = snapshot.chart_labels
    plots: tuple[tuple[ChartPresentationMetadata, Callable[[Axes, PCAResult, PCAChartLabels], None]], ...] = (
        (labels.scree_metadata, draw_scree_plot),
        (labels.scatter_metadata, draw_score_plot),
    )
    images: list[ExcelChartImage] = []
    for index, (metadata, draw) in enumerate(plots):
        if cancel_cb is not None and cancel_cb():
            raise ExcelChartCancelledError
        with STATISTICS_CHART_LOCK:
            geometry = PCA_CHART_PROFILE.geometry
            figure = Figure(
                figsize=geometry.figsize,
                dpi=geometry.dpi,
                constrained_layout=geometry.constrained_layout,
            )
            draw(figure.add_subplot(111), snapshot.result, labels)
            raster = render_chart_png(figure, corr_id=corr_id)
        images.append(
            ExcelChartImage(
                metadata.worksheet_heading,
                raster.image_data,
                raster.width_px,
                raster.height_px,
                metadata.captions,
                accessible_name=metadata.accessible_name,
            )
        )
        if progress_cb is not None:
            progress_cb((index + 1) * 100 // len(plots))
    if cancel_cb is not None and cancel_cb():
        raise ExcelChartCancelledError
    return tuple(images)
