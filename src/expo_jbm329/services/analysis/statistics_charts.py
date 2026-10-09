"""Qt-free histogram and boxplot rendering for Statistics views and exports."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from math import ceil, isfinite
from threading import RLock
from typing import TYPE_CHECKING

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.statistics import ColumnDescriptiveStatistics

STATISTICS_CHART_LOCK = RLock()
_IMAGE_DPI = 120
_FIGURE_SIZE = (9.0, 3.5)


@dataclass(frozen=True, slots=True)
class StatisticsChartLabels:
    """Translated text used within one statistics chart pair."""

    histogram: str
    boxplot: str
    no_data: str


def draw_histogram(ax: Axes, stats: ColumnDescriptiveStatistics, labels: StatisticsChartLabels) -> None:
    """Draw the precomputed histogram values for one numeric column."""
    if not stats.histogram_bins or not stats.histogram_counts:
        _draw_no_data(ax, labels.no_data)
        return

    bins = np.asarray(stats.histogram_bins)
    counts = np.asarray(stats.histogram_counts)
    ax.bar(bins[:-1], counts, width=np.diff(bins), align="edge", edgecolor="#333")
    ax.set_title(labels.histogram)


def draw_boxplot(ax: Axes, stats: ColumnDescriptiveStatistics, labels: StatisticsChartLabels) -> None:
    """Draw the precomputed five-number boxplot for one numeric column."""
    values = (stats.minimum, stats.q1, stats.median, stats.q3, stats.maximum)
    if any(not isfinite(value) for value in values):
        _draw_no_data(ax, labels.no_data)
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
    ax.set_title(labels.boxplot)


def render_statistics_charts(
    columns: Sequence[ColumnDescriptiveStatistics],
    labels: StatisticsChartLabels,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render a histogram/boxplot image for every numeric column.

    Figures use the Agg canvas and remain local to the calling worker. The
    shared lock serializes rendering against StatisticsView's figure mutations
    and actual Qt canvas drawing. Other Matplotlib views do not use this lock.
    """
    images: list[ExcelChartImage] = []
    total = len(columns)
    for index, stats in enumerate(columns):
        if cancel_cb is not None and cancel_cb():
            raise ExcelChartCancelledError
        with STATISTICS_CHART_LOCK:
            figure = Figure(figsize=_FIGURE_SIZE, dpi=_IMAGE_DPI, constrained_layout=True)
            canvas = FigureCanvasAgg(figure)
            histogram = figure.add_subplot(121)
            boxplot = figure.add_subplot(122)
            draw_histogram(histogram, stats, labels)
            draw_boxplot(boxplot, stats, labels)
            figure.suptitle(stats.column)
            output = BytesIO()
            canvas.print_png(output)  # type: ignore[no-untyped-call]
            image_data = output.getvalue()
        width_px, height_px = (round(_FIGURE_SIZE[0] * _IMAGE_DPI), round(_FIGURE_SIZE[1] * _IMAGE_DPI))
        images.append(ExcelChartImage(stats.column, image_data, width_px, height_px))
        if progress_cb is not None:
            progress_cb(ceil((index + 1) * 100 / total))
    return tuple(images)


def _draw_no_data(ax: Axes, text: str) -> None:
    """Show the same explicit no-data state for either chart."""
    ax.text(0.5, 0.5, text, ha="center", va="center", transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
