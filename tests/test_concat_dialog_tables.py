"""Read-only concatenation schema tables and translated headers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from PyQt6.QtCore import Qt, QTranslator
from PyQt6.QtWidgets import QHeaderView, QTableWidget

from expo_jbm329.gui.dialogs.workflows.concat.concat_dialog import ConcatDialog, ConcatDialogResult
from expo_jbm329.services.data_operations.column_defaults import describe_fill_column


def test_concat_tables_preserve_order_types_and_dataset_switch(qt_app) -> None:
    metadata = {
        "z": describe_fill_column(pd.Series([], name="z", dtype="Int64")),
        "a": describe_fill_column(pd.Series([], name="a", dtype="datetime64[ns, Europe/Stockholm]")),
    }
    dialog = ConcatDialog(
        parent=None,
        left_tab_title="first",
        right_tab_titles=["second", "third"],
        left_columns=["z", "a"],
        right_columns_map={"second": ["a"], "third": ["unknown", "z"]},
        left_column_metadata=metadata,
        right_column_metadata={"second": {"a": metadata["a"]}, "third": {"z": metadata["z"]}},
    )
    try:
        assert dialog.cb_left_dataset.count() == 1
        assert dialog.left_columns_table.rowCount() == 2
        assert dialog.left_columns_table.item(0, 0).text() == "z"
        assert dialog.left_columns_table.item(0, 1).text() == "Int64"
        assert dialog.left_columns_table.item(1, 1).text() == "datetime64[ns, Europe/Stockholm]"
        assert dialog.right_columns_table.item(0, 0).text() == "a"
        for table in (dialog.left_columns_table, dialog.right_columns_table):
            assert table.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers
            assert table.selectionMode() == QTableWidget.SelectionMode.NoSelection
            assert table.columnCount() == 2
            assert table.verticalHeader().isHidden()
            assert table.horizontalHeader().sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
            for row in range(table.rowCount()):
                for column in range(2):
                    item = table.item(row, column)
                    assert not item.flags() & (Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
                    assert item.toolTip() == item.text()
        dialog.cb_right_dataset.setCurrentText("third")
        assert dialog.right_columns_table.rowCount() == 2
        assert dialog.right_columns_table.item(0, 0).text() == "unknown"
        assert dialog.right_columns_table.item(0, 1).text() == "-"
        assert dialog.right_columns_table.item(1, 1).text() == "Int64"
        assert dialog.build_result() == ConcatDialogResult("first", "third", False)
        assert dialog.left_columns_table.item(0, 0).text() == "z"
        assert dialog.isSizeGripEnabled()
        assert dialog.maximumWidth() > dialog.minimumWidth()
        assert dialog.maximumHeight() > dialog.minimumHeight()
        dialog.show()
        qt_app.processEvents()
        initial_width = dialog.left_columns_table.width()
        dialog.resize(dialog.width() + 200, dialog.height() + 100)
        qt_app.processEvents()
        assert dialog.left_columns_table.width() > initial_width
    finally:
        dialog.close()


@pytest.mark.parametrize("count", [0, 1, 501])
def test_concat_table_missing_metadata_and_wide_schema(qt_app, count: int) -> None:
    columns = [f"column_{index}" for index in range(count)]
    dialog = ConcatDialog(
        parent=None,
        left_tab_title="first",
        right_tab_titles=["second"],
        left_columns=columns,
        right_columns_map={"second": columns},
    )
    try:
        assert dialog.left_columns_table.rowCount() == count
        assert dialog.right_columns_table.rowCount() == count
        for row in range(count):
            assert dialog.left_columns_table.item(row, 0).text() == columns[row]
            assert dialog.left_columns_table.item(row, 1).text() == "-"
            assert dialog.left_columns_table.cellWidget(row, 1) is None
        assert dialog.build_result().left_fill == {}
        assert dialog.build_result().right_fill == {}
    finally:
        dialog.close()


@pytest.mark.parametrize(
    "language,column_label,type_label",
    [
        ("en", "Column", "Type"),
        ("sv", "Kolumn", "Typ"),
        ("de", "Spalte", "Typ"),
        ("fr", "Colonne", "Type"),
        ("it", "Colonna", "Tipo"),
        ("es", "Columna", "Tipo"),
        ("pl", "Kolumna", "Typ"),
    ],
)
def test_concat_headers_in_compiled_catalogs(qt_app, language: str, column_label: str, type_label: str) -> None:
    translator = QTranslator()
    catalog = Path(__file__).resolve().parents[1] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language}.qm"
    assert translator.load(str(catalog))
    qt_app.installTranslator(translator)
    dialog = ConcatDialog(
        parent=None,
        left_tab_title="first",
        right_tab_titles=["second"],
        left_columns=["id"],
        right_columns_map={"second": ["id"]},
    )
    try:
        for table in (dialog.left_columns_table, dialog.right_columns_table):
            assert table.horizontalHeaderItem(0).text() == column_label
            assert table.horizontalHeaderItem(1).text() == type_label
    finally:
        dialog.close()
        qt_app.removeTranslator(translator)
