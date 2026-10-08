from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QPushButton

from expo_jbm329.gui.dialogs.analysis.report_notes_dialog import ReportNotesDialog


def test_notes_dialog_keeps_analysis_name_and_notes_as_plain_text():
    dialog = ReportNotesDialog("<b>Linear Regression</b>")
    heading = next(label for label in dialog.findChildren(QLabel) if label.text() == "<b>Linear Regression</b>")
    assert heading.textFormat() is Qt.TextFormat.PlainText
    assert dialog.notes() == ""

    dialog.findChild(QPlainTextEdit).setPlainText("<script>note</script>\nSecond line")

    assert dialog.notes() == "<script>note</script>\nSecond line"
    assert any("not implemented yet" in label.text() for label in dialog.findChildren(QLabel))


def test_notes_preview_cannot_add_an_entry_and_cancel_rejects():
    dialog = ReportNotesDialog("Linear Regression")
    add_button = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Add to report")
    assert not add_button.isEnabled()
    assert "No analysis or note will be saved" in add_button.toolTip()
    box = dialog.findChild(QDialogButtonBox)
    cancel = box.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel.isEnabled()
    dialog.show()

    cancel.click()

    assert not dialog.isVisible()
    assert dialog.result() == QDialog.DialogCode.Rejected
