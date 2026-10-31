"""Floating manual condition editor interaction and text preservation."""

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
from expo_jbm329.services.data_operations.reshape_condition_import import (
    ConditionBuilderDiagnostic,
    condition_group_from_text,
)
from expo_jbm329.services.data_operations.reshape_condition_lint import ConditionLintCode, parse_condition
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionColumn,
    ConditionGroup,
    ConditionOperator,
    ConditionProblem,
    ConditionRule,
    ConditionValue,
    condition_columns,
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


def test_collapsed_field_shows_start_and_full_literal_content_tooltip(qt_app):
    parent, editor, _other = show_editor(qt_app)
    guidance = editor.text.toolTip()
    content = "[Column] = '<b>literal</b>'\nOR " + "[Other] = 'value' " * 50
    editor.text.setText(content)
    assert editor.text.cursorPosition() == 0
    assert "&lt;b&gt;literal&lt;/b&gt;" in editor.text.toolTip()
    assert "<br>" in editor.text.toolTip()
    assert editor.text.toolTip() == editor.expanded_text.toolTip()
    editor.text.setFocus(Qt.FocusReason.TabFocusReason)
    qt_app.processEvents()
    editor.expanded_text.moveCursor(editor.expanded_text.textCursor().MoveOperation.End)
    QTest.keyClicks(editor.expanded_text, " changed")
    assert editor.text.text().endswith(" changed")
    QTest.keyClick(editor.expanded_text, Qt.Key.Key_Escape)
    qt_app.processEvents()
    assert editor.text.cursorPosition() == 0
    assert " changed" in editor.text.toolTip()
    editor.text.clear()
    assert editor.text.toolTip() == guidance
    assert editor.expanded_text.toolTip() == guidance
    parent.close()


def test_builder_state_imports_current_text_without_waiting_for_lint(qt_app):
    parent = QWidget()
    columns = condition_columns(["a", "b", "amount", "flag"], ["object", "string", "float64", "boolean"])
    editor = ConditionEditor(parent, columns)
    value = "[a] = 'manual' OR [amount] >= 1.00 AND [flag] = true"
    editor.text.setText(value)
    assert editor.lint_pending
    assert editor.builder_state() == condition_group_from_text(value, columns)
    assert editor.builder_state().group is not None
    assert editor.text.text() == editor.expanded_text.toPlainText() == value
    assert editor.restorable_group() is None
    parent.close()


def test_builder_state_retains_unchanged_group_and_original_value_identity(qt_app):
    parent = QWidget()
    columns = condition_columns(["date"], ["datetime64[ns]"])
    editor = ConditionEditor(parent, columns)
    group = ConditionGroup((
        ConditionGroup((ConditionRule(columns[0], ConditionOperator.EQUAL, (ConditionValue("date", "2026-10-31"),)),)),
    ))
    editor.apply_group(group)
    result = editor.builder_state()
    assert result.diagnostic is None
    assert result.group is group
    editor.text.setText(" " + editor.text.text())
    imported = editor.builder_state()
    assert imported.diagnostic is None
    assert imported.group is not None
    assert imported.group != group
    assert imported == condition_group_from_text(editor.text.text(), columns)
    parent.close()


@pytest.mark.parametrize("value", ["", " \n\t"])
def test_builder_state_blank_text_does_not_fall_back_to_previous_group(qt_app, value):
    parent = QWidget()
    columns = condition_columns(["a"])
    editor = ConditionEditor(parent, columns)
    editor.apply_group(ConditionGroup((ConditionRule(columns[0], ConditionOperator.IS_NULL),)))
    editor.text.setText(value)
    result = editor.builder_state()
    assert result.group is None
    assert result.diagnostic is None
    assert editor.text.text() == value
    parent.close()


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("[a] = 'unfinished", ConditionLintCode.QUOTE),
        ("[missing] = 'x'", ConditionLintCode.UNKNOWN_COLUMN),
        ("[a] IN ('x', 'x')", ConditionProblem.INVALID_RULE),
    ],
)
def test_builder_state_reports_current_error_without_restoring_stale_group(qt_app, value, code):
    parent = QWidget()
    columns = condition_columns(["a"])
    editor = ConditionEditor(parent, columns)
    editor.apply_group(ConditionGroup((ConditionRule(columns[0], ConditionOperator.IS_NULL),)))
    editor.text.setText(value)
    result = editor.builder_state()
    assert result.group is None
    assert result.diagnostic is not None
    assert result.diagnostic.code == code
    if isinstance(result.diagnostic, ConditionBuilderDiagnostic):
        assert not parse_condition(value, columns).diagnostics
    else:
        assert result.diagnostic == parse_condition(value, columns).diagnostics[0]
    assert editor.text.text() == editor.expanded_text.toPlainText() == value
    parent.close()


def test_builder_state_reads_edits_from_the_expanded_editor(qt_app):
    parent = QWidget()
    columns = condition_columns(["a"])
    editor = ConditionEditor(parent, columns)
    editor.expanded_text.setPlainText("[a] = 'first'")
    first = editor.builder_state()
    editor.expanded_text.setPlainText("[a] = 'second'")
    second = editor.builder_state()
    assert first != second
    assert second == condition_group_from_text("[a] = 'second'", columns)
    assert editor.text.text() == "[a] = 'second'"
    parent.close()


def test_import_diagnostic_focus_selects_utf16_span_without_changing_text(qt_app):
    parent, editor, _other = show_editor(qt_app)
    value = "[emoji] = '😀'\nAND [missing] IS NULL"
    editor.text.setText(value)
    result = editor.builder_state(condition_columns(["emoji"]))
    assert result.diagnostic is not None
    editor.focus_builder_diagnostic(result.diagnostic)
    qt_app.processEvents()
    assert editor.popup.isVisible()
    assert editor.expanded_text.hasFocus()
    cursor = editor.expanded_text.textCursor()
    assert cursor.selectedText() == "[missing]"
    assert cursor.selectionStart() == len(value[: value.index("[missing]")].encode("utf-16-le")) // 2
    assert editor.text.text() == editor.expanded_text.toPlainText() == value
    parent.close()


def test_import_diagnostic_focus_positions_cursor_at_eof(qt_app):
    parent, editor, _other = show_editor(qt_app)
    value = "[a] = 'x' AND "
    editor.text.setText(value)
    result = editor.builder_state(condition_columns(["a"]))
    assert result.diagnostic is not None
    editor.focus_builder_diagnostic(result.diagnostic)
    qt_app.processEvents()
    assert editor.expanded_text.textCursor().position() == len(value)
    assert not editor.expanded_text.textCursor().hasSelection()
    assert editor.text.text() == value
    parent.close()
