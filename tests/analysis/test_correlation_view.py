from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QSplitter

from expo_jbm329.gui.dialogs.analysis.correlation_view import MAX_ANNOTATED_COLUMNS, CorrelationView
from expo_jbm329.gui.dialogs.analysis.statistics_view import SerializedAnalysisCanvas
from expo_jbm329.services.analysis.correlation import (
    SCATTER_SAMPLE_SIZE,
    CorrelationError,
    CorrelationMatrixResult,
    CorrelationMethod,
    CorrelationStrength,
    analyze_correlation_matrix,
    analyze_correlation_pair,
)
from tests.analysis.test_statistics_view import _worker_holds_chart_lock


@pytest.fixture(autouse=True)
def _flush_deferred_draws():
    yield
    # Matplotlib canvases schedule a deferred draw_idle(); flush it while
    # the view is still alive.
    QApplication.processEvents()


def _frame(size: int = 40, columns: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    base = rng.normal(size=size)
    return pd.DataFrame({f"c{i}": base * i + rng.normal(size=size) for i in range(columns)})


def _matrix(df: pd.DataFrame, method: CorrelationMethod = CorrelationMethod.PEARSON) -> CorrelationMatrixResult:
    result = analyze_correlation_matrix(df, method=method)
    assert result is not None
    return result


def _flush_deletes() -> None:
    """Run pending deleteLater() calls, which processEvents() alone doesn't."""
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def _labels_text(widget) -> str:
    return "\n".join(label.text() for label in widget.findChildren(QLabel))


def _canvas_axes(widget):
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

    return [canvas.figure.axes[0] for canvas in widget.findChildren(FigureCanvasQTAgg)]


def _scatter_axes(view: CorrelationView):
    return [axis for axis in _canvas_axes(view.pair_panel()) if axis.get_xlabel()]


def test_ranking_caption_shares_the_tables_shaded_panel():
    view = CorrelationView(_matrix(_frame()), None)
    table = view.table()
    assert table is not None
    panel = table.parentWidget()
    assert isinstance(panel, QFrame)
    assert panel.frameShape() is QFrame.Shape.NoFrame
    assert panel.autoFillBackground()
    assert panel.backgroundRole() is QPalette.ColorRole.Button
    caption = next(label for label in panel.findChildren(QLabel) if label.text().startswith("Pairs are ranked"))
    assert panel.layout().itemAt(0).widget() is table
    assert panel.layout().itemAt(1).widget() is caption
    assert caption.wordWrap()
    assert caption.textFormat() is Qt.TextFormat.PlainText
    assert view.pair_panel().isAncestorOf(caption) is False


@pytest.mark.parametrize("with_pair", [False, True])
def test_correlation_plots_header_gap_stays_fixed_when_section_grows(with_pair):
    df = _frame()
    detail = analyze_correlation_pair(df, "c0", "c1") if with_pair else None
    view = CorrelationView(_matrix(df), detail)
    panel = view.pair_panel().findChild(QSplitter).widget(0)
    panel.setParent(None)
    panel.resize(1100, 500)
    panel.show()
    try:
        QApplication.processEvents()
        layout = panel.layout()
        heading = layout.itemAt(0).widget()
        charts = layout.itemAt(1).widget()
        gap = charts.y() - heading.geometry().bottom()
        heading_height = heading.height()
        chart_height = charts.height()
        panel.resize(1100, 800)
        QApplication.processEvents()
        assert heading.height() == heading_height
        assert charts.y() - heading.geometry().bottom() == gap
        assert charts.height() > chart_height
        assert layout.stretch(1) == 1
    finally:
        panel.close()
        panel.deleteLater()
        view.close()


@pytest.mark.parametrize("with_error", [False, True])
def test_pair_details_header_and_text_stay_at_top_when_section_grows(with_error):
    df = _frame()
    if with_error:
        df["c0"] = 1.0
    detail = analyze_correlation_pair(df, "c0", "c1")
    view = CorrelationView(_matrix(df), detail)
    panel = view.pair_panel().findChild(QSplitter).widget(1)
    panel.setParent(None)
    panel.resize(1100, 500)
    panel.show()
    try:
        QApplication.processEvents()
        layout = panel.layout()
        heading = layout.itemAt(0).widget()
        text_panel = layout.itemAt(1).widget()
        label = text_panel.findChild(QLabel)
        gap = text_panel.y() - heading.geometry().bottom()
        heading_geometry = (heading.y(), heading.height())
        text_geometry = (text_panel.y(), text_panel.height(), label.y(), label.height())
        assert heading.y() == layout.contentsMargins().top()
        assert label.alignment() == Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        panel.resize(1100, 800)
        QApplication.processEvents()
        assert (heading.y(), heading.height()) == heading_geometry
        assert text_panel.y() - heading.geometry().bottom() == gap
        assert (text_panel.y(), text_panel.height(), label.y(), label.height()) == text_geometry
    finally:
        panel.close()
        panel.deleteLater()
        view.close()


def test_correlation_canvases_defer_matrix_and_scatter_mutations_without_blocking():
    df = _frame()
    result = _matrix(df)
    detail = analyze_correlation_pair(df, "c0", "c1")
    with _worker_holds_chart_lock():
        view = CorrelationView(result, detail)
        canvases = view.findChildren(SerializedAnalysisCanvas)
        assert len(canvases) == 2
        assert all(not canvas.figure.axes for canvas in canvases)
        QApplication.processEvents()
        assert all(not canvas.figure.axes for canvas in canvases)
    for canvas in canvases:
        canvas._retry_render()
    assert sorted(len(canvas.figure.axes) for canvas in canvases) == [1, 2]
    view.deleteLater()


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


def test_matrix_error_shows_only_the_message():
    result = _matrix(pd.DataFrame({"a": [1.0, 2.0, 3.0]}))
    view = CorrelationView(result, None)

    assert result.error is CorrelationError.NOT_ENOUGH_NUMERIC_COLUMNS
    assert view.table() is None
    assert view.findChildren(QSplitter) == []
    assert "at least 2 numeric columns" in _labels_text(view)
    assert view.pair_panel().isHidden()


@pytest.mark.parametrize("error", list(CorrelationError))
def test_every_error_has_a_message(error):
    view = CorrelationView(_matrix(_frame()), None)

    assert view.error_text(error)


def test_set_pair_detail_on_an_error_view_does_not_fail():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    view = CorrelationView(_matrix(df), None)

    view.set_pair_detail(analyze_correlation_pair(df, "a", "b"))

    assert view.pair_detail() is not None


# ----------------------------------------------------------------------
# Heatmap and table
# ----------------------------------------------------------------------


def test_heatmap_is_annotated_for_small_matrices():
    view = CorrelationView(_matrix(_frame()), None)
    (heatmap,) = _canvas_axes(view)

    assert len(heatmap.texts) == 9
    assert "Pearson" in heatmap.get_title()


def test_heatmap_is_not_annotated_for_large_matrices():
    view = CorrelationView(_matrix(_frame(columns=MAX_ANNOTATED_COLUMNS + 1)), None)
    (heatmap,) = _canvas_axes(view)

    assert len(heatmap.texts) == 0


def test_heatmap_skips_undefined_cells():
    df = _frame()
    df["k"] = 1.0
    view = CorrelationView(_matrix(df), None)
    (heatmap,) = _canvas_axes(view)

    assert len(heatmap.texts) == 9  # the constant column's row/column/diagonal are NaN


def test_table_lists_every_pair_in_ranked_order():
    result = _matrix(_frame())
    view = CorrelationView(result, None)
    table = view.table()

    assert table is not None
    assert table.rowCount() == 3
    for row, pair in enumerate(result.pairs):
        assert table.item(row, 0).text() == pair.x_column
        assert table.item(row, 1).text() == pair.y_column
        assert table.item(row, 6).text() == str(pair.n)


@pytest.mark.parametrize(
    ("method", "symbol"),
    [(CorrelationMethod.PEARSON, "r"), (CorrelationMethod.SPEARMAN, "rho"), (CorrelationMethod.KENDALL, "tau")],
)
def test_table_coefficient_header_matches_the_method(method, symbol):
    view = CorrelationView(_matrix(_frame(), method), None)
    table = view.table()

    assert table is not None
    assert table.horizontalHeaderItem(2).text() == symbol
    assert view.method() is method


def test_significant_pairs_are_marked_and_undefined_values_show_na():
    df = _frame(size=200)
    df["k"] = 1.0
    result = _matrix(df)
    view = CorrelationView(result, None)
    table = view.table()

    assert table is not None
    assert table.item(0, 5).text().endswith(" *")
    last = table.rowCount() - 1
    assert table.item(last, 3).text() == "N/A"
    assert table.item(last, 7).text() == "N/A"
    assert not table.item(last, 5).text().endswith("*")


def test_clicking_and_activating_rows_updates_selected_pair_before_emitting():
    result = _matrix(_frame())
    view = CorrelationView(result, None)
    received: list[tuple[tuple[str, str] | None, tuple[str, str]]] = []
    view.pair_activated.connect(lambda x, y: received.append((view.selected_pair(), (x, y))))
    table = view.table()
    assert table is not None

    assert view.selected_pair() is None
    table.cellClicked.emit(1, 0)
    table.cellActivated.emit(2, 0)
    table.cellActivated.emit(99, 0)

    first_pair = (result.pairs[1].x_column, result.pairs[1].y_column)
    second_pair = (result.pairs[2].x_column, result.pairs[2].y_column)
    assert received == [(first_pair, first_pair), (second_pair, second_pair)]
    assert view.selected_pair() == second_pair
    assert [index.row() for index in table.selectionModel().selectedRows()] == [2]


def test_select_pair_activates_and_highlights_the_canonical_table_pair():
    result = _matrix(_frame())
    view = CorrelationView(result, None)
    received: list[tuple[str, str]] = []
    view.pair_activated.connect(lambda x, y: received.append((x, y)))

    pair = result.pairs[1]
    view.select_pair(pair.y_column, pair.x_column)

    table = view.table()
    assert table is not None
    assert view.selected_pair() == (pair.x_column, pair.y_column)
    assert received == [(pair.x_column, pair.y_column)]
    assert [index.row() for index in table.selectionModel().selectedRows()] == [1]


def test_select_pair_raises_when_the_pair_has_no_table_row():
    view = CorrelationView(_matrix(_frame()), None)

    with pytest.raises(ValueError, match="row in the displayed correlation matrix"):
        view.select_pair("missing-x", "missing-y")


@pytest.mark.parametrize(
    ("strength", "text"),
    [
        (None, "N/A"),
        (CorrelationStrength.NEGLIGIBLE, "Negligible"),
        (CorrelationStrength.WEAK, "Weak"),
        (CorrelationStrength.MODERATE, "Moderate"),
        (CorrelationStrength.STRONG, "Strong"),
    ],
)
def test_strength_text(strength, text):
    view = CorrelationView(_matrix(_frame()), None)

    assert view.strength_text(strength) == text


# ----------------------------------------------------------------------
# Pair detail
# ----------------------------------------------------------------------


def test_initial_pair_detail_is_shown_and_its_row_selected():
    df = _frame()
    result = _matrix(df)
    pair = result.pairs[1]
    detail = analyze_correlation_pair(df, pair.y_column, pair.x_column)
    view = CorrelationView(result, detail)
    table = view.table()

    assert view.pair_detail() is detail
    assert view.selected_pair() == (pair.y_column, pair.x_column)
    assert table is not None
    assert [index.row() for index in table.selectionModel().selectedRows()] == [1]
    assert len(_canvas_axes(view)) == 2
    (scatter,) = _scatter_axes(view)
    assert scatter.get_xlabel() == pair.y_column
    assert len(scatter.lines) == 1
    assert "Least-squares line" in _labels_text(view.pair_panel())


def test_layout_places_table_above_side_by_side_charts_and_statistics_below():
    df = _frame()
    view = CorrelationView(_matrix(df), analyze_correlation_pair(df, "c0", "c1"))

    splitters = view.findChildren(QSplitter)
    vertical = [splitter for splitter in splitters if splitter.orientation() is Qt.Orientation.Vertical]
    horizontal = [splitter for splitter in splitters if splitter.orientation() is Qt.Orientation.Horizontal]
    assert len(vertical) == 2
    assert len(horizontal) == 1
    assert all(not splitter.childrenCollapsible() for splitter in splitters)

    root = next(splitter for splitter in vertical if splitter.parent() is view)
    detail = next(splitter for splitter in vertical if splitter.parent() is view.pair_panel())
    table = view.table()
    assert table is not None
    assert root.widget(0).isAncestorOf(table)
    assert "Strongest correlations" in _labels_text(root.widget(0))

    charts = horizontal[0]
    assert len(_canvas_axes(charts)) == 2
    assert "Correlation plots" in _labels_text(detail.widget(0))

    statistics = next(label for label in view.pair_panel().findChildren(QLabel) if "Least-squares line" in label.text())
    assert detail.widget(1).isAncestorOf(statistics)
    assert "Pair details" in _labels_text(detail.widget(1))
    assert not charts.isAncestorOf(statistics)


def test_set_pair_detail_replaces_the_pair_panel_content():
    df = _frame()
    result = _matrix(df)
    view = CorrelationView(result, analyze_correlation_pair(df, "c0", "c1"))

    detail = analyze_correlation_pair(df, "c1", "c2")
    view.set_pair_detail(detail)
    _flush_deletes()

    assert view.selected_pair() == (detail.pair.x_column, detail.pair.y_column)
    scatters = _scatter_axes(view)
    assert len(scatters) == 1
    assert scatters[0].get_xlabel() == "c1"


def test_pair_error_shows_message_and_clears_selection_for_unknown_pair():
    df = _frame()
    view = CorrelationView(_matrix(df), analyze_correlation_pair(df, "c0", "c1"))

    detail = analyze_correlation_pair(df, "c0", "c0")
    view.set_pair_detail(detail)
    _flush_deletes()

    table = view.table()
    assert table is not None
    assert view.selected_pair() == (detail.pair.x_column, detail.pair.y_column)
    assert table.selectionModel().selectedRows() == []
    assert _scatter_axes(view) == []
    assert "different numeric columns" in _labels_text(view.pair_panel())


def test_rank_methods_note_that_the_line_is_linear():
    df = _frame()
    view = CorrelationView(
        _matrix(df, CorrelationMethod.SPEARMAN),
        analyze_correlation_pair(df, "c0", "c1", CorrelationMethod.SPEARMAN),
    )

    assert "monotonic" in _labels_text(view.pair_panel())


def test_pearson_has_no_linear_line_note():
    df = _frame()
    view = CorrelationView(_matrix(df), analyze_correlation_pair(df, "c0", "c1"))

    assert "monotonic" not in _labels_text(view.pair_panel())


def test_sampled_pair_shows_sampling_caption():
    df = _frame(size=SCATTER_SAMPLE_SIZE + 10, columns=2)
    view = CorrelationView(_matrix(df), analyze_correlation_pair(df, "c0", "c1"))

    assert "random sample" in _labels_text(view.pair_panel())


def test_unsampled_pair_has_no_sampling_caption():
    df = _frame()
    view = CorrelationView(_matrix(df), analyze_correlation_pair(df, "c0", "c1"))

    assert "random sample" not in _labels_text(view.pair_panel())


def test_column_names_are_html_escaped_in_the_statistics():
    df = _frame().rename(columns={"c0": "<b>x</b>"})
    view = CorrelationView(_matrix(df), analyze_correlation_pair(df, "<b>x</b>", "c1"))

    assert "&lt;b&gt;x&lt;/b&gt;" in _labels_text(view.pair_panel())


def test_small_p_value_is_html_escaped_in_the_statistics():
    df = pd.DataFrame({"x": range(20), "y": range(20)})
    view = CorrelationView(_matrix(df), analyze_correlation_pair(df, "x", "y"))

    text = _labels_text(view.pair_panel())
    assert "p = &lt; " in text
    assert "p = < " not in text
