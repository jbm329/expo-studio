from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FixedLocator

from expo_jbm329.services.analysis.chart_config import AxisPolicy, AxisRole, ChartConfig, RotationMode
from expo_jbm329.services.analysis.chart_layout import ChartFigure


def render(figure: ChartFigure) -> FigureCanvasAgg:
    """Draw a ChartFigure through a real Agg renderer."""
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    return canvas


def add_category_axis(
    figure: ChartFigure,
    labels: list[str],
    *,
    rotation: float = 0.0,
    position: int = 111,
):
    axis = figure.add_subplot(position)
    axis.set_xticks(range(len(labels)), labels)
    axis.tick_params(axis="x", labelrotation=rotation)
    return axis


def test_auto_rotation_preserves_preferred_angle_when_labels_fit_and_rotates_when_crowded():
    wide = ChartFigure(figsize=(12, 4), dpi=100)
    wide_axis = add_category_axis(wide, ["Alpha", "Beta", "Gamma"], rotation=30)
    render(wide)
    assert [label.get_rotation() for label in wide_axis.get_xticklabels()] == [30.0] * 3
    vertical_axis = add_category_axis(wide, ["Small", "Set"], rotation=90, position=212)
    render(wide)
    assert [label.get_rotation() for label in vertical_axis.get_xticklabels()] == [90.0] * 2

    narrow = ChartFigure(figsize=(3, 3), dpi=100, constrained_layout=True)
    narrow_axis = add_category_axis(narrow, ["A long category", "Another long category", "Third long category"])
    canvas = render(narrow)
    assert [label.get_rotation() for label in narrow_axis.get_xticklabels()] == [90.0] * 3
    assert len(narrow_axis.get_xticklabels()) == 3
    extents = [label.get_window_extent(canvas.get_renderer()) for label in narrow_axis.get_xticklabels()]
    assert all(current.x0 >= previous.x1 for previous, current in pairwise(extents))


def test_resize_and_dpi_changes_recompute_from_the_preferred_angle():
    figure = ChartFigure(figsize=(3, 3), dpi=100, constrained_layout=True)
    axis = add_category_axis(
        figure,
        ["Alpha long category", "Beta long category", "Gamma long category"],
        rotation=30,
    )

    render(figure)
    assert [label.get_rotation() for label in axis.get_xticklabels()] == [90.0] * 3

    figure.set_size_inches(12, 4)
    render(figure)
    assert [label.get_rotation() for label in axis.get_xticklabels()] == [30.0] * 3

    figure.set_size_inches(3, 3)
    figure.set_dpi(160)
    render(figure)
    assert [label.get_rotation() for label in axis.get_xticklabels()] == [90.0] * 3


def test_resize_restores_preferred_alignment_and_rotation_mode():
    figure = ChartFigure(figsize=(3, 3), constrained_layout=True)
    axis = add_category_axis(figure, ["Alpha long category", "Beta long category", "Gamma long category"])
    labels = axis.get_xticklabels()
    for label in labels:
        label.set_horizontalalignment("right")
        label.set_rotation_mode("anchor")

    render(figure)
    assert [label.get_rotation() for label in axis.get_xticklabels()] == [90.0] * 3

    figure.set_size_inches(12, 4)
    render(figure)
    assert [label.get_rotation() for label in axis.get_xticklabels()] == [0.0] * 3
    assert [label.get_horizontalalignment() for label in axis.get_xticklabels()] == ["right"] * 3
    assert [label.get_rotation_mode() for label in axis.get_xticklabels()] == ["anchor"] * 3


def test_explicit_rotation_policies_override_auto_measurement():
    figure = ChartFigure(figsize=(2, 2))
    horizontal_axis = add_category_axis(figure, ["long label", "another long label"], position=211)
    vertical_axis = add_category_axis(figure, ["long label", "another long label"], position=212)
    fixed_axis = figure.add_subplot(223)
    fixed_axis.set_xticks([0, 1], ["long label", "another long label"])
    excluded_axis = figure.add_subplot(224)
    excluded_axis.set_xticks([0, 1], ["long label", "another long label"])

    figure.configure_axis(horizontal_axis, AxisPolicy(rotation_mode=RotationMode.HORIZONTAL))
    figure.configure_axis(vertical_axis, AxisPolicy(rotation_mode=RotationMode.VERTICAL))
    figure.configure_axis(fixed_axis, AxisPolicy(rotation_mode=RotationMode.FIXED, fixed_rotation_degrees=37.5))
    figure.configure_axis(excluded_axis, AxisPolicy(role=AxisRole.EXCLUDED))

    render(figure)
    assert [label.get_rotation() for label in horizontal_axis.get_xticklabels()] == [0.0, 0.0]
    assert [label.get_rotation() for label in vertical_axis.get_xticklabels()] == [90.0, 90.0]
    assert [label.get_rotation() for label in fixed_axis.get_xticklabels()] == [37.5, 37.5]
    assert [label.get_rotation() for label in excluded_axis.get_xticklabels()] == [0.0, 0.0]


def test_forced_vertical_is_applied_before_first_layout(monkeypatch):
    figure = ChartFigure(figsize=(3, 5), constrained_layout=True)
    axis = add_category_axis(figure, [f"{'L' * 39}{index}" for index in range(3)])
    figure.configure_axis(axis, AxisPolicy(rotation_mode=RotationMode.VERTICAL))
    rotations_at_draw = []
    original_draw = Figure.draw

    def record_draw(self, renderer):
        rotations_at_draw.append([label.get_rotation() for label in axis.get_xticklabels()])
        original_draw(self, renderer)

    monkeypatch.setattr(Figure, "draw", record_draw)
    render(figure)

    assert rotations_at_draw == [[90.0] * 3]


def test_multiple_panels_measure_final_layout_without_demoting_promoted_labels():
    figure = ChartFigure(figsize=(6, 5), constrained_layout=True)
    top = figure.add_subplot(211)
    bottom = figure.add_subplot(212)
    top.set_xticks(range(6), [f"Top category {index}" for index in range(6)])
    bottom.set_xticks(range(4), [f"Bottom category {index} with long text" for index in range(4)])
    canvas = render(figure)
    renderer = canvas.get_renderer()

    for axis in (top, bottom):
        labels = axis.get_xticklabels()
        extents = [label.get_window_extent(renderer) for label in labels]
        assert all(current.x0 >= previous.x1 for previous, current in pairwise(extents))
        assert all(bounds.y0 >= -1 and bounds.y1 <= figure.bbox.height + 1 for bounds in extents)
    assert all(label.get_rotation() == 90 for label in bottom.get_xticklabels())


def test_colorbar_hidden_and_unavailable_axes_are_not_modified():
    figure = ChartFigure(figsize=(4, 3))
    heatmap_axis = figure.add_subplot(121)
    image = heatmap_axis.imshow([[0, 1], [1, 0]])
    colorbar = figure.colorbar(image, ax=heatmap_axis)
    colorbar_axis = colorbar.ax
    colorbar_axis.set_xticks([0, 1], ["color label", "another color label"])
    colorbar_axis.tick_params(axis="x", labelrotation=17)
    unavailable_axis = figure.add_subplot(122)
    unavailable_axis.set_xticks([0, 1], ["unavailable", "hidden labels"])
    unavailable_axis.set_axis_off()

    render(figure)

    assert [label.get_rotation() for label in colorbar_axis.get_xticklabels()] == [17.0, 17.0]
    assert [label.get_rotation() for label in unavailable_axis.get_xticklabels()] == [0.0, 0.0]


@pytest.mark.parametrize("hidden_part", ["axes", "xaxis"])
def test_hidden_axes_do_not_change_label_rotation(hidden_part):
    figure = ChartFigure(figsize=(2, 2))
    axis = add_category_axis(figure, ["A very long label", "Another very long label"])
    if hidden_part == "axes":
        axis.set_visible(False)
    else:
        axis.xaxis.set_visible(False)
    render(figure)
    assert all(label.get_rotation() == 0 for label in axis.get_xticklabels())


def test_out_of_view_ticks_do_not_trigger_rotation():
    figure = ChartFigure(figsize=(3, 3))
    axis = add_category_axis(figure, ["Short", "Outside viewport " * 20, "Another outside label " * 20])
    axis.set_xlim(-0.1, 0.1)
    render(figure)

    assert all(label.get_rotation() == 0 for label in axis.get_xticklabels())
    assert len(axis.get_xticklabels()) == 3


def test_top_and_bottom_labels_do_not_collide_across_different_rows():
    figure = ChartFigure(figsize=(6, 3), constrained_layout=True)
    axis = add_category_axis(figure, ["One", "Two", "Three"])
    axis.tick_params(axis="x", labeltop=True, labelbottom=True)
    render(figure)

    assert len(axis.get_xticklabels()) == 6
    assert all(label.get_rotation() == 0 for label in axis.get_xticklabels())


def test_shared_axes_and_tick_formatting_are_preserved():
    figure = ChartFigure(figsize=(4, 4), constrained_layout=True)
    top = figure.add_subplot(211)
    bottom = figure.add_subplot(212, sharex=top)
    top.set_xticks(range(4), ["first long label", "second long label", "third long label", "fourth long label"])
    top.tick_params(axis="x", labelbottom=False, labelrotation=17)
    locator = FixedLocator(range(4))
    bottom.xaxis.set_major_locator(locator)
    bottom.tick_params(axis="x", labelrotation=30)

    render(figure)

    assert top.get_xticklabels() == []
    assert [tick.label1.get_rotation() for tick in top.xaxis.get_major_ticks()] == [17.0] * 4
    assert bottom.xaxis.get_major_locator() is locator
    assert [label.get_text() for label in bottom.get_xticklabels()] == [
        "first long label",
        "second long label",
        "third long label",
        "fourth long label",
    ]
    assert [label.get_rotation() for label in bottom.get_xticklabels()] == [90.0] * 4


def test_repeated_rendering_is_stable_and_clear_prunes_axis_state():
    figure = ChartFigure(figsize=(3, 3), constrained_layout=True)
    axis = add_category_axis(figure, ["Alpha category", "Beta category", "Gamma category"], rotation=30)

    for _ in range(4):
        render(figure)
        assert [label.get_rotation() for label in axis.get_xticklabels()] == [90.0] * 3

    figure.clear()
    assert figure._axis_layout == {}

    rebuilt_axis = add_category_axis(figure, ["One", "Two", "Three"], rotation=0)
    render(figure)
    assert [label.get_rotation() for label in rebuilt_axis.get_xticklabels()] == [0.0] * 3


def test_extreme_density_keeps_all_ticks_even_when_vertical_labels_still_overlap():
    figure = ChartFigure(figsize=(1.2, 2), dpi=100)
    labels = [f"Category {index:03} with deliberately long text" for index in range(30)]
    axis = add_category_axis(figure, labels)
    canvas = render(figure)
    extents = [label.get_window_extent(canvas.get_renderer()) for label in axis.get_xticklabels()]

    assert len(axis.get_xticklabels()) == len(labels)
    assert all(label.get_rotation() == 90.0 for label in axis.get_xticklabels())
    assert any(current.x0 < previous.x1 for previous, current in pairwise(extents))


def test_config_and_standard_figure_options():
    figure = ChartFigure(
        figsize=(6, 4),
        dpi=90,
        facecolor="white",
        edgecolor="black",
        linewidth=1.5,
        frameon=True,
        layout="none",
        config=ChartConfig(),
        label="configured chart",
    )
    axis = add_category_axis(figure, ["A", "B"])
    render(figure)

    assert figure.get_size_inches().tolist() == [6.0, 4.0]
    assert figure.dpi == 90
    assert figure.get_label() == "configured chart"
    assert axis.figure is figure


def test_configure_axis_rejects_axes_from_another_figure():
    figure = ChartFigure()
    other_axis = Figure().add_subplot()

    with pytest.raises(ValueError, match="belong to this figure"):
        figure.configure_axis(other_axis)


def test_final_render_keeps_rotated_labels_inside_constrained_figure_bounds():
    figure = ChartFigure(figsize=(3, 3), dpi=100, constrained_layout=True)
    axis = add_category_axis(figure, ["A substantially long category", "Another substantial category"])
    canvas = render(figure)
    renderer = canvas.get_renderer()

    assert [label.get_rotation() for label in axis.get_xticklabels()] == [90.0, 90.0]
    for label in axis.get_xticklabels():
        bounds = label.get_window_extent(renderer)
        assert bounds.x0 >= -1
        assert bounds.x1 <= figure.bbox.width + 1
        assert bounds.y0 >= -1
        assert bounds.y1 <= figure.bbox.height + 1


def test_constrained_layout_recovers_bounds_after_long_horizontal_labels():
    labels = [f"{'L' * 39}{index}" for index in range(3)]
    figure = ChartFigure(figsize=(3, 5), dpi=100, constrained_layout=True)
    axis = add_category_axis(figure, labels)
    with pytest.warns(UserWarning, match="axes sizes collapsed"):
        canvas = render(figure)
    renderer = canvas.get_renderer()

    assert [label.get_rotation() for label in axis.get_xticklabels()] == [90.0] * 3
    assert axis.bbox.width > 0
    assert axis.bbox.height > 0
    for label in axis.get_xticklabels():
        bounds = label.get_window_extent(renderer)
        assert bounds.x0 >= -1
        assert bounds.x1 <= figure.bbox.width + 1
        assert bounds.y0 >= -1
        assert bounds.y1 <= figure.bbox.height + 1


def test_renderer_clear_prevents_old_label_pixels_on_transparent_redraw():
    labels = ["One long category label", "Another long category label", "Final long category label"]

    adaptive = ChartFigure(figsize=(4, 3), dpi=100)
    adaptive.patch.set_alpha(0)
    adaptive_axis = add_category_axis(adaptive, labels)
    adaptive_canvas = render(adaptive)
    assert [label.get_rotation() for label in adaptive_axis.get_xticklabels()] == [90.0] * 3

    reference = ChartFigure(figsize=(4, 3), dpi=100)
    reference.patch.set_alpha(0)
    reference_axis = add_category_axis(reference, labels)
    for label in reference_axis.get_xticklabels():
        label.set_rotation(90)
    reference_canvas = FigureCanvasAgg(reference)
    reference_canvas.draw()

    np.testing.assert_array_equal(
        np.asarray(adaptive_canvas.buffer_rgba()),
        np.asarray(reference_canvas.buffer_rgba()),
    )


def test_draw_does_not_require_renderer_clear_method():
    class RendererWithoutClear:
        clear = None

        def __init__(self, renderer):
            self._renderer = renderer

        def __getattr__(self, name):
            return getattr(self._renderer, name)

    figure = ChartFigure(figsize=(2, 2))
    add_category_axis(figure, ["A long label", "Another long label"])
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    figure.draw(RendererWithoutClear(canvas.get_renderer()))
