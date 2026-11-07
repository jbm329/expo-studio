from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QEvent, Qt, QTranslator, QUrl
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QMainWindow, QPushButton

from expo_jbm329.app.help_topics import HelpTopic
from expo_jbm329.app.settings import settings_editor
from expo_jbm329.app.settings.config_store import load_settings, read_log_config
from expo_jbm329.app.settings.log_config_editor import LogConfigEditor
from expo_jbm329.app.settings.settings_editor import SettingsEditor
from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
from expo_jbm329.workbench.controllers.menu_controller import MenuController

if TYPE_CHECKING:
    from collections.abc import Iterator

HELP_LABELS = {"en": "Help", "sv": "Hjälp", "de": "Hilfe", "fr": "Aide", "it": "Aiuto", "es": "Ayuda", "pl": "Pomoc"}


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


@pytest.fixture(params=[HelpTopic.GENERAL_SETTINGS, HelpTopic.LOG_SETTINGS], ids=["general", "log"])
def help_topic(request: pytest.FixtureRequest) -> HelpTopic:
    topic = request.param
    assert isinstance(topic, HelpTopic)
    return topic


def _dialog_for_topic(
    topic: HelpTopic, dialogs: MagicMock, parent: QMainWindow | None = None
) -> SettingsEditor | LogConfigEditor:
    if topic is HelpTopic.LOG_SETTINGS:
        return LogConfigEditor(parent=parent, dialogs=dialogs)
    assert topic is HelpTopic.GENERAL_SETTINGS
    return _settings_dialog(dialogs, parent)


def _help_button(dialog: SettingsEditor | LogConfigEditor) -> QPushButton:
    boxes = dialog.findChildren(QDialogButtonBox)
    assert len(boxes) == 1
    button = boxes[0].button(QDialogButtonBox.StandardButton.Help)
    assert button is not None
    assert boxes[0].buttonRole(button) == QDialogButtonBox.ButtonRole.HelpRole
    return button


def _press_f1(app: QApplication, dialog: SettingsEditor | LogConfigEditor) -> None:
    focus_widget = dialog.txt_documents_dir if isinstance(dialog, SettingsEditor) else dialog.cb_logger_level
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
    dialogs = MagicMock(spec=DialogService)
    dialog = _dialog_for_topic(help_topic, dialogs)
    persisted = load_settings() if isinstance(dialog, SettingsEditor) else read_log_config()
    if isinstance(dialog, SettingsEditor):
        dialog.spin_undo_limit.setValue(37)
    else:
        dialog.spin_file_backup.setValue(37)
    try:
        dialog.show()
        dialog.activateWindow()
        qt_app.processEvents()
        help_button = _help_button(dialog)
        assert help_button.text() == HELP_LABELS[help_language]
        assert not help_button.autoDefault()
        assert not help_button.isDefault()
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
        else:
            assert dialog.spin_file_backup.value() == 37
            assert read_log_config() == persisted
        dialogs.info.assert_not_called()
        dialogs.critical.assert_not_called()
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
