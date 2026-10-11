"""Qt-free time-series plots and their Excel images."""

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
    from collections.abc import Callable, Sequence

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.timeseries import TimeSeriesResult
    from expo_jbm329.services.analysis.timeseries_export import TimeSeriesExportSnapshot

_EXPORT_DPI = 120
_PLOT_FIGURE_SIZE = (8.0, 4.0)
_DECOMPOSITION_FIGURE_SIZE = (8.0, 8.0)
DECOMPOSITION_PANELS = 4


@dataclass(frozen=True, slots=True)
class TimeSeriesChartLabels:
    """Translated time-series plot text captured on the GUI thread.

    Attributes:
        series_title: Series plot title, also its Excel heading.
        value_axis: Series y-axis label, the analyzed value column.
        acf_title: Autocorrelation plot title, also its Excel heading.
        lag_axis: Autocorrelation x-axis label.
        acf_axis: Autocorrelation y-axis label.
        decomposition_title: Decomposition title, also its Excel heading.
        observed: Y-axis label of the observed panel.
        trend: Y-axis label of the trend panel.
        seasonal: Y-axis label of the seasonal panel.
        residual: Y-axis label of the residual panel.
    """

    series_title: str
    value_axis: str
    acf_title: str
    lag_axis: str
    acf_axis: str
    decomposition_title: str
    observed: str
    trend: str
    seasonal: str
    residual: str


def has_autocorrelation(result: TimeSeriesResult) -> bool:
    """Return whether the result has autocorrelation coefficients to show."""
    return bool(result.acf_values)


def has_decomposition(result: TimeSeriesResult) -> bool:
    """Return whether the result has a seasonal decomposition to show."""
    return bool(result.trend)


def draw_series_plot(ax: Axes, result: TimeSeriesResult, labels: TimeSeriesChartLabels) -> None:
    """Draw the prepared series over time.

    Args:
        ax: Target axes.
        result: Successful time-series analysis.
        labels: Translated title and axis text.
    """
    ax.plot(result.timestamps, result.values, marker="o", markersize=3)  # type: ignore[arg-type]
    ax.set_title(labels.series_title)
    ax.set_ylabel(labels.value_axis)
    ax.tick_params(axis="x", rotation=30)


def draw_acf_plot(ax: Axes, result: TimeSeriesResult, labels: TimeSeriesChartLabels) -> None:
    """Draw autocorrelation stems for lags 1 to n.

    Args:
        ax: Target axes.
        result: Successful analysis with autocorrelation coefficients.
        labels: Translated title and axis text.
    """
    lags = np.arange(1, len(result.acf_values) + 1)
    ax.vlines(lags, 0, result.acf_values)
    ax.scatter(lags, result.acf_values, s=12)
    ax.axhline(0, color="0.5", linewidth=0.8)
    ax.set_xlabel(labels.lag_axis)
    ax.set_ylabel(labels.acf_axis)
    ax.set_title(labels.acf_title)


def draw_decomposition(axes: Sequence[Axes], result: TimeSeriesResult, labels: TimeSeriesChartLabels) -> None:
    """Draw observed, trend, seasonal and residual panels top to bottom.

    Args:
        axes: Four vertically stacked axes sharing the time axis.
        result: Successful analysis with a seasonal decomposition.
        labels: Translated title and panel text.

    Raises:
        ValueError: If not exactly four axes are given.
    """
    if len(axes) != DECOMPOSITION_PANELS:
        message = "Seasonal decomposition needs exactly four axes."
        raise ValueError(message)
    panels = (
        (labels.observed, result.values),
        (labels.trend, result.trend),
        (labels.seasonal, result.seasonal),
        (labels.residual, result.residual),
    )
    for ax, (label, values) in zip(axes, panels, strict=True):
        ax.plot(result.timestamps, values)  # type: ignore[arg-type]
        ax.set_ylabel(label)
    axes[0].set_title(labels.decomposition_title)
    axes[-1].tick_params(axis="x", rotation=30)


def _draw_series_figure(figure: Figure, result: TimeSeriesResult, labels: TimeSeriesChartLabels) -> None:
    draw_series_plot(figure.add_subplot(111), result, labels)


def _draw_acf_figure(figure: Figure, result: TimeSeriesResult, labels: TimeSeriesChartLabels) -> None:
    draw_acf_plot(figure.add_subplot(111), result, labels)


def _draw_decomposition_figure(figure: Figure, result: TimeSeriesResult, labels: TimeSeriesChartLabels) -> None:
    draw_decomposition(list(figure.subplots(DECOMPOSITION_PANELS, 1, sharex=True)), result, labels)


def render_time_series_charts(
    snapshot: TimeSeriesExportSnapshot,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render the series plot and, when available, the autocorrelation and decomposition.

    Unavailable plots are skipped; the model summary notes explain why.

    Args:
        snapshot: Successful analysis with its chart text.
        progress_cb: Optional per-image progress, reaching 100.
        cancel_cb: Optional cancellation callback, checked before each image and at the end.

    Returns:
        PNG images owned by the worker, never live Qt canvases.

    Raises:
        ExcelChartCancelledError: If cancellation is requested.
    """
    result = snapshot.result
    labels = snapshot.chart_labels
    plots: list[tuple[str, Callable[[Figure, TimeSeriesResult, TimeSeriesChartLabels], None], tuple[float, float]]]
    plots = [(labels.series_title, _draw_series_figure, _PLOT_FIGURE_SIZE)]
    if has_autocorrelation(result):
        plots.append((labels.acf_title, _draw_acf_figure, _PLOT_FIGURE_SIZE))
    if has_decomposition(result):
        plots.append((labels.decomposition_title, _draw_decomposition_figure, _DECOMPOSITION_FIGURE_SIZE))

    images: list[ExcelChartImage] = []
    for index, (heading, draw, size) in enumerate(plots):
        if cancel_cb is not None and cancel_cb():
            raise ExcelChartCancelledError
        with STATISTICS_CHART_LOCK:
            figure = Figure(figsize=size, dpi=_EXPORT_DPI, constrained_layout=True)
            canvas = FigureCanvasAgg(figure)
            draw(figure, result, labels)
            output = BytesIO()
            canvas.print_png(output)  # type: ignore[no-untyped-call]
        width, height = size
        images.append(
            ExcelChartImage(heading, output.getvalue(), round(width * _EXPORT_DPI), round(height * _EXPORT_DPI))
        )
        if progress_cb is not None:
            progress_cb((index + 1) * 100 // len(plots))
    if cancel_cb is not None and cancel_cb():
        raise ExcelChartCancelledError
    return tuple(images)
