"""Qt-free, bounded PNG rendering that reserves space for actual chart content."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from io import BytesIO
from itertools import pairwise
from typing import TYPE_CHECKING, cast

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from matplotlib.axes import Axes
    from matplotlib.axis import Axis
    from matplotlib.backend_bases import RendererBase
    from matplotlib.transforms import Bbox

    from expo_jbm329.services.analysis.chart_layout import ChartFigure

_MINIMUM_LAYOUT_FRACTION = 0.05
_LAYOUT_REFERENCE_DPI = 100.0


def _edge_growth(lower: float, upper: float, size: float) -> float:
    """Estimate growth while avoiding overshoot for mostly off-canvas labels."""
    anchor = (lower + upper) / (2 * size)
    centered = upper - lower <= size / 2 and _MINIMUM_LAYOUT_FRACTION <= anchor <= 1 - _MINIMUM_LAYOUT_FRACTION
    near_scale = anchor if centered else 1.0
    far_scale = 1 - anchor if centered else 1.0
    return max(0.0, -lower / near_scale, (upper - size) / far_scale)


@dataclass(frozen=True, slots=True)
class ChartRaster:
    """Owned PNG bytes and their actual encoded pixel dimensions."""

    image_data: bytes
    width_px: int
    height_px: int


def _tick_boxes(axis: Axis, renderer: RendererBase) -> list[Bbox]:
    """Measure only visible ticks inside the axis's current viewport."""
    if not axis.get_visible():
        return []
    lower, upper = sorted(axis.get_view_interval())
    return [
        label.get_window_extent(renderer)
        for ticks in (axis.get_major_ticks(), axis.get_minor_ticks())
        for tick in ticks
        if lower <= tick.get_loc() <= upper
        for label in (tick.label1, tick.label2)
        if label.get_visible() and label.get_text().strip()
    ]


def _overlap_growth(boxes: list[Bbox], *, horizontal: bool, gap: float) -> float:
    """Find the spacing multiplier needed without dropping or shrinking ticks."""
    ordered = sorted(boxes, key=lambda box: box.x0 if horizontal else box.y0)
    growth = 1.0
    for previous, current in pairwise(ordered):
        if horizontal:
            intersects = current.y0 < previous.y1 and previous.y0 < current.y1
            distance = (current.x0 + current.x1 - previous.x0 - previous.x1) / 2
            required = (previous.width + current.width) / 2 + gap
        else:
            intersects = current.x0 < previous.x1 and previous.x0 < current.x1
            distance = (current.y0 + current.y1 - previous.y0 - previous.y1) / 2
            required = (previous.height + current.height) / 2 + gap
        if intersects and distance > 0 and required > distance:
            growth = max(growth, required / distance)
    return growth


def _content_boxes(figure: ChartFigure, renderer: RendererBase) -> list[Bbox]:
    """Include decorations omitted by layout-only tight bounding boxes."""
    boxes: list[Bbox] = []
    for axis in figure.axes:
        if not axis.get_visible():
            continue
        tight = axis.get_tightbbox(renderer)
        if tight is not None:
            boxes.append(tight)
        for artist in (*axis.texts, *axis.get_default_bbox_extra_artists()):
            if artist.get_visible():
                extent = artist.get_tightbbox(renderer)
                if extent is not None:
                    boxes.append(extent)
    for artist in (*figure.texts, *figure.legends, *figure.artists):
        if artist.get_visible():
            extent = artist.get_tightbbox(renderer)
            if extent is not None:
                boxes.append(extent)
    return [box for box in boxes if all(math.isfinite(value) for value in box.extents)]


def _plot_axes(figure: ChartFigure) -> list[Axes]:
    """Exclude colorbar strips and text-only panels from minimum data areas."""
    return [
        axis
        for axis in figure.axes
        if axis.get_visible()
        and axis.axison
        and getattr(axis, "_colorbar", None) is None
        and not (axis.tables and not axis.has_data())
    ]


def _minimum_plot_size(figure: ChartFigure) -> tuple[float, float]:
    """Convert logical plot-area minimums to the active renderer's pixels."""
    config = figure.config.content_layout
    scale = figure.dpi / _LAYOUT_REFERENCE_DPI
    return config.minimum_plot_width_px * scale, config.minimum_plot_height_px * scale


def measure_chart_growth(
    figure: ChartFigure,
    renderer: RendererBase,
    minimums: Mapping[Axes, tuple[float, float]] | None = None,
) -> tuple[float, float]:
    """Measure extra renderer pixels needed by the current, already drawn chart.

    This read-only operation is shared with live canvases. Returned values are
    additional width and height, before the configured safety padding is added.
    Colorbars participate in clipping checks but not minimum plot dimensions.
    Optional per-axis minimums are renderer pixels; otherwise configured
    physical plot minimums are converted for the current figure DPI.
    """
    resolved_minimums = dict.fromkeys(_plot_axes(figure), _minimum_plot_size(figure)) if minimums is None else minimums
    return _measure_growth(figure, renderer, resolved_minimums)


def required_chart_size(
    figure: ChartFigure,
    renderer: RendererBase,
) -> tuple[float, float]:
    """Return the content's requested figure size in inches without mutations.

    Call this after drawing so rotations and tick extents are current. The
    returned size never shrinks the current figure and includes safety padding
    only on dimensions requiring growth. Minimum data-panel area is physical
    (1.2 inches by default), independent of renderer DPI or Qt's device ratio.
    Callers must apply configured size limits and schedule any resize outside
    drawing; repeated measurements can be needed after layout redistributes space.

    Args:
        figure: Already drawn chart with captured immutable configuration.
        renderer: Renderer that drew the current figure.

    Returns:
        Requested width and height in inches.
    """
    extra_width, extra_height = measure_chart_growth(figure, renderer)
    config = figure.config.content_layout
    width, height = figure.bbox.width, figure.bbox.height
    return (
        (width + extra_width + config.padding_px) / figure.dpi
        if extra_width > config.tolerance_px
        else width / figure.dpi,
        (height + extra_height + config.padding_px) / figure.dpi
        if extra_height > config.tolerance_px
        else height / figure.dpi,
    )


def _measure_growth(
    figure: ChartFigure,
    renderer: RendererBase,
    minimums: Mapping[Axes, tuple[float, float]],
) -> tuple[float, float]:
    """Measure clipping, data-panel collapse and remaining tick collisions."""
    width, height = figure.bbox.width, figure.bbox.height
    boxes = _content_boxes(figure, renderer)
    extra_width = extra_height = 0.0
    for box in boxes:
        # Edge-panel titles move outward when the figure grows. Account for
        # their anchor's motion rather than repeatedly adding a tiny deficit.
        extra_width = max(extra_width, _edge_growth(box.x0, box.x1, width))
        extra_height = max(extra_height, _edge_growth(box.y0, box.y1, height))
    for axis, (minimum_width, minimum_height) in minimums.items():
        box = axis.get_window_extent(renderer)
        subplot = axis.get_subplotspec()
        fraction = subplot.get_position(figure) if subplot is not None else axis.get_position()
        extra_width = max(extra_width, (minimum_width - box.width) / max(fraction.width, _MINIMUM_LAYOUT_FRACTION))
        extra_height = max(extra_height, (minimum_height - box.height) / max(fraction.height, _MINIMUM_LAYOUT_FRACTION))
        gap = cast("float", renderer.points_to_pixels(figure.config.overlap_gap_points))
        x_growth = _overlap_growth(_tick_boxes(axis.xaxis, renderer), horizontal=True, gap=gap)
        y_growth = _overlap_growth(_tick_boxes(axis.yaxis, renderer), horizontal=False, gap=gap)
        extra_width = max(extra_width, width * (x_growth - 1))
        extra_height = max(extra_height, height * (y_growth - 1))
    return extra_width, extra_height


def render_chart_png(
    figure: ChartFigure,
    *,
    check_cancelled: Callable[[], None] | None = None,
) -> ChartRaster:
    """Render all decorations and tick labels within a bounded Agg raster.

    Existing geometry remains exact when it already fits. Otherwise the figure
    grows, height first for vertical labels and width for remaining tick
    collisions. Layout engines get fresh renderer measurements at every size;
    fonts, ticks, chart data and global Matplotlib defaults are never changed.
    The caller retains responsibility for its existing Matplotlib lock.

    Args:
        figure: Worker-owned figure with frozen content layout configuration.
        check_cancelled: Optional callback raising the caller's cancellation error.

    Returns:
        Frozen PNG bytes with dimensions read from the PNG header.

    Raises:
        ValueError: If content cannot fit within the configured raster limits.
    """
    config = figure.config.content_layout
    canvas = FigureCanvasAgg(figure)
    initial_width, initial_height = canvas.get_width_height()
    minimum_width, minimum_height = _minimum_plot_size(figure)
    minimums = {
        axis: (
            min(minimum_width, axis.get_position().width * initial_width),
            min(minimum_height, axis.get_position().height * initial_height),
        )
        for axis in _plot_axes(figure)
    }
    for _ in range(config.max_passes):
        if check_cancelled is not None:
            check_cancelled()
        width, height = canvas.get_width_height()
        if width > config.max_width_px or height > config.max_height_px or width * height > config.max_pixels:
            break
        # Constrained layout can collapse before sufficient label space exists.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="constrained_layout not applied.*", category=UserWarning)
            canvas.draw()  # type: ignore[no-untyped-call]
            canvas.draw()  # type: ignore[no-untyped-call]
        renderer = canvas.get_renderer()  # type: ignore[no-untyped-call]
        extra_width, extra_height = measure_chart_growth(figure, renderer, minimums)
        tolerance = config.tolerance_px
        if extra_width <= tolerance and extra_height <= tolerance:
            output = BytesIO()
            # Encode the verified renderer directly: print_png would draw again.
            pixels = canvas.buffer_rgba()  # type: ignore[no-untyped-call]
            Image.fromarray(np.asarray(pixels)).save(output, "PNG")
            data = output.getvalue()
            return ChartRaster(data, int.from_bytes(data[16:20]), int.from_bytes(data[20:24]))
        if figure.get_layout_engine() is None:
            figure.set_layout_engine("constrained")
        new_width = math.ceil(width + max(0.0, extra_width) + (config.padding_px if extra_width > tolerance else 0))
        new_height = math.ceil(height + max(0.0, extra_height) + (config.padding_px if extra_height > tolerance else 0))
        if (
            new_width > config.max_width_px
            or new_height > config.max_height_px
            or new_width * new_height > config.max_pixels
        ):
            break
        figure.set_size_inches(new_width / figure.dpi, new_height / figure.dpi, forward=False)
    message = "Chart content cannot fit within the configured PNG layout limits."
    raise ValueError(message)
