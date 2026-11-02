"""Derived formula completion, positioned lint feedback and dialog acceptance."""

import pandas as pd
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QHelpEvent, QTextCharFormat, QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog

from expo_jbm329.gui.dialogs.workflows.derived_column.derived_column_dialog import DerivedColumnDialog
from expo_jbm329.gui.dialogs.workflows.derived_column.month_labels import capture_month_labels
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
    validate_derived_column_spec,
)


def make_dialog(frame):
    def validate(name, text):
        result = validate_derived_column_spec(frame, DerivedColumnSpec(name, text))
        return result, "Valid formula." if result.ok else result.error.code

    return DerivedColumnDialog(df=frame, validate_callback=validate)


@pytest.mark.parametrize(
    "formula",
    [
        "IF([Vehicle] IN('BMW', 'Volvo'); 'Cars'; 'Other')",
        "IF([Column1] IS NULL; 'Empty'; [Column1])",
        "IF([Age] IS NULL; 0; [Age])",
    ],
)
def test_dialog_accepts_conditional_formulas_without_insertion_controls(formula, widget_language):
    frame = pd.DataFrame({
        "Vehicle": pd.Series(["BMW", None], dtype="string"),
        "Column1": pd.Series(["text", None], dtype="string"),
        "Age": pd.Series([1, None], dtype="Int64"),
    })

    dialog = make_dialog(frame)
    dialog._column_name_edit.setText("Group")
    dialog._formula_edit.setPlainText(formula)
    assert dialog._ok_button.isEnabled()
    assert not dialog.findChildren(QComboBox)
    assert not hasattr(dialog, "_insert_btn")
    dialog._on_accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.get_result() == DerivedColumnSpec("Group", formula, month_labels=capture_month_labels())


def test_text_only_dialog_completes_text_columns_and_rejects_without_a_result():
    frame = pd.DataFrame({"Vehicle": ["BMW"]})
    dialog = make_dialog(frame)
    assert dialog._formula_edit.completer.model().stringList() == ["Vehicle"]
    assert dialog._formula_edit.toPlainText() == ""
    dialog.reject()
    assert dialog.get_result() is None


def test_invalid_formula_disables_accept_and_presents_validation_error():
    frame = pd.DataFrame({"Age": [1]})
    dialog = make_dialog(frame)
    dialog._column_name_edit.setText("Group")
    dialog._formula_edit.setPlainText("IF([Age] IS NULL; 'Empty'; [Age])")
    assert not dialog._ok_button.isEnabled()
    assert "incompatible_branch_types" in dialog._validation_label.text()
    assert dialog._formula_edit.extraSelections()
    dialog._on_accept()
    assert dialog.get_result() is None


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab])
def test_completion_accepts_before_dialog_and_escapes_column_names(qt_app, key):
    dialog = make_dialog(pd.DataFrame({"a]b": [1], "Age": [20], "Vehicle": ["BMW"]}))
    dialog._column_name_edit.setText("Group")
    dialog.show()
    editor = dialog._formula_edit
    editor.setFocus()
    QTest.keyClicks(editor, "[a]]")
    qt_app.processEvents()
    assert editor.completer.popup().isVisible()
    assert editor.completer.completionCount() == 1
    QTest.keyClick(editor, key)
    assert editor.toPlainText() == "[a]]b]"
    assert not editor.completer.popup().isVisible()
    assert dialog.isVisible()
    assert dialog.get_result() is None
    dialog.close()


def test_completion_filters_all_supported_unique_columns():
    frame = pd.DataFrame([[1, 2, 3, 4, "BMW", True, pd.Timestamp("2020-01-01")]])
    frame.columns = ["dup", "dup", 2, "Age", "Vehicle", "Flag", "Date"]
    dialog = make_dialog(frame)
    assert dialog._formula_edit.completer.model().stringList() == ["Age", "Date", "Flag", "Vehicle"]
    dialog.close()


def test_datetime_completion_and_positioned_time_function_validation(qt_app):
    dialog = make_dialog(pd.DataFrame({"When": pd.to_datetime(["2026-01-01"]), "Age": [1]}))
    dialog._column_name_edit.setText("Year")
    dialog.show()
    editor = dialog._formula_edit
    editor.setFocus()
    QTest.keyClicks(editor, "YEAR([Wh")
    assert editor.completer.completionCount() == 1
    assert editor.completer.popup().isVisible()
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    QTest.keyClicks(editor, ")")
    assert editor.toPlainText() == "YEAR([When])"
    assert dialog._ok_button.isEnabled()
    assert not editor.extraSelections()
    editor.setPlainText("YEAR([Age])")
    assert not dialog._ok_button.isEnabled()
    assert editor.extraSelections()[0].cursor.selectedText() == "YEAR"
    assert "datetime_operand_required" in editor.toolTip()
    dialog.close()


def test_completion_arrow_and_mouse_acceptance_after_unicode(qt_app):
    dialog = make_dialog(pd.DataFrame({"Age": [1], "Area": [2], "😀 Date": ["today"]}))
    dialog.show()
    editor = dialog._formula_edit
    editor.setFocus()
    editor.setPlainText("IF(TRUE; '😀'; [")
    editor.moveCursor(QTextCursor.MoveOperation.End)
    popup = editor.completer.popup()
    assert popup.isVisible()
    QTest.keyClick(popup, Qt.Key.Key_Down)
    selected = popup.currentIndex().data()
    QTest.keyClick(popup, Qt.Key.Key_Return)
    assert editor.toPlainText() == f"IF(TRUE; '😀'; [{selected}]"
    assert dialog.isVisible()
    editor.setPlainText("IF(TRUE; '😀'; [")
    editor.moveCursor(QTextCursor.MoveOperation.End)
    index = editor.completer.completionModel().index(2, 0)
    QTest.mouseClick(popup.viewport(), Qt.MouseButton.LeftButton, pos=popup.visualRect(index).center())
    qt_app.processEvents()
    assert editor.toPlainText() == "IF(TRUE; '😀'; [😀 Date]"
    assert not popup.isVisible()
    assert dialog.isVisible()
    dialog.close()


def test_completion_ignores_literals_and_no_matches_and_escape_keeps_dialog_open(qt_app):
    dialog = make_dialog(pd.DataFrame({"Vehicle": ["BMW"]}))
    dialog.show()
    editor = dialog._formula_edit
    editor.setFocus()
    QTest.keyClicks(editor, "[")
    qt_app.processEvents()
    assert editor.completer.popup().isVisible()
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    assert not editor.completer.popup().isVisible()
    assert dialog.isVisible()
    for text in ("IF(TRUE; 'O''Brien ['; 'Other')", "[nonexistent"):
        editor.setPlainText(text)
        editor.moveCursor(QTextCursor.MoveOperation.End)
        assert not editor.completer.popup().isVisible()
    dialog.close()


def test_lint_uses_raw_multiline_utf16_positions_and_clears_after_correction(qt_app):
    dialog = make_dialog(pd.DataFrame({"😀": [1]}))
    dialog._column_name_edit.setText("Group")
    editor = dialog._formula_edit
    text = "  [😀] +\n [missing]"
    editor.setPlainText(text)
    selection = editor.extraSelections()[0]
    assert selection.cursor.selectedText() == "[missing]"
    assert selection.cursor.selectionStart() == len(text[: text.index("[missing]")].encode("utf-16-le")) // 2
    assert selection.format.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline
    assert "unknown_column" in editor.toolTip()
    editor.setPlainText("  [😀] +\n 1")
    assert not editor.extraSelections()
    assert not editor.toolTip()
    assert dialog._ok_button.isEnabled()
    editor.setPlainText("[😀] + ")
    assert editor.extraSelections()[0].cursor.selectionEnd() == len("[😀] + ".encode("utf-16-le")) // 2
    dialog.close()


def test_output_name_errors_are_not_underlined_as_formula_errors():
    dialog = make_dialog(pd.DataFrame({"Age": [1]}))
    dialog._column_name_edit.setText("Age")
    dialog._formula_edit.setPlainText("[Age] + 1")
    assert "output_column_exists" in dialog._validation_label.text()
    assert not dialog._formula_edit.extraSelections()
    assert not dialog._formula_edit.toolTip()
    assert not dialog._ok_button.isEnabled()
    dialog._column_name_edit.setText("Group")
    assert dialog._ok_button.isEnabled()
    dialog.close()


def test_lint_preserves_caret_selection_and_undo_and_escapes_tooltip(qt_app, monkeypatch):
    dialog = make_dialog(pd.DataFrame({"Age": [1]}))
    dialog._column_name_edit.setText("Group")
    editor = dialog._formula_edit
    text = "[<b>missing & column</b>]"
    editor.insertPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(2)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    dialog._update_validation()
    assert (editor.textCursor().position(), editor.textCursor().anchor()) == (5, 2)
    assert editor.document().isUndoAvailable()
    shown = []
    monkeypatch.setattr(
        "expo_jbm329.gui.dialogs.workflows.derived_column.formula_editor.QToolTip.showText",
        lambda *args: shown.append(args),
    )
    viewport = editor.viewport()
    point = QPoint(5, 5)
    event = QHelpEvent(QEvent.Type.ToolTip, point, viewport.mapToGlobal(point))
    QApplication.sendEvent(viewport, event)
    error = validate_derived_column_spec(pd.DataFrame({"Age": [1]}), DerivedColumnSpec("Group", text)).error
    editor.set_diagnostic(error, text)
    assert "&lt;b&gt;missing &amp; column&lt;/b&gt;" in editor.toolTip()
    assert shown
    editor.undo()
    assert editor.toPlainText() == ""
    assert not editor.extraSelections()
    dialog.close()


def test_dialog_hide_and_disposal_dismiss_completion(qt_app):
    dialog = make_dialog(pd.DataFrame({"Age": [1]}))
    dialog.show()
    editor = dialog._formula_edit
    editor.setFocus()
    QTest.keyClicks(editor, "[")
    qt_app.processEvents()
    popup = editor.completer.popup()
    assert popup.isVisible()
    dialog.reject()
    assert not popup.isVisible()
    support = editor._completion
    dialog.deleteLater()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(support)


def test_accept_rechecks_current_validation_before_creating_result():
    frame = pd.DataFrame({"Age": [1]})
    dialog = make_dialog(frame)
    dialog._column_name_edit.setText("Group")
    dialog._formula_edit.setPlainText("[Age] + 1")
    assert dialog._ok_button.isEnabled()
    frame["Group"] = 0
    dialog._on_accept()
    assert dialog.get_result() is None
    assert not dialog._ok_button.isEnabled()
    assert "output_column_exists" in dialog._validation_label.text()
    dialog.close()
