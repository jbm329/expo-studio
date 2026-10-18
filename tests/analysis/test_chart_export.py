"""Renderer-level coverage for content-aware PNG export."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from itertools import pairwise

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image

from expo_jbm329.services.analysis.chart_config import (
    AxisPolicy,
    ChartConfig,
    ChartContentLayoutConfig,
    RotationMode,
)
from expo_jbm329.services.analysis.chart_export import measure_chart_growth, render_chart_png, required_chart_size
from expo_jbm329.services.analysis.chart_layout import ChartFigure


def assert_inside(figure):
    renderer = figure.canvas.get_renderer()
    width, height = figure.canvas.get_width_height()
    for axis in figure.axes:
        ticks = [
            label
            for dimension in (axis.xaxis, axis.yaxis)
            for tick in dimension.get_major_ticks()
            if min(dimension.get_view_interval()) <= tick.get_loc() <= max(dimension.get_view_interval())
            for label in (tick.label1, tick.label2)
        ]
        for label in (*ticks, axis.xaxis.label, axis.yaxis.label, axis.title):
            if label.get_visible() and label.get_text():
                box = label.get_window_extent(renderer)
                assert box.x0 >= -1
                assert box.y0 >= -1
                assert box.x1 <= width + 1
                assert box.y1 <= height + 1
        assert axis.get_window_extent(renderer).height >= 119


def test_normal_dimensions_and_frozen_actual_png_size():
    figure = ChartFigure(figsize=(9, 3.5), dpi=120, constrained_layout=True)
    axis = figure.add_subplot()
    axis.plot([1, 2, 3], [3, 4, 2])
    axis.set(xlabel="Value", ylabel="Count", title="Distribution")
    raster = render_chart_png(figure)
    assert (raster.width_px, raster.height_px) == (1080, 420)
    with Image.open(BytesIO(raster.image_data)) as image:
        assert image.size == (raster.width_px, raster.height_px)
    with pytest.raises(FrozenInstanceError):
        raster.width_px = 1
    assert_inside(figure)


def test_png_preserves_verified_renderer_rgba_pixels() -> None:
    figure = ChartFigure(figsize=(4, 3), dpi=100, constrained_layout=True)
    figure.patch.set_alpha(0)
    axis = figure.add_subplot()
    axis.plot([0, 1], [1, 0], color="red", linewidth=4)
    raster = render_chart_png(figure)
    expected = np.asarray(figure.canvas.buffer_rgba()).copy()
    with Image.open(BytesIO(raster.image_data)) as image:
        assert image.mode == "RGBA"
        np.testing.assert_array_equal(np.asarray(image), expected)


@pytest.mark.parametrize("count,length", [(12, 90), (100, 25), (12, 250), (12, 600)])
def test_crowded_categories_keep_every_label_and_font_size(count, length):
    figure = ChartFigure(figsize=(9, 3.5), dpi=120, constrained_layout=True)
    axis = figure.add_subplot()
    names = [f"{index:03d} " + "Long name " * (length // 10) for index in range(count)]
    axis.bar(names, range(count))
    axis.set(xlabel="Category", ylabel="Count", title="All categories")
    fontsize = axis.get_xticklabels()[0].get_fontsize()
    raster = render_chart_png(figure)
    assert raster.height_px > 420
    if count == 100:
        assert raster.width_px > 1080
    labels = axis.get_xticklabels()
    assert [label.get_text() for label in labels] == names
    assert all(label.get_fontsize() == fontsize for label in labels)
    boxes = sorted((label.get_window_extent(figure.canvas.get_renderer()) for label in labels), key=lambda box: box.x0)
    assert all(left.x1 <= right.x0 for left, right in pairwise(boxes))
    assert_inside(figure)


def test_multi_panel_annotations_legend_colorbar_and_figure_title():
    figure = ChartFigure(figsize=(8, 6), dpi=120, constrained_layout=True)
    upper = figure.add_subplot(211)
    lower = figure.add_subplot(212)
    upper.plot([0, 1], [0, 1], label="Observed values")
    upper.legend(loc="center left", bbox_to_anchor=(1.01, 0.5))
    upper.annotate("Outside annotation", xy=(1, 1), xytext=(1.02, 0.7), textcoords="axes fraction")
    image = lower.imshow(np.eye(5))
    figure.colorbar(image, ax=lower, label="Color scale")
    lower.set_xticks(range(5), ["Long category " * 15] * 5)
    figure.suptitle("Figure title " * 12)
    raster = render_chart_png(figure)
    assert raster.height_px >= 720
    assert_inside(figure)
    renderer = figure.canvas.get_renderer()
    artists = [*figure.texts, *upper.texts, upper.get_legend()]
    for artist in artists:
        box = artist.get_window_extent(renderer)
        assert box.x0 >= -1 and box.y0 >= -1
        assert box.x1 <= raster.width_px + 1 and box.y1 <= raster.height_px + 1


def test_four_long_label_panels_fit_without_collapsed_fraction_overshoot():
    figure = ChartFigure(figsize=(9, 6), dpi=100, constrained_layout=True)
    for index in range(4):
        axis = figure.add_subplot(2, 2, index + 1)
        axis.bar([f"{category}: " + "Long name " * 9 for category in range(12)], range(12))

    raster = render_chart_png(figure)

    assert raster.height_px < 3000
    assert raster.width_px <= 1800
    assert_inside(figure)


def test_explicit_fixed_horizontal_policy_grows_width_instead_of_rotating():
    figure = ChartFigure(figsize=(4, 3), dpi=100, constrained_layout=True)
    axis = figure.add_subplot()
    axis.bar(["Category one", "Category two", "Category three", "Category four"], [1, 2, 3, 4])
    figure.configure_axis(axis, AxisPolicy(rotation_mode=RotationMode.HORIZONTAL))
    raster = render_chart_png(figure)
    assert raster.width_px > 400
    assert all(label.get_rotation() == 0 for label in axis.get_xticklabels())
    assert_inside(figure)


def test_bounded_failure_is_explicit_and_does_not_encode_clipped_png():
    config = ChartConfig(content_layout=ChartContentLayoutConfig(max_width_px=500, max_height_px=400))
    figure = ChartFigure(figsize=(4, 3), dpi=100, constrained_layout=True, config=config)
    axis = figure.add_subplot()
    axis.bar(["Category " * 200, "Other category " * 200], [1, 2])
    with pytest.raises(ValueError, match="cannot fit.*limits"):
        render_chart_png(figure)


def test_cancellation_between_growth_passes():
    figure = ChartFigure(figsize=(4, 3), dpi=100, constrained_layout=True)
    figure.add_subplot().bar(["Long label " * 40] * 2, [1, 2])
    calls = []

    def check():
        calls.append(True)
        if len(calls) == 2:
            raise InterruptedError

    with pytest.raises(InterruptedError):
        render_chart_png(figure, check_cancelled=check)
    assert len(calls) == 2


@pytest.mark.parametrize("dpi", [100, 200])
def test_required_size_is_physical_and_does_not_mutate_figure(dpi):
    figure = ChartFigure(figsize=(5, 3), dpi=dpi, constrained_layout=True)
    axis = figure.add_subplot()
    axis.bar([f"{index}: " + "Long category " * 6 for index in range(8)], range(8))
    canvas = FigureCanvasAgg(figure)
    with pytest.warns(UserWarning, match="constrained_layout not applied"):
        canvas.draw()
    original_size = figure.get_size_inches().copy()
    original_position = axis.get_position().bounds
    required_width, required_height = required_chart_size(figure, canvas.get_renderer())
    assert required_width >= 5
    assert required_height > 3
    assert np.array_equal(figure.get_size_inches(), original_size)
    assert axis.get_position().bounds == original_position


def test_required_size_preserves_fitting_chart_and_skips_table_and_axis_off_minimums():
    figure = ChartFigure(figsize=(9, 3.5), dpi=120, constrained_layout=True)
    axis = figure.add_subplot(131)
    axis.plot([1, 2], [2, 3])
    table_axis = figure.add_axes((0.5, 0.5, 0.1, 0.1))
    table_axis.set_xticks([])
    table_axis.set_yticks([])
    table_axis.table(cellText=[["A"]], loc="center")
    off_axis = figure.add_axes((0.7, 0.5, 0.1, 0.1))
    off_axis.set_axis_off()
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    assert required_chart_size(figure, canvas.get_renderer()) == pytest.approx((9, 3.5))


def test_growth_measurement_accepts_explicit_renderer_pixel_minimums():
    figure = ChartFigure(figsize=(5, 3), dpi=100, constrained_layout=True)
    axis = figure.add_subplot()
    axis.plot([1, 2], [2, 3])
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    renderer = canvas.get_renderer()
    assert measure_chart_growth(figure, renderer, {}) == (0, 0)
    extra_width, extra_height = measure_chart_growth(figure, renderer, {axis: (500, 400)})
    assert extra_width > 0
    assert extra_height > 0


def test_hidden_axis_labels_do_not_trigger_export_growth():
    figure = ChartFigure(figsize=(6, 3), dpi=100, constrained_layout=True)
    axis = figure.add_subplot()
    axis.plot([0, 1], [0, 1])
    axis.set_xticks([0, 0.001, 0.002], ["Hidden extremely long label " * 20] * 3)
    axis.xaxis.set_visible(False)
    axis.set_yticks([0, 0.001, 0.002], ["Hidden extremely long label " * 20] * 3)
    axis.yaxis.set_visible(False)

    raster = render_chart_png(figure)

    assert (raster.width_px, raster.height_px) == (600, 300)
    assert measure_chart_growth(figure, figure.canvas.get_renderer()) == (0, 0)


@pytest.mark.parametrize("kwargs", [{"max_passes": 0}, {"max_pixels": -1}, {"padding_px": float("nan")}])
def test_content_configuration_rejects_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        ChartContentLayoutConfig(**kwargs)
