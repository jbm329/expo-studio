from __future__ import annotations

import pytest
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QCheckBox, QDialog, QLabel, QLineEdit, QMessageBox, QRadioButton, QWidget

from expo_jbm329.gui.dialogs.service.dialog_service import (
    BooleanConversionResult,
    CategoryConversionResult,
    CategoryOrderResult,
    CategoryRenameResult,
    DateTimeConversionResult,
    MergeColumnsResult,
    ProfileChoice,
    SplitColumnResult,
    TextFilterMatchResult,
)
from expo_jbm329.gui.dialogs.service.null_dialog_service import (
    NullDialogService,
)
from expo_jbm329.gui.dialogs.service.prompts import choice, column_operations, text


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def parent() -> QWidget:
    return QWidget()


@pytest.fixture
def dialogs() -> NullDialogService:
    return NullDialogService()


# ----------------------------------------------------------------------
# Basic behaviour
# ----------------------------------------------------------------------


def test_info_is_logged(dialogs: NullDialogService, parent: QWidget) -> None:
    dialogs.info(parent, "Title", "Text")
    assert dialogs.calls[-1][0] == "info"


def test_qt_info_displays_path_as_literal_plain_text(monkeypatch, parent: QWidget) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox

    from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService

    text = "Export completed successfully.\n\nSaved to:\nC:\\reports\\A&B <b>overview.csv"
    observed = []

    def inspect_message(message: QMessageBox) -> int:
        observed.append((message.textFormat(), message.text()))
        return 0

    monkeypatch.setattr(QMessageBox, "exec", inspect_message)
    QtDialogService().info(parent, "Export completed", text)
    assert observed == [(Qt.TextFormat.PlainText, text)]


@pytest.mark.parametrize("accepted", [False, True])
@pytest.mark.parametrize("size_hint", [None, "", " (size {name} %1 %2)"])
def test_confirm_delete_formats_compiled_translation(
    monkeypatch: pytest.MonkeyPatch,
    parent: QWidget,
    widget_language: str,
    accepted: bool,
    size_hint: str | None,
) -> None:
    name = "Dataset {size_hint} %1 %2"
    path = r"C:\data\Dataset {name} %2.csv"
    prefix = "Vill du radera permanent:" if widget_language == "sv" else "Do you want to permanently delete:"
    observed: list[str] = []

    def inspect_message(message: QMessageBox) -> int:
        observed.append(message.text())
        assert message.windowTitle() == ("Bekräfta radera" if widget_language == "sv" else "Confirm delete")
        assert message.informativeText() == path
        assert message.defaultButton() is message.button(QMessageBox.StandardButton.No)
        assert message.button(QMessageBox.StandardButton.Yes).text() == ("Ja" if widget_language == "sv" else "Yes")
        return QMessageBox.StandardButton.Yes if accepted else QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "exec", inspect_message)

    result = choice.confirm_delete(parent, name=name, full_path=path, size_hint=size_hint)

    assert result is accepted
    assert observed == [f"{prefix}\n\n{name}{size_hint or ''}"]


def test_confirm_delete_supports_reordered_fields_and_custom_title(
    monkeypatch: pytest.MonkeyPatch, parent: QWidget
) -> None:
    def reordered_translate(context: str, source: str) -> str:
        if context == "QtDialogService" and source == choice.TR_DELETE_CONFIRMATION:
            return "{size_hint}: {name}"
        return source

    monkeypatch.setattr(QCoreApplication, "translate", reordered_translate)
    observed: list[tuple[str, str]] = []

    def inspect_message(message: QMessageBox) -> int:
        observed.append((message.windowTitle(), message.text()))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "exec", inspect_message)
    choice.confirm_delete(parent, title="Custom title", name="Name %2 {name}", full_path="path", size_hint="Size")

    assert observed == [("Custom title", "Size: Name %2 {name}")]


@pytest.mark.parametrize("accepted", [False, True])
def test_split_column_formats_compiled_labels_and_preserves_defaults(
    monkeypatch: pytest.MonkeyPatch, parent: QWidget, widget_language: str, accepted: bool
) -> None:
    column = "Column {column} %1"
    observed: list[str] = []

    def inspect_dialog(dialog: QDialog) -> int:
        observed.extend(label.text() for label in dialog.findChildren(QLabel))
        assert dialog.findChild(QLineEdit).text() == r"\t"
        assert dialog.findChild(QCheckBox).isChecked() is False
        radios = dialog.findChildren(QRadioButton)
        assert [radio.isChecked() for radio in radios] == [False, True]
        return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect_dialog)
    result = column_operations.prompt_split_column(
        parent, title="Split", column=column, default_delimiter=r"\t", default_keep_original=False, default_mode="last"
    )

    assert f"{'Kolumn' if widget_language == 'sv' else 'Column'}: {column}" in observed
    assert ("Avgränsare / sträng:" if widget_language == "sv" else "Delimiter / string:") in observed
    assert result == {"delimiter": "\t" if accepted else "", "keep_original": False, "mode": "last", "ok": accepted}


@pytest.mark.parametrize("accepted", [False, True])
def test_value_replace_formats_compiled_labels_and_preserves_defaults(
    monkeypatch: pytest.MonkeyPatch, parent: QWidget, widget_language: str, accepted: bool
) -> None:
    column = "Column {column} %1"
    value = "Value {current_value} %1 %2"
    observed: list[str] = []

    def inspect_dialog(dialog: QDialog) -> int:
        observed.extend(label.text() for label in dialog.findChildren(QLabel))
        assert dialog.findChild(QLineEdit).text() == "Replacement {value} %1"
        assert dialog.findChild(QCheckBox).isChecked() is True
        return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect_dialog)
    result = text.prompt_value_replace(
        parent,
        title="Replace",
        column=column,
        current_value=value,
        default_new_value="Replacement {value} %1",
        default_replace_all=True,
    )

    assert f"{'Kolumn' if widget_language == 'sv' else 'Column'}: {column}" in observed
    assert f"{'Nuvarande värde' if widget_language == 'sv' else 'Current value'}: {value}" in observed
    assert result == {"new_value": "Replacement {value} %1" if accepted else "", "replace_all": True, "ok": accepted}


def test_warn_is_logged(dialogs: NullDialogService, parent: QWidget) -> None:
    dialogs.warn(parent, "Title", "Text")
    assert dialogs.calls[-1][0] == "warn"


def test_confirm_profile_scope_returns_default(dialogs: NullDialogService, parent: QWidget) -> None:
    result = dialogs.confirm_profile_scope(parent)
    assert result == ProfileChoice.ACTIVE


# ----------------------------------------------------------------------
# Test split & merge
# ----------------------------------------------------------------------
def test_prompt_split_column_override(
    dialogs: NullDialogService,
    parent: QWidget,
) -> None:
    override: SplitColumnResult = {
        "delimiter": "_",
        "keep_original": True,
        "mode": "first",
        "ok": True,
    }

    dialogs.set_next_prompt_split_column(override)

    result = dialogs.prompt_split_column(
        parent,
        title="Split",
        column="col_a",
        default_delimiter="-",
        default_keep_original=False,
        default_mode="last",
    )

    assert result == override


def test_prompt_merge_columns_override(
    dialogs: NullDialogService,
    parent: QWidget,
) -> None:
    override: MergeColumnsResult = {
        "columns": ["a", "b"],
        "delimiter": "_",
        "new_name": "a_b",
        "keep_original": True,
        "ok": True,
    }

    dialogs.set_next_prompt_merge_columns(override)

    result = dialogs.prompt_merge_columns(
        parent,
        title="Merge",
        all_columns=["a", "b", "c"],
        default_columns=["a"],
        default_delimiter=" ",
        default_new_name="a",
        default_keep_original=True,
    )

    assert result == override


# ----------------------------------------------------------------------
# Text filter match
# ----------------------------------------------------------------------
def test_prompt_filter_match_default_cancel(
    dialogs: NullDialogService,
    parent: QWidget,
) -> None:
    result = dialogs.prompt_filter_match(
        parent,
        title="Filter",
        label="Label",
        default_value="abc",
        default_case_sensitive=False,
    )

    assert result == {
        "value": "abc",
        "case_sensitive": False,
        "ok": False,
    }


def test_prompt_filter_match_override_used_once(
    dialogs: NullDialogService,
    parent: QWidget,
) -> None:
    override: TextFilterMatchResult = {
        "value": "xyz",
        "case_sensitive": True,
        "ok": True,
    }

    dialogs.set_next_prompt_filter_match(override)

    result1 = dialogs.prompt_filter_match(
        parent,
        title="Filter",
        label="Label",
        default_value="",
        default_case_sensitive=False,
    )
    result2 = dialogs.prompt_filter_match(
        parent,
        title="Filter",
        label="Label",
        default_value="",
        default_case_sensitive=False,
    )

    assert result1 == override
    assert result2["ok"] is False  # one‑shot


# ----------------------------------------------------------------------
# Category rename
# ----------------------------------------------------------------------


def test_prompt_category_rename_cancel(
    dialogs: NullDialogService,
    parent: QWidget,
) -> None:
    result = dialogs.prompt_category_rename(
        parent,
        title="Rename",
        categories=["A", "B"],
        default_old_value="A",
        default_new_value="A",
    )

    assert result == {
        "old": "A",
        "new": "A",
        "ok": False,
    }


def test_prompt_category_rename_override(
    dialogs: NullDialogService,
    parent: QWidget,
) -> None:
    override: CategoryRenameResult = {
        "old": "A",
        "new": "B",
        "ok": True,
    }

    dialogs.set_next_prompt_category_rename(override)

    result = dialogs.prompt_category_rename(
        parent,
        title="Rename",
        categories=["A", "B"],
        default_old_value="A",
        default_new_value="A",
    )

    assert result == override


# ----------------------------------------------------------------------
# Category set order
# ----------------------------------------------------------------------


def test_prompt_category_set_order_override(
    dialogs: NullDialogService,
    parent: QWidget,
) -> None:
    override: CategoryOrderResult = {
        "order_list": ["B", "A"],
        "ordered": True,
        "strict": False,
        "append_missing_tail": True,
        "ok": True,
    }

    dialogs.set_next_prompt_category_set_order(override)

    result = dialogs.prompt_category_set_order(
        parent,
        title="Order",
        default_order_list=["A", "B"],
        default_ordered=False,
        default_strict=False,
        default_append_missing_tail=True,
    )

    assert result == override


# ----------------------------------------------------------------------
# Category conversion
# ----------------------------------------------------------------------


def test_prompt_category_conversion_override(
    dialogs: NullDialogService,
    parent: QWidget,
) -> None:
    override: CategoryConversionResult = {
        "order": "freq",
        "ordered": True,
        "strict": False,
        "ok": True,
    }

    dialogs.set_next_prompt_category_conversion(override)

    result = dialogs.prompt_category_conversion(
        parent,
        title="Convert",
        default_order="alpha",
        default_ordered=False,
        default_strict=True,
    )

    assert result == override


# ----------------------------------------------------------------------
# Boolean conversion
# ----------------------------------------------------------------------


def test_prompt_boolean_conversion_override(
    dialogs: NullDialogService,
    parent: QWidget,
) -> None:
    override: BooleanConversionResult = {
        "true_values": ["1"],
        "false_values": ["0"],
        "ok": True,
    }

    dialogs.set_next_prompt_boolean_conversion(override)

    result = dialogs.prompt_boolean_conversion(
        parent,
        title="Bool",
        default_true_values=["true"],
        default_false_values=["false"],
    )

    assert result == override


# ----------------------------------------------------------------------
# Datetime conversion
# ----------------------------------------------------------------------


def test_prompt_datetime_conversion_override(
    dialogs: NullDialogService,
    parent: QWidget,
) -> None:

    override: DateTimeConversionResult = {
        "format_key": "iso_date",
        "target": "date",
        "ok": True,
    }

    dialogs.set_next_prompt_datetime_conversion(override)

    result = dialogs.prompt_datetime_conversion(
        parent,
        title="Datetime",
        default_format_key="auto",
        default_target="datetime",
    )

    assert result == override


# ----------------------------------------------------------------------
# One‑shot behaviour is consistent
# ----------------------------------------------------------------------


def test_override_is_consumed(dialogs: NullDialogService, parent: QWidget) -> None:
    dialogs.set_next_prompt_filter_match({"value": "x", "case_sensitive": False, "ok": True})

    dialogs.prompt_filter_match(
        parent,
        title="T",
        label="L",
        default_value="",
        default_case_sensitive=False,
    )

    result = dialogs.prompt_filter_match(
        parent,
        title="T",
        label="L",
        default_value="",
        default_case_sensitive=False,
    )

    assert result["ok"] is False
