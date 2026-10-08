from __future__ import annotations

import pandas as pd
import pytest
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel, QPushButton

from expo_jbm329.gui.dialogs.analysis.analysis_export_dialog import AnalysisExportDialog, ExportSelectionMode
from expo_jbm329.services.analysis.overview import OverviewExportFormat, OverviewExportTable, analyze_dataset_overview


def test_overview_formats_preserve_choices_and_disable_multi_table_single_file_export():
    overview = analyze_dataset_overview(pd.DataFrame({"a": [1, 2]}))
    dialog = AnalysisExportDialog(ExportSelectionMode.DATA, overview=overview)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == ["Columns metadata", "Sample (first 100 rows)"]
    export = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Export")
    formats = dialog.findChild(QComboBox)
    assert export.isEnabled()
    choices[1].setChecked(True)
    assert not export.isEnabled()
    assert dialog.export_request() is None
    formats.setCurrentIndex(1)
    assert export.isEnabled()
    request = dialog.export_request()
    assert request.result is overview
    assert request.tables == (OverviewExportTable.COLUMNS, OverviewExportTable.SAMPLE)
    assert request.format is OverviewExportFormat.EXCEL
    formats.setCurrentIndex(2)
    assert all(choice.isChecked() for choice in choices)
    assert not export.isEnabled()
    assert any("Choose exactly one table" in label.text() for label in dialog.findChildren(QLabel))
    choices[0].setChecked(False)
    assert export.isEnabled()
    assert dialog.export_request().format is OverviewExportFormat.BINARY
    choices[1].setChecked(False)
    assert not export.isEnabled()


@pytest.mark.parametrize("source", [None, pd.DataFrame(), pd.DataFrame({"a": pd.Series(dtype="int64")})])
def test_overview_empty_and_missing_results_have_explicit_disabled_tables(source):
    result = analyze_dataset_overview(source) if source is not None else None
    dialog = AnalysisExportDialog(ExportSelectionMode.DATA, overview=result, overview_mode=True)
    choices = dialog.findChildren(QCheckBox)
    assert len(choices) == 2
    assert not choices[1].isEnabled()
    assert bool(choices[0].isEnabled()) == (source is not None and source.shape[1] > 0)
    assert ("empty" if source is not None else "Run Overview") in choices[1].toolTip()


def test_overview_result_mode_remains_preview_even_with_overview_payload():
    result = analyze_dataset_overview(pd.DataFrame({"a": [1]}))
    dialog = AnalysisExportDialog(ExportSelectionMode.RESULTS, overview=result)
    assert dialog.export_request() is None
    export = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Export")
    assert not export.isEnabled()


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
