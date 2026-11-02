"""Shared expression mechanics work without a Reshape editor or grammar."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit

from expo_jbm329.gui.widgets.expression_editor_support import (
    ColumnCompletionSupport,
    qt_text_position,
    underline_diagnostics,
)
from expo_jbm329.services.data_operations.expression_completion import column_completion
from expo_jbm329.services.data_operations.reshape_condition_completion import (
    column_completion as reshape_column_completion,
)


@pytest.mark.parametrize(
    ("text", "prefix"),
    [
        ("IF([Ag", "Ag"),
        ("IF([Age] > 1; [a]]", "a]"),
        ("IF([Age] > 1; 'a [", None),
        ("IF([Age] > 1; 'O''Brien ['; [😀", "😀"),
    ],
)
def test_shared_reference_context_in_formulas(text, prefix):
    context = column_completion(text, len(text))
    assert (context.prefix if context is not None else None) == prefix
    assert reshape_column_completion is column_completion


def test_plain_editor_completion_gate_filter_and_keyboard(qt_app):
    editor = QPlainTextEdit()
    enabled = False
    support = ColumnCompletionSupport(editor, ["Age", "Area", "Age", "a]b"], enabled=lambda: enabled)
    editor.show()
    editor.setFocus()
    editor.insertPlainText("[ag")
    qt_app.processEvents()
    assert not support.completer.popup().isVisible()
    enabled = True
    support.update()
    qt_app.processEvents()
    assert support.completer.popup().isVisible()
    assert support.completer.completionCount() == 1
    assert not support.handle_key(Qt.Key.Key_Left)
    assert support.handle_key(Qt.Key.Key_Tab)
    assert editor.toPlainText() == "[Age]"
    assert not support.completer.popup().isVisible()
    assert not support.handle_key(Qt.Key.Key_Tab)
    editor.setPlainText("[")
    editor.moveCursor(QTextCursor.MoveOperation.End)
    support.update()
    assert support.handle_key(Qt.Key.Key_Escape)
    assert editor.toPlainText() == "["
    editor.close()


def test_completion_replaces_unicode_reference_and_preserves_suffix_and_undo(qt_app):
    editor = QPlainTextEdit()
    support = ColumnCompletionSupport(editor, ["a]b"], enabled=lambda: False)
    value = "'😀' + [ab] + 1"
    editor.setPlainText(value)
    cursor = editor.textCursor()
    cursor.setPosition(qt_text_position(value, value.index("ab") + 1))
    editor.setTextCursor(cursor)
    support.insert("a]b")
    assert editor.toPlainText() == "'😀' + [a]]b] + 1"
    editor.undo()
    assert editor.toPlainText() == value
    editor.close()


def test_diagnostics_preserve_text_caret_and_undo_without_text_changed(qt_app):
    editor = QPlainTextEdit()
    value = "'😀'\n[missing]"
    editor.insertPlainText(value)
    cursor = editor.textCursor()
    cursor.setPosition(2)
    cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    changed = []
    editor.textChanged.connect(lambda: changed.append(True))
    start = value.index("[missing]")
    underline_diagnostics(editor, [(start, len(value)), (len(value), len(value))])
    assert not changed
    assert editor.toPlainText() == value
    assert (editor.textCursor().position(), editor.textCursor().anchor()) == (4, 2)
    selections = editor.extraSelections()
    assert selections[0].cursor.selectedText() == "[missing]"
    assert selections[1].cursor.selectedText() == "]"
    assert selections[0].format.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline
    underline_diagnostics(editor, [])
    assert not editor.extraSelections()
    editor.undo()
    assert editor.toPlainText() == ""
    editor.close()
