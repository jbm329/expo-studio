"""Floating manual condition editor interaction and text preservation."""

from PyQt6 import sip
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionColumn,
    ConditionGroup,
    ConditionOperator,
    ConditionRule,
)


def show_editor(qt_app):
    parent = QWidget()
    layout = QVBoxLayout(parent)
    other = QPushButton("Other", parent)
    layout.addWidget(other)
    editor = ConditionEditor(parent)
    layout.addWidget(editor)
    parent.resize(600, 200)
    parent.show()
    other.setFocus()
    qt_app.processEvents()
    return parent, editor, other


def test_focus_opens_overlay_keeps_multiline_edits_and_escape_closes(qt_app):
    parent, editor, _other = show_editor(qt_app)
    group = ConditionGroup((ConditionRule(ConditionColumn(0, "a", True), ConditionOperator.IS_NULL),))
    editor.apply_group(group)
    original_height = editor.height()
    editor.text.setFocus(Qt.FocusReason.TabFocusReason)
    qt_app.processEvents()
    assert editor.popup.isVisible()
    assert editor.expanded_text.toPlainText() == "[a] IS NULL"
    assert editor.restorable_group() == group
    assert editor.height() == original_height
    assert editor.popup.height() > editor.height()
    value = "[a] IS NULL\nOR [b] = 'text'"
    editor.expanded_text.setPlainText(value)
    assert editor.text.text() == value
    assert editor.restorable_group() is None
    QTest.keyClick(editor.expanded_text, Qt.Key.Key_Escape)
    qt_app.processEvents()
    assert not editor.popup.isVisible()
    assert editor.text.text() == value
    qt_app.processEvents()
    assert not editor.popup.isVisible()
    QTest.mouseClick(editor.text, Qt.MouseButton.LeftButton)
    qt_app.processEvents()
    assert editor.popup.isVisible()
    assert editor.expanded_text.toPlainText() == value
    parent.close()
    qt_app.processEvents()
    assert not editor.popup.isVisible()


def test_popup_closes_outside_and_builder_retains_current_text(qt_app):
    parent, editor, other = show_editor(qt_app)
    QTest.mouseClick(editor.text, Qt.MouseButton.LeftButton)
    qt_app.processEvents()
    assert editor.popup.isVisible()
    editor.expanded_text.setPlainText("[a] = 'manual'")
    QTest.mouseClick(other, Qt.MouseButton.LeftButton)
    qt_app.processEvents()
    assert not editor.popup.isVisible()
    assert editor.text.text() == "[a] = 'manual'"
    opened = []
    editor.builder_requested.connect(lambda: opened.append(editor.text.text()))
    QTest.mouseClick(editor.text, Qt.MouseButton.LeftButton)
    qt_app.processEvents()
    assert editor.popup.isVisible()
    QTest.mouseClick(editor.button, Qt.MouseButton.LeftButton)
    assert not editor.popup.isVisible()
    assert opened == ["[a] = 'manual'"]
    parent.close()


def test_selection_is_transferred_and_overlay_stays_on_screen(qt_app):
    parent, editor, _other = show_editor(qt_app)
    editor.text.setText("[Year] = '2019'")
    editor.text.setSelection(10, 4)
    editor.text.setFocus(Qt.FocusReason.TabFocusReason)
    qt_app.processEvents()
    assert editor.expanded_text.textCursor().selectedText() == "2019"
    available = editor.text.screen().availableGeometry()
    assert available.contains(editor.popup.geometry())
    parent.close()


def test_popup_tracks_external_updates_and_dies_with_editor(qt_app):
    parent, editor, _other = show_editor(qt_app)
    editor.text.setText("first")
    editor.text.setFocus(Qt.FocusReason.TabFocusReason)
    qt_app.processEvents()
    editor.text.setText("replacement")
    assert editor.expanded_text.toPlainText() == "replacement"
    popup = editor.popup
    expanded = editor.expanded_text
    editor.deleteLater()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(popup)
    assert sip.isdeleted(expanded)
    parent.close()
