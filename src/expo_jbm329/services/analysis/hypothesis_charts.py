"""Qt-free construction of the displayed hypothesis charts and Excel images."""

from __future__ import annotations

import math
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
    HYPOTHESIS_CHART_PROFILE,
    PAIRED_COMPARISON_PREFERRED_ROTATION,
)
from expo_jbm329.services.analysis.chi_square import ChiSquareResult
from expo_jbm329.services.analysis.group_comparison import GroupComparisonResult
from expo_jbm329.services.analysis.paired_comparison import PairedComparisonResult
from expo_jbm329.services.analysis.statistics_charts import STATISTICS_CHART_LOCK
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage
from expo_jbm329.utils.format_utils import fmt_num

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.group_comparison import GroupSummary
    from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportSnapshot, HypothesisResult

RESIDUAL_SIGNIFICANCE_THRESHOLD = 1.96
MAX_ANNOTATED_CELLS = 100


def _format_residual_annotation(value: float) -> str:
    """Match the app's three-significant-digit heatmap labels."""
    return fmt_num(value, sig=3)


@dataclass(frozen=True, slots=True)
class GroupComparisonChartPresentation:
    """Titles and named axes for a group-comparison chart."""

    title: str
    x_axis_label: str
    y_axis_label: str
    metadata: ChartPresentationMetadata


@dataclass(frozen=True, slots=True)
class ChiSquareChartPresentation:
    """Title and annotations for an adjusted-residual heatmap."""

    title: str
    annotations: tuple[tuple[str, ...], ...]
    metadata: ChartPresentationMetadata


@dataclass(frozen=True, slots=True)
class PairedComparisonChartPresentation:
    """Titles and axes for paired distributions and subject trajectories."""

    distribution_title: str
    trajectories_title: str
    value_axis_label: str
    occasion_axis_label: str
    metadata: ChartPresentationMetadata


HypothesisChartPresentation = (
    GroupComparisonChartPresentation | ChiSquareChartPresentation | PairedComparisonChartPresentation
)


def build_hypothesis_chart_presentation(
    result: HypothesisResult,
    translate: Callable[[str, str], str],
    *,
    number_format: Callable[[float], str] = _format_residual_annotation,
) -> HypothesisChartPresentation:
    """Build translated labels, named axes, annotations and adapter metadata for a result.

    Args:
        result: Successfully computed hypothesis result.
        translate: Translation callback accepting a context and source label.
        number_format: Canonical formatter for residual annotations.

    Returns:
        A frozen presentation containing every chart-semantic value needed by
        the app and worker renderer.
    """
    match result:
        case GroupComparisonResult():
            return GroupComparisonChartPresentation(
                title=translate("GroupComparisonView", "Distribution by group"),
                x_axis_label=result.grouping_column,
                y_axis_label=result.numeric_column,
                metadata=ChartPresentationMetadata(
                    worksheet_heading=DEFAULT_WORKSHEET_HEADING,
                    accessible_name=f"{result.numeric_column} / {result.grouping_column}",
                ),
            )
        case ChiSquareResult():
            return ChiSquareChartPresentation(
                title=translate("ChiSquareView", "Adjusted standardized residuals"),
                annotations=tuple(tuple(number_format(value) for value in row) for row in result.adjusted_residuals),
                metadata=ChartPresentationMetadata(
                    worksheet_heading=DEFAULT_WORKSHEET_HEADING,
                    accessible_name=f"{result.row_column} / {result.column_column}",
                ),
            )
        case PairedComparisonResult():
            return PairedComparisonChartPresentation(
                distribution_title=translate("PairedComparisonView", "Distribution by occasion"),
                trajectories_title=translate("PairedComparisonView", "Subject trajectories"),
                value_axis_label=translate("PairedComparisonView", "Value"),
                occasion_axis_label=translate("PairedComparisonView", "Measurement occasion"),
                metadata=ChartPresentationMetadata(
                    worksheet_heading=DEFAULT_WORKSHEET_HEADING,
                    accessible_name=" / ".join(result.columns),
                ),
            )
        case _:
            message = "A hypothesis chart presentation requires a supported result."
            raise TypeError(message)


def draw_group_distribution(ax: Axes, groups: Sequence[GroupSummary], title: str) -> None:
    """Draw displayed min/max boxes from the full-group summaries."""
    ax.bxp(
        [
            {
                "label": group.label,
                "med": group.median,
                "q1": group.q1,
                "q3": group.q3,
                "whislo": group.minimum,
                "whishi": group.maximum,
                "fliers": [],
            }
            for group in groups
        ],
        showfliers=False,
    )
    ax.set_title(title)


def heatmap_color_limit(residuals: np.ndarray) -> float:
    """Keep a symmetric color scale no smaller than the significance threshold."""
    finite = np.abs(residuals[np.isfinite(residuals)])
    return max(float(finite.max()), RESIDUAL_SIGNIFICANCE_THRESHOLD) if finite.size else RESIDUAL_SIGNIFICANCE_THRESHOLD


def draw_residual_heatmap(
    figure: Figure,
    ax: Axes,
    result: ChiSquareResult,
    presentation: ChiSquareChartPresentation,
) -> None:
    """Draw row-major residuals with the same axes, colors and annotations as Qt."""
    residuals = np.asarray(result.adjusted_residuals, dtype=float)
    limit = heatmap_color_limit(residuals)
    image = ax.imshow(residuals, cmap="RdBu_r", vmin=-limit, vmax=limit, aspect="auto")
    figure.colorbar(image, ax=ax)
    ax.set_xticks(range(len(result.column_labels)), labels=list(result.column_labels))
    ax.set_yticks(range(len(result.row_labels)), labels=list(result.row_labels))
    ax.set_xlabel(result.column_column)
    ax.set_ylabel(result.row_column)
    ax.set_title(presentation.title)
    if residuals.size <= MAX_ANNOTATED_CELLS:
        for (row, column), value in np.ndenumerate(residuals):
            if math.isfinite(value):
                text = (
                    presentation.annotations[row][column]
                    if presentation.annotations
                    else str(
                        np.format_float_positional(
                            float(value),
                            precision=3,
                            unique=False,
                            trim="k",
                        )
                    )
                )
                ax.text(column, row, text, ha="center", va="center")


def draw_paired_charts(
    figure: Figure,
    result: PairedComparisonResult,
    presentation: PairedComparisonChartPresentation,
) -> None:
    """Draw full-cohort boxes and already sampled, ordered subject trajectories."""
    distribution = figure.add_subplot(121)
    trajectories = figure.add_subplot(122)
    distribution.bxp(
        [
            {
                "label": summary.column,
                "med": summary.median,
                "q1": summary.q1,
                "q3": summary.q3,
                "whislo": summary.minimum,
                "whishi": summary.maximum,
                "fliers": [],
            }
            for summary in result.summaries
        ],
        showfliers=False,
    )
    distribution.set_title(presentation.distribution_title)
    distribution.set_ylabel(presentation.value_axis_label)
    positions = list(range(1, len(result.columns) + 1))
    if result.plot_data is not None:
        for values in result.plot_data.trajectories:
            trajectories.plot(positions, values, marker=".", color="tab:blue", alpha=0.25, linewidth=0.8)
    trajectories.set_xticks(positions, result.columns)
    trajectories.set_title(presentation.trajectories_title)
    trajectories.set_ylabel(presentation.value_axis_label)
    for axis in (distribution, trajectories):
        axis.set_xlabel(presentation.occasion_axis_label)
        axis.tick_params(axis="x", labelrotation=PAIRED_COMPARISON_PREFERRED_ROTATION)


def draw_hypothesis_charts(figure: Figure, result: HypothesisResult, presentation: HypothesisChartPresentation) -> None:
    """Draw one hypothesis family's charts using the captured semantic presentation."""
    match result, presentation:
        case GroupComparisonResult(), GroupComparisonChartPresentation():
            axis = figure.add_subplot(111)
            draw_group_distribution(axis, result.groups, presentation.title)
            axis.set_xlabel(presentation.x_axis_label)
            axis.set_ylabel(presentation.y_axis_label)
        case ChiSquareResult(), ChiSquareChartPresentation():
            draw_residual_heatmap(figure, figure.add_subplot(111), result, presentation)
        case PairedComparisonResult(), PairedComparisonChartPresentation():
            draw_paired_charts(figure, result, presentation)
        case _:
            message = "The hypothesis chart presentation does not match its result family."
            raise TypeError(message)


def render_hypothesis_charts(
    snapshot: HypothesisExportSnapshot,
    presentation: HypothesisChartPresentation,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render exactly one displayed chart (paired charts share one image).

    Args:
        snapshot: Fitted result with prepared chart data; no dataset is consulted.
        presentation: Translated chart semantics captured before worker execution.
        progress_cb: Optional image preparation progress.
        cancel_cb: Optional cancellation callback.

    Returns:
        One PNG image owned by the worker, never a live Qt canvas.

    Raises:
        ExcelChartCancelledError: If cancellation is requested before or after drawing.
    """
    if cancel_cb is not None and cancel_cb():
        raise ExcelChartCancelledError
    with STATISTICS_CHART_LOCK:
        geometry = HYPOTHESIS_CHART_PROFILE.geometry
        figure = Figure(
            figsize=geometry.figsize,
            dpi=geometry.dpi,
            constrained_layout=geometry.constrained_layout,
        )
        draw_hypothesis_charts(figure, snapshot.result, presentation)
        raster = render_chart_png(figure)
    if cancel_cb is not None and cancel_cb():
        raise ExcelChartCancelledError
    if progress_cb is not None:
        progress_cb(100)
    return (
        ExcelChartImage(
            presentation.metadata.worksheet_heading,
            raster.image_data,
            raster.width_px,
            raster.height_px,
            presentation.metadata.captions,
            presentation.metadata.accessible_name,
        ),
    )
