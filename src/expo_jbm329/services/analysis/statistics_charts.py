"""Qt-free histogram and boxplot rendering for Statistics views and exports."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from threading import RLock
from typing import TYPE_CHECKING

import numpy as np

from expo_jbm329.services.analysis.chart_export import chart_render_batch, render_chart_png
from expo_jbm329.services.analysis.chart_layout import ChartFigure as Figure
from expo_jbm329.services.analysis.chart_presentation import (
    DEFAULT_WORKSHEET_HEADING,
    ChartPresentationMetadata,
)
from expo_jbm329.services.analysis.chart_profiles import STATISTICS_CHART_PROFILE
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.statistics import ColumnDescriptiveStatistics

STATISTICS_CHART_LOCK = RLock()


@dataclass(frozen=True, slots=True)
class StatisticsChartPresentation:
    """Translated chart semantics and output metadata for one numeric column."""

    histogram_title: str
    boxplot_title: str
    no_data_label: str
    metadata: ChartPresentationMetadata


def build_statistics_chart_presentation(
    stats: ColumnDescriptiveStatistics,
    translate: Callable[[str, str], str],
) -> StatisticsChartPresentation:
    """Build all translated chart labels and metadata for one numeric column.

    Args:
        stats: Computed statistics for the column represented by this chart pair.
        translate: Translation callback accepting a context and source label.

    Returns:
        A frozen presentation shared by the live view and worker renderer.
    """
    return StatisticsChartPresentation(
        histogram_title=translate("StatisticsView", "Histogram"),
        boxplot_title=translate("StatisticsView", "Boxplot"),
        no_data_label=translate("StatisticsView", "No data"),
        metadata=ChartPresentationMetadata(
            worksheet_heading=DEFAULT_WORKSHEET_HEADING,
            accessible_name=stats.column or translate("StatisticsView", "Distribution"),
        ),
    )


def build_statistics_chart_presentations(
    columns: Sequence[ColumnDescriptiveStatistics],
    translate: Callable[[str, str], str],
) -> tuple[StatisticsChartPresentation, ...]:
    """Build chart presentations in the same order as the supplied columns.

    Args:
        columns: Computed numeric-column summaries in display order.
        translate: Translation callback accepting a context and source label.

    Returns:
        One presentation for each column, preserving the supplied order.
    """
    return tuple(build_statistics_chart_presentation(stats, translate) for stats in columns)


def draw_histogram(
    ax: Axes,
    stats: ColumnDescriptiveStatistics,
    presentation: StatisticsChartPresentation,
) -> None:
    """Draw the precomputed histogram values for one numeric column."""
    if not stats.histogram_bins or not stats.histogram_counts:
        _draw_no_data(ax, presentation.no_data_label)
        return

    bins = np.asarray(stats.histogram_bins)
    counts = np.asarray(stats.histogram_counts)
    ax.bar(bins[:-1], counts, width=np.diff(bins), align="edge", edgecolor="#333")
    ax.set_title(presentation.histogram_title)


def draw_boxplot(
    ax: Axes,
    stats: ColumnDescriptiveStatistics,
    presentation: StatisticsChartPresentation,
) -> None:
    """Draw the precomputed five-number boxplot for one numeric column."""
    values = (stats.minimum, stats.q1, stats.median, stats.q3, stats.maximum)
    if any(not isfinite(value) for value in values):
        _draw_no_data(ax, presentation.no_data_label)
        return

    ax.bxp(
        [
            {
                "med": stats.median,
                "q1": stats.q1,
                "q3": stats.q3,
                "whislo": stats.minimum,
                "whishi": stats.maximum,
                "fliers": [],
            }
        ],
        showfliers=False,
    )
    ax.set_title(presentation.boxplot_title)


def draw_statistics_charts(
    figure: Figure,
    stats: ColumnDescriptiveStatistics,
    presentation: StatisticsChartPresentation,
) -> None:
    """Draw one histogram/boxplot pair with the captured chart presentation."""
    histogram = figure.add_subplot(121)
    boxplot = figure.add_subplot(122)
    draw_histogram(histogram, stats, presentation)
    draw_boxplot(boxplot, stats, presentation)
    figure.suptitle(stats.column)


def render_statistics_charts(
    columns: Sequence[ColumnDescriptiveStatistics],
    presentations: Sequence[StatisticsChartPresentation],
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
    corr_id: str | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render the worker chart batch with bounded diagnostics."""
    with chart_render_batch("statistics", len(columns), corr_id):
        return _render_statistics_charts(
            columns,
            presentations,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
            corr_id=corr_id,
        )


def _render_statistics_charts(
    columns: Sequence[ColumnDescriptiveStatistics],
    presentations: Sequence[StatisticsChartPresentation],
    *,
    progress_cb: Callable[[int], None] | None,
    cancel_cb: Callable[[], bool] | None,
    corr_id: str | None,
) -> tuple[ExcelChartImage, ...]:
    """Render a histogram/boxplot image for every numeric column.

    Figures use the Agg canvas and remain local to the calling worker. The
    shared lock serializes all application and export chart rendering against
    figure mutations and Qt canvas drawing through SerializedAnalysisCanvas.

    Args:
        columns: Computed numeric-column summaries in display order.
        presentations: Matching translated presentations, also in display order.
        progress_cb: Optional callback receiving percentage completion.
        cancel_cb: Optional cooperative cancellation callback.
        corr_id: Optional operation correlation identifier used only for diagnostics.

    Returns:
        Worker-owned PNG images in column order.

    Raises:
        ValueError: If a presentation is missing or belongs to another column.
        ExcelChartCancelledError: If cancellation is requested between charts.
    """
    if len(columns) != len(presentations):
        message = "Each Statistics column requires exactly one chart presentation."
        raise ValueError(message)

    images: list[ExcelChartImage] = []
    total = len(columns)
    for index, (stats, presentation) in enumerate(zip(columns, presentations, strict=True)):
        if cancel_cb is not None and cancel_cb():
            raise ExcelChartCancelledError
        if presentation.metadata.accessible_name != stats.column:
            message = "A Statistics chart presentation does not match its column."
            raise ValueError(message)
        with STATISTICS_CHART_LOCK:
            geometry = STATISTICS_CHART_PROFILE.geometry
            figure = Figure(
                figsize=geometry.figsize,
                dpi=geometry.dpi,
                constrained_layout=geometry.constrained_layout,
            )
            draw_statistics_charts(figure, stats, presentation)
            raster = render_chart_png(figure, corr_id=corr_id)
        images.append(
            ExcelChartImage(
                presentation.metadata.worksheet_heading,
                raster.image_data,
                raster.width_px,
                raster.height_px,
                presentation.metadata.captions,
                presentation.metadata.accessible_name,
            )
        )
        if progress_cb is not None:
            progress_cb(ceil((index + 1) * 100 / total))
    return tuple(images)


def _draw_no_data(ax: Axes, text: str) -> None:
    """Show the same explicit no-data state for either chart."""
    ax.text(0.5, 0.5, text, ha="center", va="center", transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
