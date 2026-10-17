"""Shared Qt-free correlation plots and worker-owned Excel images."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

import numpy as np

from expo_jbm329.services.analysis.chart_config import AxisPolicy, AxisRole, RotationMode
from expo_jbm329.services.analysis.chart_export import render_chart_png
from expo_jbm329.services.analysis.chart_layout import ChartFigure as Figure
from expo_jbm329.services.analysis.chart_presentation import (
    DEFAULT_CHART_NUMERIC_LOCALE,
    DEFAULT_WORKSHEET_HEADING,
    ChartNumericLocale,
    ChartPresentationMetadata,
)
from expo_jbm329.services.analysis.chart_profiles import (
    CORRELATION_ANNOTATION_FONT_SIZE,
    CORRELATION_CHART_PROFILE,
    CORRELATION_MATRIX_PREFERRED_ROTATION,
)
from expo_jbm329.services.analysis.correlation import (
    MIN_OBSERVATIONS,
    CorrelationError,
    CorrelationMethod,
    analyze_correlation_pair,
)
from expo_jbm329.services.analysis.correlation_export import CorrelationExportComponent
from expo_jbm329.services.analysis.presentation import (
    PresentationLabel,
    correlation_method_label,
    translate_presentation_label,
)
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


@dataclass(frozen=True, slots=True)
class CorrelationMatrixPresentation:
    """Shared matrix title, cell annotations and output metadata."""

    title: str
    annotations: tuple[tuple[str, ...], ...]
    metadata: ChartPresentationMetadata


@dataclass(frozen=True, slots=True)
class CorrelationPairPresentation:
    """Shared pair title, actual column axes, unavailable state and captions."""

    title: str
    x_label: str
    y_label: str
    unavailable_message: str | None
    metadata: ChartPresentationMetadata


def build_correlation_chart_labels(
    result: CorrelationMatrixResult,
    translate: Callable[[str, str], str],
    numeric_locale: ChartNumericLocale = DEFAULT_CHART_NUMERIC_LOCALE,
) -> CorrelationChartLabels:
    """Capture translated templates and canonical app precision for later rendering.

    Args:
        result: Applied matrix whose ordered cells will be annotated.
        translate: Translation callback, called only while building these labels.
        numeric_locale: Numeric separators captured before worker dispatch.

    Returns:
        Frozen labels with Qt-free formatters for pair details computed later.
    """
    return CorrelationChartLabels(
        matrix_title=translate_presentation_label(PresentationLabel.CORRELATION_MATRIX, translate),
        scatter_heading=translate_presentation_label(PresentationLabel.SCATTERPLOT_TITLE, translate),
        line_equation=translate("AnalysisExportDialog", "Least-squares line: y = ({slope}) x + ({intercept})"),
        descriptive_line=translate(
            "CorrelationView",
            "The line is a linear fit shown for reference. {method} measures monotonic, "
            "not necessarily linear, association.",
        ).format(method=correlation_method_label(result.method, translate)),
        sampling=translate(
            "CorrelationView", "Showing a random sample of {shown} of {total} points. Statistics use all points."
        ),
        insufficient_observations=translate(
            "CorrelationView",
            "Fewer than {minimum} rows have values in both columns, so no correlation can be computed.",
        ).format(minimum=numeric_locale.count(MIN_OBSERVATIONS)),
        constant_input=translate(
            "CorrelationView",
            "At least one of the columns is constant over the rows with values in both, "
            "so no correlation can be computed.",
        ),
        number_format=numeric_locale.number,
        count_format=numeric_locale.count,
        matrix_annotations=tuple(
            tuple(numeric_locale.number(value, precision=2) for value in row) for row in result.coefficients
        ),
    )


def build_correlation_matrix_presentation(labels: CorrelationChartLabels) -> CorrelationMatrixPresentation:
    """Build matrix semantics without repeating the plotted title outside the image."""
    return CorrelationMatrixPresentation(
        labels.matrix_title,
        labels.matrix_annotations,
        ChartPresentationMetadata(worksheet_heading=DEFAULT_WORKSHEET_HEADING, accessible_name=labels.matrix_title),
    )


def build_correlation_pair_presentation(
    detail: CorrelationPairDetail, labels: CorrelationChartLabels
) -> CorrelationPairPresentation:
    """Build pair semantics, retaining explanatory notes but no repeated pair heading."""
    title = labels.scatter_heading.format(x=detail.pair.x_column, y=detail.pair.y_column)
    captions = scatter_captions(detail, labels)
    return CorrelationPairPresentation(
        title,
        detail.pair.x_column,
        detail.pair.y_column,
        captions[0] if detail.error is not None else None,
        ChartPresentationMetadata(
            worksheet_heading=DEFAULT_WORKSHEET_HEADING, accessible_name=title, captions=captions
        ),
    )


def draw_correlation_matrix(
    figure: Figure,
    ax: Axes,
    result: CorrelationMatrixResult,
    presentation: CorrelationMatrixPresentation,
) -> None:
    """Draw the applied matrix with the GUI's fixed scale and annotation rules."""
    coefficients = np.asarray(result.coefficients, dtype=float)
    image = ax.imshow(coefficients, cmap="RdBu_r", vmin=-1.0, vmax=1.0)
    figure.colorbar(image, ax=ax)
    labels = list(result.columns)
    ax.set_xticks(range(len(labels)), labels=labels, rotation=CORRELATION_MATRIX_PREFERRED_ROTATION)
    if isinstance(figure, Figure):
        figure.configure_axis(ax, AxisPolicy(role=AxisRole.CATEGORICAL, rotation_mode=RotationMode.VERTICAL))
    ax.set_yticks(range(len(labels)), labels=labels)
    ax.set_title(presentation.title)
    if len(labels) <= MAX_ANNOTATED_COLUMNS:
        for (row, column), value in np.ndenumerate(coefficients):
            if math.isfinite(value):
                ax.text(
                    column,
                    row,
                    presentation.annotations[row][column] if presentation.annotations else format(float(value), ".2g"),
                    ha="center",
                    va="center",
                    fontsize=CORRELATION_ANNOTATION_FONT_SIZE,
                    color="white" if abs(value) > _LIGHT_TEXT_THRESHOLD else "black",
                )


def draw_correlation_scatter(
    ax: Axes, detail: CorrelationPairDetail, presentation: CorrelationPairPresentation
) -> None:
    """Draw the pair title, deterministic sample and full-cohort line or explicit error."""
    ax.set_title(presentation.title)
    ax.set_xlabel(presentation.x_label)
    ax.set_ylabel(presentation.y_label)
    if presentation.unavailable_message is not None:
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(0.5, 0.5, presentation.unavailable_message, ha="center", va="center", wrap=True, transform=ax.transAxes)
        return
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

    def render(metadata: ChartPresentationMetadata, builder: Callable[[Figure], None]) -> None:
        check_cancel()
        with STATISTICS_CHART_LOCK:
            check_cancel()
            geometry = CORRELATION_CHART_PROFILE.geometry
            figure = Figure(
                figsize=geometry.figsize,
                dpi=geometry.dpi,
                constrained_layout=geometry.constrained_layout,
            )
            try:
                builder(figure)
                raster = render_chart_png(figure, check_cancelled=check_cancel)
            finally:
                figure.clear()
        check_cancel()
        images.append(
            ExcelChartImage(
                metadata.worksheet_heading,
                raster.image_data,
                raster.width_px,
                raster.height_px,
                metadata.captions,
                metadata.accessible_name,
            )
        )
        if progress_cb is not None:
            progress_cb(len(images) * 100 // total)

    if include_matrix:
        matrix_presentation = build_correlation_matrix_presentation(labels)
        render(
            matrix_presentation.metadata,
            lambda figure: draw_correlation_matrix(figure, figure.add_subplot(111), matrix, matrix_presentation),
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
        presentation = build_correlation_pair_presentation(detail, labels)

        def build_scatter(
            figure: Figure,
            detail: CorrelationPairDetail = detail,
            presentation: CorrelationPairPresentation = presentation,
        ) -> None:
            ax = figure.add_subplot(111)
            draw_correlation_scatter(ax, detail, presentation)

        render(presentation.metadata, build_scatter)
    return tuple(images)
