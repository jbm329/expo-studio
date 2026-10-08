from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel, QPushButton

from expo_jbm329.gui.dialogs.analysis.analysis_export_dialog import AnalysisExportDialog, ExportSelectionMode


@pytest.mark.parametrize("mode", list(ExportSelectionMode))
def test_export_preview_allows_selection_but_cannot_export(mode):
    dialog = AnalysisExportDialog(mode)
    choices = dialog.findChildren(QCheckBox)
    assert len(choices) == 4
    assert all("Availability will depend" in choice.toolTip() for choice in choices)
    choice = choices[0]
    previous = choice.isChecked()
    choice.click()
    assert choice.isChecked() is not previous
    export = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Export")
    assert not export.isEnabled()
    assert "No file will be created" in export.toolTip()
    assert any("not available outputs" in label.text() for label in dialog.findChildren(QLabel))
    dialog.show()

    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel).click()

    assert not dialog.isVisible()
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_data_preview_has_cohort_and_derived_choices_and_existing_data_formats():
    dialog = AnalysisExportDialog(ExportSelectionMode.DATA)

    assert dialog.windowTitle() == "Export analysis data"
    assert {choice.text(): choice.isChecked() for choice in dialog.findChildren(QCheckBox)} == {
        "Original dataset": False,
        "Analysis dataset": True,
        "Predictions": False,
        "Residuals": False,
    }
    formats = dialog.findChildren(QComboBox)
    assert len(formats) == 1
    assert [formats[0].itemText(index) for index in range(formats[0].count())] == [
        "CSV",
        "Excel workbook (.xlsx)",
        "Parquet",
        "Feather",
        "Pickle",
    ]
    assert any("rows used by the analysis" in label.text() for label in dialog.findChildren(QLabel))


def test_result_preview_separates_workbook_and_standalone_chart_formats():
    dialog = AnalysisExportDialog(ExportSelectionMode.RESULTS)

    assert dialog.windowTitle() == "Export results"
    assert {choice.text(): choice.isChecked() for choice in dialog.findChildren(QCheckBox)} == {
        "Summary / statistics tables": True,
        "Coefficients": False,
        "Model metrics": False,
        "Charts": True,
    }
    formats = dialog.findChildren(QComboBox)
    assert formats[0].count() == 1
    assert formats[0].currentText() == "Excel workbook (.xlsx)"
    assert [formats[1].itemText(index) for index in range(formats[1].count())] == ["PNG", "SVG"]
    assert any(
        "static chart images" in label.text() and "all supported chart variants" in label.text()
        for label in dialog.findChildren(QLabel)
    )
