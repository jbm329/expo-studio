from __future__ import annotations

from dataclasses import replace
from html import escape

import pandas as pd
import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PyQt6.QtGui import QHelpEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.analysis import timeseries_config as timeseries_config_module
from expo_jbm329.gui.dialogs.analysis.analysis_dialog import AnalysisDialog, build_placeholder_label
from expo_jbm329.gui.dialogs.analysis.analysis_export_dialog import AnalysisExportDialog
from expo_jbm329.gui.dialogs.analysis.clustering_config import ClusteringConfigWidget
from expo_jbm329.gui.dialogs.analysis.column_combo_box import ColumnComboBox
from expo_jbm329.gui.dialogs.analysis.correlation_config import CorrelationConfigWidget
from expo_jbm329.gui.dialogs.analysis.hypothesis_tests_config import HypothesisTestsConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_config import OutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_config import MultivariateOutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.pca_config import PCAConfigWidget
from expo_jbm329.gui.dialogs.analysis.pca_view import PCAView
from expo_jbm329.gui.dialogs.analysis.regression_config import RegressionConfigWidget
from expo_jbm329.gui.dialogs.analysis.report_notes_dialog import ReportNotesDialog
from expo_jbm329.gui.dialogs.analysis.timeseries_config import TimeSeriesConfigWidget
from expo_jbm329.gui.dialogs.service.common.localization import TR_CLOSE
from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.chi_square import initialize_chi_square
from expo_jbm329.services.analysis.clustering import ClusteringMethod, initialize_clustering
from expo_jbm329.services.analysis.clustering_export import ClusteringExportComponent, ClusteringExportRequest
from expo_jbm329.services.analysis.correlation import (
    CorrelationMethod,
    analyze_correlation_matrix,
    initialize_correlation,
)
from expo_jbm329.services.analysis.correlation_export import (
    CorrelationExportComponent,
    CorrelationExportRequest,
    CorrelationExportSnapshot,
)
from expo_jbm329.services.analysis.group_comparison import (
    ColumnExclusionReason,
    ExcludedColumn,
    initialize_group_comparison,
)
from expo_jbm329.services.analysis.multivariate_outliers import (
    MultivariateOutlierMethod,
    initialize_multivariate_outliers,
)
from expo_jbm329.services.analysis.outliers import OutlierMethod, initialize_outlier_summary
from expo_jbm329.services.analysis.outliers_export import OutlierExportComponent, OutlierExportRequest
from expo_jbm329.services.analysis.paired_comparison import initialize_paired_comparison
from expo_jbm329.services.analysis.pca import analyze_pca, initialize_pca
from expo_jbm329.services.analysis.pca_export import PCAExportComponent, PCAExportRequest, PCAExportSnapshot
from expo_jbm329.services.analysis.presentation import (
    AnalysisPresentation,
    ConfigurationField,
    build_analysis_presentation,
)
from expo_jbm329.services.analysis.regression import initialize_regression
from expo_jbm329.services.analysis.regression_export import (
    RegressionExportComponent,
    RegressionExportRequest,
    RegressionExportSnapshot,
)
from expo_jbm329.services.analysis.regression_glm import RegressionModel, initialize_generalized_targets
from expo_jbm329.services.analysis.report import ReportDocument, create_report_entry
from expo_jbm329.services.analysis.statistics import (
    StatisticsExportFormat,
    StatisticsExportRequest,
    StatisticsExportTable,
    analyze_descriptive_statistics,
)
from expo_jbm329.services.analysis.survival import initialize_survival_columns
from expo_jbm329.services.analysis.timeseries import DecompositionModel, analyze_time_series, initialize_time_series
from expo_jbm329.services.analysis.timeseries_export import (
    TimeSeriesAppliedConfiguration,
    TimeSeriesExportComponent,
    TimeSeriesExportRequest,
    TimeSeriesExportSnapshot,
)
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.utils.format_utils import fmt_int
from tests.analysis.test_clustering_export import clustering_snapshot
from tests.analysis.test_outliers_export import multivariate_snapshot as multivariate_outliers_snapshot
from tests.analysis.test_outliers_export import univariate_snapshot
from tests.analysis.test_pca_export import pca_frame, pca_snapshot
from tests.analysis.test_regression_export import (
    cox_snapshot,
    generalized_snapshot,
    linear_snapshot,
    poisson_snapshot,
)
from tests.analysis.test_timeseries_export import CHART_LABELS, time_series_snapshot


def _make_datasets() -> list[DatasetRef]:
    return [
        DatasetRef(tab_id="t1", title="Sheet1", row_count=100, column_count=5),
        DatasetRef(tab_id="t2", title="Sheet2", row_count=50, column_count=3),
    ]


def test_dialog_keeps_the_provided_source_tab_id():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[1])

    assert dialog.source_tab_id() == "t2"


@pytest.mark.parametrize("action", ["preview", "save"])
def test_report_actions_capture_title_description_order_and_immutable_entry_selections(action):
    datasets = _make_datasets()
    dialog = AnalysisDialog(parent=None, source_dataset=datasets[0])
    first = create_report_entry(AnalysisCategory.PCA, datasets[0], pca_snapshot())
    second = create_report_entry(
        AnalysisCategory.STATISTICS,
        datasets[0],
        analyze_descriptive_statistics(pd.DataFrame({"value": [1, 2, 3]})),
    )
    draft = dialog.report_document()
    draft.upsert(second)
    draft.upsert(first)
    page = dialog.report_page()
    page.set_entries(draft.entries)
    page.findChild(QLineEdit).setText("<b>Report title</b>")
    page.findChild(QPlainTextEdit).setPlainText("Purpose\nSecond line")
    requests: list[ReportDocument] = []
    signal = dialog.report_preview_requested if action == "preview" else dialog.report_save_requested
    signal.connect(requests.append)

    button = page._preview_button if action == "preview" else page._generate_button
    button.click()
    captured = requests[0]
    draft.remove(second.entry_id)
    draft.upsert(first.with_selection(("model_summary",), "New note"))
    page.findChild(QLineEdit).setText("Changed title")

    assert captured is not draft
    assert captured.title == "<b>Report title</b>"
    assert captured.description == "Purpose\nSecond line"
    assert captured.entries == (second, first)
    assert captured.entries[1].note == ""


def test_empty_report_does_not_emit_preview_request():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    requests: list[ReportDocument] = []
    dialog.report_preview_requested.connect(requests.append)
    dialog.report_save_requested.connect(requests.append)

    dialog._request_report_preview()
    dialog._request_report_save()

    assert requests == []


def test_dialog_has_maximize_and_close_buttons_but_no_minimize_button():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])

    flags = dialog.windowFlags()
    assert flags & Qt.WindowType.WindowMaximizeButtonHint
    assert flags & Qt.WindowType.WindowCloseButtonHint
    assert not flags & Qt.WindowType.WindowMinimizeButtonHint


def test_dialog_can_be_resized_shorter_than_tall_word_wrapped_content():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    content = QWidget()
    layout = QVBoxLayout(content)
    for _ in range(40):
        label = QLabel("A long explanation that wraps across several lines in the result pane. " * 3, content)
        label.setWordWrap(True)
        layout.addWidget(label)
    dialog.set_content_widget(content)
    dialog.show()
    try:
        QCoreApplication.processEvents()
        assert content.hasHeightForWidth()
        assert not dialog.hasHeightForWidth()

        dialog.resize(1100, 600)
        QCoreApplication.processEvents()

        assert dialog.height() == max(600, dialog.minimumSizeHint().height())
        assert dialog.height() < content.heightForWidth(content.width())
    finally:
        dialog.close()


def test_dialog_source_is_read_only_metadata():
    source = _make_datasets()[1]
    dialog = AnalysisDialog(parent=None, source_dataset=source)

    assert dialog.source_tab_id() == source.tab_id
    assert not hasattr(dialog, "select_dataset")
    assert not hasattr(dialog, "dataset_changed")
    assert dialog.windowTitle() == "Advanced analysis — Sheet2 (50 rows × 3 columns)"
    assert not hasattr(dialog, "_dataset_panel")


@pytest.mark.parametrize("name", ["Sheet2", "<b>Dataset</b>", "Prepared customer transactions for regional reporting"])
def test_window_title_preserves_full_dataset_name_and_formatted_dimensions(name):
    source = DatasetRef(tab_id="source", title=name, row_count=12345, column_count=1200)
    dialog = AnalysisDialog(parent=None, source_dataset=source)
    expected = f"Advanced analysis — {name} ({fmt_int(12345)} rows × {fmt_int(1200)} columns)"
    assert dialog.windowTitle() == expected
    dialog.resize(800, 600)
    assert dialog.windowTitle() == expected


def test_statistics_export_snapshot_is_scoped_to_current_category_and_dataset():
    result = analyze_descriptive_statistics(pd.DataFrame({"number": [1, 2, 3]}))
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.STATISTICS)
    dialog.set_exportable_statistics(result)

    assert dialog.exportable_statistics() is result
    assert dialog.source_tab_id() == "t1"
    assert dialog.exportable_statistics() is result
    dialog.set_exportable_statistics(result)
    dialog.select_category(AnalysisCategory.OVERVIEW)
    assert dialog.exportable_statistics() is None


def test_correlation_export_snapshot_is_scoped_to_current_category_and_dataset():
    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [2.0, 4.0, 5.0]})
    matrix = analyze_correlation_matrix(frame, tuple(frame.columns), CorrelationMethod.PEARSON)
    assert matrix is not None
    snapshot = CorrelationExportSnapshot(matrix, frame.copy(deep=True))
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.CORRELATION)
    dialog.set_exportable_correlation(snapshot)

    assert dialog.exportable_correlation() is snapshot
    assert dialog.source_tab_id() == "t1"
    assert dialog.exportable_correlation() is snapshot
    dialog.set_exportable_correlation(snapshot)
    dialog.select_category(AnalysisCategory.STATISTICS)
    assert dialog.exportable_correlation() is None


def test_correlation_export_selection_emits_only_the_current_snapshot(monkeypatch):
    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [2.0, 4.0, 5.0]})
    matrix = analyze_correlation_matrix(frame, tuple(frame.columns), CorrelationMethod.PEARSON)
    assert matrix is not None
    snapshot = CorrelationExportSnapshot(matrix, frame.copy(deep=True))
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.CORRELATION)
    dialog.set_content_widget(QWidget())
    dialog.set_exportable_correlation(snapshot)
    received: list[CorrelationExportRequest] = []
    dialog.correlation_export_requested.connect(received.append)
    captured: list[AnalysisExportDialog] = []

    def accept_ranked_table(export_dialog):
        captured.append(export_dialog)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(AnalysisExportDialog, "exec", accept_ranked_table)
    dialog._show_export_selection()

    assert len(captured) == 1
    assert [choice.text() for choice in captured[0].findChildren(QCheckBox)] == [
        "Strongest correlations",
        "Correlation matrix",
        "Scatterplots",
    ]
    assert received[0].snapshot is snapshot
    assert received[0].components == (CorrelationExportComponent.STRONGEST_CORRELATIONS,)
    dialog.select_category(AnalysisCategory.STATISTICS)
    dialog._show_export_selection()
    assert len(received) == 1


def test_regression_export_snapshot_is_scoped_to_current_category_and_dataset():
    snapshot = linear_snapshot()
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.CORRELATION)
    dialog.set_exportable_regression(snapshot)
    assert dialog.exportable_regression() is None

    dialog.select_category(AnalysisCategory.REGRESSION)
    dialog.set_exportable_regression(snapshot)
    assert dialog.exportable_regression() is snapshot
    dialog.set_content_widget(QWidget())
    assert dialog.exportable_regression() is None
    dialog.set_exportable_regression(snapshot)
    assert dialog.source_tab_id() == "t1"
    assert dialog.exportable_regression() is snapshot
    dialog.set_exportable_regression(snapshot)
    dialog.select_category(AnalysisCategory.STATISTICS)
    assert dialog.exportable_regression() is None


def test_regression_export_selection_emits_only_the_current_snapshot(monkeypatch):
    snapshot = linear_snapshot()
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.REGRESSION)
    dialog.set_content_widget(QWidget())
    dialog.set_exportable_regression(snapshot)
    received: list[RegressionExportRequest] = []
    dialog.regression_export_requested.connect(received.append)
    captured: list[AnalysisExportDialog] = []

    def accept_default_selection(export_dialog):
        captured.append(export_dialog)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(AnalysisExportDialog, "exec", accept_default_selection)
    dialog._show_export_selection()

    assert [choice.text() for choice in captured[0].findChildren(QCheckBox)] == [
        "Coefficients",
        "Model summary",
        "Linear diagnostics",
    ]
    assert len(received) == 1
    assert received[0].snapshot is snapshot
    assert received[0].components == (RegressionExportComponent.COEFFICIENTS,)

    dialog.set_content_widget(QWidget())
    dialog._show_export_selection()
    assert len(captured) == 2
    assert all(not choice.isEnabled() for choice in captured[1].findChildren(QCheckBox))
    assert len(received) == 1


def test_statistics_export_dialog_emits_selected_chart_only_request(monkeypatch):
    result = analyze_descriptive_statistics(pd.DataFrame({"number": [1, 2, 3]}))
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.STATISTICS)
    dialog.set_exportable_statistics(result)
    requests: list[StatisticsExportRequest] = []
    dialog.statistics_export_requested.connect(requests.append)

    def accept_chart_only(export_dialog):
        choices = {choice.text(): choice for choice in export_dialog.findChildren(QCheckBox)}
        choices["Continuous"].setChecked(False)
        choices["Charts"].setChecked(True)
        assert export_dialog.export_request().tables == (StatisticsExportTable.CHARTS,)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(AnalysisExportDialog, "exec", accept_chart_only)
    dialog._show_export_selection()

    assert requests == [
        StatisticsExportRequest(
            result,
            (StatisticsExportTable.CHARTS,),
            StatisticsExportFormat.EXCEL,
        )
    ]


def test_dialog_lists_every_analysis_category_once():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])

    selector = dialog._category_list  # noqa: SLF001
    assert selector.count() == len(list(AnalysisCategory)) + 1
    assert [selector.item(index).data(Qt.ItemDataRole.UserRole) for index in range(len(AnalysisCategory))] == [
        category.value for category in AnalysisCategory
    ]
    assert selector.item(selector.count() - 1).text() == "Reports(0)"


def test_report_navigation_uses_full_workspace_and_preserves_details_and_analysis():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    content, config = QWidget(), QWidget()
    dialog.set_content_widget(content)
    dialog.set_config_widget(config)
    received: list[str] = []
    dialog.category_changed.connect(received.append)
    dialog.show()
    page = dialog.report_page()
    page.findChild(QLineEdit).setText("My report")
    page.findChild(QPlainTextEdit).setPlainText("Description")
    try:
        dialog.select_reports()
        QCoreApplication.processEvents()

        assert dialog.selected_category() is None
        assert received == []
        assert page.isVisible()
        assert page.width() == dialog._workspace_stack.width()  # noqa: SLF001
        assert not dialog._config_panel.isVisible()  # noqa: SLF001
        assert not dialog._action_bar.isVisible()  # noqa: SLF001
        assert dialog.source_tab_id() == "t1"
        assert dialog.windowTitle() == "Advanced analysis — Sheet1 (100 rows × 5 columns)"

        dialog.select_category(AnalysisCategory.OVERVIEW)
        assert received == [AnalysisCategory.OVERVIEW.value]
        assert dialog._config_panel.isVisible()  # noqa: SLF001
        assert dialog._action_bar.isVisible()  # noqa: SLF001
        assert dialog.windowTitle() == "Advanced analysis — Sheet1 (100 rows × 5 columns)"
        assert dialog.content_widget() is content
        assert dialog.config_widget() is config
        dialog.select_reports()
        assert dialog.report_page() is page
        assert page.report_title() == "My report"
        assert page.report_description() == "Description"
    finally:
        dialog.close()


@pytest.mark.parametrize("category", [AnalysisCategory.OVERVIEW, AnalysisCategory.TIME_SERIES])
def test_export_button_opens_selection_dialog_with_full_text_tooltips(monkeypatch, category):
    captured: list[AnalysisExportDialog] = []
    monkeypatch.setattr(AnalysisExportDialog, "exec", lambda self: captured.append(self))
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(category)
    tool = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Export")

    assert tool.menu() is None
    tool.click()

    assert len(captured) == 1
    preview = captured[0]
    assert preview.parent() is dialog
    assert preview.windowTitle() == "Export"
    assert [group.title() for group in preview.findChildren(QGroupBox)] == ["Data", "Results"]
    for combo in preview.findChildren(QComboBox):
        _request_tooltip(combo)
        assert combo.currentText() in QToolTip.text()
    assert dialog.report_page().findChild(QListWidget).count() == 0


def test_add_to_report_captures_applied_analysis_components_and_note(monkeypatch):
    captured: list[ReportNotesDialog] = []

    def accept_new_entry(report_dialog):
        report_dialog.findChild(QPlainTextEdit).setPlainText("Useful analysis note")
        report_dialog.findChildren(QCheckBox)[0].setChecked(False)
        captured.append(report_dialog)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        ReportNotesDialog,
        "exec",
        accept_new_entry,
    )
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.PCA)
    snapshot = pca_snapshot()
    dialog.set_exportable_pca(snapshot)
    add = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Add to report")

    add.click()

    assert len(captured) == 1
    assert captured[0].parent() is dialog
    assert any(label.text() == "PCA" for label in captured[0].findChildren(QLabel))
    assert len(captured[0].selected_components()) == 3
    assert len(dialog.report_document().entries) == 1
    entry = dialog.report_document().entries[0]
    assert entry.note == "Useful analysis note"
    assert entry.selected_components == tuple(component.key for component in entry.components[1:])
    assert dialog._category_list.item(dialog._category_list.count() - 1).text() == "Reports(1)"  # noqa: SLF001
    assert next(button for button in dialog.findChildren(QPushButton) if button.text() == "Remove from report")

    dialog.select_reports()
    report_item = dialog.report_page().findChild(QListWidget).item(0)
    assert report_item is not None
    assert report_item.text().splitlines() == [
        "PCA - Sheet1",
        "Features: x, y, z",
        "Standardization: Standardized",
    ]
    edit_dialogs: list[ReportNotesDialog] = []

    def accept_edit(report_dialog):
        assert report_dialog.notes() == "Useful analysis note"
        assert report_dialog.selected_components() == entry.selected_components
        report_dialog.findChild(QPlainTextEdit).setPlainText("Revised note")
        edit_dialogs.append(report_dialog)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ReportNotesDialog, "exec", accept_edit)
    dialog.report_page()._edit_button.click()  # noqa: SLF001
    assert len(edit_dialogs) == 1
    assert len(dialog.report_document().entries) == 1
    assert dialog.report_document().entries[0].note == "Revised note"
    dialog.report_page()._remove_button.click()  # noqa: SLF001
    assert dialog.report_document().entries == ()
    assert dialog._category_list.item(dialog._category_list.count() - 1).text() == "Reports(0)"  # noqa: SLF001


def test_pca_configurations_coexist_and_reruns_require_atomic_explicit_update(monkeypatch):
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.PCA)

    def fit(columns: tuple[str, ...], standardize: bool) -> PCAExportSnapshot:
        result = analyze_pca(pca_frame(), columns, standardize=standardize)
        view = PCAView(result)
        return PCAExportSnapshot(view.result(), view.chart_labels(), view.export_notes())

    configurations = (
        (("x", "y", "z"), True),
        (("x", "y", "z"), False),
        (("y", "x", "z"), True),
        (("x", "y"), True),
    )

    def accept_add(editor):
        editor.findChild(QPlainTextEdit).setPlainText("Keep this PCA note")
        editor._component_choices["charts"].setChecked(False)  # noqa: SLF001
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ReportNotesDialog, "exec", accept_add)
    snapshots = [fit(columns, standardize) for columns, standardize in configurations]
    dialog.set_exportable_pca(snapshots[0])
    dialog._toggle_report_entry()  # noqa: SLF001
    original = dialog.report_document().entries[0]
    for snapshot in snapshots[1:]:
        dialog.set_exportable_pca(snapshot)
        assert dialog._report_action_button.text() == "Add to report"  # noqa: SLF001
        dialog._toggle_report_entry()  # noqa: SLF001

    entries_before_update = dialog.report_document().entries
    assert len(entries_before_update) == len(configurations)
    assert len({entry.entry_id for entry in entries_before_update}) == len(configurations)
    assert entries_before_update[0].note == "Keep this PCA note"
    assert entries_before_update[0].selected_components == ("feature_loadings", "explained_variance", "model_summary")

    rerun = fit(*configurations[0])
    dialog.set_exportable_pca(rerun)
    first_candidate = dialog._current_report_candidate()  # noqa: SLF001
    inspected_candidate = dialog._current_report_candidate()  # noqa: SLF001
    assert first_candidate is not None and inspected_candidate is not None
    assert first_candidate.capture_id == inspected_candidate.capture_id == rerun.capture_id
    assert dialog._report_action_button.text() == "Update report result"  # noqa: SLF001

    def cancel_update(editor):
        labels = [label.text() for label in editor.findChildren(QLabel)]
        assert editor.notes() == "Keep this PCA note"
        assert editor.selected_components() == original.selected_components
        assert any(label == "PCA" for label in labels)
        assert any("Features: x, y, z" in label for label in labels)
        assert any("Standardization: Standardized" in label for label in labels)
        assert any(button.text() == "Update result" for button in editor.findChildren(QPushButton))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(ReportNotesDialog, "exec", cancel_update)
    dialog._toggle_report_entry()  # noqa: SLF001
    assert dialog.report_document().entries == entries_before_update

    monkeypatch.setattr(ReportNotesDialog, "exec", lambda _editor: QDialog.DialogCode.Accepted)
    dialog._toggle_report_entry()  # noqa: SLF001
    updated = dialog.report_document().entries
    assert updated[0].entry_id == original.entry_id
    assert updated[0].snapshot is rerun
    assert updated[0].capture_id == rerun.capture_id
    assert updated[0].note == original.note
    assert updated[0].selected_components == original.selected_components
    assert updated[1:] == entries_before_update[1:]
    assert dialog._report_action_button.text() == "Remove from report"  # noqa: SLF001


def test_correlation_report_slot_explicitly_updates_or_replaces_frozen_capture(monkeypatch):
    frame = pd.DataFrame({
        "Age": [1.0, 2.0, 3.0, 4.0],
        "Income": [2.0, 1.0, 4.0, 3.0],
        "Score": [4.0, 3.0, 2.0, 1.0],
    })

    def snapshot(columns: tuple[str, ...], method: CorrelationMethod = CorrelationMethod.SPEARMAN):
        selected = frame.loc[:, list(columns)].copy(deep=True)
        matrix = analyze_correlation_matrix(selected, columns, method)
        assert matrix is not None
        return CorrelationExportSnapshot(matrix, selected)

    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.CORRELATION)
    first_snapshot = snapshot(("Age", "Income"))
    dialog.set_exportable_correlation(first_snapshot)
    monkeypatch.setattr(
        ReportNotesDialog,
        "exec",
        lambda self: (self.findChild(QPlainTextEdit).setPlainText("Keep this note"), QDialog.DialogCode.Accepted)[1],
    )
    dialog._toggle_report_entry()  # noqa: SLF001
    original = dialog.report_document().entries[0]
    assert original.snapshot is first_snapshot
    assert original.note == "Keep this note"
    assert original.selected_components == tuple(component.key for component in original.components)

    rerun = snapshot(("Age", "Income"))
    dialog.set_exportable_correlation(rerun)
    action = dialog._report_action_button  # noqa: SLF001
    assert action.text() == "Update report result"
    original_entries = dialog.report_document().entries
    rejected_dialogs: list[ReportNotesDialog] = []

    def cancel_update(review_dialog):
        rejected_dialogs.append(review_dialog)
        assert review_dialog.notes() == "Keep this note"
        assert "Correlation — Spearman" in [label.text() for label in review_dialog.findChildren(QLabel)]
        assert any("Columns: Age, Income" in label.text() for label in review_dialog.findChildren(QLabel))
        assert any(button.text() == "Update result" for button in review_dialog.findChildren(QPushButton))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(ReportNotesDialog, "exec", cancel_update)
    dialog._toggle_report_entry()  # noqa: SLF001
    assert len(rejected_dialogs) == 1
    assert dialog.report_document().entries == original_entries
    assert dialog.report_document().entries[0].snapshot is first_snapshot

    def accept_update(review_dialog):
        assert review_dialog.notes() == "Keep this note"
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ReportNotesDialog, "exec", accept_update)
    dialog._toggle_report_entry()  # noqa: SLF001
    updated = dialog.report_document().entries[0]
    assert updated.entry_id == original.entry_id
    assert updated.snapshot is rerun
    assert updated.capture_id == rerun.capture_id
    assert updated.note == original.note
    assert updated.selected_components == original.selected_components

    replacement = snapshot(("Score", "Age", "Income"))
    dialog.set_exportable_correlation(replacement)
    assert action.text() == "Replace report result"

    def accept_replace(review_dialog):
        assert review_dialog.notes() == "Keep this note"
        assert any("Columns: Age, Income" in label.text() for label in review_dialog.findChildren(QLabel))
        assert any("Columns: Score, Age, Income" in label.text() for label in review_dialog.findChildren(QLabel))
        assert any(button.text() == "Replace in report" for button in review_dialog.findChildren(QPushButton))
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ReportNotesDialog, "exec", accept_replace)
    dialog._toggle_report_entry()  # noqa: SLF001
    replaced = dialog.report_document().entries[0]
    assert replaced.entry_id == original.entry_id
    assert replaced.snapshot is replacement
    assert replaced.note == original.note
    assert replaced.selected_components == original.selected_components

    dialog.set_exportable_correlation(replacement)
    assert action.text() == "Remove from report"
    action.click()
    assert dialog.report_document().entries == ()


@pytest.mark.parametrize("method", list(ClusteringMethod))
def test_clustering_configurations_coexist_and_reruns_require_explicit_review(monkeypatch, method):
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.CLUSTERING)
    initial = clustering_snapshot(method)

    def accept_add(editor):
        editor.findChild(QPlainTextEdit).setPlainText("Keep clustering note")
        editor._component_choices["charts"].setChecked(False)  # noqa: SLF001
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ReportNotesDialog, "exec", accept_add)
    configs = [
        initial,
        replace(initial, result=replace(initial.result, standardize=not initial.result.standardize)),
        replace(initial, result=replace(initial.result, columns=tuple(reversed(initial.result.columns)))),
        replace(
            initial,
            result=replace(
                initial.result,
                **({"dbscan_epsilon": 1.5} if method is ClusteringMethod.DBSCAN else {"cluster_count": 4}),
            ),
        ),
    ]
    for snapshot in configs:
        dialog.set_exportable_clustering(snapshot)
        assert dialog._report_action_button.text() == "Add to report"  # noqa: SLF001
        dialog._toggle_report_entry()  # noqa: SLF001
    before = dialog.report_document().entries
    assert len(before) == 4

    rerun = clustering_snapshot(method)
    inactive = {"cluster_count": 9} if method is ClusteringMethod.DBSCAN else {"dbscan_epsilon": 99.0}
    rerun = replace(rerun, result=replace(rerun.result, **inactive))
    dialog.set_exportable_clustering(rerun)
    assert dialog._current_report_candidate().capture_id == rerun.capture_id  # noqa: SLF001
    assert dialog._current_report_candidate().capture_id == rerun.capture_id  # noqa: SLF001
    assert dialog._report_action_button.text() == "Update report result"  # noqa: SLF001
    assert dialog.report_document().entries == before

    def cancel(editor):
        assert editor.notes() == "Keep clustering note"
        assert editor.selected_components() == ("cluster_sizes", "model_summary")
        assert any(button.text() == "Update result" for button in editor.findChildren(QPushButton))
        assert any("Clustering —" in label.text() for label in editor.findChildren(QLabel))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(ReportNotesDialog, "exec", cancel)
    dialog._toggle_report_entry()  # noqa: SLF001
    assert dialog.report_document().entries == before
    monkeypatch.setattr(ReportNotesDialog, "exec", lambda _editor: QDialog.DialogCode.Accepted)
    dialog._toggle_report_entry()  # noqa: SLF001
    updated = dialog.report_document().entries
    assert updated[0].snapshot is rerun
    assert updated[0].capture_id == rerun.capture_id
    assert updated[0].note == before[0].note
    assert updated[0].selected_components == before[0].selected_components
    assert updated[0].entry_id == before[0].entry_id
    assert updated[1:] == before[1:]


def test_regression_configurations_coexist_and_identical_reruns_update_explicitly(monkeypatch):
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.REGRESSION)
    initial = linear_snapshot()
    added: list[ReportNotesDialog] = []

    def accept_add(report_dialog):
        index = len(added)
        added.append(report_dialog)
        if index == 0:
            report_dialog.findChild(QPlainTextEdit).setPlainText("Keep this regression note")
            report_dialog._component_choices["charts"].setChecked(False)  # noqa: SLF001
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ReportNotesDialog, "exec", accept_add)
    candidates = [
        initial,
        generalized_snapshot(RegressionModel.LOGISTIC),
        poisson_snapshot(),
        generalized_snapshot(RegressionModel.NEGATIVE_BINOMIAL),
        cox_snapshot(),
    ]
    linear_result = initial.result
    candidates.extend((
        RegressionExportSnapshot(replace(linear_result, target="another outcome"), initial.chart_labels),
        RegressionExportSnapshot(
            replace(linear_result, predictors=tuple(reversed(linear_result.predictors))),
            initial.chart_labels,
        ),
    ))
    for snapshot in candidates:
        dialog.set_exportable_regression(snapshot)
        assert dialog._report_action_button.text() == "Add to report"  # noqa: SLF001
        dialog._toggle_report_entry()  # noqa: SLF001

    entries_before_update = dialog.report_document().entries
    assert len(entries_before_update) == 7
    assert len({entry.entry_id for entry in entries_before_update}) == 7
    original = entries_before_update[0]
    assert original.note == "Keep this regression note"
    assert original.selected_components == ("coefficients", "model_metrics")

    rerun = linear_snapshot()
    dialog.set_exportable_regression(rerun)
    first_candidate = dialog._current_report_candidate()  # noqa: SLF001
    inspected_candidate = dialog._current_report_candidate()  # noqa: SLF001
    assert first_candidate is not None and inspected_candidate is not None
    assert first_candidate.capture_id == inspected_candidate.capture_id == rerun.capture_id
    assert dialog._report_action_button.text() == "Update report result"  # noqa: SLF001

    def cancel_update(review_dialog):
        assert review_dialog.notes() == "Keep this regression note"
        assert review_dialog.selected_components() == ("coefficients", "model_metrics")
        labels = [label.text() for label in review_dialog.findChildren(QLabel)]
        assert any("Regression — Linear regression" in label for label in labels)
        assert any("Outcome: y" in label for label in labels)
        assert any("Predictors: x, g" in label for label in labels)
        assert any(button.text() == "Update result" for button in review_dialog.findChildren(QPushButton))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(ReportNotesDialog, "exec", cancel_update)
    dialog._toggle_report_entry()  # noqa: SLF001
    assert dialog.report_document().entries == entries_before_update

    monkeypatch.setattr(ReportNotesDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted)
    dialog._toggle_report_entry()  # noqa: SLF001
    updated = dialog.report_document().entries
    assert updated[0].entry_id == original.entry_id
    assert updated[0].snapshot is rerun
    assert updated[0].capture_id == rerun.capture_id
    assert updated[0].note == original.note
    assert updated[0].selected_components == original.selected_components
    assert updated[1:] == entries_before_update[1:]


def test_univariate_outlier_detail_replacement_and_summary_rerun_preserve_report_state(monkeypatch):
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.OUTLIERS)
    initial = univariate_snapshot(column="a")

    def accept_initial(report_dialog):
        report_dialog.findChild(QPlainTextEdit).setPlainText("Keep this outlier note")
        report_dialog._component_choices["charts"].setChecked(False)  # noqa: SLF001
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ReportNotesDialog, "exec", accept_initial)
    dialog.set_exportable_outliers(initial)
    dialog._toggle_report_entry()  # noqa: SLF001
    original = dialog.report_document().entries[0]
    other_entry = create_report_entry(AnalysisCategory.PCA, _make_datasets()[0], pca_snapshot())
    dialog.report_document().upsert(other_entry)
    ordered_entries = dialog.report_document().entries

    changed_detail = initial.with_detail(univariate_snapshot(column="few").detail, ("Changed detail note",))
    dialog.set_exportable_outliers(changed_detail)
    assert dialog._report_action_button.text() == "Replace report result"  # noqa: SLF001
    rejected: list[ReportNotesDialog] = []

    def cancel_detail_replacement(review_dialog):
        rejected.append(review_dialog)
        labels = [label.text() for label in review_dialog.findChildren(QLabel)]
        assert any("Stored result" in label and "Selected detail column: a" in label for label in labels)
        assert any("Incoming result" in label and "Selected detail column: few" in label for label in labels)
        assert any("Unavailable stored selections: Potential outliers" in label for label in labels)
        assert review_dialog.notes() == "Keep this outlier note"
        assert any(button.text() == "Replace in report" for button in review_dialog.findChildren(QPushButton))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(ReportNotesDialog, "exec", cancel_detail_replacement)
    dialog._toggle_report_entry()  # noqa: SLF001
    assert len(rejected) == 1
    assert dialog.report_document().entries == ordered_entries

    monkeypatch.setattr(ReportNotesDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted)
    dialog._toggle_report_entry()  # noqa: SLF001
    replaced = dialog.report_document().entries
    assert tuple(entry.entry_id for entry in replaced) == tuple(entry.entry_id for entry in ordered_entries)
    assert replaced[0].snapshot is changed_detail
    assert replaced[0].capture_id == initial.capture_id
    assert replaced[0].note == original.note
    assert replaced[0].selected_components == ("column_summary", "column_details")

    rerun = univariate_snapshot(column="few")
    dialog.set_exportable_outliers(rerun)
    assert dialog._report_action_button.text() == "Update report result"  # noqa: SLF001
    before_cancel = dialog.report_document().entries
    monkeypatch.setattr(
        ReportNotesDialog,
        "exec",
        lambda review_dialog: (
            pytest.fail("The cancellation test below must retain report state")
            if review_dialog.notes() != original.note
            else QDialog.DialogCode.Rejected
        ),
    )
    dialog._toggle_report_entry()  # noqa: SLF001
    assert dialog.report_document().entries == before_cancel

    monkeypatch.setattr(ReportNotesDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted)
    dialog._toggle_report_entry()  # noqa: SLF001
    updated = dialog.report_document().entries
    assert updated[0].snapshot is rerun
    assert updated[0].capture_id == rerun.capture_id
    assert updated[0].note == original.note
    assert updated[0].selected_components == replaced[0].selected_components
    assert updated[1] == other_entry

    different_method = univariate_snapshot(OutlierMethod.Z_SCORE)
    dialog.set_exportable_outliers(different_method)
    assert dialog._report_action_button.text() == "Add to report"  # noqa: SLF001
    dialog._toggle_report_entry()  # noqa: SLF001
    assert len(dialog.report_document().entries) == 3
    assert dialog.report_document().entries[0].entry_id == original.entry_id
    assert dialog.report_document().entries[1].entry_id == other_entry.entry_id
    assert dialog.report_document().entries[2].snapshot is different_method


def test_hypothesis_report_slots_coexist_and_identical_reruns_require_atomic_update(monkeypatch):
    from tests.analysis.test_hypothesis_export import chi_snapshot, group_snapshot, paired_snapshot

    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.HYPOTHESIS_TESTS)
    first_snapshot = group_snapshot()

    def accept_add(report_dialog):
        report_dialog._component_choices["charts"].setChecked(False)  # noqa: SLF001
        report_dialog.findChild(QPlainTextEdit).setPlainText("Retain this hypothesis note")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ReportNotesDialog, "exec", accept_add)
    dialog.set_exportable_hypothesis(first_snapshot)
    first_candidate = dialog._current_report_candidate()  # noqa: SLF001
    inspected_candidate = dialog._current_report_candidate()  # noqa: SLF001
    assert first_candidate is not None
    assert inspected_candidate is not None
    assert first_candidate.capture_id == inspected_candidate.capture_id == first_snapshot.capture_id
    dialog._toggle_report_entry()  # noqa: SLF001
    original = dialog.report_document().entries[0]

    for snapshot in (chi_snapshot(), paired_snapshot()):
        dialog.set_exportable_hypothesis(snapshot)
        dialog._toggle_report_entry()  # noqa: SLF001

    assert len(dialog.report_document().entries) == 3
    assert len({entry.entry_id for entry in dialog.report_document().entries}) == 3
    assert [entry.snapshot.test for entry in dialog.report_document().entries] == [
        HypothesisTest.GROUP_COMPARISON,
        HypothesisTest.CHI_SQUARE,
        HypothesisTest.PAIRED_COMPARISON,
    ]

    rerun = group_snapshot()
    dialog.set_exportable_hypothesis(rerun)
    action = dialog._report_action_button  # noqa: SLF001
    assert action.text() == "Update report result"
    before_cancel = dialog.report_document().entries

    def cancel_update(review_dialog):
        assert review_dialog.notes() == "Retain this hypothesis note"
        assert review_dialog.selected_components() == ("summary", "test_results")
        labels = [label.text() for label in review_dialog.findChildren(QLabel)]
        assert any("Hypothesis Tests — Group comparison" in label for label in labels)
        assert any("Tests computed: Welch's t-test, Student's t-test, Mann-Whitney U" in label for label in labels)
        assert any(button.text() == "Update result" for button in review_dialog.findChildren(QPushButton))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(ReportNotesDialog, "exec", cancel_update)
    dialog._toggle_report_entry()  # noqa: SLF001
    assert dialog.report_document().entries == before_cancel
    assert dialog.report_document().entries[0].snapshot is first_snapshot

    def accept_update(review_dialog):
        assert review_dialog.notes() == "Retain this hypothesis note"
        assert review_dialog.selected_components() == ("summary", "test_results")
        review_dialog.findChild(QPlainTextEdit).setPlainText("Reviewed rerun")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ReportNotesDialog, "exec", accept_update)
    dialog._toggle_report_entry()  # noqa: SLF001
    updated = dialog.report_document().entries[0]
    assert updated.entry_id == original.entry_id
    assert updated.snapshot is rerun
    assert updated.capture_id == rerun.capture_id
    assert updated.note == "Reviewed rerun"
    assert updated.selected_components == original.selected_components == ("summary", "test_results")
    assert dialog.report_document().entries[1:] == before_cancel[1:]


@pytest.mark.parametrize(
    ("category", "factory_name"),
    [
        (AnalysisCategory.OVERVIEW, "overview"),
        (AnalysisCategory.STATISTICS, "statistics"),
        (AnalysisCategory.HYPOTHESIS_TESTS, "hypothesis"),
        (AnalysisCategory.CORRELATION, "correlation"),
        (AnalysisCategory.REGRESSION, "regression"),
        (AnalysisCategory.OUTLIERS, "outliers"),
        (AnalysisCategory.CLUSTERING, "clustering"),
        (AnalysisCategory.PCA, "pca"),
        (AnalysisCategory.TIME_SERIES, "time_series"),
    ],
)
def test_add_to_report_uses_current_applied_snapshot_for_each_analysis(monkeypatch, category, factory_name):
    from expo_jbm329.services.analysis.overview import analyze_dataset_overview
    from tests.analysis.test_clustering_export import clustering_snapshot
    from tests.analysis.test_correlation_export import _snapshot as correlation_snapshot
    from tests.analysis.test_hypothesis_export import group_snapshot
    from tests.analysis.test_outliers_export import univariate_snapshot
    from tests.analysis.test_regression_export import linear_snapshot
    from tests.analysis.test_timeseries_export import time_series_snapshot

    frame = pd.DataFrame({"value": [1.0, 2.0, 3.0], "other": [4.0, 5.0, 6.0]})
    snapshots = {
        "overview": analyze_dataset_overview(frame),
        "statistics": analyze_descriptive_statistics(frame),
        "hypothesis": group_snapshot(),
        "correlation": correlation_snapshot(),
        "regression": linear_snapshot(),
        "outliers": univariate_snapshot(),
        "clustering": clustering_snapshot(),
        "pca": pca_snapshot(),
        "time_series": time_series_snapshot(),
    }
    setters = {
        "overview": "set_exportable_overview",
        "statistics": "set_exportable_statistics",
        "hypothesis": "set_exportable_hypothesis",
        "correlation": "set_exportable_correlation",
        "regression": "set_exportable_regression",
        "outliers": "set_exportable_outliers",
        "clustering": "set_exportable_clustering",
        "pca": "set_exportable_pca",
        "time_series": "set_exportable_time_series",
    }
    captured: list[ReportNotesDialog] = []
    monkeypatch.setattr(
        ReportNotesDialog,
        "exec",
        lambda self: (captured.append(self), QDialog.DialogCode.Accepted)[1],
    )
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(category)
    snapshot = snapshots[factory_name]
    getattr(dialog, setters[factory_name])(snapshot)

    next(button for button in dialog.findChildren(QPushButton) if button.text() == "Add to report").click()

    assert len(dialog.report_document().entries) == 1
    entry = dialog.report_document().entries[0]
    assert entry.category is category
    assert entry.snapshot is snapshot
    assert len(captured[0].selected_components()) == len(entry.components)


def test_export_and_add_to_report_use_matching_push_button_sizes():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.show()
    QCoreApplication.processEvents()
    try:
        buttons = dialog._action_bar.findChildren(QPushButton)  # noqa: SLF001
        assert len(buttons) == 2
        export, add = buttons
        assert export.menu() is None
        assert add.menu() is None
        assert export.size() == add.size()
    finally:
        dialog.close()


def test_report_navigation_remains_reachable_when_selector_scrolls():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.resize(900, 700)
    dialog.show()
    try:
        dialog.select_reports()
        QCoreApplication.processEvents()
        selector = dialog._category_list  # noqa: SLF001
        selector.scrollToItem(selector.currentItem())
        QCoreApplication.processEvents()

        assert selector.viewport().rect().intersects(selector.visualItemRect(selector.currentItem()))
        assert dialog.report_page().isVisible()
    finally:
        dialog.close()


def test_dialog_places_the_horizontal_analysis_selector_above_the_workspace():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.set_config_widget(QWidget())
    dialog.show()
    QCoreApplication.processEvents()
    try:
        assert dialog._analysis_panel.width() == dialog._workspace_stack.width()  # noqa: SLF001
        assert dialog._content_panel.y() > dialog._analysis_panel.y()  # noqa: SLF001
        assert dialog._config_panel.y() > dialog._analysis_panel.y()  # noqa: SLF001
        assert dialog._content_panel.width() > dialog._config_panel.width()  # noqa: SLF001
        assert dialog._category_list.flow().name == "LeftToRight"  # noqa: SLF001
        assert dialog._category_list.isWrapping() is False  # noqa: SLF001
        assert dialog._category_list.verticalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAlwaysOff  # noqa: SLF001
    finally:
        dialog.close()


def test_selecting_category_emits_category_changed_with_its_value():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    received: list[str] = []
    dialog.category_changed.connect(received.append)

    dialog.select_category(AnalysisCategory.CORRELATION)

    assert received == [AnalysisCategory.CORRELATION.value]
    assert dialog.selected_category() == AnalysisCategory.CORRELATION


def test_show_placeholder_updates_content_label():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])

    dialog.show_placeholder("Not implemented yet.")

    content = dialog.content_widget()
    assert isinstance(content, QLabel)
    assert content.text() == "Not implemented yet."


def test_build_placeholder_label_centers_and_wraps_the_message():
    label = build_placeholder_label("Choose settings.")

    assert label.text() == "Choose settings."
    assert label.alignment() == Qt.AlignmentFlag.AlignCenter
    assert label.wordWrap() is True


def test_dialog_selects_overview_category_by_default():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])

    assert dialog.selected_category() == AnalysisCategory.OVERVIEW


def test_dialog_starts_with_no_content_widget():
    """Populating the content panel is entirely the controller's job."""
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])

    assert dialog.content_widget() is None


def test_content_panel_is_a_stable_widget_across_content_changes():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    panel_before = dialog.content_panel()

    dialog.show_placeholder("Hello")

    assert dialog.content_panel() is panel_before


def test_applied_hypothesis_presentation_is_visible_and_cleared_with_replaced_content():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    presentation = AnalysisPresentation(
        "Hypothesis Tests",
        "Hypothesis Tests — Group comparison",
        (ConfigurationField("Numeric variable:", ("value",)),),
    )

    dialog.set_analysis_presentation(presentation)
    labels = dialog.content_panel().findChildren(QLabel)
    assert any(label.text() == presentation.title for label in labels)
    assert any(label.text() == "Numeric variable: value" for label in labels)
    assert all(label.textFormat() is Qt.TextFormat.PlainText for label in labels[-2:])

    dialog.set_content_widget(QWidget())
    assert dialog._analysis_presentation_widget is None  # noqa: SLF001


@pytest.mark.parametrize("method", [*OutlierMethod, *MultivariateOutlierMethod])
def test_outlier_configured_header_has_separate_bold_title_and_normal_applied_settings(
    method: OutlierMethod | MultivariateOutlierMethod,
) -> None:
    snapshot = (
        univariate_snapshot(method) if isinstance(method, OutlierMethod) else multivariate_outliers_snapshot(method)
    )
    presentation = build_analysis_presentation(AnalysisCategory.OUTLIERS, snapshot, QCoreApplication.translate)
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.OUTLIERS)
    content = QWidget()
    dialog.set_content_widget(content)

    dialog.set_analysis_presentation(presentation)

    header = dialog._analysis_presentation_widget
    assert header is not None
    layout = dialog.content_panel().layout()
    assert layout is not None
    assert layout.itemAt(0).widget() is header
    title, settings = header.findChildren(QLabel)
    assert title.text() == presentation.title
    assert title.font().bold()
    assert title.textFormat() is Qt.TextFormat.PlainText
    assert title.wordWrap()
    assert settings.text() == "\n".join(presentation.summary_lines)
    assert not settings.font().bold()
    assert settings.textFormat() is Qt.TextFormat.PlainText
    assert settings.wordWrap()
    assert settings.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert dialog.content_widget() is content

    dialog.set_analysis_presentation(presentation)
    replacement = dialog._analysis_presentation_widget
    assert replacement is not None and replacement is not header
    assert header.isHidden()
    assert layout.count() == 2
    assert layout.itemAt(0).widget() is replacement

    dialog.show_placeholder("Apply the new configuration")
    assert replacement.isHidden()
    assert dialog._analysis_presentation_widget is None
    assert layout.count() == 1


def test_set_content_widget_replaces_the_previous_widget():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    first = QWidget()
    dialog.set_content_widget(first)
    replacement = QWidget()

    dialog.set_content_widget(replacement)

    assert dialog.content_widget() is replacement
    assert dialog.content_widget() is not first
    assert first.isHidden()


def test_config_panel_starts_hidden_with_no_widget():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.show()
    try:
        assert dialog.config_widget() is None
        assert dialog._config_panel.isVisible() is False  # noqa: SLF001
    finally:
        dialog.close()


def test_set_config_widget_shows_the_panel_and_stores_the_widget():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.show()
    try:
        widget = QWidget()

        dialog.set_config_widget(widget)

        assert dialog.config_widget() is widget
        assert dialog._config_panel.isVisible() is True  # noqa: SLF001
    finally:
        dialog.close()


def test_set_config_widget_none_hides_the_panel_again():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.show()
    try:
        dialog.set_config_widget(QWidget())

        dialog.set_config_widget(None)

        assert dialog.config_widget() is None
        assert dialog._config_panel.isVisible() is False  # noqa: SLF001
    finally:
        dialog.close()


def test_statistics_table_selection_uses_full_results_area_without_configuration():
    from expo_jbm329.gui.dialogs.analysis.statistics_view import StatisticsView

    result = analyze_descriptive_statistics(pd.DataFrame({"a": [1.0, 2, 3], "b": [4.0, 5, 6]}))
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.set_config_widget(QWidget())
    view = StatisticsView(result)
    dialog.set_content_widget(view)
    dialog.set_config_widget(None)
    dialog.show()
    try:
        QCoreApplication.processEvents()
        assert dialog.config_widget() is None
        assert not dialog._config_panel.isVisible()  # noqa: SLF001
        table = view._table  # noqa: SLF001
        assert table is not None
        table.cellClicked.emit(1, 0)
        assert table.currentRow() == 1
        assert "b: Shapiro-Wilk suggests" in view._recommendation_label.text()  # noqa: SLF001
    finally:
        dialog.close()


def test_set_config_widget_replaces_the_previous_widget():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    first = QWidget()
    dialog.set_config_widget(first)
    replacement = QWidget()

    dialog.set_config_widget(replacement)

    assert dialog.config_widget() is replacement
    assert first.isHidden()


def test_source_metadata_remains_in_window_title_on_reports_page():
    source = _make_datasets()[1]
    dialog = AnalysisDialog(parent=None, source_dataset=source)

    dialog.select_reports()

    assert dialog.windowTitle() == "Advanced analysis — Sheet2 (50 rows × 3 columns)"
    assert dialog.source_tab_id() == "t2"


def test_report_candidates_across_categories_and_configurations_keep_the_fixed_source():
    from expo_jbm329.services.analysis.overview import analyze_dataset_overview

    source = _make_datasets()[1]
    dialog = AnalysisDialog(parent=None, source_dataset=source)
    overview = analyze_dataset_overview(pd.DataFrame({"value": [1, 2]}))
    statistics = analyze_descriptive_statistics(pd.DataFrame({"value": [1, 2, 3]}))

    dialog.set_exportable_overview(overview)
    overview_entry = dialog._current_report_candidate()  # noqa: SLF001
    dialog.select_category(AnalysisCategory.STATISTICS)
    dialog.set_exportable_statistics(statistics)
    statistics_entry = dialog._current_report_candidate()  # noqa: SLF001
    dialog.select_category(AnalysisCategory.PCA)
    dialog.set_exportable_pca(pca_snapshot(standardize=True))
    first_pca_entry = dialog._current_report_candidate()  # noqa: SLF001
    dialog.set_exportable_pca(pca_snapshot(standardize=False))
    second_pca_entry = dialog._current_report_candidate()  # noqa: SLF001

    assert overview_entry is not None
    assert statistics_entry is not None
    assert first_pca_entry is not None
    assert second_pca_entry is not None
    assert overview_entry.dataset_id == source.tab_id
    assert overview_entry.dataset_name == source.title
    assert statistics_entry.dataset_id == source.tab_id
    assert statistics_entry.dataset_name == source.title
    assert overview_entry.category is AnalysisCategory.OVERVIEW
    assert statistics_entry.category is AnalysisCategory.STATISTICS
    assert first_pca_entry.dataset_id == source.tab_id
    assert second_pca_entry.dataset_id == source.tab_id
    assert first_pca_entry.entry_id != second_pca_entry.entry_id


def test_dialog_has_a_localized_close_button():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])

    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box is not None
    close_button = button_box.button(QDialogButtonBox.StandardButton.Close)
    assert close_button is not None
    assert close_button.text() == QCoreApplication.translate("QtDialogService", TR_CLOSE)


def test_dialog_routes_close_button_through_the_shared_localization_helper(monkeypatch):
    calls: list[QDialogButtonBox] = []
    monkeypatch.setattr(
        "expo_jbm329.gui.dialogs.analysis.analysis_dialog.localize_dialog_buttons",
        calls.append,
    )

    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])

    assert calls == [dialog.findChild(QDialogButtonBox)]


def test_clicking_close_button_rejects_the_dialog():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    button_box = dialog.findChild(QDialogButtonBox)
    close_button = button_box.button(QDialogButtonBox.StandardButton.Close)

    close_button.click()

    assert dialog.result() == QDialog.DialogCode.Rejected


def _configuration_widgets() -> list[QWidget]:
    """Build every configuration type, including nested analysis modes."""
    df = pd.DataFrame({
        "measurement_with_a_long_column_name": [float(index + 1) for index in range(30)],
        "other_measurement": [float(index % 7) for index in range(30)],
        "event": [0, 1] * 15,
        "group": ["a", "b"] * 15,
        "time": pd.date_range("2024-01-01", periods=30),
    })
    widgets: list[QWidget] = [
        CorrelationConfigWidget(initialize_correlation(df)),
        ClusteringConfigWidget(initialize_clustering(df)),
        PCAConfigWidget(initialize_pca(df)),
        OutliersConfigWidget(initialize_outlier_summary(df)),
        MultivariateOutliersConfigWidget(initialize_multivariate_outliers(df)),
        TimeSeriesConfigWidget(initialize_time_series(df)),
    ]
    for test in HypothesisTest:
        config = HypothesisTestsConfigWidget(
            initialize_group_comparison(df),
            initialize_chi_square(df),
            initialize_paired_comparison(df),
        )
        config._test_combo.setCurrentIndex(config._test_combo.findData(test.value))  # noqa: SLF001
        widgets.append(config)
    for model in RegressionModel:
        config = RegressionConfigWidget(
            initialize_regression(df),
            initialize_generalized_targets(df),
            initialize_survival_columns(df),
        )
        config._model_combo.setCurrentIndex(config._model_combo.findData(model.value))  # noqa: SLF001
        widgets.append(config)
    return widgets


@pytest.mark.parametrize("width", [1280, 1600])
def test_all_configurations_share_reference_width_and_adaptive_layout(width):
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.resize(width, 900)
    dialog.show()
    QCoreApplication.processEvents()
    # Resize after native window creation so screen-fit adjustments do not
    # replace the explicit dimensions exercised by this layout test.
    dialog.resize(width, 900)
    QCoreApplication.processEvents()
    widths: list[int] = []
    try:
        for widget in _configuration_widgets():
            dialog.set_config_widget(widget)
            QCoreApplication.processEvents()
            widths.append(dialog._config_panel.width())  # noqa: SLF001
            assert dialog.width() == width
            assert dialog._config_scroll.widget() is widget  # noqa: SLF001
            assert widget.layout().contentsMargins().left() == 0
            for form in widget.findChildren(QFormLayout):
                assert form.rowWrapPolicy() is QFormLayout.RowWrapPolicy.WrapLongRows
                assert form.fieldGrowthPolicy() is QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            for combo in widget.findChildren(QComboBox):
                assert combo.sizeAdjustPolicy() is QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            scrollbar = dialog._config_scroll.horizontalScrollBar()  # noqa: SLF001
            assert scrollbar is not None
            assert scrollbar.maximum() == 0, type(widget).__name__
        assert len(set(widths)) == 1
        assert widths[0] < width / 4
    finally:
        dialog.close()


def _bottom_in(widget: QWidget, ancestor: QWidget) -> int:
    """Return `widget`'s bottom edge in `ancestor` coordinates."""
    return widget.mapTo(ancestor, QPoint(0, widget.height())).y()


def test_hypothesis_apply_stays_at_pane_bottom_and_controls_stay_compact():
    df = pd.DataFrame({
        "before": [float(index) for index in range(30)],
        "after": [float(index + 2) for index in range(30)],
        "group": ["a", "b"] * 15,
        "segment": ["x", "y", "z"] * 10,
    })
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    config = HypothesisTestsConfigWidget(
        initialize_group_comparison(df),
        initialize_chi_square(df),
        initialize_paired_comparison(df),
    )
    dialog.resize(1280, 800)
    dialog.show()
    dialog.set_config_widget(config)
    QCoreApplication.processEvents()
    try:
        viewport = dialog._config_scroll.viewport()  # noqa: SLF001
        apply_button = config._apply_button  # noqa: SLF001
        stack = config._stack  # noqa: SLF001
        for test in (*HypothesisTest, HypothesisTest.GROUP_COMPARISON):
            config._test_combo.setCurrentIndex(config._test_combo.findData(test.value))  # noqa: SLF001
            QCoreApplication.processEvents()
            page = stack.currentWidget()
            assert page is not None

            assert apply_button.isVisible(), test
            assert apply_button.parentWidget() is config, test
            assert viewport.height() - _bottom_in(apply_button, viewport) <= 1, test
            assert apply_button.mapTo(config, QPoint(0, 0)).y() > stack.geometry().bottom(), test
            if isinstance(page.layout(), QFormLayout):
                combos = [combo for combo in page.findChildren(QComboBox) if combo.isVisible()]
                rows = sorted(combo.mapTo(page, QPoint(0, 0)).y() for combo in combos)
                assert rows[0] <= page.layout().contentsMargins().top() + 1, test
                assert rows[1] - rows[0] <= combos[0].height() + page.layout().verticalSpacing() + 1, test
            else:
                checklist = page.findChild(QListWidget)
                group = page.findChild(QGroupBox)
                assert checklist is not None
                assert group is not None
                assert checklist.parentWidget() is group
                # The framed checklist fills the free height directly above Apply.
                assert _bottom_in(group, config) == _bottom_in(page, config), test
                gap = apply_button.mapTo(config, QPoint(0, 0)).y() - _bottom_in(group, config)
                assert 0 <= gap <= config.layout().spacing() + 1, test
    finally:
        dialog.close()


def _assert_apply_below_frame_at_pane_bottom(dialog: AnalysisDialog, config: QWidget, group: QWidget) -> None:
    """Assert Apply is outside `group`, directly below it and at the pane bottom."""
    viewport = dialog._config_scroll.viewport()  # noqa: SLF001
    apply_button = config._apply_button  # noqa: SLF001
    assert isinstance(group, QGroupBox)
    assert apply_button.parentWidget() is config
    assert group.layout().indexOf(apply_button) == -1
    assert config.layout().indexOf(apply_button) == config.layout().count() - 1
    assert viewport.height() - _bottom_in(apply_button, viewport) <= 1
    gap = apply_button.mapTo(config, QPoint(0, 0)).y() - _bottom_in(group, config)
    assert 0 <= gap <= config.layout().spacing() + 1


def test_correlation_apply_sits_below_the_columns_frame_at_the_pane_bottom():
    frame = pd.DataFrame({"a": range(30), "b": range(1, 31), "c": [index % 7 for index in range(30)]})
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    config = CorrelationConfigWidget(initialize_correlation(frame))
    dialog.resize(1280, 800)
    dialog.show()
    dialog.set_config_widget(config)
    QCoreApplication.processEvents()
    try:
        _assert_apply_below_frame_at_pane_bottom(dialog, config, config._column_list.parentWidget())  # noqa: SLF001
    finally:
        dialog.close()


def _show_config_in_dialog(config: QWidget) -> AnalysisDialog:
    """Show `config` in a real Configuration pane and settle its layout."""
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.resize(1280, 800)
    dialog.show()
    dialog.set_config_widget(config)
    QCoreApplication.processEvents()
    return dialog


def test_univariate_outliers_apply_is_anchored_at_the_pane_bottom():
    frame = pd.DataFrame({"a": [float(index) for index in range(30)], "b": [float(index % 7) for index in range(30)]})
    config = OutliersConfigWidget(initialize_outlier_summary(frame))
    dialog = _show_config_in_dialog(config)
    try:
        viewport = dialog._config_scroll.viewport()  # noqa: SLF001
        apply_button = config._apply_button  # noqa: SLF001
        assert config.layout().indexOf(apply_button) == config.layout().count() - 1
        assert viewport.height() - _bottom_in(apply_button, viewport) <= 1
        assert apply_button.mapTo(config, QPoint(0, 0)).y() > _bottom_in(config._threshold_spin, config)  # noqa: SLF001
    finally:
        dialog.close()


def test_multivariate_outliers_apply_sits_below_the_features_frame_at_the_pane_bottom():
    frame = pd.DataFrame({"a": [float(index) for index in range(30)], "b": [float(index % 7) for index in range(30)]})
    config = MultivariateOutliersConfigWidget(initialize_multivariate_outliers(frame))
    dialog = _show_config_in_dialog(config)
    try:
        _assert_apply_below_frame_at_pane_bottom(dialog, config, config._column_list.parentWidget())  # noqa: SLF001
    finally:
        dialog.close()


def test_clustering_apply_sits_below_the_features_frame_at_the_pane_bottom():
    frame = pd.DataFrame({"a": [float(index) for index in range(30)], "b": [float(index % 7) for index in range(30)]})
    config = ClusteringConfigWidget(initialize_clustering(frame))
    dialog = _show_config_in_dialog(config)
    try:
        for method_index in (*range(config._method_combo.count()), 0):  # noqa: SLF001
            config._method_combo.setCurrentIndex(method_index)  # noqa: SLF001
            QCoreApplication.processEvents()
            _assert_apply_below_frame_at_pane_bottom(dialog, config, config._column_list.parentWidget())  # noqa: SLF001
    finally:
        dialog.close()


def test_pca_apply_sits_below_the_features_frame_at_the_pane_bottom():
    frame = pd.DataFrame({
        "a": [float(index) for index in range(30)],
        "b": [float(index % 7) for index in range(30)],
        "c": [float(index % 5) for index in range(30)],
    })
    config = PCAConfigWidget(initialize_pca(frame))
    dialog = _show_config_in_dialog(config)
    try:
        _assert_apply_below_frame_at_pane_bottom(dialog, config, config._column_list.parentWidget())  # noqa: SLF001
    finally:
        dialog.close()


def test_time_series_apply_is_anchored_at_the_pane_bottom():
    frame = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=30),
        "value": [float(index % 7) for index in range(30)],
    })
    config = TimeSeriesConfigWidget(initialize_time_series(frame))
    dialog = _show_config_in_dialog(config)
    try:
        viewport = dialog._config_scroll.viewport()  # noqa: SLF001
        apply_button = config._apply_button  # noqa: SLF001
        assert config.layout().indexOf(apply_button) == config.layout().count() - 1
        assert viewport.height() - _bottom_in(apply_button, viewport) <= 1
    finally:
        dialog.close()


def test_regression_apply_sits_below_the_predictors_frame_for_every_model():
    df = pd.DataFrame({
        "measurement": [float(index + 1) for index in range(30)],
        "other_measurement": [float(index % 7) for index in range(30)],
        "event": [0, 1] * 15,
        "group": ["a", "b"] * 15,
    })
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    config = RegressionConfigWidget(
        initialize_regression(df),
        initialize_generalized_targets(df),
        initialize_survival_columns(df),
    )
    dialog.resize(1280, 800)
    dialog.show()
    dialog.set_config_widget(config)
    QCoreApplication.processEvents()
    try:
        for model in (*RegressionModel, RegressionModel.LINEAR):
            config._model_combo.setCurrentIndex(config._model_combo.findData(model.value))  # noqa: SLF001
            QCoreApplication.processEvents()
            group = config._predictor_list.parentWidget()  # noqa: SLF001
            _assert_apply_below_frame_at_pane_bottom(dialog, config, group)
    finally:
        dialog.close()


@pytest.mark.parametrize("width", [1280, 1600])
@pytest.mark.parametrize("translated", [False, True])
def test_narrow_correlation_and_time_series_keep_controls_and_full_labels_accessible(monkeypatch, width, translated):
    translations = {
        "Auto-detect seasonal period": "Automatically detect the seasonal period from the selected time series",
        "Time column:": "Applied time role",
        "Value column:": "Applied value role",
        "Resampling:": "Applied resampling",
        "Seasonal period:": "Applied seasonal period",
        "Decomposition model:": "Applied decomposition model",
    }
    if translated:
        monkeypatch.setattr(timeseries_config_module, "tr", lambda _context, text: translations.get(text, text))
    frame = pd.DataFrame({
        "when": pd.date_range("2025-01-01", periods=30),
        "a": range(30),
        "b": range(1, 31),
    })
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.resize(width, 900)
    dialog.show()
    pane_widths: list[int] = []
    try:
        correlation = CorrelationConfigWidget(initialize_correlation(frame))
        time_series = TimeSeriesConfigWidget(initialize_time_series(frame))
        for config in (correlation, time_series):
            dialog.set_config_widget(config)
            QCoreApplication.processEvents()
            scroll = dialog._config_scroll
            pane_widths.append(dialog._config_panel.width())
            assert scroll.horizontalScrollBar().maximum() == 0
            assert config.width() <= scroll.viewport().width()
            if isinstance(config, CorrelationConfigWidget):
                controls = [config._select_all_button, config._clear_button]
                for button in controls:
                    assert button.width() == button.sizeHint().width()
                # Like Regression, both buttons share one right-aligned row.
                assert controls[1].y() == controls[0].y()
                assert controls[1].x() > controls[0].x()
                group = controls[0].parentWidget()
                margin = group.layout().contentsMargins().right()
                assert controls[1].geometry().right() == group.contentsRect().right() - margin
                controls[1].click()
                assert config.checked_columns() == ()
                controls[0].click()
                assert config.checked_columns() == ("a", "b")
            else:
                role_labels = {label.text() for label in config.findChildren(QLabel)}
                if translated:
                    assert {
                        "Applied time role",
                        "Applied value role",
                        "Applied resampling",
                        "Applied seasonal period",
                        "Applied decomposition model",
                    }.issubset(role_labels)
                checkbox = config._auto_period
                label = checkbox.findChild(QLabel)
                assert label is not None
                expected = translations["Auto-detect seasonal period"] if translated else "Auto-detect seasonal period"
                assert label.text() == expected
                assert checkbox.accessibleName() == expected
                assert checkbox.toolTip() == expected
                assert label.wordWrap()
                assert label.height() >= label.heightForWidth(label.width())
                if translated:
                    assert label.height() > label.fontMetrics().height()
                checked = checkbox.isChecked()
                QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton, pos=label.geometry().center())
                assert checkbox.isChecked() is not checked
                assert config._period_spin.isEnabled() is checked
                checkbox.setFocus()
                QTest.keyClick(checkbox, Qt.Key.Key_Space)
                assert checkbox.isChecked() is checked
                controls = [checkbox]
            for control in controls:
                scroll.ensureWidgetVisible(control)
                QCoreApplication.processEvents()
                assert control.isVisible()
                position = control.mapTo(config, QPoint(0, 0))
                assert position.x() >= 0
                assert position.x() + control.width() <= config.width()
        assert len(set(pane_widths)) == 1
    finally:
        dialog.close()


@pytest.mark.parametrize("viewport_width", [225, 289])
def test_narrow_time_series_checkbox_wraps_at_its_size_hint_with_a_larger_font(viewport_width):
    frame = pd.DataFrame({
        "when": pd.date_range("2025-01-01", periods=30),
        "a": range(30),
        "b": range(1, 31),
    })
    config = TimeSeriesConfigWidget(initialize_time_series(frame))
    checkbox = config._auto_period
    font = checkbox.font()
    font.setPointSize(18)
    checkbox.setFont(font)
    AnalysisDialog._prepare_config_layout(config)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(config)
    scroll.resize(viewport_width + 2 * scroll.frameWidth(), 700)
    scroll.show()
    QCoreApplication.processEvents()
    try:
        assert scroll.viewport().width() == viewport_width
        assert scroll.horizontalScrollBar().maximum() == 0
        label = checkbox.findChild(QLabel)
        assert label is not None
        assert label.height() >= label.heightForWidth(label.width())
        assert label.height() > label.fontMetrics().height()
    finally:
        scroll.close()


def test_tall_configuration_can_scroll_without_expanding_the_dialog():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.show()
    QCoreApplication.processEvents()
    initial_size = dialog.size()
    config = QWidget()
    config.setMinimumHeight(1200)
    dialog.set_config_widget(config)
    QCoreApplication.processEvents()
    try:
        scrollbar = dialog._config_scroll.verticalScrollBar()  # noqa: SLF001
        assert scrollbar is not None
        assert scrollbar.maximum() > 0
        assert dialog.size() == initial_size
    finally:
        dialog.close()


def test_bordered_configuration_forms_keep_padding_on_both_sides():
    frame = pd.DataFrame({"a": range(30), "b": range(1, 31)})
    config = ClusteringConfigWidget(initialize_clustering(frame))
    group = next(group for group in config.findChildren(QGroupBox) if group.title() == "Parameters")
    form = group.layout()
    assert isinstance(form, QFormLayout)
    margins = form.contentsMargins()
    assert margins.left() > 0
    assert margins.right() > 0
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.set_config_widget(config)
    dialog.show()
    QCoreApplication.processEvents()
    try:
        assert form.contentsMargins() == margins
        for row in range(form.rowCount()):
            for role in (QFormLayout.ItemRole.LabelRole, QFormLayout.ItemRole.FieldRole):
                item = form.itemAt(row, role)
                assert item is not None
                control = item.widget()
                assert control is not None
                if control.isHidden():
                    continue
                assert control.geometry().left() >= margins.left()
                assert group.width() - control.geometry().right() - 1 >= margins.right()
    finally:
        dialog.close()


def _request_tooltip(widget: QWidget, position: QPoint | None = None) -> None:
    """Send a deterministic hover-help event without waiting for a timer."""
    point = position if position is not None else QPoint(1, 1)
    event = QHelpEvent(QEvent.Type.ToolTip, point, widget.mapToGlobal(point))
    QCoreApplication.sendEvent(widget, event)
    assert event.isAccepted()


def test_full_text_tooltips_cover_dataset_and_every_analysis_dropdown(monkeypatch):
    shown: list[str] = []
    monkeypatch.setattr(QToolTip, "showText", lambda _position, text, _widget: shown.append(text))
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    try:
        for widget in _configuration_widgets():
            dialog.set_config_widget(widget)
            for combo in dialog.findChildren(QComboBox):
                if combo.currentIndex() < 0:
                    continue
                _request_tooltip(combo)
                expected = combo.currentData(Qt.ItemDataRole.ToolTipRole) or f"<qt>{escape(combo.currentText())}</qt>"
                assert shown[-1] == expected
    finally:
        dialog.close()


def test_dropdown_tooltips_follow_selection_and_repopulation_with_blocked_signals(monkeypatch):
    shown: list[str] = []
    hidden: list[bool] = []
    monkeypatch.setattr(QToolTip, "showText", lambda _position, text, _widget: shown.append(text))
    monkeypatch.setattr(QToolTip, "hideText", lambda: hidden.append(True))
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    config = QWidget()
    layout = QVBoxLayout(config)
    combo = QComboBox(config)
    layout.addWidget(combo)
    combo.addItems(["first long value", "second long value"])
    dialog.set_config_widget(config)
    try:
        _request_tooltip(combo)
        assert shown[-1] == "<qt>first long value</qt>"
        combo.setCurrentIndex(1)
        _request_tooltip(combo)
        assert shown[-1] == "<qt>second long value</qt>"

        combo.blockSignals(True)
        combo.clear()
        combo.addItem("<b>literal column</b> & more")
        combo.blockSignals(False)
        _request_tooltip(combo)
        assert shown[-1] == "<qt>&lt;b&gt;literal column&lt;/b&gt; &amp; more</qt>"

        combo.clear()
        _request_tooltip(combo)
        assert len(shown) == 3
        assert hidden == [True]
    finally:
        dialog.close()


def test_popup_tooltips_preserve_disabled_reasons_and_ignore_separators(monkeypatch):
    shown: list[str] = []
    hidden: list[bool] = []
    monkeypatch.setattr(QToolTip, "showText", lambda _position, text, _widget: shown.append(text))
    monkeypatch.setattr(QToolTip, "hideText", lambda: hidden.append(True))
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    config = QWidget()
    layout = QVBoxLayout(config)
    combo = ColumnComboBox(config)
    layout.addWidget(combo)
    combo.set_columns(
        ["eligible_long_column_name"],
        [ExcludedColumn("excluded_long_column_name", 57, ColumnExclusionReason.TOO_MANY_VALUES)],
    )
    dialog.set_config_widget(config)
    dialog.show()
    combo.showPopup()
    QCoreApplication.processEvents()
    view = combo.view()
    try:
        _request_tooltip(view.viewport(), view.visualRect(combo.model().index(0, 0)).center())
        assert shown[-1] == "<qt>eligible_long_column_name</qt>"
        _request_tooltip(view.viewport(), view.visualRect(combo.model().index(2, 0)).center())
        reason = combo.itemData(2, Qt.ItemDataRole.ToolTipRole)
        assert shown[-1] == reason
        assert "57" in reason

        combo.setCurrentIndex(2)
        _request_tooltip(combo)
        assert shown[-1] == reason

        _request_tooltip(view.viewport(), view.visualRect(combo.model().index(1, 0)).center())
        _request_tooltip(view.viewport(), QPoint(-1, -1))
        assert len(shown) == 3
        assert hidden == [True, True]
        assert combo.itemData(0, Qt.ItemDataRole.ToolTipRole) is None
        assert combo.itemData(2, Qt.ItemDataRole.ToolTipRole) == reason
    finally:
        combo.hidePopup()
        dialog.close()


def test_outliers_export_snapshot_is_scoped_to_current_category_and_dataset():
    snapshot = univariate_snapshot()
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.REGRESSION)
    dialog.set_exportable_outliers(snapshot)
    assert dialog.exportable_outliers() is None

    dialog.select_category(AnalysisCategory.OUTLIERS)
    dialog.set_exportable_outliers(snapshot)
    assert dialog.exportable_outliers() is snapshot
    dialog.set_content_widget(QWidget())
    assert dialog.exportable_outliers() is None
    dialog.set_exportable_outliers(snapshot)
    assert dialog.source_tab_id() == "t1"
    assert dialog.exportable_outliers() is snapshot
    dialog.set_exportable_outliers(snapshot)
    dialog.select_category(AnalysisCategory.STATISTICS)
    assert dialog.exportable_outliers() is None


def test_outliers_export_selection_emits_only_the_current_snapshot(monkeypatch):
    snapshot = multivariate_outliers_snapshot()
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.OUTLIERS)
    dialog.set_content_widget(QWidget())
    dialog.set_exportable_outliers(snapshot)
    received: list[OutlierExportRequest] = []
    dialog.outliers_export_requested.connect(received.append)
    captured: list[AnalysisExportDialog] = []

    def accept_default_selection(export_dialog):
        captured.append(export_dialog)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(AnalysisExportDialog, "exec", accept_default_selection)
    dialog._show_export_selection()

    assert [choice.text() for choice in captured[0].findChildren(QCheckBox)] == [
        "Model summary",
        "Potential outliers",
        "Outlier projection",
    ]
    assert len(received) == 1
    assert received[0].snapshot is snapshot
    assert received[0].components == (OutlierExportComponent.MODEL_SUMMARY,)

    dialog.set_content_widget(QWidget())
    dialog._show_export_selection()
    assert len(captured) == 2
    assert all(not choice.isEnabled() for choice in captured[1].findChildren(QCheckBox))
    assert len(received) == 1


@pytest.mark.parametrize(
    ("multivariate", "first_choice"),
    [(False, "Column summary"), (True, "Model summary")],
)
def test_outliers_export_before_apply_follows_the_displayed_mode(monkeypatch, multivariate, first_choice):
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0], "y": [2.0, 1.0, 4.0, 3.0]})
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.OUTLIERS)
    config = (
        MultivariateOutliersConfigWidget(initialize_multivariate_outliers(df))
        if multivariate
        else OutliersConfigWidget(initialize_outlier_summary(df))
    )
    dialog.set_config_widget(config)
    captured: list[AnalysisExportDialog] = []

    def reject(export_dialog):
        captured.append(export_dialog)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(AnalysisExportDialog, "exec", reject)
    dialog._show_export_selection()

    choices = captured[0].findChildren(QCheckBox)
    assert choices[0].text() == first_choice
    assert all(not choice.isEnabled() for choice in choices)


def test_clustering_export_snapshot_is_scoped_to_current_category_and_dataset():
    snapshot = clustering_snapshot()
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.OUTLIERS)
    dialog.set_exportable_clustering(snapshot)
    assert dialog.exportable_clustering() is None

    dialog.select_category(AnalysisCategory.CLUSTERING)
    dialog.set_exportable_clustering(snapshot)
    assert dialog.exportable_clustering() is snapshot
    dialog.set_content_widget(QWidget())
    assert dialog.exportable_clustering() is None
    dialog.set_exportable_clustering(snapshot)
    assert dialog.source_tab_id() == "t1"
    assert dialog.exportable_clustering() is snapshot
    dialog.set_exportable_clustering(snapshot)
    dialog.select_category(AnalysisCategory.STATISTICS)
    assert dialog.exportable_clustering() is None


def test_clustering_export_selection_emits_only_the_current_snapshot(monkeypatch):
    snapshot = clustering_snapshot()
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.CLUSTERING)
    dialog.set_content_widget(QWidget())
    dialog.set_exportable_clustering(snapshot)
    received: list[ClusteringExportRequest] = []
    dialog.clustering_export_requested.connect(received.append)
    captured: list[AnalysisExportDialog] = []

    def accept_default_selection(export_dialog):
        captured.append(export_dialog)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(AnalysisExportDialog, "exec", accept_default_selection)
    dialog._show_export_selection()

    assert [choice.text() for choice in captured[0].findChildren(QCheckBox)] == [
        "Cluster sizes",
        "Model summary",
        "Cluster projection",
    ]
    assert len(received) == 1
    assert received[0].snapshot is snapshot
    assert received[0].components == (ClusteringExportComponent.CLUSTER_SIZES,)

    dialog.set_content_widget(QWidget())
    dialog._show_export_selection()
    assert len(captured) == 2
    assert all(not choice.isEnabled() for choice in captured[1].findChildren(QCheckBox))
    assert len(received) == 1


def test_pca_export_snapshot_is_scoped_to_current_category_and_dataset():
    snapshot = pca_snapshot()
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.CLUSTERING)
    dialog.set_exportable_pca(snapshot)
    assert dialog.exportable_pca() is None

    dialog.select_category(AnalysisCategory.PCA)
    dialog.set_exportable_pca(snapshot)
    assert dialog.exportable_pca() is snapshot
    dialog.set_content_widget(QWidget())
    assert dialog.exportable_pca() is None
    dialog.set_exportable_pca(snapshot)
    assert dialog.source_tab_id() == "t1"
    assert dialog.exportable_pca() is snapshot
    dialog.set_exportable_pca(snapshot)
    dialog.select_category(AnalysisCategory.STATISTICS)
    assert dialog.exportable_pca() is None


def test_pca_export_selection_emits_only_the_current_snapshot(monkeypatch):
    snapshot = pca_snapshot()
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.PCA)
    dialog.set_content_widget(QWidget())
    dialog.set_exportable_pca(snapshot)
    received: list[PCAExportRequest] = []
    dialog.pca_export_requested.connect(received.append)
    captured: list[AnalysisExportDialog] = []

    def accept_default_selection(export_dialog):
        captured.append(export_dialog)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(AnalysisExportDialog, "exec", accept_default_selection)
    dialog._show_export_selection()

    assert [choice.text() for choice in captured[0].findChildren(QCheckBox)] == [
        "Feature loadings",
        "Explained variance",
        "Model summary",
        "PCA plots",
    ]
    identity = next(label for label in captured[0].findChildren(QLabel) if "Features:" in label.text())
    assert identity.text().splitlines() == [
        "PCA",
        "Features: x, y, z",
        "Standardization: Standardized",
    ]
    assert len(received) == 1
    assert received[0].snapshot is snapshot
    assert received[0].components == (PCAExportComponent.FEATURE_LOADINGS,)

    dialog.set_content_widget(QWidget())
    dialog._show_export_selection()
    assert len(captured) == 2
    assert all(not choice.isEnabled() for choice in captured[1].findChildren(QCheckBox))
    assert len(received) == 1


def test_time_series_export_snapshot_is_scoped_to_current_category_and_dataset():
    snapshot = time_series_snapshot()
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.PCA)
    dialog.set_exportable_time_series(snapshot)
    assert dialog.exportable_time_series() is None

    dialog.select_category(AnalysisCategory.TIME_SERIES)
    dialog.set_exportable_time_series(snapshot)
    assert dialog.exportable_time_series() is snapshot
    dialog.set_content_widget(QWidget())
    assert dialog.exportable_time_series() is None
    dialog.set_exportable_time_series(snapshot)
    assert dialog.source_tab_id() == "t1"
    assert dialog.exportable_time_series() is snapshot
    dialog.set_exportable_time_series(snapshot)
    dialog.select_category(AnalysisCategory.STATISTICS)
    assert dialog.exportable_time_series() is None


def test_time_series_export_selection_emits_only_the_current_snapshot(monkeypatch):
    snapshot = time_series_snapshot()
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.TIME_SERIES)
    dialog.set_content_widget(QWidget())
    dialog.set_exportable_time_series(snapshot)
    received: list[TimeSeriesExportRequest] = []
    dialog.time_series_export_requested.connect(received.append)
    captured: list[AnalysisExportDialog] = []

    def accept_default_selection(export_dialog):
        captured.append(export_dialog)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(AnalysisExportDialog, "exec", accept_default_selection)
    dialog._show_export_selection()

    assert [choice.text() for choice in captured[0].findChildren(QCheckBox)] == [
        "Series",
        "Autocorrelation",
        "Model summary",
        "Charts",
    ]
    presentation_labels = [label.text() for label in captured[0].findChildren(QLabel)]
    identity = next(text for text in presentation_labels if text.startswith("Time Series\n"))
    assert "Time column: day" in identity
    assert "Value column: sales" in identity
    assert not any(text.startswith("Applied series:") for text in presentation_labels)
    assert len(received) == 1
    assert received[0].snapshot is snapshot
    assert received[0].components == (TimeSeriesExportComponent.SERIES,)

    dialog.set_content_widget(QWidget())
    dialog._show_export_selection()
    assert len(captured) == 2
    assert all(not choice.isEnabled() for choice in captured[1].findChildren(QCheckBox))
    assert len(received) == 1


def test_time_series_configurations_coexist_and_same_config_reruns_require_reviewed_update(monkeypatch):
    frame = pd.DataFrame({
        "day": pd.date_range("2025-01-01", periods=28, freq="D"),
        "other_day": pd.date_range("2025-02-01", periods=28, freq="D"),
        "sales": [float(index + 1) for index in range(28)],
        "units": [float(index + 2) for index in range(28)],
    })
    dataset = _make_datasets()[0]

    def fit(
        time_column: str = "day",
        value_column: str = "sales",
        frequency: str | None = None,
        period: int | None = None,
        model: DecompositionModel = DecompositionModel.ADDITIVE,
    ) -> TimeSeriesExportSnapshot:
        result = analyze_time_series(
            frame,
            time_column,
            value_column,
            resample_frequency=frequency,
            seasonal_period=period,
            decomposition_model=model,
        )
        assert result.error is None
        return TimeSeriesExportSnapshot(
            result,
            CHART_LABELS,
            (f"Applied model: {model.value}",),
            applied_configuration=TimeSeriesAppliedConfiguration(
                time_column,
                value_column,
                frequency,
                period,
                model,
            ),
        )

    configurations = (
        fit(),
        fit(time_column="other_day"),
        fit(value_column="units"),
        fit(frequency="D"),
        fit(period=7),
        fit(model=DecompositionModel.MULTIPLICATIVE),
    )
    dialog = AnalysisDialog(parent=None, source_dataset=dataset)
    dialog.select_category(AnalysisCategory.TIME_SERIES)

    def accept_initial(editor):
        editor.findChild(QPlainTextEdit).setPlainText("Keep this Time Series note")
        editor._component_choices["charts"].setChecked(False)  # noqa: SLF001
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ReportNotesDialog, "exec", accept_initial)
    dialog.set_exportable_time_series(configurations[0])
    dialog._toggle_report_entry()  # noqa: SLF001
    original = dialog.report_document().entries[0]
    assert original.note == "Keep this Time Series note"
    assert original.selected_components == ("series", "autocorrelation", "model_summary")

    other_entry = create_report_entry(AnalysisCategory.PCA, dataset, pca_snapshot())
    dialog.report_document().upsert(other_entry)
    monkeypatch.setattr(ReportNotesDialog, "exec", lambda _editor: QDialog.DialogCode.Accepted)
    for snapshot in configurations[1:]:
        dialog.set_exportable_time_series(snapshot)
        assert dialog._report_action_button.text() == "Add to report"  # noqa: SLF001
        dialog._toggle_report_entry()  # noqa: SLF001

    before_update = dialog.report_document().entries
    assert len(before_update) == len(configurations) + 1
    assert len({entry.entry_id for entry in before_update}) == len(before_update)
    assert before_update[0].entry_id == original.entry_id
    assert before_update[1].entry_id == other_entry.entry_id

    rerun = fit()
    dialog.set_exportable_time_series(rerun)
    assert dialog._report_action_button.text() == "Update report result"  # noqa: SLF001

    def cancel_update(editor):
        assert editor.notes() == original.note
        assert editor.selected_components() == original.selected_components
        labels = [label.text() for label in editor.findChildren(QLabel)]
        assert any("Time column: day" in text for text in labels)
        assert any("Value column: sales" in text for text in labels)
        assert any("Decomposition model: Additive" in text for text in labels)
        assert any(button.text() == "Update result" for button in editor.findChildren(QPushButton))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(ReportNotesDialog, "exec", cancel_update)
    dialog._toggle_report_entry()  # noqa: SLF001
    assert dialog.report_document().entries == before_update

    monkeypatch.setattr(ReportNotesDialog, "exec", lambda _editor: QDialog.DialogCode.Accepted)
    dialog._toggle_report_entry()  # noqa: SLF001
    updated = dialog.report_document().entries
    assert tuple(entry.entry_id for entry in updated) == tuple(entry.entry_id for entry in before_update)
    assert updated[0].snapshot is rerun
    assert updated[0].capture_id == rerun.capture_id
    assert updated[0].note == original.note
    assert updated[0].selected_components == original.selected_components
    assert updated[1:] == before_update[1:]


def test_time_series_update_drops_only_components_unavailable_in_the_new_capture(monkeypatch):
    regular_frame = pd.DataFrame({
        "day": pd.date_range("2025-01-01", periods=28, freq="D"),
        "sales": [float(index + 1) for index in range(28)],
    })
    irregular_frame = pd.DataFrame({
        "day": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-05", "2025-01-11"]),
        "sales": [1.0, 2.0, 3.0, 4.0],
    })

    def fit(frame: pd.DataFrame) -> TimeSeriesExportSnapshot:
        result = analyze_time_series(frame, "day", "sales")
        assert result.error is None
        return TimeSeriesExportSnapshot(
            result,
            CHART_LABELS,
            applied_configuration=TimeSeriesAppliedConfiguration(
                "day", "sales", None, None, DecompositionModel.ADDITIVE
            ),
        )

    original_snapshot = fit(regular_frame)
    rerun = fit(irregular_frame)
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])
    dialog.select_category(AnalysisCategory.TIME_SERIES)
    monkeypatch.setattr(
        ReportNotesDialog,
        "exec",
        lambda editor: (
            editor._component_choices["model_summary"].setChecked(False),  # noqa: SLF001
            editor._component_choices["charts"].setChecked(False),  # noqa: SLF001
            QDialog.DialogCode.Accepted,
        )[-1],
    )
    dialog.set_exportable_time_series(original_snapshot)
    dialog._toggle_report_entry()  # noqa: SLF001
    original = dialog.report_document().entries[0]
    assert original.selected_components == ("series", "autocorrelation")
    dialog.set_exportable_time_series(rerun)
    assert dialog._report_action_button.text() == "Update report result"  # noqa: SLF001

    def accept_update(editor):
        assert editor.selected_components() == ("series",)
        assert editor.notes() == original.note
        assert any(
            "Unavailable stored selections: Autocorrelation" in label.text() for label in editor.findChildren(QLabel)
        )
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ReportNotesDialog, "exec", accept_update)
    dialog._toggle_report_entry()  # noqa: SLF001
    updated = dialog.report_document().entries[0]
    assert updated.snapshot is rerun
    assert updated.selected_components == ("series",)


def test_footer_explains_that_exports_follow_an_applied_analysis():
    dialog = AnalysisDialog(parent=None, source_dataset=_make_datasets()[0])

    assert any(
        label.text() == "Export and Add to report are available after an analysis has been applied."
        for label in dialog.findChildren(QLabel)
    )
