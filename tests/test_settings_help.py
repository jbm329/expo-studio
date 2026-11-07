from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QEvent, Qt, QTranslator, QUrl
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QMainWindow, QPushButton

from expo_jbm329.app.help_topics import HelpTopic
from expo_jbm329.app.settings import rest_connection_editor, settings_editor
from expo_jbm329.app.settings.config_store import (
    load_settings,
    read_connections,
    read_log_config,
    read_rest_connections,
)
from expo_jbm329.app.settings.connection_editor import ConnectionEditor
from expo_jbm329.app.settings.log_config_editor import LogConfigEditor
from expo_jbm329.app.settings.rest_connection_editor import RestConnectionEditor
from expo_jbm329.app.settings.settings_editor import SettingsEditor
from expo_jbm329.gui.dialogs.rest import scb_browser_dialog
from expo_jbm329.gui.dialogs.rest.scb_browser_dialog import ScbBrowserDialog
from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
from expo_jbm329.services.rest.scb.browser import ScbTableMetadata, ScbTableSummary, ScbVariable, ScbVariableValue
from expo_jbm329.workbench.controllers.menu_controller import MenuController

if TYPE_CHECKING:
    from collections.abc import Iterator

HELP_LABELS = {"en": "Help", "sv": "Hjälp", "de": "Hilfe", "fr": "Aide", "it": "Aiuto", "es": "Ayuda", "pl": "Pomoc"}
type SettingsHelpDialog = SettingsEditor | LogConfigEditor | ConnectionEditor | RestConnectionEditor | ScbBrowserDialog


@pytest.fixture(autouse=True)
def offline_scb_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = ScbTableMetadata(
        table_id="sample",
        label="Sample table",
        variables=(
            ScbVariable(
                name="Region",
                label="Region",
                display_name="Region",
                values=(ScbVariableValue(code="01", label="First"), ScbVariableValue(code="02", label="Second")),
            ),
        ),
    )
    monkeypatch.setattr(
        scb_browser_dialog, "fetch_scb_tables", MagicMock(return_value=[ScbTableSummary("sample", "Sample")])
    )
    monkeypatch.setattr(scb_browser_dialog, "fetch_scb_table_metadata", MagicMock(return_value=metadata))


@pytest.fixture(params=list(HELP_LABELS))
def help_language(request: pytest.FixtureRequest, qt_app: QApplication) -> Iterator[str]:
    language = str(request.param)
    translator = QTranslator()
    catalog = Path(__file__).resolve().parents[1] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language}.qm"
    assert translator.load(str(catalog))
    qt_app.installTranslator(translator)
    try:
        yield language
    finally:
        qt_app.removeTranslator(translator)


def _settings_dialog(dialogs: MagicMock, parent: QMainWindow | None = None) -> SettingsEditor:
    highlighter = MagicMock()
    highlighter.available_themes_with_labels.return_value = [("system", "System")]
    return SettingsEditor(
        parent=parent, dialogs=dialogs, file_dialogs=MagicMock(), highlighter_theme_service=highlighter
    )


@pytest.fixture(
    params=[
        HelpTopic.GENERAL_SETTINGS,
        HelpTopic.LOG_SETTINGS,
        HelpTopic.DATABASE_CONNECTIONS,
        HelpTopic.REST_API_CONNECTIONS,
        HelpTopic.SCB_QUERY_BUILDER,
    ],
    ids=["general", "log", "database", "rest", "scb"],
)
def help_topic(request: pytest.FixtureRequest) -> HelpTopic:
    topic = request.param
    assert isinstance(topic, HelpTopic)
    return topic


def _dialog_for_topic(topic: HelpTopic, dialogs: MagicMock, parent: QMainWindow | None = None) -> SettingsHelpDialog:
    if topic is HelpTopic.SCB_QUERY_BUILDER:
        return ScbBrowserDialog(parent=parent, dialogs=dialogs)
    if topic is HelpTopic.REST_API_CONNECTIONS:
        return RestConnectionEditor(parent=parent, dialogs=dialogs)
    if topic is HelpTopic.DATABASE_CONNECTIONS:
        return ConnectionEditor(parent=parent, dialogs=dialogs)
    if topic is HelpTopic.LOG_SETTINGS:
        return LogConfigEditor(parent=parent, dialogs=dialogs)
    assert topic is HelpTopic.GENERAL_SETTINGS
    return _settings_dialog(dialogs, parent)


def _help_button(dialog: SettingsHelpDialog) -> QPushButton:
    boxes = dialog.findChildren(QDialogButtonBox)
    assert len(boxes) == 1
    button = boxes[0].button(QDialogButtonBox.StandardButton.Help)
    assert button is not None
    assert boxes[0].buttonRole(button) == QDialogButtonBox.ButtonRole.HelpRole
    return button


def _press_f1(app: QApplication, dialog: SettingsHelpDialog) -> None:
    app.setActiveWindow(dialog)
    if isinstance(dialog, SettingsEditor):
        focus_widget = dialog.txt_documents_dir
    elif isinstance(dialog, LogConfigEditor):
        focus_widget = dialog.cb_logger_level
    elif isinstance(dialog, RestConnectionEditor):
        focus_widget = dialog.url_edit
    elif isinstance(dialog, ScbBrowserDialog):
        focus_widget = dialog.value_list
    else:
        focus_widget = dialog.list_widget
    focus_widget.setFocus()
    app.processEvents()
    for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        app.sendEvent(focus_widget, QKeyEvent(event_type, Qt.Key.Key_F1, Qt.KeyboardModifier.NoModifier))


def test_standard_help_button_localizes_in_every_language(help_language: str) -> None:
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Help)
    localize_dialog_buttons(buttons)
    button = buttons.button(QDialogButtonBox.StandardButton.Help)
    assert button is not None
    assert button.text() == HELP_LABELS[help_language]


@pytest.mark.parametrize("opened", [True, False])
def test_settings_help_button_and_f1_preserve_edits(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, help_language: str, help_topic: HelpTopic, opened: bool
) -> None:
    urls: list[str] = []

    def open_url(url: QUrl) -> bool:
        urls.append(url.toString())
        return opened

    monkeypatch.setattr(settings_editor.QDesktopServices, "openUrl", open_url)
    fetch = MagicMock()
    monkeypatch.setattr(rest_connection_editor, "fetch_json", fetch)
    dialogs = MagicMock(spec=DialogService)
    changes = MagicMock()
    dialog = _dialog_for_topic(help_topic, dialogs)
    if isinstance(dialog, SettingsEditor):
        persisted = load_settings()
        dialog.spin_undo_limit.setValue(37)
    elif isinstance(dialog, LogConfigEditor):
        persisted = read_log_config()
        dialog.spin_file_backup.setValue(37)
    elif isinstance(dialog, (RestConnectionEditor, ScbBrowserDialog)):
        persisted = read_rest_connections()
    else:
        persisted = read_connections()
    try:
        dialog.show()
        dialog.activateWindow()
        qt_app.processEvents()
        if isinstance(dialog, ConnectionEditor):
            dialog.db_type_combo.setCurrentIndex(dialog.db_type_combo.findData("postgresql"))
            dialog.server_edit.setText("unsaved.example")
            dialog.connections_changed.connect(changes)
        elif isinstance(dialog, RestConnectionEditor):
            dialog.url_edit.setText("https://unsaved.example/api")
            dialog.connections_changed.connect(changes)
        elif isinstance(dialog, ScbBrowserDialog):
            dialog.select_all_button.click()
        help_button = _help_button(dialog)
        assert help_button.text() == HELP_LABELS[help_language]
        assert not help_button.autoDefault()
        assert not help_button.isDefault()
        if isinstance(dialog, (ConnectionEditor, RestConnectionEditor)):
            list_bottom = dialog.list_widget.mapTo(dialog, dialog.list_widget.rect().bottomLeft())
            help_top = help_button.mapTo(dialog, help_button.rect().topLeft())
            assert help_top.y() > list_bottom.y()
            assert help_top.x() == list_bottom.x()
            assert help_top.x() < dialog.btn_add.mapTo(dialog, dialog.btn_add.rect().topLeft()).x()
        elif isinstance(dialog, ScbBrowserDialog):
            assert dialog.variable_list.height() == dialog.value_list.height()
            assert dialog.variable_list.y() == dialog.value_list.y()
            help_top = help_button.mapTo(dialog, help_button.rect().topLeft())
            assert help_top.y() > dialog.selection_counter.y() + dialog.selection_counter.height()
            assert help_top.x() < dialog.apply_button.x()
        else:
            action_buttons = [
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() in {dialog.tr("Reset defaults"), dialog.tr("Cancel"), dialog.tr("Save")}
            ]
            assert len(action_buttons) == 3
            help_left = help_button.mapTo(dialog, help_button.rect().topLeft()).x()
            assert all(button.mapTo(dialog, button.rect().topLeft()).x() > help_left for button in action_buttons)
        help_button.click()
        assert urls == [help_topic.url]
        _press_f1(qt_app, dialog)
        assert urls == [help_topic.url] * 2
        assert dialog.isVisible()
        if isinstance(dialog, SettingsEditor):
            assert dialog.spin_undo_limit.value() == 37
            assert load_settings() == persisted
        elif isinstance(dialog, LogConfigEditor):
            assert dialog.spin_file_backup.value() == 37
            assert read_log_config() == persisted
        elif isinstance(dialog, RestConnectionEditor):
            assert dialog.url_edit.text() == "https://unsaved.example/api"
            assert read_rest_connections() == persisted
            changes.assert_not_called()
        elif isinstance(dialog, ScbBrowserDialog):
            assert dialog.result_data is None
            assert dialog.apply_button.isEnabled()
            for row in range(dialog.value_list.count()):
                item = dialog.value_list.item(row)
                assert item is not None
                assert item.checkState() == Qt.CheckState.Checked
            assert read_rest_connections() == persisted
            assert dialog.variable_list.height() == dialog.value_list.height()
        else:
            assert dialog.server_edit.text() == "unsaved.example"
            assert read_connections() == persisted
            changes.assert_not_called()
        dialogs.info.assert_not_called()
        dialogs.critical.assert_not_called()
        fetch.assert_not_called()
        if opened:
            dialogs.warn.assert_not_called()
        else:
            assert dialogs.warn.call_count == 2
            dialogs.warn.assert_called_with(
                dialog,
                dialog.tr("Unable to open link"),
                dialog.tr("The user manual could not be opened.\n\n{url}").format(url=help_topic.url),
            )
            if help_language != "en":
                assert dialog.tr("Unable to open link") != "Unable to open link"
                assert dialog.tr("The user manual could not be opened.\n\n{url}") != (
                    "The user manual could not be opened.\n\n{url}"
                )
    finally:
        dialog.close()


def test_settings_f1_does_not_trigger_parent_manual_action(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, help_topic: HelpTopic
) -> None:
    opener = MagicMock(return_value=True)
    monkeypatch.setattr(settings_editor.QDesktopServices, "openUrl", opener)
    parent = QMainWindow()
    menubar = parent.menuBar()
    assert menubar is not None
    noop = MagicMock()
    homepage = MagicMock()
    MenuController(
        menubar=menubar,
        new_file=noop,
        open_file=noop,
        save_file=noop,
        save_file_as=noop,
        quit_app=noop,
        export_csv=noop,
        export_excel=noop,
        export_data=noop,
        export_profile=noop,
        clear_editor=noop,
        open_settings_dialog=noop,
        open_log_settings_dialog=noop,
        open_connection_dialog=noop,
        open_rest_connection_dialog=noop,
        show_about_dialog=noop,
        open_user_manual=homepage,
    )
    dialog = _dialog_for_topic(help_topic, MagicMock(spec=DialogService), parent)
    try:
        parent.show()
        dialog.show()
        dialog.activateWindow()
        qt_app.processEvents()
        _press_f1(qt_app, dialog)
        opener.assert_called_once()
        assert opener.call_args.args[0].toString() == help_topic.url
        homepage.assert_not_called()
        dialog.close()
        parent.activateWindow()
        qt_app.processEvents()
        for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            qt_app.sendEvent(parent, QKeyEvent(event_type, Qt.Key.Key_F1, Qt.KeyboardModifier.NoModifier))
        homepage.assert_called_once_with(False)
        assert opener.call_count == 1
    finally:
        dialog.close()
        parent.close()


def test_scb_lists_keep_equal_height_with_limit_warning(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, help_language: str
) -> None:
    values = tuple(ScbVariableValue(str(index), str(index)) for index in range(101))
    metadata = ScbTableMetadata(
        table_id="sample",
        label="Sample table",
        variables=tuple(ScbVariable(name, name, name, values) for name in ("Region", "Period")),
    )
    monkeypatch.setattr(scb_browser_dialog, "fetch_scb_table_metadata", MagicMock(return_value=metadata))
    opener = MagicMock(return_value=True)
    monkeypatch.setattr(scb_browser_dialog.QDesktopServices, "openUrl", opener)
    dialog = ScbBrowserDialog(dialogs=MagicMock(spec=DialogService))
    try:
        dialog.show()
        dialog.activateWindow()
        dialog.select_all_button.click()
        dialog.variable_list.setCurrentRow(1)
        dialog.select_all_button.click()
        qt_app.processEvents()
        assert dialog.selection_warning.text() == dialog.tr("This selection exceeds the SCB limit.")
        assert not dialog.apply_button.isEnabled()
        assert dialog.variable_list.height() == dialog.value_list.height()
        assert dialog.variable_list.y() == dialog.value_list.y()
        help_button = _help_button(dialog)
        help_top = help_button.mapTo(dialog, help_button.rect().topLeft())
        assert help_top.y() > dialog.selection_warning.y() + dialog.selection_warning.height()
        assert dialog.selection_counter.geometry().right() <= dialog.width()
        assert dialog.selection_warning.geometry().right() <= dialog.width()
        help_button.click()
        _press_f1(qt_app, dialog)
        assert opener.call_count == 2
        assert not dialog.apply_button.isEnabled()
        assert dialog.result_data is None
        assert dialog.selection_warning.text() == dialog.tr("This selection exceeds the SCB limit.")
        dialog.clear_selection_button.click()
        assert dialog.apply_button.isEnabled()
        assert dialog.selection_warning.text() == ""
        assert dialog.variable_list.height() == dialog.value_list.height()
    finally:
        dialog.close()


def test_scb_f1_uses_builder_topic_then_rest_topic_after_closing(
    monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, help_language: str
) -> None:
    urls: list[str] = []

    def open_url(url: QUrl) -> bool:
        urls.append(url.toString())
        return True

    monkeypatch.setattr(scb_browser_dialog.QDesktopServices, "openUrl", open_url)
    dialogs = MagicMock(spec=DialogService)
    parent = RestConnectionEditor(dialogs=dialogs)
    dialog = ScbBrowserDialog(parent=parent, dialogs=dialogs)
    try:
        parent.show()
        dialog.show()
        _press_f1(qt_app, dialog)
        assert urls == [HelpTopic.SCB_QUERY_BUILDER.url]
        dialog.close()
        _press_f1(qt_app, parent)
        assert urls == [HelpTopic.SCB_QUERY_BUILDER.url, HelpTopic.REST_API_CONNECTIONS.url]
    finally:
        dialog.close()
        parent.close()
