from __future__ import annotations

from unittest.mock import MagicMock

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtGui import QKeyEvent
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


def test_current_line_text_returns_line_before_cursor():
    editor = make_editor("SELECT 1\n    FROM dual")
    ctrl = EditorController(editor)
    cursor = editor.textCursor()
    cursor.setPosition(len("SELECT 1\n    FR"))
    editor.setTextCursor(cursor)

    assert ctrl.get_current_line_text() == "    FROM dual"


def test_current_line_indent_returns_leading_whitespace():
    editor = make_editor("SELECT 1\n    FROM dual")
    ctrl = EditorController(editor)
    cursor = editor.textCursor()
    cursor.setPosition(len("SELECT 1\n    FR"))
    editor.setTextCursor(cursor)

    assert ctrl.get_current_line_indent() == "    "


def test_current_line_indent_returns_empty_string_without_leading_whitespace():
    editor = make_editor("SELECT 1")
    ctrl = EditorController(editor)

    assert ctrl.get_current_line_indent() == ""


def test_compute_next_line_indent_preserves_existing_indentation():
    editor = make_editor("SELECT 1\n    FROM dual")
    ctrl = EditorController(editor)
    cursor = editor.textCursor()
    cursor.setPosition(len("SELECT 1\n    FROM"))
    editor.setTextCursor(cursor)

    assert ctrl.compute_next_line_indent() == "    "


def test_compute_next_line_indent_adds_one_level_after_open_parenthesis():
    editor = make_editor("SELECT (\n    value")
    ctrl = EditorController(editor)
    cursor = editor.textCursor()
    cursor.setPosition(len("SELECT ("))
    editor.setTextCursor(cursor)

    assert ctrl.compute_next_line_indent() == "    "


def test_compute_next_line_indent_keeps_existing_indent_and_adds_one_level_after_open_parenthesis():
    editor = make_editor("    SELECT (")
    ctrl = EditorController(editor)

    assert ctrl.compute_next_line_indent() == "        "


def test_compute_next_line_indent_does_not_add_level_when_parentheses_are_balanced():
    editor = make_editor("    SELECT (value)")
    ctrl = EditorController(editor)

    assert ctrl.compute_next_line_indent() == "    "


def test_compute_next_line_indent_adds_level_after_with_clause():
    editor = make_editor("WITH cte AS")
    ctrl = EditorController(editor)

    assert ctrl.compute_next_line_indent() == "    "


def test_compute_next_line_indent_adds_level_after_join_on_clause():
    editor = make_editor("    JOIN sales.orders o ON")
    ctrl = EditorController(editor)

    assert ctrl.compute_next_line_indent() == "        "


def test_compute_next_line_indent_adds_level_after_where_clause():
    editor = make_editor("WHERE")
    ctrl = EditorController(editor)

    assert ctrl.compute_next_line_indent() == "    "


def test_compute_next_line_indent_does_not_add_level_after_complete_from_clause():
    editor = make_editor("    FROM dbo.users")
    ctrl = EditorController(editor)

    assert ctrl.compute_next_line_indent() == "    "


def test_handle_keypress_inserts_newline_with_existing_indentation():
    editor = make_editor("SELECT 1\n    FROM dual")
    ctrl = EditorController(editor)
    cursor = editor.textCursor()
    cursor.setPosition(len("SELECT 1\n    FROM dual"))
    editor.setTextCursor(cursor)

    handled = ctrl.handle_keypress(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    )

    assert handled is True
    assert editor.toPlainText() == "SELECT 1\n    FROM dual\n    "


def test_handle_keypress_inserts_newline_with_extra_indent_after_open_parenthesis():
    editor = make_editor("SELECT (")
    ctrl = EditorController(editor)
    cursor = editor.textCursor()
    cursor.setPosition(len("SELECT ("))
    editor.setTextCursor(cursor)

    handled = ctrl.handle_keypress(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    )

    assert handled is True
    assert editor.toPlainText() == "SELECT (\n    "


def test_handle_keypress_returns_false_for_non_enter_keys():
    editor = make_editor("SELECT 1")
    ctrl = EditorController(editor)

    handled = ctrl.handle_keypress(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a")
    )

    assert handled is False
    assert editor.toPlainText() == "SELECT 1"
