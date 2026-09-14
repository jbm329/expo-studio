from __future__ import annotations

from unittest.mock import MagicMock

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit

from expo_jbm329.workbench.controllers.editor_controller import EditorController


def make_editor(text: str = "") -> QPlainTextEdit:
    editor = QPlainTextEdit()
    editor.setPlainText(text)
    return editor


def test_insert_sql_appends_with_spacing():
    editor = make_editor("SELECT 1")
    ctrl = EditorController(editor)

    ctrl.insert_sql("SELECT 2")

    assert "SELECT 1" in editor.toPlainText()
    assert "SELECT 2" in editor.toPlainText()
    assert "\n\n" in editor.toPlainText()


def test_get_sql_prefers_selection_when_requested():
    editor = make_editor("SELECT 1")
    ctrl = EditorController(editor)
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(6, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)

    assert ctrl.get_sql(True) == "SELECT"
    assert ctrl.get_sql(False) == "SELECT 1"


def test_change_notifications_can_be_suppressed():
    editor = make_editor()
    ctrl = EditorController(editor)
    on_change = MagicMock()

    ctrl.set_on_change(on_change)
    ctrl.notify_text_changed()
    on_change.assert_called_once_with()

    ctrl.suppress_change()
    ctrl.notify_text_changed()
    on_change.assert_called_once_with()

