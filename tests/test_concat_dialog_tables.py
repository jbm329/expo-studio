"""Concatenation column inclusion, schema tables and translated controls."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from PyQt6.QtCore import Qt, QTranslator
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QHeaderView, QStyle, QStyleOptionViewItem, QTableWidget

from expo_jbm329.gui.dialogs.workflows.concat.concat_dialog import ConcatDialog, ConcatDialogResult
from expo_jbm329.services.data_operations.column_defaults import describe_fill_column
from expo_jbm329.services.data_operations.concat import ConcatRequest, concat_dataframes


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
                    assert not item.flags() & Qt.ItemFlag.ItemIsEditable
                    assert bool(item.flags() & Qt.ItemFlag.ItemIsUserCheckable) == (column == 0)
                    if column == 0:
                        assert item.checkState() == Qt.CheckState.Checked
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
        assert dialog.left_select_all.isEnabled() == (count > 0)
        assert dialog.right_select_all.isEnabled() == (count > 0)
        assert dialog._ok_button.isEnabled() == (count > 0)
        if count > 0:
            dialog.left_select_all.click()
            dialog.right_select_all.click()
            assert dialog.build_result().left_columns == []
            assert dialog.build_result().right_columns == []
            assert not dialog._ok_button.isEnabled()
            dialog.left_select_all.click()
            assert dialog.build_result().left_columns is None
            assert dialog._ok_button.isEnabled()
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
        expected = translator.translate("ConcatDialog", "Select all") or "Select all"
        if language != "en":
            assert translator.translate("ConcatDialog", "Select all")
        assert dialog.left_select_all.text() == expected
        assert dialog.right_select_all.text() == expected
        for source in (
            "Rename duplicate columns to enable column selection.",
            (
                "Only checked columns supply values. Unchecking a column on one side keeps that dataset's rows, "
                "but uses NULL for them if the column is included on the other side."
            ),
        ):
            if language != "en":
                assert translator.translate("ConcatDialog", source)
    finally:
        dialog.close()
        qt_app.removeTranslator(translator)


@pytest.fixture
def selection_dialog(qt_app):
    dialog = ConcatDialog(
        parent=None,
        left_tab_title="first",
        right_tab_titles=["second", "third", "empty"],
        left_columns=["id", "value", "drop"],
        right_columns_map={"second": ["id", "value"], "third": ["third", "value"], "empty": []},
    )
    yield dialog
    dialog.close()


@pytest.mark.parametrize("side", ["left", "right"])
def test_select_all_tracks_partial_and_empty_selections(selection_dialog, side: str) -> None:
    dialog = selection_dialog
    table = getattr(dialog, f"{side}_columns_table")
    control = getattr(dialog, f"{side}_select_all")
    assert control.checkState() == Qt.CheckState.Checked
    table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    assert control.checkState() == Qt.CheckState.PartiallyChecked
    control.click()
    assert control.checkState() == Qt.CheckState.Checked
    assert all(table.item(row, 0).checkState() == Qt.CheckState.Checked for row in range(table.rowCount()))
    control.click()
    assert control.checkState() == Qt.CheckState.Unchecked
    assert getattr(dialog.build_result(), f"{side}_columns") == []
    control.click()
    assert control.checkState() == Qt.CheckState.Checked
    assert getattr(dialog.build_result(), f"{side}_columns") is None


def test_no_columns_disables_ok_and_restoring_one_enables_it(selection_dialog) -> None:
    dialog = selection_dialog
    dialog.left_select_all.click()
    dialog.right_select_all.click()
    assert not dialog._ok_button.isEnabled()
    dialog._ok_button.click()
    assert dialog.result() == QDialog.DialogCode.Rejected
    dialog.right_columns_table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    assert dialog._ok_button.isEnabled()
    assert dialog.build_result().right_columns == ["value"]
    assert dialog.build_result().left_columns == []
    dialog._ok_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_dataset_switch_resets_right_and_preserves_left_selections(selection_dialog) -> None:
    dialog = selection_dialog
    dialog.left_columns_table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    dialog.right_select_all.click()
    dialog.cb_right_dataset.setCurrentText("third")
    assert dialog.build_result().left_columns == ["value", "drop"]
    assert dialog.build_result().right_columns is None
    assert dialog.right_select_all.checkState() == Qt.CheckState.Checked
    dialog.cb_right_dataset.setCurrentText("empty")
    assert not dialog.right_select_all.isEnabled()
    assert dialog.right_select_all.checkState() == Qt.CheckState.Unchecked
    dialog.left_select_all.click()
    dialog.left_select_all.click()
    assert not dialog._ok_button.isEnabled()
    dialog.cb_right_dataset.setCurrentText("second")
    assert dialog._ok_button.isEnabled()
    assert dialog.build_result().left_columns == []
    assert dialog.build_result().right_columns is None


def test_click_and_keyboard_toggle_inclusion_without_editing_text(selection_dialog, qt_app) -> None:
    dialog = selection_dialog
    dialog.show()
    qt_app.processEvents()
    table = dialog.left_columns_table
    item = table.item(0, 0)
    option = QStyleOptionViewItem()
    option.initFrom(table)
    option.rect = table.visualItemRect(item)
    option.features = QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
    option.checkState = item.checkState()
    indicator = table.style().subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, table)
    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=indicator.center())
    assert item.checkState() == Qt.CheckState.Unchecked
    table.setCurrentItem(item)
    table.setFocus()
    QTest.keyClick(table, Qt.Key.Key_Space)
    assert item.checkState() == Qt.CheckState.Checked
    assert item.text() == "id"
    assert dialog.left_select_all.checkState() == Qt.CheckState.Checked


def test_selection_dto_drives_real_concat_without_discarding_rows(selection_dialog) -> None:
    dialog = selection_dialog
    dialog.left_columns_table.item(2, 0).setCheckState(Qt.CheckState.Unchecked)
    dialog.right_columns_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
    cfg = dialog.build_result()
    left = pd.DataFrame({"id": [1, 1], "value": pd.Series([None, 2**62 + 1], dtype="Int64"), "drop": [2, 3]})
    right = pd.DataFrame({"id": [4, 4], "value": [5, 6]})
    result = concat_dataframes(
        ConcatRequest(left, right, left_columns=cfg.left_columns, right_columns=cfg.right_columns)
    )
    pd.testing.assert_frame_equal(
        result,
        pd.DataFrame({"id": [1, 1, 4, 4], "value": pd.Series([None, 2**62 + 1, None, None], dtype="Int64")}),
    )


def test_duplicate_schema_remains_included_without_ambiguous_selection(qt_app) -> None:
    dialog = ConcatDialog(
        parent=None,
        left_tab_title="first",
        right_tab_titles=["second"],
        left_columns=["a", "a"],
        right_columns_map={"second": ["a", "a"]},
    )
    try:
        assert not dialog.left_select_all.isEnabled()
        assert not dialog.right_select_all.isEnabled()
        assert dialog._ok_button.isEnabled()
        for table in (dialog.left_columns_table, dialog.right_columns_table):
            assert not table.item(0, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable
            assert "duplicate" in table.item(0, 0).toolTip()
        cfg = dialog.build_result()
        assert cfg.left_columns is None
        assert cfg.right_columns is None
        frame = pd.DataFrame([[1, 2]], columns=["a", "a"])
        result = concat_dataframes(
            ConcatRequest(frame, frame, left_columns=cfg.left_columns, right_columns=cfg.right_columns)
        )
        pd.testing.assert_frame_equal(result, pd.concat([frame, frame], ignore_index=True))
    finally:
        dialog.close()
