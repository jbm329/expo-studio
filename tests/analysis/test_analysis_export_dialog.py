from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
from PyQt6.QtCore import QCoreApplication, Qt, QTranslator
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
from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.clustering import ClusteringMethod
from expo_jbm329.services.analysis.clustering_export import (
    CLUSTERING_COMPONENTS,
    ClusteringExportComponent,
    ClusteringExportRequest,
)
from expo_jbm329.services.analysis.correlation import CorrelationMethod, analyze_correlation_matrix
from expo_jbm329.services.analysis.correlation_export import CorrelationExportComponent, CorrelationExportSnapshot
from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportComponent, HypothesisExportRequest
from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierMethod
from expo_jbm329.services.analysis.outliers import OutlierMethod, analyze_outlier_summary
from expo_jbm329.services.analysis.outliers_export import (
    UNIVARIATE_COMPONENTS,
    OutlierExportComponent,
    OutlierExportRequest,
    UnivariateOutlierExportSnapshot,
)
from expo_jbm329.services.analysis.overview import OverviewExportFormat, OverviewExportTable, analyze_dataset_overview
from expo_jbm329.services.analysis.pca_export import PCA_COMPONENTS, PCAExportComponent, PCAExportRequest
from expo_jbm329.services.analysis.presentation import build_analysis_presentation
from expo_jbm329.services.analysis.regression_charts import RegressionChartLabels
from expo_jbm329.services.analysis.regression_export import (
    RegressionExportComponent,
    RegressionExportRequest,
    RegressionExportSnapshot,
)
from expo_jbm329.services.analysis.regression_glm import RegressionModel
from expo_jbm329.services.analysis.statistics import (
    StatisticsExportFormat,
    StatisticsExportTable,
    analyze_descriptive_statistics,
)
from expo_jbm329.services.analysis.timeseries_export import (
    TIME_SERIES_COMPONENTS,
    TimeSeriesExportComponent,
    TimeSeriesExportRequest,
)
from expo_jbm329.utils.format_utils import fmt_num, fmt_pct
from tests.analysis.test_clustering_export import clustering_snapshot
from tests.analysis.test_hypothesis_export import chi_snapshot, group_snapshot, paired_snapshot
from tests.analysis.test_outliers_export import HISTOGRAM_LABELS, multivariate_snapshot, univariate_snapshot
from tests.analysis.test_pca_export import pca_snapshot
from tests.analysis.test_regression_export import (
    LINEAR_LABELS,
    cox_snapshot,
    linear_result,
    linear_snapshot,
    logistic_snapshot,
    negative_binomial_snapshot,
    poisson_snapshot,
)
from tests.analysis.test_timeseries_export import IRREGULAR_NOTE, irregular_snapshot, time_series_snapshot


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
    assert [choice.text() for choice in choices] == ["Columns metadata", "Sample (first/last 10 rows)", "Summary"]
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
    assert ("unavailable" if source is not None else "Run Overview") in choices[1].toolTip()
    assert choices[2].isEnabled() is (source is not None)
    if source is None:
        assert "Run Overview" in choices[2].toolTip()


def test_overview_partial_legacy_sample_is_disabled_without_changing_other_tables():
    result = analyze_dataset_overview(pd.DataFrame({"value": range(120)}))
    partial = replace(result, sample_last_rows=(), sample_last_frame=None)
    dialog = AnalysisExportDialog(overview=partial)
    choices = dialog.findChildren(QCheckBox)
    assert choices[0].isEnabled()
    assert not choices[1].isEnabled()
    assert "first/last sample is unavailable" in choices[1].toolTip()
    assert choices[2].isEnabled()


@pytest.mark.parametrize(
    ("locale", "sample_label", "group_label", "first_label", "last_label"),
    [
        ("en", "Sample (first/last 10 rows)", "Sample group", "First ({count})", "Last ({count})"),
        ("sv", "Urval (de första/sista 10 raderna)", "Urvalsgrupp", "Första ({count})", "Sista ({count})"),
    ],
)
def test_overview_sample_compiled_translations(locale, sample_label, group_label, first_label, last_label):
    translator = QTranslator()
    path = Path(__file__).parents[2] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{locale}.qm"
    assert translator.load(str(path))
    app = QApplication.instance()
    app.installTranslator(translator)
    dialog = None
    try:
        dialog = AnalysisExportDialog(overview=analyze_dataset_overview(pd.DataFrame({"value": [1]})))
        assert dialog.findChildren(QCheckBox)[1].text() == sample_label
        assert translator.translate("OverviewView", "Sample group") == group_label
        assert translator.translate("OverviewView", "First ({count})") == first_label
        assert translator.translate("OverviewView", "Last ({count})") == last_label
    finally:
        if dialog is not None:
            dialog.close()
        app.removeTranslator(translator)


@pytest.mark.parametrize(
    "modes",
    [{}, {"overview_mode": True, "time_series_mode": True}],
    ids=["no-analysis", "two-analyses"],
)
def test_export_dialog_requires_exactly_one_analysis(modes):
    with pytest.raises(ValueError, match="exactly one analysis result"):
        AnalysisExportDialog(**modes)


@pytest.mark.parametrize("mode", ["overview_mode", "time_series_mode"])
def test_export_selection_cancel_rejects_dialog(mode):
    dialog = AnalysisExportDialog(**{mode: True})
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
    "factory,title,summary",
    [
        (
            group_snapshot,
            "Group summary",
            (
                "Numeric variable: Value",
                "Grouping variable: Group",
                "Tests computed: Welch's t-test, Student's t-test, Mann-Whitney U",
            ),
        ),
        (
            chi_snapshot,
            "Contingency table",
            (
                "Row variable: Row",
                "Column variable: Column",
                "Tests available: Pearson's chi-square test, Fisher's exact test",
            ),
        ),
        (
            paired_snapshot,
            "Measurement summary",
            ("Measurement variables (selected order): Time 1, Time 0",),
        ),
    ],
)
def test_hypothesis_dialog_uses_applied_presentation_and_preserves_choices(factory, title, summary):
    snapshot = factory()
    dialog = AnalysisExportDialog(hypothesis=snapshot)
    choices = dialog.findChildren(QCheckBox)
    chart_title = {
        "Group summary": "Group distributions",
        "Contingency table": "Association plots",
        "Measurement summary": "Paired measurement plots",
    }[title]
    assert [choice.text() for choice in choices] == [title, "Test results", chart_title]
    identity = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("Hypothesis Tests —"))
    assert identity.textFormat() is Qt.TextFormat.PlainText
    assert all(line in identity.text() for line in summary)
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
    with pytest.raises(ValueError, match="exactly one"):
        AnalysisExportDialog(hypothesis_mode=True, statistics_mode=True)


def test_correlation_dialog_names_applied_matrix_and_enables_all_components():
    snapshot = _correlation_snapshot()
    dialog = AnalysisExportDialog(correlation=snapshot)
    choices = dialog.findChildren(QCheckBox)
    formats = dialog.findChild(QComboBox)
    export = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Export")

    assert [choice.text() for choice in choices] == [
        "Strongest correlations",
        "Correlation matrix",
        "Scatterplots",
    ]
    assert choices[0].isEnabled() and choices[0].isChecked()
    assert choices[1].isEnabled() and choices[2].isEnabled()
    assert formats.currentData() is StatisticsExportFormat.EXCEL
    identity = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("Correlation — Spearman"))
    assert identity.textFormat() is Qt.TextFormat.PlainText
    assert "Columns: first column, second column" in identity.text()

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
        "Correlation matrix",
        "Scatterplots",
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


@pytest.mark.parametrize(
    ("factory", "model", "chart_heading"),
    [
        (linear_snapshot, RegressionModel.LINEAR, "Linear diagnostics"),
        (logistic_snapshot, RegressionModel.LOGISTIC, "Logistic diagnostics"),
        (poisson_snapshot, RegressionModel.POISSON, "Count-model diagnostics"),
        (negative_binomial_snapshot, RegressionModel.NEGATIVE_BINOMIAL, "Count-model diagnostics"),
        (cox_snapshot, RegressionModel.COX, "Survival charts"),
    ],
)
def test_regression_dialog_names_applied_configuration_and_shared_components(factory, model, chart_heading):
    snapshot = factory()
    dialog = AnalysisExportDialog(regression=snapshot)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == ["Coefficients", "Model metrics", chart_heading]
    assert all(choice.isEnabled() for choice in choices)
    assert [choice.isChecked() for choice in choices] == [True, False, False]
    label = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("Regression — "))
    presentation = build_analysis_presentation(
        AnalysisCategory.REGRESSION,
        snapshot,
        QCoreApplication.translate,
    )
    assert label.text() == "\n".join((presentation.title, *presentation.summary_lines))
    assert label.textFormat() is Qt.TextFormat.PlainText
    assert snapshot.model is model
    assert "model comments" in choices[1].toolTip()
    request = dialog.export_request()
    assert isinstance(request, RegressionExportRequest)
    assert request.snapshot is snapshot
    assert request.components == (RegressionExportComponent.COEFFICIENTS,)
    assert request.format is StatisticsExportFormat.EXCEL


def test_regression_dialog_limits_single_file_formats_to_one_table_and_keeps_choices():
    dialog = AnalysisExportDialog(regression=linear_snapshot())
    choices = dialog.findChildren(QCheckBox)
    formats = dialog.findChild(QComboBox)
    for choice in choices:
        choice.setChecked(True)
    assert dialog.export_request().components == tuple(RegressionExportComponent)
    for format_choice in (StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY):
        formats.setCurrentIndex(formats.findData(format_choice))
        assert dialog.export_request() is None
        assert not dialog._export_button.isEnabled()
        assert all(choice.isChecked() for choice in choices)
    choices[2].setChecked(False)
    assert dialog.export_request() is None
    choices[0].setChecked(False)
    request = dialog.export_request()
    assert request.components == (RegressionExportComponent.MODEL_METRICS,)
    assert request.format is StatisticsExportFormat.BINARY
    assert dialog._export_button.isEnabled()
    choices[1].setChecked(False)
    assert dialog.export_request() is None


def test_regression_charts_are_disabled_when_the_model_drew_none():
    snapshot = RegressionExportSnapshot(replace(linear_result(), plot=None), RegressionChartLabels("h", LINEAR_LABELS))
    dialog = AnalysisExportDialog(regression=snapshot)
    choices = dialog.findChildren(QCheckBox)
    assert not choices[2].isEnabled()
    assert "empty" in choices[2].toolTip()
    choices[2].setChecked(True)
    choices[0].setChecked(False)
    assert dialog.export_request() is None
    assert not dialog._export_button.isEnabled()


def test_regression_dialog_without_applied_model_never_enables_export():
    dialog = AnalysisExportDialog(regression_mode=True)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == ["Coefficients", "Model metrics", "Linear diagnostics"]
    assert all(not choice.isEnabled() and not choice.isChecked() for choice in choices)
    assert all("Apply a regression model" in choice.toolTip() for choice in choices)
    assert not any(label.text().startswith("Regression — ") for label in dialog.findChildren(QLabel))
    assert dialog.export_request() is None
    assert not dialog._export_button.isEnabled()
    with pytest.raises(ValueError, match="exactly one"):
        AnalysisExportDialog(regression_mode=True, correlation_mode=True)


def test_univariate_outliers_dialog_names_screening_and_defaults_to_column_summary():
    snapshot = univariate_snapshot()
    dialog = AnalysisExportDialog(outliers=snapshot)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == [
        "Column summary",
        "Column details",
        "Potential outliers",
        "Column distributions",
    ]
    assert all(choice.isEnabled() for choice in choices)
    assert [choice.isChecked() for choice in choices] == [True, False, False, False]
    assert "at most 100" in choices[2].toolTip()
    label = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("Outliers —"))
    assert label.text() == (
        f"Outliers — IQR (Tukey's fences)\nIQR multiplier: {fmt_num(1.5)}\n"
        "Screened columns: a, b, few, Row\nSelected detail column: a"
    )
    assert label.textFormat() is Qt.TextFormat.PlainText
    assert "not the original dataset" in dialog.findChildren(QLabel)[0].text()
    request = dialog.export_request()
    assert isinstance(request, OutlierExportRequest)
    assert request.snapshot is snapshot
    assert request.components == (OutlierExportComponent.COLUMN_SUMMARY,)
    assert request.format is StatisticsExportFormat.EXCEL


def test_univariate_outliers_dialog_disables_empty_components():
    dialog = AnalysisExportDialog(outliers=univariate_snapshot(column=None))
    choices = dialog.findChildren(QCheckBox)
    assert [choice.isEnabled() for choice in choices] == [True, False, False, True]
    assert all("empty" in choice.toolTip() for choice in choices[1:3])
    label = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("Outliers —"))
    assert label.text().endswith("Selected detail column: None")


def test_single_charted_column_uses_distribution_heading():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 50.0]})
    summary = analyze_outlier_summary(df)
    dialog = AnalysisExportDialog(outliers=UnivariateOutlierExportSnapshot(summary, df.copy(), HISTOGRAM_LABELS))
    assert dialog.findChildren(QCheckBox)[-1].text() == "Column distributions"


@pytest.mark.parametrize(
    ("method", "name"),
    [
        (MultivariateOutlierMethod.ISOLATION_FOREST, "Isolation Forest"),
        (MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR, "Local Outlier Factor"),
    ],
)
def test_multivariate_outliers_dialog_names_fit_and_offers_its_components(method, name):
    snapshot = multivariate_snapshot(method)
    dialog = AnalysisExportDialog(outliers=snapshot, outliers_multivariate=False)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == ["Model summary", "Potential outliers", "Outlier projection"]
    assert [choice.isChecked() for choice in choices] == [True, False, False]
    label = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("Outliers —"))
    expected_settings = (
        f"Standardization: Standardized\nExpected outlier fraction: {fmt_pct(0.2, decimals=1)}"
        if method is MultivariateOutlierMethod.ISOLATION_FOREST
        else (f"Standardization: Standardized\nExpected outlier fraction: {fmt_pct(0.2, decimals=1)}\nLOF neighbors: 2")
    )
    assert label.text() == f"Outliers — {name}\nFeatures: x, y\n{expected_settings}"
    assert dialog.export_request().components == (OutlierExportComponent.MODEL_SUMMARY,)


@pytest.mark.parametrize("method", [OutlierMethod.Z_SCORE, OutlierMethod.MODIFIED_Z_SCORE])
def test_outliers_dialog_names_every_univariate_method(method):
    dialog = AnalysisExportDialog(outliers=univariate_snapshot(method))
    title = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("Outliers —")).text()
    assert ("Modified Z-score" in title) is (method is OutlierMethod.MODIFIED_Z_SCORE)
    assert title.startswith("Outliers — Z-score\n") is (method is OutlierMethod.Z_SCORE)


def test_outliers_dialog_limits_single_file_formats_to_one_table_and_keeps_choices():
    dialog = AnalysisExportDialog(outliers=univariate_snapshot())
    choices = dialog.findChildren(QCheckBox)
    formats = dialog.findChild(QComboBox)
    for choice in choices:
        choice.setChecked(True)
    assert dialog.export_request().components == UNIVARIATE_COMPONENTS
    for format_choice in (StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY):
        formats.setCurrentIndex(formats.findData(format_choice))
        assert dialog.export_request() is None
        assert not dialog._export_button.isEnabled()
        assert all(choice.isChecked() for choice in choices)
    assert "Charts are available only in Excel" in dialog._selection_explanation.text()
    choices[3].setChecked(False)
    assert dialog.export_request() is None
    choices[0].setChecked(False)
    choices[1].setChecked(False)
    request = dialog.export_request()
    assert request.components == (OutlierExportComponent.POTENTIAL_OUTLIERS,)
    assert request.format is StatisticsExportFormat.BINARY
    assert dialog._export_button.isEnabled()
    choices[2].setChecked(False)
    assert dialog.export_request() is None


@pytest.mark.parametrize(
    ("multivariate", "texts"),
    [
        (False, ["Column summary", "Column details", "Potential outliers", "Column distributions"]),
        (True, ["Model summary", "Potential outliers", "Outlier projection"]),
    ],
)
def test_outliers_dialog_without_applied_screening_never_enables_export(multivariate, texts):
    dialog = AnalysisExportDialog(outliers_mode=True, outliers_multivariate=multivariate)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == texts
    assert all(not choice.isEnabled() and not choice.isChecked() for choice in choices)
    assert all("Apply an outlier screening" in choice.toolTip() for choice in choices)
    assert "Apply an outlier screening" in dialog._selection_explanation.text()
    assert dialog.export_request() is None
    assert not dialog._export_button.isEnabled()
    with pytest.raises(ValueError, match="exactly one"):
        AnalysisExportDialog(outliers_mode=True, regression_mode=True)


@pytest.mark.parametrize(
    ("method", "name"),
    [
        (ClusteringMethod.K_MEANS, "K-Means"),
        (ClusteringMethod.DBSCAN, "DBSCAN"),
        (ClusteringMethod.AGGLOMERATIVE, "Agglomerative"),
    ],
)
def test_clustering_dialog_names_fit_and_defaults_to_cluster_sizes(method, name):
    snapshot = clustering_snapshot(method, dbscan_min_samples=3)
    dialog = AnalysisExportDialog(clustering=snapshot)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == ["Cluster sizes", "Model summary", "Charts"]
    assert all(choice.isEnabled() for choice in choices)
    assert [choice.isChecked() for choice in choices] == [True, False, False]
    assert "model comments" in choices[1].toolTip()
    label = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("Applied method:"))
    assert label.text() == f"Applied method: {name}\nFeatures: x / y"
    assert label.textFormat() is Qt.TextFormat.PlainText
    assert "not the original dataset" in dialog.findChildren(QLabel)[0].text()
    request = dialog.export_request()
    assert isinstance(request, ClusteringExportRequest)
    assert request.snapshot is snapshot
    assert request.components == (ClusteringExportComponent.CLUSTER_SIZES,)
    assert request.format is StatisticsExportFormat.EXCEL


def test_clustering_dialog_limits_single_file_formats_to_one_table_and_keeps_choices():
    dialog = AnalysisExportDialog(clustering=clustering_snapshot())
    choices = dialog.findChildren(QCheckBox)
    formats = dialog.findChild(QComboBox)
    for choice in choices:
        choice.setChecked(True)
    assert dialog.export_request().components == CLUSTERING_COMPONENTS
    for format_choice in (StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY):
        formats.setCurrentIndex(formats.findData(format_choice))
        assert dialog.export_request() is None
        assert not dialog._export_button.isEnabled()
        assert all(choice.isChecked() for choice in choices)
    assert "Charts are available only in Excel" in dialog._selection_explanation.text()
    choices[2].setChecked(False)
    assert dialog.export_request() is None
    choices[0].setChecked(False)
    request = dialog.export_request()
    assert request.components == (ClusteringExportComponent.MODEL_SUMMARY,)
    assert request.format is StatisticsExportFormat.BINARY
    assert dialog._export_button.isEnabled()
    choices[1].setChecked(False)
    assert dialog.export_request() is None


def test_clustering_dialog_without_applied_fit_never_enables_export():
    dialog = AnalysisExportDialog(clustering_mode=True)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == ["Cluster sizes", "Model summary", "Charts"]
    assert all(not choice.isEnabled() and not choice.isChecked() for choice in choices)
    assert all("Apply a clustering" in choice.toolTip() for choice in choices)
    assert "Apply a clustering" in dialog._selection_explanation.text()
    assert not any(label.text().startswith("Outliers —") for label in dialog.findChildren(QLabel))
    assert dialog.export_request() is None
    assert not dialog._export_button.isEnabled()
    with pytest.raises(ValueError, match="exactly one"):
        AnalysisExportDialog(clustering_mode=True, outliers_mode=True)


def test_pca_dialog_names_features_and_defaults_to_feature_loadings():
    snapshot = pca_snapshot()
    dialog = AnalysisExportDialog(pca=snapshot)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == [
        "Feature loadings",
        "Explained variance",
        "Model summary",
        "Charts",
    ]
    assert all(choice.isEnabled() for choice in choices)
    assert [choice.isChecked() for choice in choices] == [True, False, False, False]
    assert "scree plot" in choices[1].toolTip()
    assert "model comments" in choices[2].toolTip()
    label = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("Applied features:"))
    assert label.text() == "Applied features: x / y / z"
    assert label.textFormat() is Qt.TextFormat.PlainText
    assert "not the original dataset" in dialog.findChildren(QLabel)[0].text()
    request = dialog.export_request()
    assert isinstance(request, PCAExportRequest)
    assert request.snapshot is snapshot
    assert request.components == (PCAExportComponent.FEATURE_LOADINGS,)
    assert request.format is StatisticsExportFormat.EXCEL


def test_pca_dialog_limits_single_file_formats_to_one_table_and_keeps_choices():
    dialog = AnalysisExportDialog(pca=pca_snapshot())
    choices = dialog.findChildren(QCheckBox)
    formats = dialog.findChild(QComboBox)
    for choice in choices:
        choice.setChecked(True)
    assert dialog.export_request().components == PCA_COMPONENTS
    for format_choice in (StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY):
        formats.setCurrentIndex(formats.findData(format_choice))
        assert dialog.export_request() is None
        assert not dialog._export_button.isEnabled()
        assert all(choice.isChecked() for choice in choices)
    assert "Charts are available only in Excel" in dialog._selection_explanation.text()
    choices[3].setChecked(False)
    assert dialog.export_request() is None
    choices[0].setChecked(False)
    choices[2].setChecked(False)
    request = dialog.export_request()
    assert request.components == (PCAExportComponent.EXPLAINED_VARIANCE,)
    assert request.format is StatisticsExportFormat.BINARY
    assert dialog._export_button.isEnabled()
    choices[1].setChecked(False)
    assert dialog.export_request() is None


def test_pca_dialog_without_applied_fit_never_enables_export():
    dialog = AnalysisExportDialog(pca_mode=True)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == [
        "Feature loadings",
        "Explained variance",
        "Model summary",
        "Charts",
    ]
    assert all(not choice.isEnabled() and not choice.isChecked() for choice in choices)
    assert all("Apply a PCA" in choice.toolTip() for choice in choices)
    assert "Apply a PCA" in dialog._selection_explanation.text()
    assert not any(label.text().startswith("Applied features:") for label in dialog.findChildren(QLabel))
    assert dialog.export_request() is None
    assert not dialog._export_button.isEnabled()
    with pytest.raises(ValueError, match="exactly one"):
        AnalysisExportDialog(pca_mode=True, clustering_mode=True)


def test_time_series_dialog_names_series_and_defaults_to_series():
    snapshot = time_series_snapshot()
    dialog = AnalysisExportDialog(time_series=snapshot)
    groups = dialog.findChildren(QGroupBox)
    assert [group.title() for group in groups] == ["Data", "Results"]
    assert [choice.text() for choice in groups[0].findChildren(QCheckBox)] == ["Series"]
    assert [choice.text() for choice in groups[1].findChildren(QCheckBox)] == [
        "Autocorrelation",
        "Model summary",
        "Charts",
    ]
    choices = dialog.findChildren(QCheckBox)
    assert all(choice.isEnabled() for choice in choices)
    assert [choice.isChecked() for choice in choices] == [True, False, False, False]
    assert "averaging duplicate timestamps" in choices[0].toolTip()
    assert "model comments" in choices[2].toolTip()
    assert "decomposition" in choices[3].toolTip()
    label = next(label for label in dialog.findChildren(QLabel) if label.text().startswith("Applied series:"))
    assert label.text() == "Applied series: sales by day"
    assert label.textFormat() is Qt.TextFormat.PlainText
    assert "not the original dataset" in dialog.findChildren(QLabel)[0].text()
    request = dialog.export_request()
    assert isinstance(request, TimeSeriesExportRequest)
    assert request.snapshot is snapshot
    assert request.components == (TimeSeriesExportComponent.SERIES,)
    assert request.format is StatisticsExportFormat.EXCEL


def test_time_series_dialog_disables_unavailable_autocorrelation_with_reason():
    dialog = AnalysisExportDialog(time_series=irregular_snapshot())
    choices = dict(zip(TIME_SERIES_COMPONENTS, dialog.findChildren(QCheckBox), strict=True))
    autocorrelation = choices[TimeSeriesExportComponent.AUTOCORRELATION]
    assert not autocorrelation.isEnabled()
    assert autocorrelation.toolTip() == IRREGULAR_NOTE
    for choice in choices.values():
        choice.setChecked(True)
    assert dialog.export_request().components == (
        TimeSeriesExportComponent.SERIES,
        TimeSeriesExportComponent.MODEL_SUMMARY,
        TimeSeriesExportComponent.CHARTS,
    )


def test_time_series_dialog_limits_single_file_formats_to_one_table_and_keeps_choices():
    dialog = AnalysisExportDialog(time_series=time_series_snapshot())
    choices = dialog.findChildren(QCheckBox)
    formats = dialog.findChild(QComboBox)
    for choice in choices:
        choice.setChecked(True)
    assert dialog.export_request().components == TIME_SERIES_COMPONENTS
    for format_choice in (StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY):
        formats.setCurrentIndex(formats.findData(format_choice))
        assert dialog.export_request() is None
        assert not dialog._export_button.isEnabled()
        assert all(choice.isChecked() for choice in choices)
    assert "Charts are available only in Excel" in dialog._selection_explanation.text()
    choices[3].setChecked(False)
    assert dialog.export_request() is None
    choices[0].setChecked(False)
    choices[2].setChecked(False)
    request = dialog.export_request()
    assert request.components == (TimeSeriesExportComponent.AUTOCORRELATION,)
    assert request.format is StatisticsExportFormat.BINARY
    assert dialog._export_button.isEnabled()
    choices[1].setChecked(False)
    assert dialog.export_request() is None
    assert "Select at least one available component" in dialog._selection_explanation.text()


def test_time_series_dialog_without_applied_series_never_enables_export():
    dialog = AnalysisExportDialog(time_series_mode=True)
    choices = dialog.findChildren(QCheckBox)
    assert [choice.text() for choice in choices] == ["Series", "Autocorrelation", "Model summary", "Charts"]
    assert all(not choice.isEnabled() and not choice.isChecked() for choice in choices)
    assert all("Apply a time series" in choice.toolTip() for choice in choices)
    assert "Apply a time series" in dialog._selection_explanation.text()
    assert not any(label.text().startswith("Applied series:") for label in dialog.findChildren(QLabel))
    assert dialog.export_request() is None
    assert not dialog._export_button.isEnabled()
    with pytest.raises(ValueError, match="exactly one"):
        AnalysisExportDialog(time_series_mode=True, pca_mode=True)
