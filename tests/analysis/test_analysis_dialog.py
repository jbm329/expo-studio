from __future__ import annotations

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QWidget

from expo_jbm329.gui.dialogs.analysis.analysis_dialog import AnalysisDialog
from expo_jbm329.gui.dialogs.service.common.localization import TR_CLOSE
from expo_jbm329.services.analysis.categories import AnalysisCategory
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
    first = dialog.content_widget()
    replacement = QWidget()

    dialog.set_content_widget(replacement)

    assert dialog.content_widget() is replacement
    assert dialog.content_widget() is not first


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
    dialog.set_config_widget(QWidget())
    replacement = QWidget()

    dialog.set_config_widget(replacement)

    assert dialog.config_widget() is replacement


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
