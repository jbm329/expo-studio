"""Typed absent-column defaults and bulk editors in the concatenate dialog."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QStyleOptionViewItem

from expo_jbm329.gui.dialogs.workflows.column_fill_editor import FILL_COLUMN_ROLE, FILL_VALUE_ROLE, ColumnFillDelegate
from expo_jbm329.gui.dialogs.workflows.concat.concat_dialog import ConcatDialog
from expo_jbm329.services.data_operations.column_defaults import ColumnFill, describe_fill_column


@pytest.fixture
def typed_default_dialog(qt_app):
    left_columns = ["shared", "integer", "float", "flag", "text", "category", "date", "period", "object"]
    right_columns = ["shared", "integer", "right_only"]
    left_metadata = {
        "shared": describe_fill_column(pd.Series([], name="shared", dtype="int64")),
        "integer": describe_fill_column(pd.Series([], name="integer", dtype="int8")),
        "right_only": describe_fill_column(pd.Series([], name="right_only", dtype="float64")),
        "float": describe_fill_column(pd.Series([], name="float", dtype="float64")),
        "flag": describe_fill_column(pd.Series([], name="flag", dtype="boolean")),
        "text": describe_fill_column(pd.Series([], name="text", dtype="string")),
        "category": describe_fill_column(pd.Series([], name="category", dtype="category")),
        "date": describe_fill_column(pd.Series([], name="date", dtype="datetime64[s]")),
        "period": describe_fill_column(pd.Series([], name="period", dtype="period[M]")),
        "object": describe_fill_column(pd.Series([], name="object", dtype="object")),
    }
    dialogs = MagicMock()
    dialog = ConcatDialog(
        parent=None,
        left_tab_title="first",
        right_tab_titles=["second", "third"],
        left_columns=left_columns,
        right_columns_map={"second": right_columns, "third": ["third"]},
        dialogs=dialogs,
        left_column_metadata=left_metadata,
        right_column_metadata={
            "second": {
                "shared": left_metadata["shared"],
                "integer": left_metadata["integer"],
                "right_only": left_metadata["right_only"],
            },
            "third": {"third": left_metadata["text"]},
        },
    )
    yield dialog
    dialog.close()


def _row(dialog: ConcatDialog, side: str, name: str) -> int:
    table = getattr(dialog, f"{side}_columns_table")
    return next(row for row in range(table.rowCount()) if table.item(row, 0).text() == name)


def _default_item(dialog: ConcatDialog, side: str, name: str):
    table = getattr(dialog, f"{side}_columns_table")
    return table.item(_row(dialog, side, name), 2)


def _mouse_release() -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(1, 1),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_default_cells_follow_effective_schema_and_supported_types(typed_default_dialog: ConcatDialog) -> None:
    dialog = typed_default_dialog
    assert dialog.left_columns_table.columnCount() == 3
    assert dialog.left_columns_table.horizontalHeaderItem(2).text() == "If absent"
    assert not _default_item(dialog, "left", "shared").flags() & Qt.ItemFlag.ItemIsEditable
    assert not _default_item(dialog, "left", "shared").flags() & Qt.ItemFlag.ItemIsEnabled
    assert not _default_item(dialog, "left", "integer").flags() & Qt.ItemFlag.ItemIsEditable
    assert not _default_item(dialog, "left", "integer").flags() & Qt.ItemFlag.ItemIsEnabled
    for column in ("float", "flag", "text", "category", "date", "object"):
        assert _default_item(dialog, "left", column).flags() & Qt.ItemFlag.ItemIsEditable
        assert _default_item(dialog, "left", column).flags() & Qt.ItemFlag.ItemIsEnabled
    assert not _default_item(dialog, "left", "period").flags() & Qt.ItemFlag.ItemIsEditable
    assert not _default_item(dialog, "left", "period").flags() & Qt.ItemFlag.ItemIsEnabled
    assert _default_item(dialog, "left", "period").text() == "NULL"
    assert dialog.left_bulk_button.isEnabled()
    assert _default_item(dialog, "right", "right_only").flags() & Qt.ItemFlag.ItemIsEditable
    assert dialog.right_bulk_button.isEnabled()

    dialog.right_columns_table.item(_row(dialog, "right", "shared"), 0).setCheckState(Qt.CheckState.Unchecked)
    assert _default_item(dialog, "left", "shared").flags() & Qt.ItemFlag.ItemIsEditable
    dialog.left_columns_table.item(_row(dialog, "left", "float"), 0).setCheckState(Qt.CheckState.Unchecked)
    assert not _default_item(dialog, "left", "float").flags() & Qt.ItemFlag.ItemIsEditable
    assert dialog.build_result().left_fill == {}


def test_defaults_return_only_eligible_non_null_values(typed_default_dialog: ConcatDialog) -> None:
    dialog = typed_default_dialog
    left = dialog.left_columns_table
    left.item(_row(dialog, "left", "flag"), 2).setData(FILL_VALUE_ROLE, ColumnFill(False))
    left.item(_row(dialog, "left", "text"), 2).setData(FILL_VALUE_ROLE, ColumnFill(""))
    left.item(_row(dialog, "left", "shared"), 2).setData(FILL_VALUE_ROLE, ColumnFill(5))
    assert dialog.build_result().left_fill == {"flag": ColumnFill(False), "text": ColumnFill("")}


def test_selected_schema_default_reaches_concatenation(typed_default_dialog: ConcatDialog) -> None:
    dialog = typed_default_dialog
    dialog.right_columns_table.item(_row(dialog, "right", "integer"), 0).setCheckState(Qt.CheckState.Unchecked)
    dialog.right_columns_table.item(_row(dialog, "right", "right_only"), 0).setCheckState(Qt.CheckState.Unchecked)
    _default_item(dialog, "left", "integer").setData(FILL_VALUE_ROLE, ColumnFill(0))
    cfg = dialog.build_result()
    left = pd.DataFrame({"shared": [1], "integer": pd.Series([5], dtype="int8")})
    right = pd.DataFrame({"shared": [2], "integer": pd.Series([99], dtype="int8")})
    from expo_jbm329.services.data_operations.concat import ConcatRequest, concat_dataframes

    result = concat_dataframes(
        ConcatRequest(
            left,
            right,
            left_columns=cfg.left_columns,
            right_columns=cfg.right_columns,
            left_fill=cfg.left_fill,
            right_fill=cfg.right_fill,
        )
    )
    pd.testing.assert_frame_equal(
        result,
        pd.DataFrame({"shared": [1, 2], "integer": pd.Series([5, 0], dtype="int8")}),
    )


@pytest.mark.parametrize("event", ["mouse", "keyboard"])
@pytest.mark.parametrize("accepted", [False, True])
def test_on_demand_default_editor_event_stores_only_accepted_values(
    typed_default_dialog: ConcatDialog,
    qt_app,
    monkeypatch: pytest.MonkeyPatch,
    event: str,
    accepted: bool,
) -> None:
    dialog = typed_default_dialog
    table = dialog.left_columns_table
    dialog.right_columns_table.item(_row(dialog, "right", "integer"), 0).setCheckState(Qt.CheckState.Unchecked)
    delegate = table.itemDelegateForColumn(2)
    assert isinstance(delegate, ColumnFillDelegate)
    column = _default_item(dialog, "left", "integer").data(FILL_COLUMN_ROLE)
    editor = SimpleNamespace(
        fill=ColumnFill(2**62 + 1),
        exec=lambda: QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected,
        deleteLater=MagicMock(),
    )
    created = MagicMock(return_value=editor)
    monkeypatch.setattr(delegate, "_create_dialog", created)
    dialog.show()
    qt_app.processEvents()
    index = table.model().index(_row(dialog, "left", "integer"), 2)
    if event == "mouse":
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=table.visualRect(index).center())
    else:
        table.setCurrentIndex(index)
        table.setFocus()
        QTest.keyClick(table, Qt.Key.Key_F2)
    qt_app.processEvents()
    if not created.called:
        assert delegate.editorEvent(_mouse_release(), table.model(), QStyleOptionViewItem(), index)
    assert created.call_args.args == (column, ColumnFill())
    expected = ColumnFill(2**62 + 1) if accepted else ColumnFill()
    assert _default_item(dialog, "left", "integer").data(FILL_VALUE_ROLE) == expected


@pytest.mark.parametrize("text,valid", [("5", True), ("128", False)])
def test_numeric_bulk_defaults_are_atomic(
    typed_default_dialog: ConcatDialog,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    valid: bool,
) -> None:
    dialog = typed_default_dialog
    editor = MagicMock(
        fill=ColumnFill(int(text)),
        exec=MagicMock(return_value=QDialog.DialogCode.Accepted),
        choice=MagicMock(currentData=MagicMock(return_value="custom")),
        custom_value=MagicMock(text=MagicMock(return_value=text)),
        deleteLater=MagicMock(),
    )
    monkeypatch.setattr(
        "expo_jbm329.gui.dialogs.workflows.concat.concat_dialog.ColumnFillValueDialog",
        MagicMock(return_value=editor),
    )
    dialog.right_columns_table.item(_row(dialog, "right", "integer"), 0).setCheckState(Qt.CheckState.Unchecked)
    dialog.left_bulk_kind.setCurrentIndex(0)
    dialog.left_bulk_button.click()
    fills = dialog.build_result().left_fill
    if valid:
        assert fills == {"integer": ColumnFill(5), "float": ColumnFill(5.0)}
    else:
        assert fills == {}
        dialog._dialogs.warn.assert_called_once()


def test_text_bulk_defaults_include_string_category_and_object(typed_default_dialog: ConcatDialog, monkeypatch) -> None:
    dialog = typed_default_dialog
    editor = MagicMock(
        fill=ColumnFill("unknown"),
        exec=MagicMock(return_value=QDialog.DialogCode.Accepted),
        choice=MagicMock(currentData=MagicMock(return_value="custom")),
        custom_value=MagicMock(text=MagicMock(return_value="unknown")),
        deleteLater=MagicMock(),
    )
    monkeypatch.setattr(
        "expo_jbm329.gui.dialogs.workflows.concat.concat_dialog.ColumnFillValueDialog",
        MagicMock(return_value=editor),
    )
    dialog.left_bulk_kind.setCurrentIndex(1)
    dialog.left_bulk_button.click()
    assert dialog.build_result().left_fill == {
        "text": ColumnFill("unknown"),
        "category": ColumnFill("unknown"),
        "object": ColumnFill("unknown"),
    }


def test_bulk_cancel_preserves_values_and_dataset_change_resets_both_sides(
    typed_default_dialog: ConcatDialog, monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog = typed_default_dialog
    _default_item(dialog, "right", "right_only").setData(FILL_VALUE_ROLE, ColumnFill(3.5))
    dialog.right_columns_table.item(_row(dialog, "right", "integer"), 0).setCheckState(Qt.CheckState.Unchecked)
    integer = _default_item(dialog, "left", "integer")
    integer.setData(FILL_VALUE_ROLE, ColumnFill(7))
    cancelled = MagicMock(
        fill=ColumnFill(8),
        exec=MagicMock(return_value=QDialog.DialogCode.Rejected),
        choice=MagicMock(currentData=MagicMock(return_value=ColumnFill())),
        custom_value=MagicMock(text=MagicMock(return_value="")),
        deleteLater=MagicMock(),
    )
    monkeypatch.setattr(
        "expo_jbm329.gui.dialogs.workflows.concat.concat_dialog.ColumnFillValueDialog",
        MagicMock(return_value=cancelled),
    )
    dialog.left_bulk_kind.setCurrentIndex(0)
    dialog.left_bulk_button.click()
    assert integer.data(FILL_VALUE_ROLE) == ColumnFill(7)
    reset = MagicMock(
        fill=ColumnFill(),
        exec=MagicMock(return_value=QDialog.DialogCode.Accepted),
        choice=MagicMock(currentData=MagicMock(return_value=ColumnFill())),
        custom_value=MagicMock(text=MagicMock(return_value="")),
        deleteLater=MagicMock(),
    )
    monkeypatch.setattr(
        "expo_jbm329.gui.dialogs.workflows.concat.concat_dialog.ColumnFillValueDialog",
        MagicMock(return_value=reset),
    )
    dialog.left_bulk_button.click()
    assert integer.data(FILL_VALUE_ROLE) == ColumnFill()
    assert dialog.build_result().right_fill == {"right_only": ColumnFill(3.5)}
    dialog.cb_right_dataset.setCurrentText("third")
    assert integer.data(FILL_VALUE_ROLE) == ColumnFill()
    assert dialog.right_columns_table.rowCount() == 1
    assert dialog.build_result().left_fill == {}
    assert dialog.build_result().right_fill == {}


def test_null_only_bulk_and_missing_metadata_do_not_offer_editors(qt_app) -> None:
    dialog = ConcatDialog(
        parent=None,
        left_tab_title="first",
        right_tab_titles=["second"],
        left_columns=["period", "unknown"],
        right_columns_map={"second": []},
    )
    try:
        assert dialog.left_columns_table.item(0, 2).text() == "NULL"
        assert dialog.left_columns_table.item(1, 2).text() == "NULL"
        assert not dialog.left_columns_table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable
        assert not dialog.left_columns_table.item(1, 2).flags() & Qt.ItemFlag.ItemIsEditable
        assert not dialog.left_bulk_button.isEnabled()
    finally:
        dialog.close()
