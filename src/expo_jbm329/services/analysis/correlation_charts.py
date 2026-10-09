"""Shared Qt-free correlation plots and worker-owned Excel images."""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO
from itertools import combinations
from typing import TYPE_CHECKING

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from expo_jbm329.services.analysis.correlation import (
    CorrelationError,
    CorrelationMethod,
    analyze_correlation_pair,
)
from expo_jbm329.services.analysis.correlation_export import CorrelationExportComponent
from expo_jbm329.services.analysis.statistics_charts import STATISTICS_CHART_LOCK
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.correlation import CorrelationMatrixResult, CorrelationPairDetail
    from expo_jbm329.services.analysis.correlation_export import CorrelationExportSnapshot

MAX_ANNOTATED_COLUMNS = 12
_LIGHT_TEXT_THRESHOLD = 0.6


def _format_number(value: float) -> str:
    """Format a line coefficient without depending on Qt presentation utilities."""
    return format(value, ".4g")


def _format_count(value: int) -> str:
    """Format a sample count with the default presentation grouping."""
    return format(value, ",")


@dataclass(frozen=True, slots=True)
class CorrelationChartLabels:
    """Translated presentation templates captured before worker execution."""

    matrix_title: str
    scatter_heading: str
    line_equation: str
    descriptive_line: str
    sampling: str
    insufficient_observations: str
    constant_input: str
    number_format: Callable[[float], str] = _format_number
    count_format: Callable[[int], str] = _format_count
    matrix_annotations: tuple[tuple[str, ...], ...] = ()


def draw_correlation_matrix(
    figure: Figure,
    ax: Axes,
    result: CorrelationMatrixResult,
    title: str,
    annotations: tuple[tuple[str, ...], ...] = (),
) -> None:
    """Draw the applied matrix with the GUI's fixed scale and annotation rules."""
    coefficients = np.asarray(result.coefficients, dtype=float)
    image = ax.imshow(coefficients, cmap="RdBu_r", vmin=-1.0, vmax=1.0)
    figure.colorbar(image, ax=ax)
    labels = list(result.columns)
    ax.set_xticks(range(len(labels)), labels=labels, rotation=90)
    ax.set_yticks(range(len(labels)), labels=labels)
    ax.set_title(title)
    if len(labels) <= MAX_ANNOTATED_COLUMNS:
        for (row, column), value in np.ndenumerate(coefficients):
            if math.isfinite(value):
                ax.text(
                    column,
                    row,
                    annotations[row][column] if annotations else format(float(value), ".2g"),
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white" if abs(value) > _LIGHT_TEXT_THRESHOLD else "black",
                )


def draw_correlation_scatter(ax: Axes, detail: CorrelationPairDetail) -> None:
    """Draw the deterministic sample and full-cohort least-squares line."""
    if detail.error is not None or not detail.sample_x:
        message = "A scatterplot requires a defined pair with prepared sample data."
        raise ValueError(message)
    ax.scatter(detail.sample_x, detail.sample_y, s=6, alpha=0.4)
    x_min, x_max = min(detail.sample_x), max(detail.sample_x)
    ax.plot(
        [x_min, x_max],
        [detail.slope * x_min + detail.intercept, detail.slope * x_max + detail.intercept],
        color="tab:red",
    )
    ax.set_xlabel(detail.pair.x_column)
    ax.set_ylabel(detail.pair.y_column)


def scatter_captions(detail: CorrelationPairDetail, labels: CorrelationChartLabels) -> tuple[str, ...]:
    """Build line, sampling or statistical-unavailability notes below an image."""
    if detail.error is not None:
        match detail.error:
            case CorrelationError.CONSTANT_INPUT:
                return (labels.constant_input,)
            case CorrelationError.NOT_ENOUGH_OBSERVATIONS:
                return (labels.insufficient_observations,)
            case _:
                message = f"Unexpected correlation chart error: {detail.error}."
                raise ValueError(message)
    captions = [
        labels.line_equation.format(
            slope=labels.number_format(detail.slope), intercept=labels.number_format(detail.intercept)
        ),
    ]
    if detail.method is not CorrelationMethod.PEARSON:
        captions.append(labels.descriptive_line)
    if detail.sampled:
        captions.append(
            labels.sampling.format(
                shown=labels.count_format(len(detail.sample_x)), total=labels.count_format(detail.pair.n)
            )
        )
    return tuple(captions)


def render_correlation_charts(
    snapshot: CorrelationExportSnapshot,
    components: Sequence[CorrelationExportComponent],
    labels: CorrelationChartLabels,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> tuple[ExcelChartImage, ...]:
    """Render matrix first, then each unordered pair once in applied column order.

    Args:
        snapshot: Successful matrix with its worker-owned numeric source data.
        components: Selected chart components, without the ranked table.
        labels: Translated text and caption templates.
        progress_cb: Optional preparation percentage callback.
        cancel_cb: Optional cooperative cancellation callback.

    Returns:
        Worker-owned PNG images with below-image captions.

    Raises:
        ValueError: If chart components are empty, duplicated or unsupported.
        ExcelChartCancelledError: If preparation is cancelled.
    """
    selected = tuple(components)
    allowed = (CorrelationExportComponent.MATRIX_PLOT, CorrelationExportComponent.SCATTERPLOTS)
    if not selected or len(set(selected)) != len(selected) or any(item not in allowed for item in selected):
        message = "Select distinct correlation chart components."
        raise ValueError(message)
    matrix = snapshot.matrix
    pairs = tuple(combinations(matrix.columns, 2)) if CorrelationExportComponent.SCATTERPLOTS in selected else ()
    pair_statistics = {(pair.x_column, pair.y_column): pair for pair in matrix.pairs}
    include_matrix = CorrelationExportComponent.MATRIX_PLOT in selected
    total = len(pairs) + int(include_matrix)
    images: list[ExcelChartImage] = []

    def check_cancel() -> None:
        if cancel_cb is not None and cancel_cb():
            raise ExcelChartCancelledError

    def render(heading: str, builder: Callable[[Figure], None], captions: tuple[str, ...] = ()) -> None:
        check_cancel()
        with STATISTICS_CHART_LOCK:
            check_cancel()
            figure = Figure(figsize=(9, 6), dpi=120, constrained_layout=True)
            try:
                canvas = FigureCanvasAgg(figure)
                builder(figure)
                output = BytesIO()
                canvas.print_png(output)  # type: ignore[no-untyped-call]
                image_data = output.getvalue()
            finally:
                figure.clear()
        check_cancel()
        images.append(ExcelChartImage(heading, image_data, 1080, 720, captions))
        if progress_cb is not None:
            progress_cb(len(images) * 100 // total)

    if include_matrix:
        render(
            labels.matrix_title,
            lambda figure: draw_correlation_matrix(
                figure, figure.add_subplot(111), matrix, labels.matrix_title, labels.matrix_annotations
            ),
        )
    for x_column, y_column in pairs:
        check_cancel()
        detail = analyze_correlation_pair(
            snapshot.matrix_data,
            x_column,
            y_column,
            matrix.method,
            statistics=pair_statistics[x_column, y_column],
        )
        captions = scatter_captions(detail, labels)
        heading = labels.scatter_heading.format(x=x_column, y=y_column)

        def build_scatter(
            figure: Figure, detail: CorrelationPairDetail = detail, captions: tuple[str, ...] = captions
        ) -> None:
            ax = figure.add_subplot(111)
            if detail.error is None:
                draw_correlation_scatter(ax, detail)
            else:
                ax.set_axis_off()
                ax.text(0.5, 0.5, captions[0], ha="center", va="center", wrap=True, transform=ax.transAxes)

        render(heading, build_scatter, captions)
    return tuple(images)
