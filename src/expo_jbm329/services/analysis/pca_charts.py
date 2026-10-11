"""Qt-free PCA scree and score plots and their Excel images."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from expo_jbm329.services.analysis.statistics_charts import STATISTICS_CHART_LOCK
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage

if TYPE_CHECKING:
    from collections.abc import Callable

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.pca import PCAResult
    from expo_jbm329.services.analysis.pca_export import PCAExportSnapshot

_EXPORT_DPI = 120
_FIGURE_SIZE = (8.0, 5.0)


@dataclass(frozen=True, slots=True)
class PCAChartLabels:
    """Translated PCA plot text captured on the GUI thread.

    Attributes:
        scree_title: Scree plot title, also its Excel heading.
        explained: Legend label of the per-component bars.
        cumulative: Legend label of the cumulative line.
        component_axis: Scree x-axis label.
        variance_axis: Scree y-axis label.
        scatter_title: Score plot title, also its Excel heading.
        pc1_axis: Score plot x-axis label, including PC1's explained share.
        pc2_axis: Score plot y-axis label, including PC2's explained share.
        scatter_captions: Lines written below the exported score plot.
    """

    scree_title: str
    explained: str
    cumulative: str
    component_axis: str
    variance_axis: str
    scatter_title: str
    pc1_axis: str
    pc2_axis: str
    scatter_captions: tuple[str, ...] = ()


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
    ax.set_title(labels.scree_title)
    ax.set_xlabel(labels.component_axis)
    ax.set_ylabel(labels.variance_axis)
    ax.set_xticks(positions)
    ax.set_ylim(0, 105)
    ax.legend(fontsize=8)


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
    ax.set_title(labels.scatter_title)
    ax.set_xlabel(labels.pc1_axis)
    ax.set_ylabel(labels.pc2_axis)


def render_pca_charts(
    snapshot: PCAExportSnapshot,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render the displayed scree plot and PC1-vs-PC2 plot as two images.

    Args:
        snapshot: Successful fit with its score sample and chart text.
        progress_cb: Optional per-image progress (50, then 100).
        cancel_cb: Optional cancellation callback, checked before each image and at the end.

    Returns:
        PNG images owned by the worker, never live Qt canvases.

    Raises:
        ExcelChartCancelledError: If cancellation is requested.
    """
    labels = snapshot.chart_labels
    plots: tuple[tuple[str, Callable[[Axes, PCAResult, PCAChartLabels], None], tuple[str, ...]], ...] = (
        (labels.scree_title, draw_scree_plot, ()),
        (labels.scatter_title, draw_score_plot, labels.scatter_captions),
    )
    images: list[ExcelChartImage] = []
    for index, (heading, draw, captions) in enumerate(plots):
        if cancel_cb is not None and cancel_cb():
            raise ExcelChartCancelledError
        with STATISTICS_CHART_LOCK:
            figure = Figure(figsize=_FIGURE_SIZE, dpi=_EXPORT_DPI, constrained_layout=True)
            canvas = FigureCanvasAgg(figure)
            draw(figure.add_subplot(111), snapshot.result, labels)
            output = BytesIO()
            canvas.print_png(output)  # type: ignore[no-untyped-call]
        width, height = _FIGURE_SIZE
        images.append(
            ExcelChartImage(
                heading,
                output.getvalue(),
                round(width * _EXPORT_DPI),
                round(height * _EXPORT_DPI),
                captions,
            )
        )
        if progress_cb is not None:
            progress_cb((index + 1) * 100 // len(plots))
    if cancel_cb is not None and cancel_cb():
        raise ExcelChartCancelledError
    return tuple(images)
