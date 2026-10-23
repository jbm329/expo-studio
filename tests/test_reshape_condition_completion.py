"""Column completion lexical context and actual Qt popup interaction."""

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
from expo_jbm329.services.data_operations.reshape_condition_completion import column_completion
from expo_jbm329.services.data_operations.reshape_conditions import condition_columns


@pytest.mark.parametrize("text", ["", "[a]", "[a] = '[", "[a] = 'O''Brien [", "[a]]b] = 'x'"])
def test_completion_does_not_trigger_outside_column(text):
    assert column_completion(text, len(text)) is None


def test_context_replaces_existing_column_without_eating_condition_suffix():
    text = "([Ålder] > '17')"
    context = column_completion(text, 3)
    assert (context.start, context.end, context.prefix) == (1, 8, "Å")
    context = column_completion("[a]]b", 5)
    assert context.prefix == "a]b"


def show_editor(qt_app):
    parent = QWidget()
    layout = QVBoxLayout(parent)
    other = QPushButton("Other", parent)
    layout.addWidget(other)
    editor = ConditionEditor(parent, condition_columns(["Age", "Area", "a]b", "😀 Date", "dup", "dup"]))
    layout.addWidget(editor)
    parent.show()
    other.setFocus()
    qt_app.processEvents()
    editor.text.setFocus(Qt.FocusReason.TabFocusReason)
    qt_app.processEvents()
    return parent, editor, other


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Tab])
def test_bracket_filters_and_accepts_completion(qt_app, key):
    parent, editor, _other = show_editor(qt_app)
    QTest.keyClicks(editor.expanded_text, "[")
    qt_app.processEvents()
    assert editor.completer.popup().isVisible()
    assert editor.completer.popup().width() >= 240
    assert editor.completer.popup().viewport().width() >= editor.completer.popup().sizeHintForColumn(0)
    assert editor.completer.popup().viewport().height() >= editor.completer.popup().sizeHintForRow(0)
    assert editor.completer.completionCount() == 4
    QTest.keyClicks(editor.expanded_text, "ag")
    assert editor.completer.completionCount() == 1
    QTest.keyClick(editor.expanded_text, key)
    qt_app.processEvents()
    assert editor.text.text() == "[Age]"
    assert editor.expanded_text.toPlainText() == "[Age]"
    assert editor.expanded_text.textCursor().position() == 5
    assert editor.popup.isVisible()
    assert not editor.completer.popup().isVisible()
    parent.close()


def test_popup_width_fits_long_column_names_and_scrollbar(qt_app):
    parent, editor, _other = show_editor(qt_app)
    names = [f"Long dataset column name with enough text to exceed the minimum width {index}" for index in range(30)]
    editor.completer.model().setStringList(names)
    QTest.keyClicks(editor.expanded_text, "[")
    qt_app.processEvents()
    popup = editor.completer.popup()
    assert popup.isVisible()
    assert popup.width() > 240
    assert popup.viewport().width() >= popup.sizeHintForColumn(0)
    assert popup.viewport().height() >= popup.sizeHintForRow(0)
    QTest.keyClicks(editor.expanded_text, "Long")
    assert popup.viewport().width() >= popup.sizeHintForColumn(0)
    parent.close()


def test_no_completion_in_values_escape_and_no_matches(qt_app):
    parent, editor, _other = show_editor(qt_app)
    QTest.keyClicks(editor.expanded_text, "[a")
    QTest.keyClick(editor.expanded_text, Qt.Key.Key_Escape)
    assert editor.popup.isVisible()
    assert not editor.completer.popup().isVisible()
    editor.expanded_text.setPlainText("[Age] = 'O''Brien [")
    editor.expanded_text.moveCursor(editor.expanded_text.textCursor().MoveOperation.End)
    assert not editor.completer.popup().isVisible()
    editor.expanded_text.setPlainText("[nonexistent")
    editor.expanded_text.moveCursor(editor.expanded_text.textCursor().MoveOperation.End)
    assert not editor.completer.popup().isVisible()
    parent.close()


def test_completion_escapes_brackets_preserves_suffix_and_supports_unicode(qt_app):
    parent, editor, _other = show_editor(qt_app)
    editor.expanded_text.setPlainText("[Age] = '😀' AND [a] > 'x'")
    cursor = editor.expanded_text.textCursor()
    cursor.setPosition(19)
    editor.expanded_text.setTextCursor(cursor)
    editor._insert_completion("a]b")
    assert editor.text.text() == "[Age] = '😀' AND [a]]b] > 'x'"
    editor.expanded_text.undo()
    assert editor.text.text() == "[Age] = '😀' AND [a] > 'x'"
    parent.close()


def test_arrow_navigation_and_mouse_acceptance_keep_editor_open(qt_app):
    parent, editor, _other = show_editor(qt_app)
    QTest.keyClicks(editor.expanded_text, "[")
    popup = editor.completer.popup()
    QTest.keyClick(editor.expanded_text, Qt.Key.Key_Down)
    selected = popup.currentIndex().data()
    QTest.keyClick(editor.expanded_text, Qt.Key.Key_Return)
    assert editor.text.text() == "[" + selected.replace("]", "]]") + "]"
    editor.expanded_text.clear()
    QTest.keyClicks(editor.expanded_text, "[")
    model = editor.completer.completionModel()
    index = model.index(3, 0)
    QTest.mouseClick(popup.viewport(), Qt.MouseButton.LeftButton, pos=popup.visualRect(index).center())
    qt_app.processEvents()
    assert editor.text.text() == "[😀 Date]"
    assert editor.popup.isVisible()
    assert not popup.isVisible()
    parent.close()


def test_backspace_updates_matches_and_removing_bracket_closes_suggestions(qt_app):
    parent, editor, _other = show_editor(qt_app)
    QTest.keyClicks(editor.expanded_text, "[Ag")
    assert editor.completer.completionCount() == 1
    QTest.keyClick(editor.expanded_text, Qt.Key.Key_Backspace)
    assert editor.completer.completionCount() == 3
    QTest.keyClick(editor.expanded_text, Qt.Key.Key_Backspace)
    QTest.keyClick(editor.expanded_text, Qt.Key.Key_Backspace)
    assert not editor.completer.popup().isVisible()
    assert editor.popup.isVisible()
    parent.close()


def test_outside_click_and_deletion_close_completion_popup(qt_app):
    parent, editor, other = show_editor(qt_app)
    QTest.keyClicks(editor.expanded_text, "[")
    completion_popup = editor.completer.popup()
    QTest.mouseClick(other, Qt.MouseButton.LeftButton)
    qt_app.processEvents()
    assert not editor.popup.isVisible()
    assert not completion_popup.isVisible()
    editor.text.setFocus(Qt.FocusReason.TabFocusReason)
    qt_app.processEvents()
    editor.expanded_text.clear()
    QTest.keyClicks(editor.expanded_text, "[")
    assert completion_popup.isVisible()
    completer = editor.completer
    editor.deleteLater()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(completer)
    assert sip.isdeleted(completion_popup)
    parent.close()


def test_multiline_completion_after_unicode_and_linting(qt_app):
    parent, editor, _other = show_editor(qt_app)
    editor.expanded_text.setPlainText("[Age] = '😀'\nAND [😀")
    editor.expanded_text.moveCursor(editor.expanded_text.textCursor().MoveOperation.End)
    assert editor.completer.popup().isVisible()
    assert editor.completer.completionCount() == 1
    QTest.keyClick(editor.expanded_text, Qt.Key.Key_Tab)
    assert editor.text.text() == "[Age] = '😀'\nAND [😀 Date]"
    QTest.keyClicks(editor.expanded_text, " IS NULL")
    assert editor.validate_now()
    parent.close()


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab])
def test_popup_receives_acceptance_keys_after_navigation(qt_app, key):
    parent, editor, _other = show_editor(qt_app)
    QTest.keyClicks(editor.expanded_text, "[")
    popup = editor.completer.popup()
    QTest.keyClick(popup, Qt.Key.Key_Down)
    selected = popup.currentIndex().data()
    assert popup.currentIndex().row() == 1
    QTest.keyClick(popup, key)
    qt_app.processEvents()
    expected = "[" + selected.replace("]", "]]") + "]"
    assert editor.expanded_text.toPlainText() == expected
    assert editor.text.text() == expected
    assert editor.expanded_text.textCursor().position() == len(expected)
    assert editor.popup.isVisible()
    assert not popup.isVisible()
    QTest.keyClicks(editor.expanded_text, " IS NULL")
    assert editor.validate_now()
    parent.close()


def test_escape_on_completion_popup_only_dismisses_suggestions(qt_app):
    parent, editor, _other = show_editor(qt_app)
    QTest.keyClicks(editor.expanded_text, "[")
    popup = editor.completer.popup()
    QTest.keyClick(popup, Qt.Key.Key_Escape)
    qt_app.processEvents()
    assert not popup.isVisible()
    assert editor.popup.isVisible()
    assert editor.text.text() == "["
    QTest.keyClick(editor.expanded_text, Qt.Key.Key_Escape)
    assert not editor.popup.isVisible()
    parent.close()
