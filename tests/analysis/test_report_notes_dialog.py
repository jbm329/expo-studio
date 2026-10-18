from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QPushButton

from expo_jbm329.gui.dialogs.analysis.report_notes_dialog import ReportNotesDialog
from expo_jbm329.services.analysis.report import ReportComponent

COMPONENTS = (
    ReportComponent("summary", "Summary", "table"),
    ReportComponent("charts", "Charts", "chart"),
)


def test_component_and_note_dialog_keeps_user_text_literal():
    dialog = ReportNotesDialog(
        "<b>Linear Regression</b>",
        components=COMPONENTS,
    )
    heading = next(label for label in dialog.findChildren(QLabel) if label.text() == "<b>Linear Regression</b>")
    assert heading.textFormat() is Qt.TextFormat.PlainText
    assert dialog.notes() == ""
    assert dialog.selected_components() == ("summary", "charts")
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == ["Summary", "Charts"]
    assert all(choice.isChecked() for choice in choices)

    dialog.findChild(QPlainTextEdit).setPlainText("<script>note</script>\nSecond line")
    choices[1].setChecked(False)

    assert dialog.notes() == "<script>note</script>\nSecond line"
    assert dialog.selected_components() == ("summary",)


def test_add_dialog_requires_at_least_one_component_and_cancel_rejects():
    dialog = ReportNotesDialog("Linear Regression", components=COMPONENTS)
    add_button = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Add to report")
    assert add_button.isEnabled()
    for choice in dialog.findChildren(QCheckBox):
        choice.setChecked(False)
    assert not add_button.isEnabled()
    box = dialog.findChild(QDialogButtonBox)
    cancel = box.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel.isEnabled()
    dialog.show()

    cancel.click()

    assert not dialog.isVisible()
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_existing_entry_dialog_restores_choices_note_and_supports_removal():
    dialog = ReportNotesDialog(
        "Linear Regression",
        components=COMPONENTS,
        selected_components=("charts",),
        note="Saved note",
        existing=True,
    )
    assert dialog.selected_components() == ("charts",)
    assert dialog.notes() == "Saved note"
    assert any(button.text() == "Save changes" for button in dialog.findChildren(QPushButton))

    remove = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Remove from report")
    remove.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.remove_requested()


def test_correlation_review_shows_old_and_new_configuration_and_prefills_entry():
    dialog = ReportNotesDialog(
        "Correlation — Spearman",
        components=COMPONENTS,
        selected_components=("charts",),
        note="Saved note",
        configuration=("Columns: Age, Income, Score",),
        component_translation_context="CorrelationView",
        review=(
            ("Correlation — Spearman", "Columns: Age, Income"),
            ("Correlation — Spearman", "Columns: Age, Income, Score"),
        ),
        action_label="Replace in report",
    )

    assert dialog.notes() == "Saved note"
    assert dialog.selected_components() == ("charts",)
    assert any("Columns: Age, Income" in label.text() for label in dialog.findChildren(QLabel))
    assert any("Columns: Age, Income, Score" in label.text() for label in dialog.findChildren(QLabel))
    assert any(button.text() == "Replace in report" for button in dialog.findChildren(QPushButton))
    assert not any(button.text() == "Remove from report" for button in dialog.findChildren(QPushButton))
    assert not dialog.remove_requested()
