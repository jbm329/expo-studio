from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
from PyQt6.QtCore import Qt, QTranslator
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QPushButton,
)

from expo_jbm329.gui.dialogs.analysis.analysis_export_dialog import AnalysisExportDialog
from expo_jbm329.services.analysis.correlation import CorrelationMethod, analyze_correlation_matrix
from expo_jbm329.services.analysis.correlation_export import CorrelationExportComponent, CorrelationExportSnapshot
from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportComponent, HypothesisExportRequest
from expo_jbm329.services.analysis.overview import OverviewExportFormat, OverviewExportTable, analyze_dataset_overview
from expo_jbm329.services.analysis.statistics import (
    StatisticsExportFormat,
    StatisticsExportTable,
    analyze_descriptive_statistics,
)
from tests.analysis.test_hypothesis_export import chi_snapshot, group_snapshot, paired_snapshot


def _correlation_snapshot() -> CorrelationExportSnapshot:
    frame = pd.DataFrame({"first column": [1.0, 2.0, 3.0], "second column": [2.0, 4.0, 5.0]})
    matrix = analyze_correlation_matrix(frame, tuple(frame.columns), CorrelationMethod.SPEARMAN)
    assert matrix is not None
    return CorrelationExportSnapshot(matrix, frame.copy(deep=True))


def test_overview_formats_preserve_choices_and_disable_multi_table_single_file_export():
    overview = analyze_dataset_overview(pd.DataFrame({"a": [1, 2]}))
    dialog = AnalysisExportDialog(overview=overview)
    assert [group.title() for group in dialog.findChildren(QGroupBox)] == ["Data", "Results"]
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == ["Columns metadata", "Sample (first 100 rows)", "Summary"]
    assert choices[2].isEnabled()
    assert not choices[2].isChecked()
    assert "high-missing-value warnings" in choices[2].toolTip()
    export = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Export")
    formats = dialog.findChild(QComboBox)
    assert formats.currentData() is OverviewExportFormat.EXCEL
    assert export.isEnabled()
    choices[1].setChecked(True)
    assert export.isEnabled()
    formats.setCurrentIndex(formats.findData(OverviewExportFormat.CSV))
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
    choices[2].setChecked(True)
    for format_choice in (OverviewExportFormat.CSV, OverviewExportFormat.BINARY):
        formats.setCurrentIndex(formats.findData(format_choice))
        assert export.isEnabled()
        assert dialog.export_request().tables == (OverviewExportTable.SUMMARY,)
        assert dialog.export_request().format is format_choice
    choices[2].setChecked(False)
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
    assert choices[2].isEnabled() is (source is not None)
    if source is None:
        assert "Run Overview" in choices[2].toolTip()


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
    assert formats.currentData() is OverviewExportFormat.EXCEL
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


def test_statistics_format_switching_preserves_tables_and_charts_selection():
    result = analyze_descriptive_statistics(pd.DataFrame({"number": [1, 2, 3], "group": ["A", "B", "A"]}))
    dialog = AnalysisExportDialog(statistics=result)
    choices = dialog.findChildren(QCheckBox)
    by_text = {choice.text(): choice for choice in choices}
    formats = dialog.findChild(QComboBox)
    export = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Export")

    assert formats.currentData() is StatisticsExportFormat.EXCEL
    assert set(by_text) == {"Continuous", "Categorical", "Charts"}
    assert by_text["Continuous"].isChecked()
    by_text["Categorical"].setChecked(True)
    by_text["Charts"].setChecked(True)
    request = dialog.export_request()
    assert request.tables == (
        StatisticsExportTable.CONTINUOUS,
        StatisticsExportTable.CATEGORICAL,
        StatisticsExportTable.CHARTS,
    )
    assert request.format is StatisticsExportFormat.EXCEL

    formats.setCurrentIndex(formats.findData(StatisticsExportFormat.CSV))
    assert not export.isEnabled()
    assert by_text["Charts"].isChecked()
    assert "only in Excel" in export.toolTip()
    assert dialog.export_request() is None

    by_text["Charts"].setChecked(False)
    assert not export.isEnabled()
    assert "exactly one table" in export.toolTip()
    by_text["Categorical"].setChecked(False)
    assert export.isEnabled()
    assert dialog.export_request().tables == (StatisticsExportTable.CONTINUOUS,)

    formats.setCurrentIndex(formats.findData(StatisticsExportFormat.BINARY))
    assert dialog.export_request().format is StatisticsExportFormat.BINARY
    formats.setCurrentIndex(formats.findData(StatisticsExportFormat.EXCEL))
    assert dialog.export_request().tables == (StatisticsExportTable.CONTINUOUS,)


def test_statistics_charts_are_disabled_without_numeric_columns():
    result = analyze_descriptive_statistics(pd.DataFrame({"group": ["A", "B", "A"]}))
    dialog = AnalysisExportDialog(statistics=result)
    by_text = {choice.text(): choice for choice in dialog.findChildren(QCheckBox)}

    assert by_text["Categorical"].isEnabled()
    assert not by_text["Continuous"].isEnabled()
    assert not by_text["Charts"].isEnabled()
    by_text["Categorical"].setChecked(True)
    assert dialog.export_request().tables == (StatisticsExportTable.CATEGORICAL,)


@pytest.mark.parametrize(
    "factory,title",
    [
        (group_snapshot, "Group summary"),
        (chi_snapshot, "Contingency table"),
        (paired_snapshot, "Measurement summary"),
    ],
)
def test_hypothesis_dialog_names_applied_test_columns_and_preserves_choices(factory, title):
    snapshot = factory()
    dialog = AnalysisExportDialog(hypothesis=snapshot)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == [title, "Test results", "Charts"]
    identity = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("Applied test:"))
    assert identity.textFormat() is Qt.TextFormat.PlainText
    assert " / ".join(snapshot.columns) in identity.text()
    assert "not the original dataset" in dialog.findChildren(QLabel)[0].text()
    formats = dialog.findChild(QComboBox)
    assert formats.currentData() is StatisticsExportFormat.EXCEL
    assert isinstance(dialog.export_request(), HypothesisExportRequest)
    for choice in choices:
        choice.setChecked(True)
    for format_choice in (StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY):
        formats.setCurrentIndex(formats.findData(format_choice))
        assert dialog.export_request() is None
        assert all(choice.isChecked() for choice in choices)
        assert "only in Excel" in dialog._export_button.toolTip()
    choices[2].setChecked(False)
    assert dialog.export_request() is None
    assert "exactly one table" in dialog._export_button.toolTip()
    choices[0].setChecked(False)
    assert dialog.export_request().components == (HypothesisExportComponent.TEST_RESULTS,)
    formats.setCurrentIndex(formats.findData(StatisticsExportFormat.EXCEL))
    choices[1].setChecked(False)
    choices[2].setChecked(True)
    assert dialog.export_request().components == (HypothesisExportComponent.CHARTS,)
    choices[2].setChecked(False)
    assert dialog.export_request() is None
    assert "at least one" in dialog._export_button.toolTip()


def test_hypothesis_dialog_without_applied_result_never_enables_export():
    dialog = AnalysisExportDialog(hypothesis_mode=True)
    assert all(not choice.isEnabled() for choice in dialog.findChildren(QCheckBox))
    assert dialog.export_request() is None
    assert "Apply" in dialog._export_button.toolTip()
    with pytest.raises(ValueError, match="only one"):
        AnalysisExportDialog(hypothesis_mode=True, statistics_mode=True)


def test_correlation_dialog_names_applied_matrix_and_enables_all_components():
    snapshot = _correlation_snapshot()
    dialog = AnalysisExportDialog(correlation=snapshot)
    choices = dialog.findChildren(QCheckBox)
    formats = dialog.findChild(QComboBox)
    export = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Export")

    assert [choice.text() for choice in choices] == [
        "Strongest correlations",
        "Matrix plot",
        "Scatterplots (1 pair)",
    ]
    assert choices[0].isEnabled() and choices[0].isChecked()
    assert choices[1].isEnabled() and choices[2].isEnabled()
    assert formats.currentData() is StatisticsExportFormat.EXCEL
    identity = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("Applied method:"))
    assert identity.textFormat() is Qt.TextFormat.PlainText
    assert "Spearman" in identity.text()
    assert "first column / second column" in identity.text()

    for format_choice in StatisticsExportFormat:
        formats.setCurrentIndex(formats.findData(format_choice))
        request = dialog.export_request()
        assert request.snapshot is snapshot
        assert request.components == (CorrelationExportComponent.STRONGEST_CORRELATIONS,)
        assert request.format is format_choice
        assert export.isEnabled()


def test_correlation_dialog_without_successful_matrix_shows_disabled_choices():
    dialog = AnalysisExportDialog(correlation_mode=True)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == [
        "Strongest correlations",
        "Matrix plot",
        "Scatterplots (0 pairs)",
    ]
    assert all(not choice.isEnabled() and not choice.isChecked() for choice in choices)
    assert dialog.export_request() is None
    assert "Apply a correlation matrix" in dialog._export_button.toolTip()
    assert all("Apply a correlation matrix" in choice.toolTip() for choice in choices[1:])


def test_correlation_chart_choices_are_retained_when_switching_to_table_only_formats():
    dialog = AnalysisExportDialog(correlation=_correlation_snapshot())
    choices = dialog.findChildren(QCheckBox)
    formats = dialog.findChild(QComboBox)
    choices[0].setChecked(False)
    choices[1].setChecked(True)
    choices[2].setChecked(True)
    request = dialog.export_request()
    assert request is not None
    assert request.components == (
        CorrelationExportComponent.MATRIX_PLOT,
        CorrelationExportComponent.SCATTERPLOTS,
    )
    for format_choice in (StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY):
        formats.setCurrentIndex(formats.findData(format_choice))
        assert choices[1].isChecked() and choices[2].isChecked()
        assert dialog.export_request() is None
        assert "only in Excel" in dialog._export_button.toolTip()
    formats.setCurrentIndex(formats.findData(StatisticsExportFormat.EXCEL))
    assert dialog.export_request() is not None


@pytest.mark.parametrize("locale", ["en", "sv"])
def test_long_applied_labels_and_translated_export_layout_fit_without_screen_caps(locale, tmp_path):
    translator = QTranslator()
    path = Path(__file__).parents[2] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{locale}.qm"
    assert translator.load(str(path))
    app = QApplication.instance()
    app.installTranslator(translator)
    dialog = None
    try:
        snapshot = group_snapshot()
        columns = (
            "<literal numeric column> with a long descriptive measurement name " * 3,
            "<literal grouping column> with a long descriptive category name " * 3,
        )
        snapshot = replace(
            snapshot,
            result=replace(snapshot.result, numeric_column=columns[0], grouping_column=columns[1]),
            columns=columns,
        )
        dialog = AnalysisExportDialog(hypothesis=snapshot)
        dialog.show()
        # Resize after show so available-screen constraints cannot cap the requested geometry.
        dialog.resize(650, 800)
        app.processEvents()
        labels = dialog.findChildren(QLabel)
        identity = next(label for label in labels if columns[0] in label.text())
        assert identity.textFormat() is Qt.TextFormat.PlainText
        assert identity.wordWrap()
        assert identity.height() >= identity.heightForWidth(identity.width())
        button_box = dialog.findChild(QDialogButtonBox)
        assert button_box.geometry().bottom() < dialog.height()
        assert dialog._export_button.isEnabled()
        assert dialog.grab().save(str(tmp_path / f"hypothesis-export-{locale}.png"))
    finally:
        if dialog is not None:
            dialog.close()
        app.removeTranslator(translator)
