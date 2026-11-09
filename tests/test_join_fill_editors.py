"""Tests for validated, on-demand join-default editors."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QEvent, QLocale, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QStyleOptionViewItem

from expo_jbm329.gui.dialogs.workflows.join.join_dialog import JoinDialog
from expo_jbm329.gui.dialogs.workflows.join.join_fill_delegate import (
    FILL_VALUE_ROLE,
    JoinFillDelegate,
    JoinFillValueDialog,
)
from expo_jbm329.services.data_operations.joins import UnmatchedFill, describe_join_fill_column

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def join_dialog(qt_app) -> Iterator[JoinDialog]:
    frames = {
        "Left": pd.DataFrame({
            "id": [1, 2],
            "amount": [10, 20],
            "text": ["left", "matched"],
        }),
        "Right": pd.DataFrame({
            "id": [2, 3],
            "amount": pd.Series([30, 40], dtype="int8"),
            "price": [1.5, 2.5],
            "flag": [True, False],
            "text": pd.Series(["matched", "right"], dtype="string"),
            "date": pd.to_datetime(["2020-01-01", "2020-01-02"], utc=True),
            "period": pd.Series([pd.Period("2020-01"), pd.Period("2020-02")]),
        }),
        "Third": pd.DataFrame({"id": [2, 3], "other": [1, 2]}),
    }
    dialogs = MagicMock()
    dialog = JoinDialog(
        None,
        all_tab_titles=list(frames),
        left_initial="Left",
        get_columns_for_tab={name: list(frame.columns) for name, frame in frames.items()},
        joinable_map={
            ("Left", "id", "Right"): {"id"},
            ("Left", "id", "Third"): {"id"},
            ("Left", "amount", "Right"): {"amount"},
        },
        column_dtypes_for_tab={name: {col: str(frame[col].dtype) for col in frame} for name, frame in frames.items()},
        fill_columns_for_tab={
            name: {col: describe_join_fill_column(frame[col]) for col in frame} for name, frame in frames.items()
        },
        dialogs=dialogs,
    )
    dialog._left.cb_key.setCurrentText("id")
    yield dialog
    dialog.close()
    dialog.deleteLater()


def _row(dialog: JoinDialog, side: str, name: str) -> int:
    widgets = dialog._left if side == "left" else dialog._right
    return next(i for i in range(widgets.columns_table.rowCount()) if widgets.columns_table.item(i, 0).text() == name)


@pytest.mark.parametrize(
    "join_type,editable",
    [("inner", (False, False)), ("left", (False, True)), ("right", (True, False)), ("full", (True, True))],
)
def test_defaults_enabled_by_join_type(join_dialog: JoinDialog, join_type: str, editable: tuple[bool, bool]) -> None:
    getattr(join_dialog, f"rb_{join_type}").setChecked(True)
    for side, enabled in zip(("left", "right"), editable, strict=True):
        widgets = join_dialog._left if side == "left" else join_dialog._right
        item = widgets.columns_table.item(_row(join_dialog, side, "amount"), 2)
        assert bool(item.flags() & Qt.ItemFlag.ItemIsEditable) == enabled
        key = widgets.columns_table.item(_row(join_dialog, side, "id"), 2)
        assert not key.flags() & Qt.ItemFlag.ItemIsEditable
        assert widgets.btn_bulk.isEnabled() == enabled
    period = join_dialog._right.columns_table.item(_row(join_dialog, "right", "period"), 2)
    assert not period.flags() & Qt.ItemFlag.ItemIsEditable


def test_defaults_follow_inclusion_key_and_type_changes(join_dialog: JoinDialog) -> None:
    join_dialog.rb_left.setChecked(True)
    row = _row(join_dialog, "right", "amount")
    name = join_dialog._right.columns_table.item(row, 0)
    item = join_dialog._right.columns_table.item(row, 2)
    item.setData(FILL_VALUE_ROLE, UnmatchedFill(7))
    assert join_dialog.build_result().right_fill == {"amount": UnmatchedFill(7)}
    name.setCheckState(Qt.CheckState.Unchecked)
    assert not item.flags() & Qt.ItemFlag.ItemIsEditable
    assert join_dialog.build_result().right_fill == {}
    name.setCheckState(Qt.CheckState.Checked)
    assert join_dialog.build_result().right_fill == {"amount": UnmatchedFill(7)}
    join_dialog.rb_inner.setChecked(True)
    assert join_dialog.build_result().right_fill == {}
    join_dialog.rb_left.setChecked(True)
    assert join_dialog.build_result().right_fill == {"amount": UnmatchedFill(7)}
    join_dialog._left.cb_key.setCurrentText("amount")
    assert join_dialog._right.cb_key.currentText() == "amount"
    assert not item.flags() & Qt.ItemFlag.ItemIsEditable
    assert join_dialog.build_result().right_fill == {}
    join_dialog._left.cb_key.setCurrentText("id")
    assert join_dialog.build_result().right_fill == {"amount": UnmatchedFill(7)}
    join_dialog._right.cb_dataset.setCurrentText("Third")
    assert join_dialog.build_result().right_fill == {}


@pytest.mark.parametrize("dtype", ["int64", "float64", "bool", "string", "category", "datetime64[ns]"])
def test_value_picker_presets_and_cancellation(qt_app, dtype: str) -> None:
    descriptor = describe_join_fill_column(pd.Series([], name="value", dtype=dtype))
    initial = UnmatchedFill()
    editor = JoinFillValueDialog(None, descriptor, initial, MagicMock())
    choices = [editor.choice.itemData(i) for i in range(editor.choice.count())]
    assert choices[0] == UnmatchedFill()
    if dtype == "bool":
        assert choices == [UnmatchedFill(), UnmatchedFill(True), UnmatchedFill(False)]
    elif dtype in {"int64", "float64"}:
        assert choices[1] == UnmatchedFill(0)
        assert choices[-1] == "custom"
    else:
        assert choices[-1] == "custom"
    editor.reject()
    assert editor.fill == initial
    editor.deleteLater()


@pytest.mark.parametrize(
    "dtype,text,expected",
    [
        ("int64", "4611686018427387905", 2**62 + 1),
        ("uint64", "18446744073709551615", 2**64 - 1),
        ("float64", "1.25", 1.25),
        ("string", "  unknown  ", "  unknown  "),
        ("category", "", ""),
        (
            "datetime64[ns, Europe/Stockholm]",
            "2020-01-01 12:00:00",
            pd.Timestamp("2020-01-01 12:00:00", tz="Europe/Stockholm"),
        ),
    ],
)
def test_value_picker_custom_validation(qt_app, dtype: str, text: str, expected: object) -> None:
    descriptor = describe_join_fill_column(pd.Series([], name="value", dtype=dtype))
    editor = JoinFillValueDialog(None, descriptor, UnmatchedFill(), MagicMock())
    editor.choice.setCurrentIndex(editor.choice.count() - 1)
    editor.custom_value.setText(text.replace(".", editor._locale.decimalPoint()) if dtype == "float64" else text)
    editor.accept()
    assert editor.result() == QDialog.DialogCode.Accepted
    assert editor.fill.value == expected
    editor.deleteLater()


@pytest.mark.parametrize(
    "dtype,text",
    [
        ("int8", "128"),
        ("int64", "1.5"),
        ("float64", "nan"),
        ("datetime64[ns]", "2500-01-01"),
        ("datetime64[ns, Europe/Stockholm]", "2020-10-25 02:30:00"),
    ],
)
def test_invalid_value_keeps_editor_open(qt_app, dtype: str, text: str) -> None:
    dialogs = MagicMock()
    descriptor = describe_join_fill_column(pd.Series([], name="value", dtype=dtype))
    editor = JoinFillValueDialog(None, descriptor, UnmatchedFill(), dialogs)
    editor.choice.setCurrentIndex(editor.choice.count() - 1)
    editor.custom_value.setText(text)
    editor.accept()
    assert editor.result() != QDialog.DialogCode.Accepted
    assert editor.fill == UnmatchedFill()
    dialogs.warn.assert_called_once()
    editor.deleteLater()


def test_delegate_commits_only_accepted_values(join_dialog: JoinDialog, monkeypatch: pytest.MonkeyPatch) -> None:
    join_dialog.rb_left.setChecked(True)
    table = join_dialog._right.columns_table
    row = _row(join_dialog, "right", "amount")
    index = table.model().index(row, 2)
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    delegate = table.itemDelegateForColumn(2)
    assert isinstance(delegate, JoinFillDelegate)
    editor = MagicMock(fill=UnmatchedFill(7), exec=MagicMock(return_value=QDialog.DialogCode.Accepted))
    monkeypatch.setattr(
        "expo_jbm329.gui.dialogs.workflows.join.join_fill_delegate.JoinFillValueDialog", MagicMock(return_value=editor)
    )
    assert delegate.editorEvent(event, table.model(), QStyleOptionViewItem(), index)
    assert join_dialog.build_result().right_fill == {"amount": UnmatchedFill(7)}
    assert table.item(row, 2).text() == "7"
    editor.exec.return_value = QDialog.DialogCode.Rejected
    editor.fill = UnmatchedFill(8)
    assert delegate.editorEvent(event, table.model(), QStyleOptionViewItem(), index)
    assert join_dialog.build_result().right_fill == {"amount": UnmatchedFill(7)}
    editor.deleteLater.assert_called()
    join_dialog.rb_inner.setChecked(True)
    assert not delegate.editorEvent(event, table.model(), QStyleOptionViewItem(), index)


@pytest.mark.parametrize("text,valid", [("5", True), ("1.5", False), ("128", False)])
def test_numeric_bulk_defaults_are_atomic(
    join_dialog: JoinDialog, monkeypatch: pytest.MonkeyPatch, text: str, valid: bool
) -> None:
    join_dialog.rb_left.setChecked(True)
    editor = MagicMock(
        fill=UnmatchedFill(float(text)),
        exec=MagicMock(return_value=QDialog.DialogCode.Accepted),
        choice=MagicMock(currentData=MagicMock(return_value="custom")),
        custom_value=MagicMock(text=MagicMock(return_value=text)),
    )
    monkeypatch.setattr(
        "expo_jbm329.gui.dialogs.workflows.join.join_dialog.JoinFillValueDialog", MagicMock(return_value=editor)
    )
    join_dialog._right.btn_bulk.click()
    fills = join_dialog.build_result().right_fill
    assert fills == ({"amount": UnmatchedFill(5), "price": UnmatchedFill(5.0)} if valid else {})
    assert join_dialog._dialogs.warn.called != valid


def test_text_bulk_default_and_reset(join_dialog: JoinDialog, monkeypatch: pytest.MonkeyPatch) -> None:
    join_dialog.rb_left.setChecked(True)
    join_dialog._right.bulk_kind.setCurrentIndex(1)
    editor = MagicMock(
        fill=UnmatchedFill("unknown"),
        exec=MagicMock(return_value=QDialog.DialogCode.Accepted),
        choice=MagicMock(currentData=MagicMock(return_value="custom")),
        custom_value=MagicMock(text=MagicMock(return_value="unknown")),
    )
    monkeypatch.setattr(
        "expo_jbm329.gui.dialogs.workflows.join.join_dialog.JoinFillValueDialog", MagicMock(return_value=editor)
    )
    join_dialog._right.btn_bulk.click()
    assert join_dialog.build_result().right_fill == {"text": UnmatchedFill("unknown")}
    editor.choice.currentData.return_value = UnmatchedFill()
    editor.fill = UnmatchedFill()
    join_dialog._right.btn_bulk.click()
    assert join_dialog.build_result().right_fill == {}


def test_custom_number_uses_captured_numeric_locale(qt_app) -> None:
    previous = QLocale()
    try:
        QLocale.setDefault(QLocale("sv_SE"))
        column = describe_join_fill_column(pd.Series([], name="price", dtype="float64"))
        editor = JoinFillValueDialog(None, column, UnmatchedFill(), MagicMock())
        editor.choice.setCurrentIndex(editor.choice.count() - 1)
        editor.custom_value.setText("1,25")
        editor.accept()
        assert editor.fill == UnmatchedFill(1.25)
        editor.deleteLater()
    finally:
        QLocale.setDefault(previous)


def test_click_opens_real_validated_picker(join_dialog: JoinDialog, monkeypatch: pytest.MonkeyPatch, qt_app) -> None:
    seen: list[str] = []

    def choose(dialog: JoinFillValueDialog) -> int:
        seen.append(dialog._column.name)
        dialog.choice.setCurrentIndex(dialog.choice.count() - 1)
        dialog.custom_value.setText("7")
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(JoinFillValueDialog, "exec", choose)
    join_dialog.rb_left.setChecked(True)
    join_dialog.show()
    qt_app.processEvents()
    table = join_dialog._right.columns_table
    item = table.item(_row(join_dialog, "right", "amount"), 2)
    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=table.visualItemRect(item).center())
    assert seen == ["amount"]
    assert join_dialog.build_result().right_fill == {"amount": UnmatchedFill(7)}
    assert item.text() == "7"


def test_datetime_picker_respects_seconds_resolution(qt_app) -> None:
    column = describe_join_fill_column(pd.Series([], name="date", dtype="datetime64[s]"))
    editor = JoinFillValueDialog(None, column, UnmatchedFill(), MagicMock())
    editor.choice.setCurrentIndex(editor.choice.count() - 1)
    assert editor.calendar is not None
    editor.calendar.setDateTime(editor.calendar.dateTime().addDays(1))
    editor.accept()
    assert editor.result() == QDialog.DialogCode.Accepted
    assert isinstance(editor.fill.value, pd.Timestamp)
    assert editor.fill.value.unit == "s"
    editor.deleteLater()


@pytest.mark.parametrize(
    "widget_language,heading",
    [
        ("en", "If no match"),
        ("sv", "Om ingen matchning"),
        ("de", "Ohne Übereinstimmung"),
        ("fr", "Sans correspondance"),
        ("it", "Se non c'è corrispondenza"),
        ("es", "Sin coincidencia"),
        ("pl", "Przy braku dopasowania"),
    ],
    indirect=["widget_language"],
)
def test_default_picker_compiled_translations(qt_app, widget_language: str, heading: str) -> None:
    descriptor = describe_join_fill_column(pd.Series([], name="value", dtype="float64"))
    editor = JoinFillValueDialog(None, descriptor, UnmatchedFill(), MagicMock())
    assert editor.windowTitle() == heading
    assert editor.choice.itemText(editor.choice.count() - 1) != ""
    editor.choice.setCurrentIndex(editor.choice.count() - 1)
    editor.custom_value.setText("invalid")
    editor.accept()
    text = editor._dialogs.warn.call_args.args[2]
    assert "{column}" not in text
    assert "value" in text
    assert "float64" in text
    editor.deleteLater()


def test_wide_join_table_has_no_per_cell_editors(qt_app) -> None:
    columns = ["id", *[f"value{i}" for i in range(500)]]
    metadata = {column: describe_join_fill_column(pd.Series([], name=column, dtype="int64")) for column in columns}
    dialog = JoinDialog(
        None,
        all_tab_titles=["Left", "Right"],
        left_initial="Left",
        get_columns_for_tab={"Left": columns, "Right": columns},
        joinable_map={("Left", "id", "Right"): {"id"}},
        fill_columns_for_tab={"Left": metadata, "Right": metadata},
    )
    dialog.rb_full.setChecked(True)
    for side in (dialog._left, dialog._right):
        assert side.columns_table.rowCount() == 501
        assert side.columns_table.findChildren(JoinFillValueDialog) == []
    dialog.deleteLater()
