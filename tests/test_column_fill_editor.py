"""Operation-neutral picker/delegate behavior with join translation compatibility."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QEvent, QLocale, Qt, QTranslator
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QDialog, QLabel, QStyleOptionViewItem, QTableWidget, QTableWidgetItem

from expo_jbm329.gui.dialogs.workflows.column_fill_editor import (
    FILL_COLUMN_ROLE,
    FILL_VALUE_ROLE,
    ColumnFillDelegate,
    ColumnFillValueDialog,
    display_fill,
)
from expo_jbm329.gui.dialogs.workflows.join.join_fill_delegate import (
    JoinFillValueDialog,
    display_join_fill,
)
from expo_jbm329.services.data_operations.column_defaults import ColumnFill, describe_fill_column


def test_shared_picker_uses_explicit_operation_wording(qt_app) -> None:
    metadata = describe_fill_column(pd.Series([], name="text", dtype="object"))
    editor = ColumnFillValueDialog(
        None,
        metadata,
        ColumnFill(),
        MagicMock(),
        title="Absent column",
        object_hint="Checked during concatenation.",
    )
    try:
        assert editor.windowTitle() == "Absent column"
        assert "Checked during concatenation." in [label.text() for label in editor.findChildren(QLabel)]
        assert not any("join runs" in label.text() for label in editor.findChildren(QLabel))
        assert display_join_fill is display_fill
        join_editor = JoinFillValueDialog(None, metadata, ColumnFill(), MagicMock())
        assert isinstance(join_editor, ColumnFillValueDialog)
        join_editor.close()
    finally:
        editor.close()


@pytest.mark.parametrize("language", ["en", "sv", "de", "fr", "it", "es", "pl"])
def test_extracted_picker_retains_canonical_translations(qt_app, language: str) -> None:
    translator = QTranslator()
    catalog = Path(__file__).resolve().parents[1] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language}.qm"
    assert translator.load(str(catalog))
    qt_app.installTranslator(translator)
    metadata = describe_fill_column(pd.Series([], name="value", dtype="object"))
    editor = JoinFillValueDialog(None, metadata, ColumnFill(), MagicMock())
    try:
        for source in ["If no match", "NULL", "Custom value..."]:
            expected = translator.translate("JoinFillValueDialog", source)
            if language != "en":
                assert expected
            expected = expected or source
            if source == "If no match":
                assert editor.windowTitle() == expected
            else:
                assert expected in [editor.choice.itemText(index) for index in range(editor.choice.count())]
        source_hint = "Text defaults require text-only source values. This is checked when the join runs."
        expected_hint = translator.translate("JoinFillValueDialog", source_hint) or source_hint
        assert expected_hint in [label.text() for label in editor.findChildren(QLabel)]
    finally:
        editor.close()
        qt_app.removeTranslator(translator)


@pytest.mark.parametrize("accepted", [False, True])
def test_shared_delegate_creates_editor_only_on_activation(
    qt_app, monkeypatch: pytest.MonkeyPatch, accepted: bool
) -> None:
    table = QTableWidget(1, 1)
    item = QTableWidgetItem()
    item.setData(FILL_COLUMN_ROLE, describe_fill_column(pd.Series([], name="value", dtype="int64")))
    item.setData(FILL_VALUE_ROLE, ColumnFill())
    table.setItem(0, 0, item)
    delegate = ColumnFillDelegate(table, MagicMock(), title="Absent column", object_hint="Checked by worker.")
    table.setItemDelegate(delegate)
    factory = MagicMock(
        return_value=MagicMock(
            fill=ColumnFill(2**62 + 1),
            exec=MagicMock(return_value=QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected),
        )
    )
    monkeypatch.setattr("expo_jbm329.gui.dialogs.workflows.column_fill_editor.ColumnFillValueDialog", factory)
    try:
        assert not factory.called
        model = table.model()
        index = model.index(0, 0)
        irrelevant = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)
        assert not delegate.editorEvent(irrelevant, model, QStyleOptionViewItem(), index)
        assert not factory.called
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        assert delegate.editorEvent(event, model, QStyleOptionViewItem(), index)
        assert factory.call_args.kwargs["title"] == "Absent column"
        assert factory.call_args.kwargs["object_hint"] == "Checked by worker."
        assert item.data(FILL_VALUE_ROLE) == (ColumnFill(2**62 + 1) if accepted else ColumnFill())
        factory.return_value.deleteLater.assert_called_once()
    finally:
        table.close()


def test_shared_picker_captures_numeric_locale_and_keeps_invalid_values_open(qt_app) -> None:
    locale = QLocale("sv_SE")
    dialogs = MagicMock()
    metadata = describe_fill_column(pd.Series([], name="value", dtype="float64"))
    editor = ColumnFillValueDialog(
        None,
        metadata,
        ColumnFill(),
        dialogs,
        title="Absent column",
        object_hint="",
        numeric_locale=locale,
    )
    try:
        editor.choice.setCurrentIndex(editor.choice.count() - 1)
        editor.custom_value.setText("1.000")
        editor.accept()
        assert editor.result() != QDialog.DialogCode.Accepted
        dialogs.warn.assert_called_once()
        editor.custom_value.setText("1,25")
        editor.accept()
        assert editor.fill == ColumnFill(1.25)
        assert editor.result() == QDialog.DialogCode.Accepted
    finally:
        editor.close()
