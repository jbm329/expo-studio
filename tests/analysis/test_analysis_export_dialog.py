from __future__ import annotations

import pandas as pd
import pytest
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGroupBox, QLabel, QPushButton

from expo_jbm329.gui.dialogs.analysis.analysis_export_dialog import AnalysisExportDialog
from expo_jbm329.services.analysis.overview import OverviewExportFormat, OverviewExportTable, analyze_dataset_overview


def test_overview_formats_preserve_choices_and_disable_multi_table_single_file_export():
    overview = analyze_dataset_overview(pd.DataFrame({"a": [1, 2]}))
    dialog = AnalysisExportDialog(overview=overview)
    assert [group.title() for group in dialog.findChildren(QGroupBox)] == ["Data", "Results"]
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == ["Columns metadata", "Sample (first 100 rows)", "Summary"]
    assert not choices[2].isEnabled()
    assert not choices[2].isChecked()
    assert "not implemented" in choices[2].toolTip()
    export = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Export")
    formats = dialog.findChild(QComboBox)
    assert export.isEnabled()
    choices[1].setChecked(True)
    assert not export.isEnabled()
    assert "exactly one table" in export.toolTip()
    assert dialog.export_request() is None
    formats.setCurrentIndex(1)
    assert export.isEnabled()
    request = dialog.export_request()
    assert request.result is overview
    assert request.tables == (OverviewExportTable.COLUMNS, OverviewExportTable.SAMPLE)
    assert request.format is OverviewExportFormat.EXCEL
    formats.setCurrentIndex(2)
    assert all(choice.isChecked() for choice in choices[:2])
    assert not export.isEnabled()
    assert "exactly one table" in export.toolTip()
    assert any("Choose exactly one table" in label.text() for label in dialog.findChildren(QLabel))
    choices[0].setChecked(False)
    assert export.isEnabled()
    assert dialog.export_request().format is OverviewExportFormat.BINARY
    formats.setCurrentIndex(0)
    assert export.isEnabled()
    assert dialog.export_request().tables == (OverviewExportTable.SAMPLE,)
    assert dialog.export_request().format is OverviewExportFormat.CSV
    choices[1].setChecked(False)
    for index in range(formats.count()):
        formats.setCurrentIndex(index)
        assert not export.isEnabled()
        assert "Select at least one" in export.toolTip()


@pytest.mark.parametrize("source", [None, pd.DataFrame(), pd.DataFrame({"a": pd.Series(dtype="int64")})])
def test_overview_empty_and_missing_results_have_explicit_disabled_tables(source):
    result = analyze_dataset_overview(source) if source is not None else None
    dialog = AnalysisExportDialog(overview=result, overview_mode=True)
    choices = dialog.findChildren(QCheckBox)
    assert len(choices) == 3
    assert not choices[1].isEnabled()
    assert bool(choices[0].isEnabled()) == (source is not None and source.shape[1] > 0)
    assert ("empty" if source is not None else "Run Overview") in choices[1].toolTip()
    assert not choices[2].isEnabled()
    assert "not implemented" in choices[2].toolTip()


def test_export_preview_groups_all_unavailable_choices_and_cannot_export():
    dialog = AnalysisExportDialog()
    groups = dialog.findChildren(QGroupBox)
    assert [group.title() for group in groups] == ["Data", "Results"]
    assert [choice.text() for choice in groups[0].findChildren(QCheckBox)] == [
        "Original dataset",
        "Analysis dataset",
        "Predictions",
        "Residuals",
    ]
    assert [choice.text() for choice in groups[1].findChildren(QCheckBox)] == [
        "Summary / statistics tables",
        "Coefficients",
        "Model metrics",
        "Charts",
    ]
    choices = dialog.findChildren(QCheckBox)
    assert all(not choice.isEnabled() and not choice.isChecked() for choice in choices)
    assert all("Not implemented" in choice.toolTip() for choice in choices)
    export = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Export")
    formats = dialog.findChild(QComboBox)
    assert formats.count() == 3
    for index in range(formats.count()):
        formats.setCurrentIndex(index)
        assert not export.isEnabled()
        assert dialog.export_request() is None
        assert "No file will be created" in export.toolTip()
    assert any("No file will be created" in label.text() for label in dialog.findChildren(QLabel))


@pytest.mark.parametrize("overview_mode", [True, False])
def test_export_selection_cancel_rejects_dialog(overview_mode):
    dialog = AnalysisExportDialog(overview_mode=overview_mode)
    dialog.show()
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel).click()
    assert not dialog.isVisible()
    assert dialog.result() == QDialog.DialogCode.Rejected
