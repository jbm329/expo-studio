"""Qt-free construction of the displayed hypothesis charts and Excel images."""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from expo_jbm329.services.analysis.chi_square import ChiSquareResult
from expo_jbm329.services.analysis.group_comparison import GroupComparisonResult
from expo_jbm329.services.analysis.paired_comparison import PairedComparisonResult
from expo_jbm329.services.analysis.statistics_charts import STATISTICS_CHART_LOCK
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.group_comparison import GroupSummary
    from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportSnapshot

RESIDUAL_SIGNIFICANCE_THRESHOLD = 1.96
MAX_ANNOTATED_CELLS = 100


@dataclass(frozen=True, slots=True)
class HypothesisChartLabels:
    """Presentation text captured before worker execution."""

    distribution: str
    residuals: str
    trajectories: str
    value: str
    occasion: str
    residual_annotations: tuple[tuple[str, ...], ...] = ()


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
    title: str,
    annotations: tuple[tuple[str, ...], ...] = (),
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
    ax.set_title(title)
    if residuals.size <= MAX_ANNOTATED_CELLS:
        for (row, column), value in np.ndenumerate(residuals):
            if math.isfinite(value):
                text = (
                    annotations[row][column]
                    if annotations
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


def draw_paired_charts(figure: Figure, result: PairedComparisonResult, labels: HypothesisChartLabels) -> None:
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
    distribution.set_title(labels.distribution)
    distribution.set_ylabel(labels.value)
    positions = list(range(1, len(result.columns) + 1))
    if result.plot_data is not None:
        for values in result.plot_data.trajectories:
            trajectories.plot(positions, values, marker=".", color="tab:blue", alpha=0.25, linewidth=0.8)
    trajectories.set_xticks(positions, result.columns)
    trajectories.set_title(labels.trajectories)
    trajectories.set_ylabel(labels.value)
    for axis in (distribution, trajectories):
        axis.set_xlabel(labels.occasion)
        axis.tick_params(axis="x", labelrotation=30)


def render_hypothesis_charts(
    snapshot: HypothesisExportSnapshot,
    labels: HypothesisChartLabels,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render exactly one displayed chart (paired charts share one image).

    Args:
        snapshot: Fitted result with prepared chart data; no dataset is consulted.
        labels: Translated chart text captured on the GUI thread.
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
        figure = Figure(figsize=(9, 3.5), dpi=120, constrained_layout=True)
        canvas = FigureCanvasAgg(figure)
        result = snapshot.result
        match result:
            case GroupComparisonResult():
                draw_group_distribution(figure.add_subplot(111), result.groups, labels.distribution)
            case ChiSquareResult():
                draw_residual_heatmap(
                    figure,
                    figure.add_subplot(111),
                    result,
                    labels.residuals,
                    labels.residual_annotations,
                )
            case PairedComparisonResult():
                draw_paired_charts(figure, result, labels)
        output = BytesIO()
        canvas.print_png(output)  # type: ignore[no-untyped-call]
    if cancel_cb is not None and cancel_cb():
        raise ExcelChartCancelledError
    if progress_cb is not None:
        progress_cb(100)
    return (ExcelChartImage(" / ".join(snapshot.columns), output.getvalue(), 1080, 420),)
