from unittest.mock import patch

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QPlainTextEdit

from expo_jbm329.gui.autocomplete.controller import SqlAutocompleteController
from expo_jbm329.gui.autocomplete.engine import SqlAutoCompleter
from expo_jbm329.gui.autocomplete.popup import SqlEditorAutoCompletePopup


@pytest.fixture
def editor(qt_app):
    return QPlainTextEdit()

@pytest.fixture
def completer():
    c = SqlAutoCompleter()
    schema = {
        "public": {
            "users": ["id", "username"],
        }
    }
    c.set_schema(schema)
    return c

@pytest.fixture
def controller(editor, completer):
    ctrl = SqlAutocompleteController(editor, completer)
    ctrl.install()
    return ctrl

def test_popup_initialization(editor):
    popup = SqlEditorAutoCompletePopup(editor)
    assert popup.editor == editor
    assert popup.windowFlags() & Qt.WindowType.ToolTip
    assert popup.isVisible() is False

def test_popup_show_suggestions(editor):
    popup = SqlEditorAutoCompletePopup(editor)
    suggestions = ["user1", "user2"]
    popup.show_suggestions(suggestions)
    
    assert popup.list.count() == 2
    assert popup.list.item(0).text() == "user1"
    assert popup.isVisible() is True
    assert popup.list.currentRow() == 0

def test_popup_navigation(editor):
    popup = SqlEditorAutoCompletePopup(editor)
    popup.show_suggestions(["a", "b", "c"])
    
    # Down
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    popup.handle_key(event)
    assert popup.list.currentRow() == 1
    
    # Up
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
    popup.handle_key(event)
    assert popup.list.currentRow() == 0

def test_popup_escape_hides(editor):
    popup = SqlEditorAutoCompletePopup(editor)
    popup.show_suggestions(["a"])
    assert popup.isVisible()
    
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    popup.handle_key(event)
    assert popup.isVisible() is False

def test_controller_extract_prefix(editor, controller):
    editor.setPlainText("SELECT id FROM users")
    # Place cursor at the end
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    
    prefix = controller._extract_prefix()
    assert prefix == "users"
    
    editor.setPlainText("SELECT public.")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    prefix = controller._extract_prefix()
    assert prefix == "public."

@patch("expo_jbm329.gui.autocomplete.controller.QTimer.singleShot")
def test_controller_handle_keypress_period(mock_timer, controller):
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Period, Qt.KeyboardModifier.NoModifier, ".")
    handled = controller._handle_keypress(event)
    
    assert handled is False # Allow editor to receive the period
    mock_timer.assert_called_once()
    assert mock_timer.call_args[0][1] == controller._update_suggestions

def test_controller_update_suggestions(editor, controller):
    editor.setPlainText("SELECT u")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    
    controller._update_suggestions()
    
    assert controller.popup.isVisible()
    assert controller.popup.list.count() > 0
    # Should contain 'users' and 'username' from our fixture schema
    items = [controller.popup.list.item(i).text() for i in range(controller.popup.list.count())]
    assert "users" in items
    assert "username" in items

def test_popup_insert_selected(editor):
    editor.setPlainText("SELECT u")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    
    popup = SqlEditorAutoCompletePopup(editor)
    popup.show_suggestions(["users"])
    popup.list.setCurrentRow(0)
    
    popup._insert_selected()
    
    assert editor.toPlainText() == "SELECT users"
    assert popup.isVisible() is False

def test_controller_force_suggestions(editor, controller):
    editor.setPlainText("SELECT ")
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    
    # Mocking singleShot is easier for testing direct calls
    controller._force_suggestions_now()
    
    assert controller.popup.isVisible()
    # Should show all objects since prefix is empty
    # col_list (id, username) + tables (users) + schemas (public) = 4
    assert controller.popup.list.count() == 4
