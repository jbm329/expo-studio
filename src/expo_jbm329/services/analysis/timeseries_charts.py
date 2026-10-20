"""Qt-free time-series plots and their Excel images."""

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
from expo_jbm329.services.analysis.chart_profiles import (
    TIME_SERIES_CHART_PROFILE,
    TIME_SERIES_DECOMPOSITION_PROFILE,
    TIME_SERIES_PREFERRED_ROTATION,
    ChartProfile,
)
from expo_jbm329.services.analysis.statistics_charts import STATISTICS_CHART_LOCK
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.timeseries import TimeSeriesResult
    from expo_jbm329.services.analysis.timeseries_export import TimeSeriesExportSnapshot

DECOMPOSITION_PANELS = 4


@dataclass(frozen=True, slots=True)
class TimeSeriesChartLabels:
    """Translated time-series plot text captured on the GUI thread.

    Attributes:
        series_metadata: Series title, accessibility, and output metadata.
        value_axis: Series y-axis label, the analyzed value column.
        acf_metadata: Autocorrelation title, accessibility, and output metadata.
        lag_axis: Autocorrelation x-axis label.
        acf_axis: Autocorrelation y-axis label.
        decomposition_metadata: Decomposition title, accessibility, and output metadata.
        observed: Y-axis label of the observed panel.
        trend: Y-axis label of the trend panel.
        seasonal: Y-axis label of the seasonal panel.
        residual: Y-axis label of the residual panel.
    """

    series_metadata: ChartPresentationMetadata
    value_axis: str
    acf_metadata: ChartPresentationMetadata
    lag_axis: str
    acf_axis: str
    decomposition_metadata: ChartPresentationMetadata
    observed: str
    trend: str
    seasonal: str
    residual: str


def build_time_series_chart_labels(
    result: TimeSeriesResult,
    translate: Callable[[str, str], str],
) -> TimeSeriesChartLabels:
    """Capture shared chart semantics without retaining the translator.

    Args:
        result: Applied analysis with its selected value column.
        translate: Translation callback used only during capture.

    Returns:
        Frozen labels for the app and background Excel/HTML renderers.
    """
    return TimeSeriesChartLabels(
        series_metadata=ChartPresentationMetadata(
            worksheet_heading=DEFAULT_WORKSHEET_HEADING,
            accessible_name=translate("TimeSeriesPresentation", "Series"),
        ),
        value_axis=result.value_column,
        acf_metadata=ChartPresentationMetadata(
            worksheet_heading=DEFAULT_WORKSHEET_HEADING,
            accessible_name=translate("TimeSeriesPresentation", "Autocorrelation"),
        ),
        lag_axis=translate("TimeSeriesPresentation", "Lag"),
        acf_axis=translate("TimeSeriesPresentation", "Autocorrelation"),
        decomposition_metadata=ChartPresentationMetadata(
            worksheet_heading=DEFAULT_WORKSHEET_HEADING,
            accessible_name=translate("TimeSeriesPresentation", "Seasonal decomposition"),
        ),
        observed=translate("TimeSeriesPresentation", "Observed"),
        trend=translate("TimeSeriesPresentation", "Trend"),
        seasonal=translate("TimeSeriesPresentation", "Seasonal"),
        residual=translate("TimeSeriesPresentation", "Residual"),
    )


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
    ax.set_title(labels.series_metadata.accessible_name)
    ax.set_ylabel(labels.value_axis)
    ax.tick_params(axis="x", rotation=TIME_SERIES_PREFERRED_ROTATION)


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
    ax.set_title(labels.acf_metadata.accessible_name)


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
    axes[0].set_title(labels.decomposition_metadata.accessible_name)
    axes[-1].tick_params(axis="x", rotation=TIME_SERIES_PREFERRED_ROTATION)


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
    corr_id: str | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render a time-series chart batch with bounded diagnostics."""
    with chart_render_batch("time_series", 1, corr_id):
        return _render_time_series_charts(
            snapshot,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
            corr_id=corr_id,
        )


def _render_time_series_charts(
    snapshot: TimeSeriesExportSnapshot,
    *,
    progress_cb: Callable[[int], None] | None,
    cancel_cb: Callable[[], bool] | None,
    corr_id: str | None,
) -> tuple[ExcelChartImage, ...]:
    """Render the series plot and, when available, the autocorrelation and decomposition.

    Unavailable plots are skipped; the model summary notes explain why.

    Args:
        snapshot: Successful analysis with its chart text.
        progress_cb: Optional per-image progress, reaching 100.
        cancel_cb: Optional cancellation callback, checked before each image and at the end.
        corr_id: Optional operation correlation identifier used only for diagnostics.

    Returns:
        PNG images owned by the worker, never live Qt canvases.

    Raises:
        ExcelChartCancelledError: If cancellation is requested.
    """
    result = snapshot.result
    labels = snapshot.chart_labels
    plots: list[
        tuple[
            ChartPresentationMetadata,
            Callable[[Figure, TimeSeriesResult, TimeSeriesChartLabels], None],
            ChartProfile,
        ]
    ]
    plots = [(labels.series_metadata, _draw_series_figure, TIME_SERIES_CHART_PROFILE)]
    if has_autocorrelation(result):
        plots.append((labels.acf_metadata, _draw_acf_figure, TIME_SERIES_CHART_PROFILE))
    if has_decomposition(result):
        plots.append((labels.decomposition_metadata, _draw_decomposition_figure, TIME_SERIES_DECOMPOSITION_PROFILE))

    images: list[ExcelChartImage] = []
    for index, (metadata, draw, profile) in enumerate(plots):
        if cancel_cb is not None and cancel_cb():
            raise ExcelChartCancelledError
        with STATISTICS_CHART_LOCK:
            geometry = profile.geometry
            figure = Figure(
                figsize=geometry.figsize,
                dpi=geometry.dpi,
                constrained_layout=geometry.constrained_layout,
            )
            draw(figure, result, labels)
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
