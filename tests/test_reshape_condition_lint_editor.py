"""Live syntax diagnostics in collapsed and floating condition editors."""

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QHelpEvent, QTextCharFormat
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
from expo_jbm329.gui.dialogs.workflows.reshape.reshape_dialog import ReshapeDialog
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionColumn,
    ConditionGroup,
    ConditionOperator,
    ConditionRule,
    condition_columns,
)
from expo_jbm329.utils.dataset_ref import DatasetRef


def make_editor():
    parent = QWidget()
    layout = QVBoxLayout(parent)
    other = QPushButton("Other", parent)
    layout.addWidget(other)
    editor = ConditionEditor(parent, condition_columns(["a", "😀"]))
    layout.addWidget(editor)
    return parent, editor, other


def finish_lint(editor):
    editor._lint_timer.stop()
    editor._lint_timer.timeout.emit()


def test_pending_validity_error_borders_hints_and_clearing():
    parent, editor, _other = make_editor()
    guidance = editor.text.toolTip()
    assert editor.condition_valid
    editor.text.setText("[a] = 1")
    assert editor.lint_pending
    assert not editor.condition_valid
    finish_lint(editor)
    assert not editor.condition_valid
    assert "#d32f2f" in editor.text.styleSheet()
    assert editor.text.styleSheet() == editor.expanded_text.styleSheet()
    assert "single-quoted" in editor.text.toolTip()
    assert editor.text.toolTip() == editor.expanded_text.toolTip()
    editor.text.setText("[a] = 'anything'")
    assert editor.lint_pending and not editor.condition_valid
    finish_lint(editor)
    assert editor.condition_valid
    assert not editor.text.styleSheet()
    assert not editor.expanded_text.extraSelections()
    assert "anything" in editor.text.toolTip()
    editor.text.clear()
    assert editor.condition_valid
    assert editor.text.toolTip() == guidance
    assert editor.expanded_text.toolTip() == guidance
    parent.close()


def test_utf16_multiline_underline_positions_and_eof():
    parent, editor, _other = make_editor()
    value = "[😀] = 'emoji😀'\nAND [missing] = 'value'"
    editor.text.setText(value)
    assert not editor.validate_now()
    selections = editor.expanded_text.extraSelections()
    assert len(selections) == 1
    assert selections[0].cursor.selectedText() == "[missing]"
    start = value.index("[missing]")
    assert selections[0].cursor.selectionStart() == len(value[:start].encode("utf-16-le")) // 2
    assert selections[0].format.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline
    editor.text.setText("[a] = ")
    editor.validate_now()
    assert editor.diagnostics[0].start == editor.diagnostics[0].end == len("[a] = ")
    assert editor.expanded_text.extraSelections()[0].cursor.selectionEnd() == len("[a] = ")
    parent.close()


def test_expanded_lint_preserves_cursor_selection_and_undo(qt_app, monkeypatch):
    parent, editor, other = make_editor()
    parent.show()
    other.setFocus()
    qt_app.processEvents()
    editor.text.setFocus(Qt.FocusReason.TabFocusReason)
    qt_app.processEvents()
    QTest.keyClicks(editor.expanded_text, "[a] = 12")
    cursor = editor.expanded_text.textCursor()
    before = (cursor.position(), cursor.anchor())
    assert not editor.validate_now()
    cursor = editor.expanded_text.textCursor()
    assert (cursor.position(), cursor.anchor()) == before
    assert editor.expanded_text.document().isUndoAvailable()
    shown = []
    monkeypatch.setattr(
        "expo_jbm329.gui.dialogs.workflows.reshape.condition_editor.QToolTip.showText", lambda *args: shown.append(args)
    )
    viewport = editor.expanded_text.viewport()
    point = QPoint(5, 5)
    event = QHelpEvent(QEvent.Type.ToolTip, point, viewport.mapToGlobal(point))
    QApplication.sendEvent(viewport, event)
    assert "single-quoted" in shown[0][1]
    editor.expanded_text.undo()
    assert editor.text.text() == editor.expanded_text.toPlainText()
    parent.close()


def test_builder_replacement_validates_immediately():
    parent, editor, _other = make_editor()
    editor.text.setText("invalid")
    editor.validate_now()
    assert editor.diagnostics
    editor.apply_group(ConditionGroup((ConditionRule(ConditionColumn(0, "a", True), ConditionOperator.IS_NULL),)))
    assert editor.condition_valid
    assert not editor.diagnostics
    assert not editor._lint_timer.isActive()
    assert editor.restorable_group() is not None
    parent.close()


def test_disposing_pending_editor_cancels_owned_timer(qt_app):
    parent, editor, _other = make_editor()
    editor.text.setText("[missing] = 'x'")
    timer = editor._lint_timer
    assert timer.isActive()
    editor.deleteLater()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(timer)
    parent.close()


def test_error_tooltip_escapes_column_names():
    parent, editor, _other = make_editor()
    editor.text.setText("[<b>missing & column</b>] = 'x'")
    editor.validate_now()
    assert "&lt;b&gt;missing &amp; column&lt;/b&gt;" in editor.text.toolTip()
    assert "<b>missing" not in editor.text.toolTip()
    parent.close()


def test_unmatched_closing_parenthesis_hint_and_underline():
    parent, editor, _other = make_editor()
    editor.text.setText("([a] = 'x') AND [a] >= '18')")
    assert not editor.validate_now()
    assert "Unmatched closing parenthesis" in editor.text.toolTip()
    assert "Add a matching opening ( or remove this )" in editor.expanded_text.toolTip()
    selections = editor.expanded_text.extraSelections()
    assert len(selections) == 1
    assert selections[0].cursor.selectedText() == ")"
    assert selections[0].cursor.selectionEnd() == len(editor.text.text())
    parent.close()


def test_misspelled_group_connector_hint_and_underline():
    parent, editor, _other = make_editor()
    editor.text.setText("(([a] = 'x' OR [a] = 'y') AN [a] > '17')")
    assert not editor.validate_now()
    assert "Expected AND, OR or a closing parenthesis )." in editor.text.toolTip()
    assert editor.expanded_text.toolTip() == editor.text.toolTip()
    selections = editor.expanded_text.extraSelections()
    assert len(selections) == 1
    assert selections[0].cursor.selectedText() == "AN"
    parent.close()


def test_misaligned_quotes_hint_explains_possible_earlier_mistake():
    parent, editor, _other = make_editor()
    editor.text.setText("(([a] = 'AKUT OR [a] = 'True') AND [a] < '2000')")
    assert not editor.validate_now()
    assert "Unterminated quoted value." in editor.text.toolTip()
    assert "missing or misplaced single quote earlier in the condition" in editor.text.toolTip()
    assert editor.expanded_text.toolTip() == editor.text.toolTip()
    editor.text.setText("(([a] = 'AKUT' OR [a] = 'True') AND [a] < '2000')")
    assert editor.validate_now()
    parent.close()


def test_dialog_aggregates_pending_errors_removal_and_builder_readiness():
    dialog = ReshapeDialog(
        parent=None,
        source_dataset=DatasetRef("source", "Source", 2, 2),
        source_columns=("a", "b"),
        source_dtypes=("int64", "string"),
        numeric_column_positions=(0,),
        datetime_column_positions=(),
    )
    first = dialog.metrics.cellWidget(0, 3)
    dialog.metrics.cellWidget(0, 2).setCurrentIndex(1)
    assert first.button.isEnabled()
    assert dialog.conditions_valid
    dialog.add_metric_button.click()
    second = dialog.metrics.cellWidget(1, 3)
    dialog.metrics.cellWidget(1, 2).setCurrentIndex(1)
    first.text.setText("[b] = 'not a known value'")
    assert not dialog.conditions_valid
    assert dialog.validate_conditions()
    assert not dialog.apply_button.isEnabled()
    second.text.setText("[missing] = 'x'")
    finish_lint(second)
    assert not dialog.conditions_valid
    assert "Correct condition errors" in dialog.apply_button.toolTip()
    assert second.button.isEnabled()
    assert dialog.add_metric_button.isEnabled()
    dialog.metrics.selectRow(1)
    dialog.remove_metric_button.click()
    assert dialog.conditions_valid
    assert not dialog.apply_button.isEnabled()
    assert "UI only" in dialog.apply_button.toolTip()
    dialog.close()


def test_dialog_passes_source_dtypes_to_manual_linting():
    dialog = ReshapeDialog(
        parent=None,
        source_dataset=DatasetRef("source", "Source", 2, 3),
        source_columns=("age", "flag", "code"),
        source_dtypes=("Int64", "boolean", "object"),
        numeric_column_positions=(0,),
        datetime_column_positions=(),
    )
    editor = dialog.metrics.cellWidget(0, 3)
    editor.text.setText("[age] >= 18 AND [flag] = True AND [code] = '0018'")
    assert dialog.validate_conditions()
    editor.text.setText("[age] = False")
    assert not dialog.validate_conditions()
    assert "Expected a number" in editor.text.toolTip()
    editor.text.setText("[flag] = 1")
    assert not dialog.validate_conditions()
    assert "Expected True, False" in editor.text.toolTip()
    editor.text.setText("[code] = 18")
    assert not dialog.validate_conditions()
    editor.text.setText("[age] = 'anything' AND [flag] = 'legacy'")
    assert dialog.validate_conditions()
    dialog.close()
