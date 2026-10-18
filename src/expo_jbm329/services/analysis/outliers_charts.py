"""Qt-free outlier histograms, PCA projections and their Excel images."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

import numpy as np

from expo_jbm329.services.analysis.chart_export import ChartRaster, render_chart_png
from expo_jbm329.services.analysis.chart_layout import ChartFigure as Figure
from expo_jbm329.services.analysis.chart_presentation import (
    DEFAULT_WORKSHEET_HEADING,
    ChartPresentationMetadata,
)
from expo_jbm329.services.analysis.chart_profiles import (
    OUTLIER_HISTOGRAM_AXIS_FONT_SIZE,
    OUTLIER_HISTOGRAM_LEGEND_FONT_SIZE,
    OUTLIER_HISTOGRAM_PROFILE,
    OUTLIER_HISTOGRAM_TICK_FONT_SIZE,
    OUTLIER_HISTOGRAM_TITLE_FONT_SIZE,
    OUTLIER_PROJECTION_LEGEND_FONT_SIZE,
    OUTLIER_PROJECTION_PROFILE,
)
from expo_jbm329.services.analysis.outliers import analyze_outlier_column
from expo_jbm329.services.analysis.statistics_charts import STATISTICS_CHART_LOCK
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage

if TYPE_CHECKING:
    from collections.abc import Callable

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierResult
    from expo_jbm329.services.analysis.outliers import OutlierColumnDetail
    from expo_jbm329.services.analysis.outliers_export import (
        MultivariateOutlierExportSnapshot,
        UnivariateOutlierExportSnapshot,
    )


@dataclass(frozen=True, slots=True)
class OutlierHistogramLabels:
    """Translated univariate histogram text captured on the GUI thread."""

    inside: str
    outliers: str
    count_axis: str
    distribution_name: str


@dataclass(frozen=True, slots=True)
class OutlierProjectionLabels:
    """Translated projection semantics and metadata captured before rendering."""

    metadata: ChartPresentationMetadata
    title: str
    pc1_axis: str
    pc2_axis: str
    inliers: str
    outliers: str


@dataclass(frozen=True, slots=True)
class OutlierHistogramPresentation:
    """Column identity, axes, legends and output metadata for one histogram."""

    title: str
    x_label: str
    labels: OutlierHistogramLabels
    metadata: ChartPresentationMetadata


def build_outlier_histogram_labels(translate: Callable[[str, str], str]) -> OutlierHistogramLabels:
    """Capture the shared histogram text before dispatching any worker."""
    return OutlierHistogramLabels(
        inside=translate("OutliersView", "Inside the fences"),
        outliers=translate("OutliersView", "Potential outliers"),
        count_axis=translate("OutliersView", "Count"),
        distribution_name=translate("OutliersPresentation", "Column distribution"),
    )


def build_outlier_histogram_presentation(column: str, labels: OutlierHistogramLabels) -> OutlierHistogramPresentation:
    """Use the actual column for the title and value axis without repeating an outer heading."""
    return OutlierHistogramPresentation(
        title=column,
        x_label=column,
        labels=labels,
        metadata=ChartPresentationMetadata(
            worksheet_heading=DEFAULT_WORKSHEET_HEADING, accessible_name=column or labels.distribution_name
        ),
    )


def build_outlier_projection_labels(
    result: MultivariateOutlierResult,
    translate: Callable[[str, str], str],
    *,
    count_format: Callable[[int], str] = str,
) -> OutlierProjectionLabels:
    """Capture projection semantics and plain sampling notes for every output.

    Args:
        result: Applied fit with its existing PCA visualization sample.
        translate: Explicit translation callback used only during capture.
        count_format: Locale-aware count formatter used only during capture.

    Returns:
        Frozen projection labels requiring no Qt or formatter in a worker.
    """
    title = translate("MultivariateOutliersView", "PCA projection (visualization only)")
    captions = (
        (
            translate(
                "MultivariateOutliersView", "The projection shows a deterministic sample of {count} rows."
            ).format(count=count_format(len(result.sample_outliers))),
        )
        if result.sampled and result.error is None
        else ()
    )
    return OutlierProjectionLabels(
        metadata=ChartPresentationMetadata(
            worksheet_heading=DEFAULT_WORKSHEET_HEADING, accessible_name=title, captions=captions
        ),
        title=title,
        pc1_axis=translate("MultivariateOutliersView", "PC1"),
        pc2_axis=translate("MultivariateOutliersView", "PC2"),
        inliers=translate("MultivariateOutliersView", "Inliers"),
        outliers=translate("MultivariateOutliersView", "Potential outliers"),
    )


def draw_outlier_histogram(ax: Axes, detail: OutlierColumnDetail, presentation: OutlierHistogramPresentation) -> None:
    """Draw stacked inlier/outlier bars over shared bins, with the fences marked.

    Args:
        ax: Target axes.
        detail: Screened column detail with precomputed histogram bins.
        presentation: Shared title, axes, legend and output metadata.
    """
    labels = presentation.labels
    ax.set_title(presentation.title, fontsize=OUTLIER_HISTOGRAM_TITLE_FONT_SIZE)
    ax.set_xlabel(presentation.x_label, fontsize=OUTLIER_HISTOGRAM_AXIS_FONT_SIZE)
    ax.set_ylabel(labels.count_axis, fontsize=OUTLIER_HISTOGRAM_AXIS_FONT_SIZE)
    edges = detail.histogram_edges
    if not edges:
        return
    lefts = edges[:-1]
    widths = [right - left for left, right in pairwise(edges)]
    ax.bar(lefts, detail.inlier_counts, width=widths, align="edge", label=labels.inside)
    ax.bar(
        lefts,
        detail.outlier_counts,
        width=widths,
        align="edge",
        bottom=detail.inlier_counts,
        color="tab:red",
        label=labels.outliers,
    )
    for fence in (detail.summary.lower_fence, detail.summary.upper_fence):
        if math.isfinite(fence):
            ax.axvline(fence, color="tab:red", linestyle="--", linewidth=1)
    ax.tick_params(labelsize=OUTLIER_HISTOGRAM_TICK_FONT_SIZE)
    ax.legend(fontsize=OUTLIER_HISTOGRAM_LEGEND_FONT_SIZE)


def draw_outlier_projection(ax: Axes, result: MultivariateOutlierResult, labels: OutlierProjectionLabels) -> None:
    """Draw the PCA visualization without implying that the model used only two features.

    Args:
        ax: Target axes.
        result: Successful multivariate fit with its projected sample.
        labels: Translated title, axis and legend text.
    """
    x = np.asarray(result.sample_pc1)
    y = np.asarray(result.sample_pc2)
    outliers = np.asarray(result.sample_outliers, dtype=bool)
    ax.scatter(x[~outliers], y[~outliers], s=7, alpha=0.35, label=labels.inliers)
    ax.scatter(x[outliers], y[outliers], s=12, alpha=0.7, color="tab:red", label=labels.outliers)
    ax.axhline(0, color="0.8", linewidth=0.8)
    ax.axvline(0, color="0.8", linewidth=0.8)
    ax.set_title(labels.title)
    ax.set_xlabel(labels.pc1_axis)
    ax.set_ylabel(labels.pc2_axis)
    ax.legend(fontsize=OUTLIER_PROJECTION_LEGEND_FONT_SIZE)


def render_univariate_outlier_charts(
    snapshot: UnivariateOutlierExportSnapshot,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render one histogram image per screened column, in summary order.

    Each column is screened again from the snapshot's owned data copy with
    the applied method and threshold, so the images match the displayed
    histogram of whichever column the user selects.

    Args:
        snapshot: Applied summary with owned numeric data and chart text.
        progress_cb: Optional per-column progress (0-100).
        cancel_cb: Optional cancellation callback, checked for every column.

    Returns:
        PNG images owned by the worker.

    Raises:
        ExcelChartCancelledError: If cancellation is requested.
        ValueError: If no column was screened.
    """
    columns = snapshot.chart_columns
    if not columns:
        message = "The exported outlier summary has no screened column to chart."
        raise ValueError(message)
    summary = snapshot.summary
    images: list[ExcelChartImage] = []
    for index, column in enumerate(columns):
        if cancel_cb is not None and cancel_cb():
            raise ExcelChartCancelledError
        detail = analyze_outlier_column(snapshot.data, column, summary.method, summary.threshold)
        if detail.error is not None:
            message = f"Column {column!r} could not be screened for the chart export."
            raise ValueError(message)
        presentation = build_outlier_histogram_presentation(column, snapshot.chart_labels)
        with STATISTICS_CHART_LOCK:
            geometry = OUTLIER_HISTOGRAM_PROFILE.geometry
            figure = Figure(
                figsize=geometry.figsize,
                dpi=geometry.dpi,
                constrained_layout=geometry.constrained_layout,
            )
            draw_outlier_histogram(figure.add_subplot(111), detail, presentation)
            raster = render_chart_png(figure)
        images.append(_image(presentation.metadata, raster))
        if progress_cb is not None:
            progress_cb(math.ceil((index + 1) * 100 / len(columns)))
    if cancel_cb is not None and cancel_cb():
        raise ExcelChartCancelledError
    return tuple(images)


def render_multivariate_outlier_charts(
    snapshot: MultivariateOutlierExportSnapshot,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render the displayed PCA projection as one image.

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
        geometry = OUTLIER_PROJECTION_PROFILE.geometry
        figure = Figure(
            figsize=geometry.figsize,
            dpi=geometry.dpi,
            constrained_layout=geometry.constrained_layout,
        )
        draw_outlier_projection(figure.add_subplot(111), snapshot.result, labels)
        raster = render_chart_png(figure)
    if cancel_cb is not None and cancel_cb():
        raise ExcelChartCancelledError
    if progress_cb is not None:
        progress_cb(100)
    return (_image(labels.metadata, raster),)


def _image(
    metadata: ChartPresentationMetadata,
    raster: ChartRaster,
) -> ExcelChartImage:
    """Wrap rendered PNG bytes with their pixel size."""
    return ExcelChartImage(
        metadata.worksheet_heading,
        raster.image_data,
        raster.width_px,
        raster.height_px,
        metadata.captions,
        accessible_name=metadata.accessible_name,
    )
