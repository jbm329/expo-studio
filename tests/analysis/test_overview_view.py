from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QScrollArea, QSplitter, QTableWidget, QTabWidget

from expo_jbm329.gui.dialogs.analysis.overview_view import OverviewView
from expo_jbm329.gui.dialogs.analysis.section_layout import ANALYSIS_TABS_STYLE
from expo_jbm329.services.analysis.overview import (
    ColumnOverview,
    DatasetOverviewResult,
    analyze_dataset_overview,
)
from expo_jbm329.services.analysis.presentation import PresentationLabel, presentation_label_source
from expo_jbm329.services.data_operations.dtypes import SemanticDType
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_pct


def _labels_text(view: OverviewView) -> str:
    return "\n".join(label.text() for label in view.findChildren(QLabel))


def _make_result(**overrides: object) -> DatasetOverviewResult:
    defaults: dict[str, object] = {
        "row_count": 100,
        "column_count": 10,
        "missing_cell_count": 25,
        "missing_cell_fraction": 0.025,
        "duplicate_row_count": 3,
        "duplicate_row_fraction": 0.03,
        "numeric_column_count": 4,
        "categorical_column_count": 3,
        "datetime_column_count": 1,
        "boolean_column_count": 1,
        "other_column_count": 1,
        "high_missing_columns": (),
    }
    defaults.update(overrides)
    return DatasetOverviewResult(**defaults)  # type: ignore[arg-type]


def test_columns_metadata_header_uses_shared_label(monkeypatch):
    context, source = presentation_label_source(PresentationLabel.OVERVIEW_COLUMNS_METADATA)
    calls: list[tuple[str, str]] = []

    def translate(label_context: str, text: str) -> str:
        calls.append((label_context, text))
        return f"Localized {text}"

    monkeypatch.setattr(
        "expo_jbm329.gui.dialogs.analysis.overview_view.QCoreApplication.translate",
        translate,
    )
    view = OverviewView(_make_result())
    labels = [label.text() for label in view.findChildren(QLabel)]

    assert (context, source) in calls
    assert "Localized Columns metadata" in labels
    assert "Columns" not in labels


def test_summary_label_shows_rows_columns_missing_and_duplicates():
    result = _make_result(row_count=100, column_count=10, missing_cell_count=25, duplicate_row_count=3)
    view = OverviewView(result)

    text = view._build_summary_label().text()  # noqa: SLF001

    assert fmt_int(100) in text
    assert fmt_int(10) in text
    assert fmt_int(25) in text
    assert fmt_int(3) in text
    assert fmt_pct(result.missing_cell_fraction) in text
    assert fmt_pct(result.duplicate_row_fraction) in text
    assert text.split("<br>") == [
        f"Rows: <b>{fmt_int(100)}</b>",
        f"Columns: <b>{fmt_int(10)}</b>",
        f"Missing values: <b>{fmt_int(25)}</b> ({fmt_pct(result.missing_cell_fraction)})",
        f"Duplicate rows: <b>{fmt_int(3)}</b> ({fmt_pct(result.duplicate_row_fraction)})",
    ]


def test_sample_tabs_share_statistics_tab_styling():
    view = OverviewView(_make_result(sample_rows=((1,),), sample_columns=("value",), row_count=1))
    tabs = view.sample_tabs()

    assert tabs is not None
    assert tabs.styleSheet() == ANALYSIS_TABS_STYLE
    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        text_width = tabs.tabBar().fontMetrics().horizontalAdvance(tabs.tabText(index))
        assert tabs.tabBar().tabRect(index).width() >= text_width + 12


def test_column_types_label_shows_every_bucket_count():
    result = _make_result(
        numeric_column_count=4,
        categorical_column_count=3,
        datetime_column_count=1,
        boolean_column_count=1,
        other_column_count=1,
    )
    view = OverviewView(result)

    text = view._build_column_types_label().text()  # noqa: SLF001

    assert fmt_int(4) in text
    assert fmt_int(3) in text
    assert fmt_int(1) in text


def test_warnings_label_shows_no_issues_when_nothing_flagged():
    result = _make_result(high_missing_columns=())
    view = OverviewView(result)

    label = view._build_warnings_label()  # noqa: SLF001

    assert "No issues detected" in label.text()


def test_warnings_label_lists_high_missing_columns():
    result = _make_result(high_missing_columns=(("salary", 0.6), ("age", 0.25)))
    view = OverviewView(result)

    text = view._build_warnings_label().text()  # noqa: SLF001

    assert "salary" in text
    assert "age" in text
    assert fmt_pct(0.6) in text
    assert fmt_pct(0.25) in text


def _column(**overrides: object) -> ColumnOverview:
    defaults: dict[str, object] = {
        "column": "salary",
        "semantic_dtype": SemanticDType.FLOAT,
        "dtype_name": "float64",
        "missing_count": 5,
        "missing_fraction": 0.05,
        "unique_count": 42,
    }
    defaults.update(overrides)
    return ColumnOverview(**defaults)  # type: ignore[arg-type]


def test_columns_table_shows_one_row_per_column_with_its_statistics():
    column = _column()
    view = OverviewView(_make_result(columns=(column, _column(column="age"))))

    table = view.columns_table()
    assert table is not None
    assert table.selectionMode() is QTableWidget.SelectionMode.NoSelection
    assert table.rowCount() == 2
    assert [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())] == [
        "Column",
        "Type",
        "Storage type",
        "Missing",
        "Missing %",
        "Unique",
    ]
    assert [table.item(0, i).text() for i in range(table.columnCount())] == [
        "salary",
        "Float",
        "float64",
        fmt_int(column.missing_count),
        fmt_pct(column.missing_fraction),
        fmt_int(column.unique_count),
    ]


def test_columns_table_translates_every_semantic_dtype():
    view = OverviewView(_make_result(columns=tuple(_column(semantic_dtype=t) for t in SemanticDType)))

    table = view.columns_table()
    assert table is not None
    labels = [table.item(row, 1).text() for row in range(table.rowCount())]
    assert labels == ["Integer", "Float", "Boolean", "Datetime", "Text", "Category", "Other"]


def test_columns_table_is_absent_when_the_dataset_has_no_columns():
    view = OverviewView(_make_result(columns=()))

    assert view.columns_table() is None


def test_sample_table_shows_formatted_raw_values():
    result = _make_result(
        sample_columns=("a", "b"),
        sample_rows=((1.5, "x"), (float("nan"), None)),
        sample_truncated=False,
        row_count=2,
    )
    view = OverviewView(result)

    table = view.sample_table()
    assert table is not None
    assert table.selectionMode() is QTableWidget.SelectionMode.NoSelection
    assert table.rowCount() == 2
    assert [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())] == ["a", "b"]
    assert table.item(0, 0).text() == fmt_num(1.5)
    assert table.item(0, 1).text() == "x"
    # Missing values render as blank cells rather than "nan"/"None".
    assert table.item(1, 0).text() == ""
    assert table.item(1, 1).text() == ""


def test_sample_heading_is_simple_and_tabs_show_actual_snapshot_counts():
    truncated = OverviewView(_make_result(sample_rows=((1,),), sample_columns=("a",), sample_truncated=True))
    complete = OverviewView(
        _make_result(
            sample_rows=((1,), (2,), (3,)),
            sample_columns=("a",),
            sample_truncated=False,
            row_count=3,
        )
    )

    truncated_tabs = truncated.sample_tabs()
    assert truncated_tabs is not None
    assert [truncated_tabs.tabText(index) for index in range(truncated_tabs.count())] == [
        "First (1)",
        "Last (unavailable)",
    ]
    assert "Sample" in _labels_text(complete)
    assert "first 100 rows" not in _labels_text(complete)
    complete_tabs = complete.sample_tabs()
    assert complete_tabs is not None
    assert [complete_tabs.tabText(index) for index in range(complete_tabs.count())] == ["First (3)", "Last (3)"]


def test_sample_tabs_render_first_and_last_ten_rows_from_the_captured_result():
    source = pd.DataFrame({"<literal name>": pd.Series(range(120), dtype="Int64")})
    view = OverviewView(analyze_dataset_overview(source))

    tabs = view.sample_tabs()
    first = view.sample_table()
    last = view.last_sample_table()

    assert tabs is not None
    assert [tabs.tabText(index) for index in range(tabs.count())] == ["First (10)", "Last (10)"]
    assert first is not None and first.rowCount() == 10
    assert last is not None and last.rowCount() == 10
    assert first.horizontalHeaderItem(0).text() == "<literal name>"
    assert first.item(0, 0).text() == "0"
    assert last.item(0, 0).text() == "110"
    assert last.item(9, 0).text() == "119"


def test_sample_table_is_absent_when_there_are_no_rows():
    view = OverviewView(_make_result(sample_rows=(), row_count=0))

    assert view.sample_table() is None
    assert view.last_sample_table() is None
    tabs = view.sample_tabs()
    assert tabs is not None
    assert [tabs.tabText(index) for index in range(tabs.count())] == ["First (0)", "Last (0)"]
    assert "no rows to preview" in _labels_text(view)


def test_summary_panel_is_framed_and_sits_left_of_the_columns_table():
    view = OverviewView(_make_result(columns=(_column(),), sample_rows=((1.0,),), sample_columns=("salary",)))
    view.resize(900, 600)

    panel = view._build_summary_panel()  # noqa: SLF001
    scroll = panel.findChild(QScrollArea)
    assert scroll.frameShape() is QFrame.Shape.StyledPanel
    assert scroll.widgetResizable() is True
    assert scroll.verticalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert scroll.horizontalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert "Summary" in _labels_text(panel)
    assert "Summary" not in _labels_text(scroll)
    assert scroll.widget().layout().itemAt(0).widget().text() == "Dataset statistics"
    assert scroll.widget().layout().itemAt(1).widget().text().startswith("Rows:")
    assert panel.layout().itemAt(0).widget().text() == "Summary"
    assert panel.layout().itemAt(1).widget() is scroll

    splitters = view.findChildren(QSplitter)
    horizontal = [s for s in splitters if s.orientation() is Qt.Orientation.Horizontal]
    vertical = [s for s in splitters if s.orientation() is Qt.Orientation.Vertical]
    assert len(horizontal) == 1
    assert len(vertical) == 1

    top_row = horizontal[0]
    assert top_row.widget(0).findChild(QScrollArea) is not None
    columns_table = view.columns_table()
    assert columns_table is not None
    assert top_row.widget(1).isAncestorOf(columns_table)

    sample_table = view.sample_table()
    assert sample_table is not None
    assert vertical[0].widget(1).isAncestorOf(sample_table)
    assert view.sample_tabs() is not None
    assert isinstance(view.sample_tabs(), QTabWidget)
