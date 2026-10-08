from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QLineEdit, QListWidget, QPlainTextEdit, QPushButton

from expo_jbm329.gui.dialogs.analysis.report_page import ReportPage


def test_report_page_starts_with_empty_details_and_no_entries():
    page = ReportPage()

    assert page.report_title() == ""
    assert page.report_description() == ""
    assert page.findChild(QListWidget).count() == 0
    assert any("No analyses have been added" in label.text() for label in page.findChildren(QLabel))


def test_report_page_collects_only_plain_text_details():
    page = ReportPage()
    page.findChild(QLineEdit).setText("<b>Report title</b>")
    page.findChild(QPlainTextEdit).setPlainText("<script>description</script>\nSecond line")

    assert page.report_title() == "<b>Report title</b>"
    assert page.report_description() == "<script>description</script>\nSecond line"
    assert page.findChild(QListWidget).count() == 0


def test_report_processing_controls_are_disabled_and_explained():
    page = ReportPage()
    buttons = page.findChildren(QPushButton)

    assert {button.text() for button in buttons} == {
        "Move up",
        "Move down",
        "Edit note",
        "Remove",
        "Generate HTML report",
    }
    assert all(not button.isEnabled() and "Not implemented yet" in button.toolTip() for button in buttons)
