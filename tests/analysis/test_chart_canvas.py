from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PyQt6 import sip
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.analysis.pca_view import PCAView
from expo_jbm329.gui.dialogs.analysis.section_layout import build_section_scroll_area
from expo_jbm329.gui.dialogs.column_properties_dialog import ColumnPropertiesDialog
from expo_jbm329.gui.widgets import analysis_chart_canvas
from expo_jbm329.gui.widgets.analysis_chart_canvas import SerializedAnalysisCanvas
from expo_jbm329.services.analysis import chart_layout
from expo_jbm329.services.analysis.chart_config import AxisPolicy, ChartConfig, ChartContentLayoutConfig, RotationMode
from expo_jbm329.services.analysis.chart_layout import ChartFigure
from expo_jbm329.services.analysis.pca import analyze_pca
from expo_jbm329.services.data_operations.dtypes import SemanticDType
from expo_jbm329.services.data_profile.column_data_profile import ColumnProfile, PlotSpec
from tests.analysis.test_statistics_view import _worker_holds_chart_lock


def _column_dialog(labels: list[str]) -> tuple[QWidget, ColumnPropertiesDialog]:
    parent = QWidget()
    profile = ColumnProfile(
        name="Categories",
        semantic_dtype=SemanticDType.STRING,
        storage_dtype="string",
        plot=PlotSpec(kind="bar_topn", labels=labels, counts=[1] * len(labels)),
    )
    return parent, ColumnPropertiesDialog(parent, profile, None)


def test_column_properties_uses_adaptive_figure_and_shared_canvas():
    labels = [f"Category {index:02d}" for index in range(12)]
    parent, dialog = _column_dialog(labels)
    try:
        canvas = dialog.findChild(SerializedAnalysisCanvas)
        assert canvas is not None
        assert isinstance(canvas.figure, ChartFigure)
        canvas.figure.set_size_inches(5, 3)
        canvas.draw()
        axis = canvas.figure.axes[0]
        assert [label.get_text() for label in axis.get_xticklabels()] == labels
        assert all(label.get_rotation() == 90 for label in axis.get_xticklabels())
        assert len(axis.patches) == len(labels)
    finally:
        sip.delete(parent)


@pytest.mark.parametrize(
    "plot",
    [
        PlotSpec(kind="hist", bins=[0, 1, 3], counts=[4, 2]),
        PlotSpec(kind="bar_weekday", labels=["Mon", "Tue"], counts=[4, 2]),
        PlotSpec(kind="bar_bool", labels=["True", "False"], counts=[4, 2]),
    ],
)
def test_other_column_plot_kinds_preserve_bar_values(plot):
    parent = QWidget()
    profile = ColumnProfile("Values", SemanticDType.INT, "int64", plot=plot)
    dialog = ColumnPropertiesDialog(parent, profile, None)
    try:
        canvas = dialog.findChild(SerializedAnalysisCanvas)
        assert canvas is not None
        assert isinstance(canvas.figure, ChartFigure)
        canvas.draw()
        axis = canvas.figure.axes[0]
        assert [bar.get_height() for bar in axis.patches] == [4, 2]
        if plot.kind == "hist":
            assert [bar.get_width() for bar in axis.patches] == [1, 2]
        else:
            assert [label.get_text() for label in axis.get_xticklabels()] == plot.labels
    finally:
        sip.delete(parent)


def test_column_chart_build_and_draw_defer_while_worker_owns_renderer():
    with _worker_holds_chart_lock():
        parent, dialog = _column_dialog(["First", "Second"])
        canvas = dialog.findChild(SerializedAnalysisCanvas)
        assert canvas is not None
        assert canvas.figure.axes == []
        canvas.draw()
        assert canvas._draw_pending
        assert canvas._retry_timer.isActive()
    try:
        canvas._retry_timer.timeout.emit()
        assert len(canvas.figure.axes) == 1
        assert len(canvas.figure.axes[0].patches) == 2
    finally:
        sip.delete(parent)


def test_live_charts_capture_central_defaults_without_mutable_configuration(monkeypatch):
    config = ChartConfig(default_axis_policy=AxisPolicy(rotation_mode=RotationMode.VERTICAL))
    monkeypatch.setattr(chart_layout, "DEFAULT_CHART_CONFIG", config)
    parent, dialog = _column_dialog(["First", "Second"])
    try:
        canvas = dialog.findChild(SerializedAnalysisCanvas)
        assert canvas is not None
        assert canvas.figure.config is config
        monkeypatch.setattr(chart_layout, "DEFAULT_CHART_CONFIG", ChartConfig())
        canvas.draw()
        assert all(label.get_rotation() == 90 for label in canvas.figure.axes[0].get_xticklabels())
    finally:
        sip.delete(parent)


def test_pca_chart_construction_uses_the_shared_nonblocking_canvas():
    result = analyze_pca(pd.DataFrame({"a": [1, 2, 3, 4], "b": [1, 4, 2, 8]}), standardize=True)
    assert result.error is None
    with _worker_holds_chart_lock():
        view = PCAView(result)
        canvases = view.findChildren(SerializedAnalysisCanvas)
        assert len(canvases) == 2
        assert all(isinstance(canvas.figure, ChartFigure) for canvas in canvases)
        assert all(canvas.figure.axes == [] for canvas in canvases)
    try:
        for canvas in canvases:
            canvas._retry_timer.timeout.emit()
            assert len(canvas.figure.axes) == 1
    finally:
        sip.delete(view)


@pytest.mark.parametrize("width", [3, 10])
def test_qt_and_png_layout_agree_for_the_same_geometry(width):
    labels = [f"Group {index:02d}" for index in range(10)]

    def figure() -> ChartFigure:
        result = ChartFigure(figsize=(width, 4), dpi=100, constrained_layout=True)
        axis = result.add_subplot()
        axis.bar(range(len(labels)), [1] * len(labels))
        axis.set_xticks(range(len(labels)), labels)
        return result

    live = figure()
    canvas = SerializedAnalysisCanvas(live)
    exported = figure()
    try:
        canvas.draw()
        output = BytesIO()
        FigureCanvasAgg(exported).print_png(output)
        assert output.getvalue().startswith(b"\x89PNG")
        live_labels = live.axes[0].get_xticklabels()
        export_labels = exported.axes[0].get_xticklabels()
        assert [label.get_rotation() for label in live_labels] == [label.get_rotation() for label in export_labels]
        for live_label, export_label in zip(live_labels, export_labels, strict=True):
            assert live_label.get_window_extent().bounds == pytest.approx(export_label.get_window_extent().bounds)
    finally:
        sip.delete(canvas)


def test_live_long_vertical_labels_request_scrollable_height_after_draw(qt_app):
    figure = ChartFigure(
        figsize=(6, 3),
        dpi=100,
        constrained_layout=True,
        config=ChartConfig(default_axis_policy=AxisPolicy(rotation_mode=RotationMode.VERTICAL)),
    )
    axis = figure.add_subplot()
    labels = [f"Category {index}: " + "measurement name " * 3 for index in range(5)]
    axis.bar(range(5), [1] * 5)
    axis.set_xticks(range(5), labels)
    canvas = SerializedAnalysisCanvas(figure)
    parent = QWidget()
    layout = QVBoxLayout(parent)
    scroll = build_section_scroll_area(canvas, parent)
    layout.addWidget(scroll)
    parent.resize(600, 250)
    parent.show()
    try:
        for _ in range(8):
            qt_app.processEvents()
            canvas.draw()
            canvas._content_size_timer.timeout.emit()
        assert canvas.minimumHeight() > 250
        assert scroll.verticalScrollBar().maximum() > 0
        renderer = canvas.get_renderer()
        for label in axis.get_xticklabels():
            box = label.get_window_extent(renderer)
            assert box.y0 >= -1
            assert box.y1 <= figure.bbox.height + 1
        assert axis.get_window_extent(renderer).height >= figure.config.content_layout.minimum_plot_height_px - 1
    finally:
        sip.delete(parent)


def test_live_size_change_is_deferred_and_rebuilt_charts_release_old_minimum():
    figure = ChartFigure(
        figsize=(5, 2),
        constrained_layout=True,
        config=ChartConfig(default_axis_policy=AxisPolicy(rotation_mode=RotationMode.VERTICAL)),
    )
    axis = figure.add_subplot()
    axis.bar([0], [1])
    axis.set_xticks([0], ["Very long category label " * 3])
    canvas = SerializedAnalysisCanvas(figure)
    canvas.setMinimumSize(100, 100)
    try:
        canvas.draw()
        assert canvas.minimumHeight() == 100
        assert canvas._content_size_timer.isActive()
        canvas._content_size_timer.timeout.emit()
        assert canvas.minimumHeight() > 100
        figure.clear()
        figure.add_subplot().plot([1, 2], [1, 2])
        canvas.draw()
        canvas._content_size_timer.timeout.emit()
        assert canvas.minimumWidth() == canvas.minimumHeight() == 100
    finally:
        sip.delete(canvas)


def test_content_size_timer_is_destroyed_with_canvas():
    figure = ChartFigure(figsize=(5, 2), constrained_layout=True)
    axis = figure.add_subplot()
    axis.set_xticks([0, 1], ["Long label " * 8, "Another long label " * 6], rotation=90)
    canvas = SerializedAnalysisCanvas(figure)
    canvas.draw()
    timer = canvas._content_size_timer
    assert timer.isActive()
    sip.delete(canvas)
    assert sip.isdeleted(timer)


def test_live_content_limit_is_logged_without_raising_from_qt_draw(caplog):
    figure = ChartFigure(
        figsize=(5, 2),
        constrained_layout=True,
        config=ChartConfig(
            content_layout=ChartContentLayoutConfig(max_height_px=250),
            default_axis_policy=AxisPolicy(rotation_mode=RotationMode.VERTICAL),
        ),
    )
    axis = figure.add_subplot()
    axis.set_xticks([0], ["Very long measurement name " * 6])
    canvas = SerializedAnalysisCanvas(figure)
    try:
        canvas.draw()
        canvas.draw()
        assert not canvas._content_size_timer.isActive()
        assert caplog.text.count("Chart content exceeds configured live canvas layout limits") == 1
    finally:
        sip.delete(canvas)


def test_new_fitting_draw_cancels_an_obsolete_queued_growth_request(monkeypatch):
    figure = ChartFigure(figsize=(6, 4), constrained_layout=True)
    figure.add_subplot().plot([1, 2], [1, 2])
    canvas = SerializedAnalysisCanvas(figure)
    canvas.setMinimumSize(100, 100)
    sizes = iter([(0.0, 100.0), (0.0, 0.0)])
    monkeypatch.setattr(analysis_chart_canvas, "measure_chart_growth", lambda *_args: next(sizes))
    try:
        canvas.draw()
        assert canvas._content_size_timer.isActive()
        canvas.draw()
        assert not canvas._content_size_timer.isActive()
        assert canvas.minimumHeight() == 100
    finally:
        sip.delete(canvas)


def _settle_canvas(canvas: SerializedAnalysisCanvas, qt_app: QApplication) -> None:
    """Drain deferred layout work and assert it reaches a stable minimum."""
    for _ in range(12):
        qt_app.processEvents()
        canvas.draw()
        qt_app.processEvents()
    minimum = canvas.minimumSize()
    for _ in range(3):
        canvas.draw()
        qt_app.processEvents()
        assert canvas.minimumSize() == minimum
    assert not canvas._content_size_timer.isActive()


def test_updating_labels_on_existing_axes_releases_content_minimum(qt_app: QApplication) -> None:
    figure = ChartFigure(
        figsize=(5, 3),
        dpi=100,
        constrained_layout=True,
        config=ChartConfig(default_axis_policy=AxisPolicy(rotation_mode=RotationMode.VERTICAL)),
    )
    axis = figure.add_subplot()
    axis.bar([0, 1], [1, 2])
    axis.set_xticks([0, 1], ["Measurement category " * 4, "Second category " * 4])
    canvas = SerializedAnalysisCanvas(figure)
    canvas.setMinimumSize(100, 100)
    canvas.show()
    try:
        _settle_canvas(canvas, qt_app)
        assert canvas.minimumHeight() > 300
        canvas.build_chart(lambda: axis.set_xticks([0, 1], ["A", "B"]))
        _settle_canvas(canvas, qt_app)
        assert canvas.minimumWidth() == canvas.minimumHeight() == 100
        assert figure.axes == [axis]
    finally:
        sip.delete(canvas)


def test_widening_releases_rotated_label_height_and_repeated_resizes_settle(qt_app: QApplication) -> None:
    figure = ChartFigure(figsize=(4, 3), dpi=100, constrained_layout=True)
    axis = figure.add_subplot()
    names = [f"Measurement category {index}" for index in range(5)]
    axis.bar(names, range(5))
    canvas = SerializedAnalysisCanvas(figure)
    canvas.setMinimumSize(100, 100)
    parent = QWidget()
    layout = QVBoxLayout(parent)
    scroll = build_section_scroll_area(canvas, parent)
    layout.addWidget(scroll)
    parent.resize(350, 260)
    parent.show()
    try:
        for _ in range(2):
            _settle_canvas(canvas, qt_app)
            assert canvas.minimumHeight() > 260
            assert scroll.verticalScrollBar().maximum() > 0
            assert all(label.get_rotation() == 90 for label in axis.get_xticklabels())
            with _worker_holds_chart_lock():
                parent.resize(1600, 400)
                qt_app.processEvents()
                canvas.draw()
                assert canvas._draw_pending
                assert canvas._retry_timer.isActive()
            _settle_canvas(canvas, qt_app)
            assert canvas.minimumWidth() == canvas.minimumHeight() == 100
            assert scroll.verticalScrollBar().maximum() == 0
            assert all(label.get_rotation() == 0 for label in axis.get_xticklabels())
            parent.resize(350, 260)
    finally:
        sip.delete(parent)


@pytest.mark.parametrize("ratio", [1, 2])
def test_content_minimum_converts_renderer_growth_to_logical_pixels(
    monkeypatch: pytest.MonkeyPatch, ratio: int
) -> None:
    figure = ChartFigure(figsize=(5, 3), dpi=100, constrained_layout=True)
    figure.add_subplot().plot([0, 1], [0, 1])
    canvas = SerializedAnalysisCanvas(figure)
    canvas._set_device_pixel_ratio(ratio)
    canvas.setMinimumSize(100, 100)
    monkeypatch.setattr(analysis_chart_canvas, "measure_chart_growth", lambda *_args: (0.0, 100.0 * ratio))
    try:
        canvas.draw()
        canvas._content_size_timer.timeout.emit()
        assert canvas.minimumWidth() == 100
        assert canvas.minimumHeight() == pytest.approx(400, abs=4)
    finally:
        sip.delete(canvas)


def test_live_content_iteration_limit_remains_bounded(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    figure = ChartFigure(
        figsize=(5, 3),
        dpi=100,
        constrained_layout=True,
        config=ChartConfig(content_layout=ChartContentLayoutConfig(max_passes=2)),
    )
    figure.add_subplot().plot([0, 1], [0, 1])
    canvas = SerializedAnalysisCanvas(figure)
    monkeypatch.setattr(analysis_chart_canvas, "measure_chart_growth", lambda *_args: (0.0, 100.0))
    try:
        for _ in range(6):
            canvas.draw()
            canvas._content_size_timer.stop()
            canvas._apply_content_minimum()
        assert canvas._content_resize_passes == 2
        assert not canvas._content_size_timer.isActive()
        assert caplog.text.count("Chart content did not fit within the live canvas layout iteration limit") == 1
    finally:
        sip.delete(canvas)
