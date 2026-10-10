from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QSplitter, QTableWidget

from expo_jbm329.gui.dialogs.analysis.outliers_view import OutliersView
from expo_jbm329.services.analysis.outliers import (
    ColumnOutlierStatus,
    OutlierColumnDetail,
    OutlierError,
    OutlierMethod,
    OutlierSummaryResult,
    analyze_outlier_column,
    analyze_outlier_summary,
)

_VALUES = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 100.0]


def _frame() -> pd.DataFrame:
    return pd.DataFrame({
        "<a>": _VALUES,
        "b": [float(i) for i in range(10)],
        "flat": [5.0] * 10,
        "t": list("abcdefghij"),
        "when": pd.date_range("2024-01-01", periods=10),
        "maybe": [None, *range(9)],
    })


def _view(
    method: OutlierMethod = OutlierMethod.IQR, column: str | None = "<a>"
) -> tuple[OutliersView, OutlierSummaryResult]:
    df = _frame()
    result = analyze_outlier_summary(df, method)
    detail = analyze_outlier_column(df, column, method) if column is not None else None
    return OutliersView(result, detail), result


def _detail(column: str = "<a>", method: OutlierMethod = OutlierMethod.IQR) -> OutlierColumnDetail:
    return analyze_outlier_column(_frame(), column, method)


@pytest.mark.parametrize("column", ["<a>", "b"])
def test_distribution_header_gap_stays_fixed_when_section_grows(column):
    view, _ = _view()
    view.set_column_detail(_detail(column))
    panel = view._chart_panel  # noqa: SLF001
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
def test_column_details_content_stays_at_top_with_fixed_heading_gap(with_error):
    view, _ = _view()
    detail = _detail("b")
    if with_error:
        detail = dataclasses.replace(detail, error=OutlierError.INVALID_COLUMN)
    view.set_column_detail(detail)
    panel = view._statistics_panel  # noqa: SLF001
    panel.setParent(None)
    panel.resize(1100, 500)
    panel.show()
    try:
        QApplication.processEvents()
        layout = panel.layout()
        labels = [layout.itemAt(index).widget() for index in range(layout.count() - 1)]
        geometry = [(label.y(), label.height()) for label in labels]
        assert labels[0].y() == layout.contentsMargins().top()
        assert labels[-1].alignment() == Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        if not with_error:
            assert labels[0].text() == "Column details"
            gap = labels[1].y() - labels[0].geometry().bottom()
        panel.resize(1100, 800)
        QApplication.processEvents()
        assert [(label.y(), label.height()) for label in labels] == geometry
        if not with_error:
            assert labels[1].y() - labels[0].geometry().bottom() == gap
    finally:
        panel.close()
        panel.deleteLater()
        view.close()


def test_summary_caption_shares_the_tables_borderless_shaded_panel():
    view, _ = _view()
    table = view.table()
    assert table is not None
    panel = table.parentWidget()
    assert isinstance(panel, QFrame)
    assert panel.frameShape() is QFrame.Shape.NoFrame
    assert panel.autoFillBackground()
    assert panel.backgroundRole() is QPalette.ColorRole.Button
    caption = panel.findChild(QLabel)
    assert caption is not None
    assert panel.layout().itemAt(0).widget() is table
    assert panel.layout().itemAt(1).widget() is caption
    assert caption.text().startswith("Flagged values are potential outliers")
    assert caption.wordWrap()
    assert caption.textFormat() is Qt.TextFormat.PlainText


def _cells(table, row: int) -> list[str]:
    cells = []
    for col in range(table.columnCount()):
        item = table.item(row, col)
        assert item is not None
        cells.append(item.text())
    return cells


def _flush_deletes() -> None:
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def _record(signal) -> list:
    received: list = []
    signal.connect(lambda *args: received.append(args))
    return received


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


@pytest.mark.parametrize("error", list(OutlierError))
def test_summary_error_shows_only_its_message(error):
    result = dataclasses.replace(analyze_outlier_summary(_frame()), error=error)
    view = OutliersView(result, None)

    assert [label.text() for label in view.findChildren(QLabel)] == [view.error_text(error)]
    assert view.table() is None


def test_detail_error_shows_its_message_in_the_detail_panel():
    view, _ = _view()

    view.set_column_detail(analyze_outlier_column(_frame(), "t"))

    texts = [label.text() for label in view.detail_panel().findChildren(QLabel)]
    assert view.error_text(OutlierError.INVALID_COLUMN) in texts
    assert view.extremes_table() is None


# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------


def test_totals_describe_the_method_and_flagged_rows():
    view, result = _view()
    totals = next(label.text() for label in view.findChildren(QLabel) if "rows" in label.text())

    assert view.method_name(OutlierMethod.IQR) in totals
    assert f"of {result.row_count} rows" in totals


def test_totals_of_an_empty_dataset():
    df = pd.DataFrame({"a": pd.Series([], dtype="float64")})
    view = OutliersView(analyze_outlier_summary(df), None)

    assert any("0 of 0 rows" in label.text() for label in view.findChildren(QLabel))


def test_summary_table_lists_every_numeric_column_in_ranked_order():
    view, result = _view()
    table = view.table()

    assert table is not None
    assert table.selectionMode() is QTableWidget.SelectionMode.SingleSelection
    assert table.rowCount() == len(result.columns)
    assert [_cells(table, row)[0] for row in range(table.rowCount())] == [c.column for c in result.columns]
    first = _cells(table, 0)
    assert first[0] == "<a>"
    assert first[3] == "1"


def test_unscreenable_columns_show_their_status():
    view, result = _view(OutlierMethod.Z_SCORE)
    table = view.table()
    assert table is not None

    row = next(i for i, c in enumerate(result.columns) if c.column == "flat")

    cells = _cells(table, row)
    assert cells[3] == view.status_text(ColumnOutlierStatus.ZERO_SPREAD)
    assert cells[4:] == [""] * 5


def test_status_texts_are_distinct():
    view, _ = _view()

    assert len({view.status_text(status) for status in ColumnOutlierStatus}) == len(ColumnOutlierStatus)


def test_clicking_a_row_emits_the_column():
    view, result = _view()
    received = []
    view.column_activated.connect(
        lambda column: received.append((column, view.selected_column(), view.column_selection_revision()))
    )
    table = view.table()
    assert table is not None

    table.cellClicked.emit(1, 0)
    table.cellClicked.emit(99, 0)

    assert received == [(result.columns[1].column, result.columns[1].column, 1)]
    assert view.selected_column() == result.columns[1].column
    assert view.column_selection_revision() == 1


def test_select_column_activates_the_canonical_summary_row():
    view, result = _view(column=None)
    received = _record(view.column_activated)
    table = view.table()
    assert table is not None

    view.select_column("<a>")
    assert view.selected_column() == "<a>"
    assert view.column_selection_revision() == 1
    assert table.selectedItems()[0].row() == 0

    view.select_column("b")
    assert view.selected_column() == "b"
    assert view.column_selection_revision() == 2
    assert received == [("<a>",), ("b",)]
    assert table.selectedItems()[0].row() == 1
    assert result.columns[0].column == "<a>"


def test_select_column_rejects_a_column_missing_from_the_summary():
    view, _ = _view(column=None)

    with pytest.raises(ValueError, match="row in the displayed outlier summary"):
        view.select_column("t")

    assert view.selected_column() is None
    assert view.column_selection_revision() == 0


def test_setting_detail_updates_selected_column_without_advancing_selection_revision():
    view, _ = _view()
    assert view.selected_column() == "<a>"

    view.set_column_detail(_detail("b"))

    assert view.selected_column() == "b"
    assert view.column_selection_revision() == 0


def test_detail_highlights_its_summary_row_or_clears_the_selection():
    view, result = _view()
    table = view.table()
    assert table is not None

    assert table.selectedItems()[0].row() == 0

    view.set_column_detail(dataclasses.replace(_detail(), summary=dataclasses.replace(_detail().summary, column="x")))
    assert table.selectedItems() == []


def test_configuration_is_the_displayed_summarys():
    view, _ = _view(OutlierMethod.MODIFIED_Z_SCORE)

    assert view.configuration() == (OutlierMethod.MODIFIED_Z_SCORE, 3.5)


# ----------------------------------------------------------------------
# Detail
# ----------------------------------------------------------------------


def test_detail_shows_histogram_statistics_and_extremes():
    view, _ = _view()

    assert view.column_detail() is not None
    assert len(view.findChildren(FigureCanvasQTAgg)) == 1
    texts = [label.text() for label in view.detail_panel().findChildren(QLabel)]
    assert any("&lt;a&gt;" in text and "Q1 =" in text for text in texts)


def test_layout_has_four_vertically_resizable_sections_in_the_requested_order():
    view, _ = _view()

    splitters = view.findChildren(QSplitter)
    assert len(splitters) == 2
    assert all(splitter.orientation() is Qt.Orientation.Vertical for splitter in splitters)
    assert all(not splitter.childrenCollapsible() for splitter in splitters)

    root_splitter = next(splitter for splitter in splitters if splitter.parent() is view)
    detail_splitter = next(splitter for splitter in splitters if splitter.parent() is view.detail_panel())

    summary_table = view.table()
    extremes_table = view.extremes_table()
    assert summary_table is not None
    assert extremes_table is not None
    assert root_splitter.widget(0).isAncestorOf(summary_table)
    assert any(label.text() == "Columns" for label in root_splitter.widget(0).findChildren(QLabel))
    assert detail_splitter.widget(0).isAncestorOf(extremes_table)
    assert len(detail_splitter.widget(1).findChildren(FigureCanvasQTAgg)) == 1
    assert any(label.text() == "Distribution" for label in detail_splitter.widget(1).findChildren(QLabel))
    assert any(label.text() == "Column details" for label in detail_splitter.widget(2).findChildren(QLabel))
    assert any("threshold" in label.text() for label in detail_splitter.widget(2).findChildren(QLabel))


def test_histogram_stacks_outliers_and_marks_both_fences():
    view, _ = _view()
    canvas = view.findChildren(FigureCanvasQTAgg)[0]
    ax = canvas.figure.axes[0]

    assert len(ax.patches) == 2 * 50
    assert len(ax.lines) == 2
    assert ax.get_legend() is not None


def test_histogram_without_values_is_empty():
    view, _ = _view()
    empty = dataclasses.replace(_detail(), histogram_edges=(), inlier_counts=(), outlier_counts=())

    view.set_column_detail(empty)
    _flush_deletes()

    canvases = view.findChildren(FigureCanvasQTAgg)
    assert len(canvases) == 1
    assert len(canvases[0].figure.axes[0].patches) == 0


def test_extremes_table_lists_row_value_score_then_other_columns():
    view, _ = _view()
    table = view.extremes_table()

    assert table is not None
    assert table.selectionMode() is QTableWidget.SelectionMode.NoSelection
    headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]  # type: ignore[union-attr]
    assert headers == [view.tr("Row"), "<a>", view.score_header(OutlierMethod.IQR), "b", "flat", "t", "when", "maybe"]
    cells = _cells(table, 0)
    assert cells[0] == "10"
    assert cells[1] == "100"
    assert cells[5] == "j"
    assert cells[6].startswith("2024-01-10")


def test_missing_row_values_are_blank():
    view, _ = _view()
    detail = _detail()
    observation = dataclasses.replace(detail.extremes[0], row_values=(100.0, float("nan"), None, "x", None, None))

    view.set_column_detail(dataclasses.replace(detail, extremes=(observation,)))

    table = view.extremes_table()
    assert table is not None
    assert _cells(table, 0)[3:6] == ["", "", "x"]


def test_score_headers_are_distinct():
    view, _ = _view()

    assert len({view.score_header(method) for method in OutlierMethod}) == len(OutlierMethod)


def test_title_when_all_outliers_are_listed_or_capped():
    view, _ = _view()
    texts = [label.text() for label in view.detail_panel().findChildren(QLabel)]
    assert view.tr("<b>Potential outliers, most extreme first</b>") in texts

    detail = _detail()
    capped = dataclasses.replace(detail, summary=dataclasses.replace(detail.summary, outlier_count=500))
    view.set_column_detail(capped)
    _flush_deletes()
    texts = [label.text() for label in view.detail_panel().findChildren(QLabel)]
    assert any("of 500 potential outliers" in text for text in texts)


def test_column_without_outliers_has_no_table():
    view, _ = _view()

    view.set_column_detail(_detail("b"))
    _flush_deletes()

    texts = [label.text() for label in view.detail_panel().findChildren(QLabel)]
    assert view.tr("<b>No potential outliers</b>") in texts
    assert view.extremes_table() is None


def _statistics_text(view: OutliersView) -> str:
    _flush_deletes()
    return next(label.text() for label in view.detail_panel().findChildren(QLabel) if "threshold" in label.text())


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (ColumnOutlierStatus.ZERO_SPREAD, "All values are identical"),
        (ColumnOutlierStatus.NOT_ENOUGH_OBSERVATIONS, "At least 3 values"),
    ],
)
def test_unscreenable_detail_explains_why(status, expected):
    view, _ = _view()
    detail = _detail()

    view.set_column_detail(dataclasses.replace(detail, summary=dataclasses.replace(detail.summary, status=status)))

    text = _statistics_text(view)
    assert expected in text
    assert "Fences" not in text


def test_z_score_detail_notes_robustness_and_the_small_sample_bound():
    view, _ = _view(OutlierMethod.Z_SCORE)

    view.set_column_detail(_detail(method=OutlierMethod.Z_SCORE))

    text = _statistics_text(view)
    assert "Mean =" in text
    assert "more robust" in text
    assert "no |z| can exceed" in text  # n = 10: max |z| is 2.85 < 3


def test_z_score_detail_omits_the_bound_for_larger_samples():
    df = pd.DataFrame({"a": np.arange(100, dtype=float)})
    view = OutliersView(analyze_outlier_summary(df, OutlierMethod.Z_SCORE), None)

    view.set_column_detail(analyze_outlier_column(df, "a", OutlierMethod.Z_SCORE))

    assert "no |z| can exceed" not in _statistics_text(view)


def test_modified_z_score_detail_notes_the_mad_fallback():
    df = pd.DataFrame({"a": [1.0] * 7 + [2.0, 3.0, 50.0]})
    view = OutliersView(analyze_outlier_summary(df, OutlierMethod.MODIFIED_Z_SCORE), None)

    view.set_column_detail(analyze_outlier_column(df, "a", OutlierMethod.MODIFIED_Z_SCORE))
    text = _statistics_text(view)
    assert "MAD =" in text
    assert "mean absolute deviation is used" in text

    view.set_column_detail(analyze_outlier_column(_frame(), "<a>", OutlierMethod.MODIFIED_Z_SCORE))
    assert "mean absolute deviation is used" not in _statistics_text(view)


def test_view_without_initial_detail_has_an_empty_detail_panel():
    view, _ = _view(column=None)

    assert view.column_detail() is None
    assert view.detail_panel().findChildren(QLabel) == []


def test_detail_on_an_error_summary_has_no_row_to_select():
    result = dataclasses.replace(analyze_outlier_summary(_frame()), error=OutlierError.NO_NUMERIC_COLUMN)
    view = OutliersView(result, None)

    view.set_column_detail(_detail())

    assert view.column_detail() is not None
    assert view.table() is None
