"""Concatenation column inclusion, schema tables and translated controls."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from PyQt6.QtCore import Qt, QTranslator
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QFormLayout, QHeaderView, QStyle, QStyleOptionViewItem, QTableWidget

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
            assert table.columnCount() == 3
            assert table.verticalHeader().isHidden()
            assert table.horizontalHeader().sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
            assert table.horizontalHeaderItem(2).text() == "If absent"
            for row in range(table.rowCount()):
                for column in range(3):
                    item = table.item(row, column)
                    if column == 2:
                        assert bool(item.flags() & Qt.ItemFlag.ItemIsEditable) == (
                            table is dialog.left_columns_table and row == 0
                        )
                    else:
                        assert not item.flags() & Qt.ItemFlag.ItemIsEditable
                    assert bool(item.flags() & Qt.ItemFlag.ItemIsUserCheckable) == (column == 0)
                    if column == 0:
                        assert item.checkState() == Qt.CheckState.Checked
                    if column < 2:
                        assert item.toolTip() == item.text()
                    else:
                        assert item.text() == "NULL"
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


def test_column_controls_are_below_the_table_like_join(qt_app) -> None:
    dialog = ConcatDialog(
        parent=None,
        left_tab_title="first",
        right_tab_titles=["second"],
        left_columns=["left_only"],
        right_columns_map={"second": ["right_only"]},
    )
    try:
        for side in ("left", "right"):
            table = getattr(dialog, f"{side}_columns_table")
            select_all = getattr(dialog, f"{side}_select_all")
            bulk_kind = getattr(dialog, f"{side}_bulk_kind")
            bulk_button = getattr(dialog, f"{side}_bulk_button")
            layout = table.parentWidget().layout()
            assert isinstance(layout, QFormLayout)
            table_row, _ = layout.getWidgetPosition(table)
            select_all_row, _ = layout.getWidgetPosition(select_all)
            assert table_row < select_all_row
            bulk_row = layout.itemAt(select_all_row + 1, QFormLayout.ItemRole.FieldRole).layout()
            assert bulk_row is not None
            assert bulk_row.itemAt(0).widget() is bulk_kind
            assert bulk_row.itemAt(1).widget() is bulk_button
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
    "language,column_label,type_label,absent_label",
    [
        ("en", "Column", "Type", "If absent"),
        ("sv", "Kolumn", "Typ", "Om saknas"),
        ("de", "Spalte", "Typ", "Falls nicht vorhanden"),
        ("fr", "Colonne", "Type", "Si absent"),
        ("it", "Colonna", "Tipo", "Se assente"),
        ("es", "Columna", "Tipo", "Si falta"),
        ("pl", "Kolumna", "Typ", "Jeśli brak"),
    ],
)
def test_concat_headers_in_compiled_catalogs(
    qt_app, language: str, column_label: str, type_label: str, absent_label: str
) -> None:
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
            assert table.horizontalHeaderItem(2).text() == absent_label
            assert table.item(0, 2).text() == (translator.translate("JoinFillValueDialog", "NULL") or "NULL")
        expected = translator.translate("ConcatDialog", "Select all") or "Select all"
        if language != "en":
            assert translator.translate("ConcatDialog", "Select all")
        assert dialog.left_select_all.text() == expected
        assert dialog.right_select_all.text() == expected
        for source, displayed in (
            ("Exclude duplicate rows", dialog.exclude_duplicates.text()),
            (
                (
                    "Remove duplicate rows throughout the combined result, keeping the first occurrence. "
                    "Compare all output columns after column selection and defaults."
                ),
                dialog.exclude_duplicates.toolTip(),
            ),
        ):
            translated = translator.translate("ConcatDialog", source)
            if language != "en":
                assert translated
                assert translated != source
            assert displayed == (translated or source)
        for source in (
            "Rename duplicate columns to enable column selection.",
            (
                "Only checked columns supply values. Unchecking a column on one side keeps that dataset's rows, "
                "but uses NULL for them if the column is included on the other side."
            ),
        ):
            if language != "en":
                assert translator.translate("ConcatDialog", source)
        if language != "en":
            for source in (
                "Text defaults require text-only source values. This is checked when concatenation runs.",
                "Click to choose a default for rows from the other dataset.",
            ):
                assert translator.translate("ConcatDialog", source)
            assert translator.translate("JoinFillValueDialog", "NULL")
        if language != "en":
            assert translator.translate("ConcatDialog", "Select included columns of this type first.")
            assert translator.translate("JoinDialog", "Numeric columns")
            assert translator.translate("JoinDialog", "Text columns")
            assert translator.translate("JoinDialog", "Set defaults...")
        if language != "en":
            assert translator.translate(
                "ConcatDialog", "Defaults apply only to selected columns absent from the other dataset."
            )
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


def test_duplicate_option_defaults_off_and_preserves_settings_on_dataset_switch(selection_dialog) -> None:
    dialog = selection_dialog
    assert dialog.exclude_duplicates.text() == "Exclude duplicate rows"
    assert not dialog.exclude_duplicates.isChecked()
    assert dialog.build_result().remove_duplicates is False
    dialog.left_columns_table.item(2, 0).setCheckState(Qt.CheckState.Unchecked)
    before = dialog.build_result()

    dialog.exclude_duplicates.click()

    expected = ConcatDialogResult(
        before.left_tab_title,
        before.right_tab_title,
        True,
        left_fill=before.left_fill,
        right_fill=before.right_fill,
        left_columns=before.left_columns,
        right_columns=before.right_columns,
    )
    assert dialog.build_result() == expected
    dialog.cb_right_dataset.setCurrentText("third")
    assert dialog.build_result().remove_duplicates is True
    assert dialog.build_result().left_columns == before.left_columns
    dialog.exclude_duplicates.click()
    assert dialog.build_result().remove_duplicates is False


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
    metadata = {"a": describe_fill_column(pd.Series([], name="a", dtype="int64"))}
    dialog = ConcatDialog(
        parent=None,
        left_tab_title="first",
        right_tab_titles=["second"],
        left_columns=["a", "a"],
        right_columns_map={"second": ["a", "a"]},
        left_column_metadata=metadata,
        right_column_metadata={"second": metadata},
    )
    try:
        assert not dialog.left_select_all.isEnabled()
        assert not dialog.right_select_all.isEnabled()
        assert dialog._ok_button.isEnabled()
        for table in (dialog.left_columns_table, dialog.right_columns_table):
            assert not table.item(0, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable
            assert "duplicate" in table.item(0, 0).toolTip()
            assert not table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable
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
