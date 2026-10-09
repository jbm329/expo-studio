from __future__ import annotations

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

from expo_jbm329.gui.dialogs.analysis.analysis_dialog import AnalysisDialog, build_placeholder_label
from expo_jbm329.gui.dialogs.analysis.analysis_export_dialog import AnalysisExportDialog
from expo_jbm329.gui.dialogs.analysis.clustering_config import ClusteringConfigWidget
from expo_jbm329.gui.dialogs.analysis.column_combo_box import ColumnComboBox
from expo_jbm329.gui.dialogs.analysis.correlation_config import CorrelationConfigWidget
from expo_jbm329.gui.dialogs.analysis.hypothesis_tests_config import HypothesisTestsConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_config import OutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_config import MultivariateOutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.pca_config import PCAConfigWidget
from expo_jbm329.gui.dialogs.analysis.regression_config import RegressionConfigWidget
from expo_jbm329.gui.dialogs.analysis.report_notes_dialog import ReportNotesDialog
from expo_jbm329.gui.dialogs.analysis.statistics_config import StatisticsConfigWidget
from expo_jbm329.gui.dialogs.analysis.timeseries_config import TimeSeriesConfigWidget
from expo_jbm329.gui.dialogs.service.common.localization import TR_CLOSE
from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.chi_square import initialize_chi_square
from expo_jbm329.services.analysis.clustering import initialize_clustering
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
from expo_jbm329.services.analysis.multivariate_outliers import initialize_multivariate_outliers
from expo_jbm329.services.analysis.outliers import initialize_outlier_summary
from expo_jbm329.services.analysis.paired_comparison import initialize_paired_comparison
from expo_jbm329.services.analysis.pca import initialize_pca
from expo_jbm329.services.analysis.regression import initialize_regression
from expo_jbm329.services.analysis.regression_glm import RegressionModel, initialize_generalized_targets
from expo_jbm329.services.analysis.statistics import (
    StatisticsExportFormat,
    StatisticsExportRequest,
    StatisticsExportTable,
    analyze_descriptive_statistics,
)
from expo_jbm329.services.analysis.survival import initialize_survival_columns
from expo_jbm329.services.analysis.timeseries import initialize_time_series
from expo_jbm329.utils.dataset_ref import DatasetRef


def _make_datasets() -> list[DatasetRef]:
    return [
        DatasetRef(tab_id="t1", title="Sheet1", row_count=100, column_count=5),
        DatasetRef(tab_id="t2", title="Sheet2", row_count=50, column_count=3),
    ]


def test_dialog_selects_active_tab_on_init():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id="t2")

    assert dialog.selected_dataset_tab_id() == "t2"


def test_dialog_has_maximize_and_close_buttons_but_no_minimize_button():
    dialog = AnalysisDialog(parent=None, datasets=[], active_tab_id=None)

    flags = dialog.windowFlags()
    assert flags & Qt.WindowType.WindowMaximizeButtonHint
    assert flags & Qt.WindowType.WindowCloseButtonHint
    assert not flags & Qt.WindowType.WindowMinimizeButtonHint


def test_dialog_defaults_to_first_dataset_when_no_active_tab():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)

    assert dialog.selected_dataset_tab_id() == "t1"


def test_statistics_export_snapshot_is_scoped_to_current_category_and_dataset():
    result = analyze_descriptive_statistics(pd.DataFrame({"number": [1, 2, 3]}))
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id="t1")
    dialog.select_category(AnalysisCategory.STATISTICS)
    dialog.set_exportable_statistics(result)

    assert dialog.exportable_statistics() is result
    dialog.select_dataset("t2")
    assert dialog.exportable_statistics() is None
    dialog.select_dataset("t1")
    assert dialog.exportable_statistics() is None
    dialog.set_exportable_statistics(result)
    dialog.select_category(AnalysisCategory.OVERVIEW)
    assert dialog.exportable_statistics() is None


def test_correlation_export_snapshot_is_scoped_to_current_category_and_dataset():
    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [2.0, 4.0, 5.0]})
    matrix = analyze_correlation_matrix(frame, tuple(frame.columns), CorrelationMethod.PEARSON)
    assert matrix is not None
    snapshot = CorrelationExportSnapshot(matrix, frame.copy(deep=True))
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id="t1")
    dialog.select_category(AnalysisCategory.CORRELATION)
    dialog.set_exportable_correlation(snapshot)

    assert dialog.exportable_correlation() is snapshot
    dialog.select_dataset("t2")
    assert dialog.exportable_correlation() is None
    dialog.select_dataset("t1")
    assert dialog.exportable_correlation() is None
    dialog.set_exportable_correlation(snapshot)
    dialog.select_category(AnalysisCategory.STATISTICS)
    assert dialog.exportable_correlation() is None


def test_correlation_export_selection_emits_only_the_current_snapshot(monkeypatch):
    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [2.0, 4.0, 5.0]})
    matrix = analyze_correlation_matrix(frame, tuple(frame.columns), CorrelationMethod.PEARSON)
    assert matrix is not None
    snapshot = CorrelationExportSnapshot(matrix, frame.copy(deep=True))
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id="t1")
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
        "Matrix plot",
        "Scatterplots (1 pair)",
    ]
    assert received[0].snapshot is snapshot
    assert received[0].components == (CorrelationExportComponent.STRONGEST_CORRELATIONS,)
    dialog.select_category(AnalysisCategory.STATISTICS)
    dialog._show_export_selection()
    assert len(received) == 1


def test_statistics_export_dialog_emits_selected_chart_only_request(monkeypatch):
    result = analyze_descriptive_statistics(pd.DataFrame({"number": [1, 2, 3]}))
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id="t1")
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


def test_dialog_emits_dataset_changed_when_selection_changes():
    received: list[str] = []
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id="t2")
    dialog.dataset_changed.connect(received.append)

    dialog.select_dataset("t1")

    assert received == ["t1"]


def test_dialog_lists_every_analysis_category_once():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)

    selector = dialog._category_list  # noqa: SLF001
    assert selector.count() == len(list(AnalysisCategory)) + 1
    assert [selector.item(index).data(Qt.ItemDataRole.UserRole) for index in range(len(AnalysisCategory))] == [
        category.value for category in AnalysisCategory
    ]
    assert selector.item(selector.count() - 1).text() == "Reports(0)"


def test_report_navigation_uses_full_workspace_and_preserves_details_and_analysis():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id="t1")
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
        assert not dialog._dataset_combo.isEnabled()  # noqa: SLF001
        assert "multiple datasets" in dialog._dataset_combo.toolTip()  # noqa: SLF001
        _request_tooltip(dialog._dataset_combo)  # noqa: SLF001
        assert "multiple datasets" in QToolTip.text()

        dialog.select_category(AnalysisCategory.OVERVIEW)
        assert received == [AnalysisCategory.OVERVIEW.value]
        assert dialog._config_panel.isVisible()  # noqa: SLF001
        assert dialog._action_bar.isVisible()  # noqa: SLF001
        assert dialog._dataset_combo.isEnabled()  # noqa: SLF001
        assert dialog._dataset_combo.toolTip() == ""  # noqa: SLF001
        assert dialog.content_widget() is content
        assert dialog.config_widget() is config
        dialog.select_reports()
        assert dialog.report_page() is page
        assert page.report_title() == "My report"
        assert page.report_description() == "Description"
    finally:
        dialog.close()


@pytest.mark.parametrize("category", [AnalysisCategory.OVERVIEW, AnalysisCategory.REGRESSION])
def test_export_button_opens_selection_dialog_with_full_text_tooltips(monkeypatch, category):
    captured: list[AnalysisExportDialog] = []
    monkeypatch.setattr(AnalysisExportDialog, "exec", lambda self: captured.append(self))
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
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


def test_shared_notes_action_opens_preview_for_selected_category(monkeypatch):
    captured: list[ReportNotesDialog] = []
    monkeypatch.setattr(ReportNotesDialog, "exec", lambda self: captured.append(self))
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
    dialog.select_category(AnalysisCategory.REGRESSION)
    add = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Add to report")

    add.click()

    assert len(captured) == 1
    assert captured[0].parent() is dialog
    assert any(label.text() == "Regression" for label in captured[0].findChildren(QLabel))
    assert dialog._category_list.item(dialog._category_list.count() - 1).text() == "Reports(0)"  # noqa: SLF001


def test_export_and_add_to_report_use_matching_push_button_sizes():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
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
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
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
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
    dialog.set_config_widget(QWidget())
    dialog.show()
    QCoreApplication.processEvents()
    try:
        assert dialog._analysis_panel.x() > dialog._dataset_panel.x()  # noqa: SLF001
        assert dialog._analysis_panel.y() == dialog._dataset_panel.y()  # noqa: SLF001
        assert dialog._content_panel.y() > dialog._analysis_panel.y()  # noqa: SLF001
        assert dialog._config_panel.y() > dialog._analysis_panel.y()  # noqa: SLF001
        assert dialog._content_panel.width() > dialog._config_panel.width()  # noqa: SLF001
        assert dialog._category_list.flow().name == "LeftToRight"  # noqa: SLF001
        assert dialog._category_list.isWrapping() is False  # noqa: SLF001
        assert dialog._category_list.verticalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAlwaysOff  # noqa: SLF001
    finally:
        dialog.close()


def test_selecting_category_emits_category_changed_with_its_value():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
    received: list[str] = []
    dialog.category_changed.connect(received.append)

    dialog.select_category(AnalysisCategory.CORRELATION)

    assert received == [AnalysisCategory.CORRELATION.value]
    assert dialog.selected_category() == AnalysisCategory.CORRELATION


def test_show_placeholder_updates_content_label():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)

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
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)

    assert dialog.selected_category() == AnalysisCategory.OVERVIEW


def test_dialog_starts_with_no_content_widget():
    """Populating the content panel is entirely the controller's job."""
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)

    assert dialog.content_widget() is None


def test_content_panel_is_a_stable_widget_across_content_changes():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
    panel_before = dialog.content_panel()

    dialog.show_placeholder("Hello")

    assert dialog.content_panel() is panel_before


def test_set_content_widget_replaces_the_previous_widget():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
    first = QWidget()
    dialog.set_content_widget(first)
    replacement = QWidget()

    dialog.set_content_widget(replacement)

    assert dialog.content_widget() is replacement
    assert dialog.content_widget() is not first
    assert first.isHidden()


def test_config_panel_starts_hidden_with_no_widget():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
    dialog.show()
    try:
        assert dialog.config_widget() is None
        assert dialog._config_panel.isVisible() is False  # noqa: SLF001
    finally:
        dialog.close()


def test_set_config_widget_shows_the_panel_and_stores_the_widget():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
    dialog.show()
    try:
        widget = QWidget()

        dialog.set_config_widget(widget)

        assert dialog.config_widget() is widget
        assert dialog._config_panel.isVisible() is True  # noqa: SLF001
    finally:
        dialog.close()


def test_set_config_widget_none_hides_the_panel_again():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
    dialog.show()
    try:
        dialog.set_config_widget(QWidget())

        dialog.set_config_widget(None)

        assert dialog.config_widget() is None
        assert dialog._config_panel.isVisible() is False  # noqa: SLF001
    finally:
        dialog.close()


def test_set_config_widget_replaces_the_previous_widget():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
    first = QWidget()
    dialog.set_config_widget(first)
    replacement = QWidget()

    dialog.set_config_widget(replacement)

    assert dialog.config_widget() is replacement
    assert first.isHidden()


def test_dialog_with_no_datasets_has_no_selection():
    dialog = AnalysisDialog(parent=None, datasets=[], active_tab_id=None)

    assert dialog.selected_dataset_tab_id() is None


def test_dialog_has_a_localized_close_button():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)

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

    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)

    assert calls == [dialog.findChild(QDialogButtonBox)]


def test_clicking_close_button_rejects_the_dialog():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
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
        StatisticsConfigWidget(analyze_descriptive_statistics(df)),
        CorrelationConfigWidget(initialize_correlation(df), None),
        ClusteringConfigWidget(initialize_clustering(df)),
        PCAConfigWidget(initialize_pca(df)),
        OutliersConfigWidget(initialize_outlier_summary(df), None),
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
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
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


@pytest.mark.parametrize("width", [1280, 1600])
@pytest.mark.parametrize("translated", [False, True])
def test_narrow_correlation_and_time_series_keep_controls_and_full_labels_accessible(monkeypatch, width, translated):
    translations = {
        "Select all": "Select all available columns",
        "Clear": "Clear selected columns",
        "Auto-detect seasonal period": "Automatically detect the seasonal period from the selected time series",
    }
    if translated:
        for config_type in (CorrelationConfigWidget, TimeSeriesConfigWidget):
            monkeypatch.setattr(config_type, "tr", lambda self, text: translations.get(text, text))
    frame = pd.DataFrame({
        "when": pd.date_range("2025-01-01", periods=30),
        "a": range(30),
        "b": range(1, 31),
    })
    dialog = AnalysisDialog(parent=None, datasets=[], active_tab_id=None)
    dialog.resize(width, 900)
    dialog.show()
    pane_widths: list[int] = []
    try:
        correlation = CorrelationConfigWidget(initialize_correlation(frame), None)
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
                    assert button.width() >= button.minimumSizeHint().width()
                if translated:
                    assert controls[1].y() > controls[0].y()
                controls[1].click()
                assert config.checked_columns() == ()
                controls[0].click()
                assert config.checked_columns() == ("a", "b")
            else:
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
def test_narrow_controls_wrap_at_their_size_hints_with_larger_fonts(viewport_width):
    frame = pd.DataFrame({
        "when": pd.date_range("2025-01-01", periods=30),
        "a": range(30),
        "b": range(1, 31),
    })
    correlation = CorrelationConfigWidget(initialize_correlation(frame), None)
    time_series = TimeSeriesConfigWidget(initialize_time_series(frame))
    for config in (correlation, time_series):
        if isinstance(config, CorrelationConfigWidget):
            controls = [config._select_all_button, config._clear_button]
            font_size = 24
        else:
            controls = [config._auto_period]
            font_size = 18
        for control in controls:
            font = control.font()
            font.setPointSize(font_size)
            control.setFont(font)
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
            if isinstance(config, CorrelationConfigWidget):
                actions = controls[0].parentWidget().layout().itemAt(1).layout()
                required_width = sum(control.minimumSizeHint().width() for control in controls)
                required_width += actions.horizontalSpacing()
                if required_width > actions.geometry().width():
                    assert controls[1].y() > controls[0].y()
                else:
                    assert controls[1].y() == controls[0].y()
                for control in controls:
                    assert control.width() >= control.minimumSizeHint().width()
            else:
                label = controls[0].findChild(QLabel)
                assert label is not None
                assert label.height() >= label.heightForWidth(label.width())
                assert label.height() > label.fontMetrics().height()
        finally:
            scroll.close()


def test_tall_configuration_can_scroll_without_expanding_the_dialog():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
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


@pytest.mark.parametrize("section", ["Scatterplot", "Parameters"])
def test_bordered_configuration_forms_keep_padding_on_both_sides(section):
    frame = pd.DataFrame({"a": range(30), "b": range(1, 31)})
    config = (
        CorrelationConfigWidget(initialize_correlation(frame), None)
        if section == "Scatterplot"
        else ClusteringConfigWidget(initialize_clustering(frame))
    )
    group = next(group for group in config.findChildren(QGroupBox) if group.title() == section)
    form = group.layout()
    assert isinstance(form, QFormLayout)
    margins = form.contentsMargins()
    assert margins.left() > 0
    assert margins.right() > 0
    dialog = AnalysisDialog(parent=None, datasets=[], active_tab_id=None)
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
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
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
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
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
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
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
