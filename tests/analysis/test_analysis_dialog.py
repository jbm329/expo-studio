from __future__ import annotations

from html import escape

import pandas as pd
import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PyQt6.QtGui import QHelpEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.analysis.analysis_dialog import AnalysisDialog, build_placeholder_label
from expo_jbm329.gui.dialogs.analysis.clustering_config import ClusteringConfigWidget
from expo_jbm329.gui.dialogs.analysis.column_combo_box import ColumnComboBox
from expo_jbm329.gui.dialogs.analysis.correlation_config import CorrelationConfigWidget
from expo_jbm329.gui.dialogs.analysis.hypothesis_tests_config import HypothesisTestsConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_config import OutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_config import MultivariateOutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.pca_config import PCAConfigWidget
from expo_jbm329.gui.dialogs.analysis.regression_config import RegressionConfigWidget
from expo_jbm329.gui.dialogs.analysis.statistics_config import StatisticsConfigWidget
from expo_jbm329.gui.dialogs.analysis.timeseries_config import TimeSeriesConfigWidget
from expo_jbm329.gui.dialogs.service.common.localization import TR_CLOSE
from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.chi_square import initialize_chi_square
from expo_jbm329.services.analysis.clustering import initialize_clustering
from expo_jbm329.services.analysis.correlation import initialize_correlation
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
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
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


def test_dialog_defaults_to_first_dataset_when_no_active_tab():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)

    assert dialog.selected_dataset_tab_id() == "t1"


def test_dialog_emits_dataset_changed_when_selection_changes():
    received: list[str] = []
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id="t2")
    dialog.dataset_changed.connect(received.append)

    dialog.select_dataset("t1")

    assert received == ["t1"]


def test_dialog_lists_every_analysis_category_once():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)

    assert dialog._category_list.count() == len(list(AnalysisCategory))  # noqa: SLF001


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


def test_tall_configuration_can_scroll_without_expanding_the_dialog():
    dialog = AnalysisDialog(parent=None, datasets=_make_datasets(), active_tab_id=None)
    config = QWidget()
    config.setMinimumHeight(1200)
    dialog.set_config_widget(config)
    dialog.show()
    QCoreApplication.processEvents()
    try:
        scrollbar = dialog._config_scroll.verticalScrollBar()  # noqa: SLF001
        assert scrollbar is not None
        assert scrollbar.maximum() > 0
        assert dialog.height() == 900
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
