from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QSplitter

from expo_jbm329.gui.dialogs.analysis.correlation_view import MAX_ANNOTATED_COLUMNS, CorrelationView
from expo_jbm329.services.analysis.correlation import (
    SCATTER_SAMPLE_SIZE,
    CorrelationError,
    CorrelationMatrixResult,
    CorrelationMethod,
    CorrelationStrength,
    analyze_correlation_matrix,
    analyze_correlation_pair,
)


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


def test_clicking_a_row_emits_pair_activated():
    result = _matrix(_frame())
    view = CorrelationView(result, None)
    received: list[tuple[str, str]] = []
    view.pair_activated.connect(lambda x, y: received.append((x, y)))

    view._on_cell_activated(1, 0)  # noqa: SLF001
    view._on_cell_activated(99, 0)  # noqa: SLF001 - out of range is ignored

    assert received == [(result.pairs[1].x_column, result.pairs[1].y_column)]


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

    view.set_pair_detail(analyze_correlation_pair(df, "c1", "c2"))
    _flush_deletes()

    scatters = _scatter_axes(view)
    assert len(scatters) == 1
    assert scatters[0].get_xlabel() == "c1"


def test_pair_error_shows_message_and_clears_selection_for_unknown_pair():
    df = _frame()
    view = CorrelationView(_matrix(df), analyze_correlation_pair(df, "c0", "c1"))

    view.set_pair_detail(analyze_correlation_pair(df, "c0", "c0"))
    _flush_deletes()

    table = view.table()
    assert table is not None
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
