from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QEvent, Qt, QUrl
from PyQt6.QtGui import QKeyEvent, QKeySequence
from PyQt6.QtWidgets import QApplication, QMainWindow

from expo_jbm329.app import expo_studio, help_topics
from expo_jbm329.app.expo_studio import ExpoStudio
from expo_jbm329.app.help_topics import HelpTopic
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.workbench.controllers.menu_controller import MenuController


class _ManualWindow(ExpoStudio):
    """Exercise the real manual callback without starting workbench services."""

    def __init__(self, dialogs: MagicMock) -> None:
        QMainWindow.__init__(self)
        self._dialogs = dialogs
        self._allow_close = True

    def open_manual(self) -> None:
        self._open_user_manual()


@pytest.mark.parametrize("opened", [True, False])
def test_manual_opening_uses_home_topic_and_preserves_warning(monkeypatch: pytest.MonkeyPatch, opened: bool) -> None:
    urls: list[str] = []

    def open_url(url: QUrl) -> bool:
        urls.append(url.toString())
        return opened

    # A different base proves the callback resolves through HelpTopic, not a
    # separate metadata import or a hard-coded homepage.
    monkeypatch.setattr(help_topics, "USER_MANUAL_URL", "https://example.com/manual/")
    monkeypatch.setattr(expo_studio.QDesktopServices, "openUrl", open_url)
    dialogs = MagicMock(spec=QtDialogService)
    window = _ManualWindow(dialogs)
    try:
        window.open_manual()
        assert urls == [HelpTopic.HOME.url]
        if opened:
            dialogs.warn.assert_not_called()
        else:
            dialogs.warn.assert_called_once_with(
                window,
                window.tr("Unable to open link"),
                window.tr("The user manual could not be opened.\n\n{url}").format(url=HelpTopic.HOME.url),
            )
    finally:
        window.close()


def test_menu_and_f1_open_home_once_per_activation(monkeypatch: pytest.MonkeyPatch, qt_app: QApplication) -> None:
    urls: list[str] = []

    def open_url(url: QUrl) -> bool:
        urls.append(url.toString())
        return True

    monkeypatch.setattr(expo_studio.QDesktopServices, "openUrl", open_url)
    dialogs = MagicMock(spec=QtDialogService)
    window = _ManualWindow(dialogs)
    noop = MagicMock()
    menubar = window.menuBar()
    assert menubar is not None
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
        open_user_manual=window.open_manual,
    )
    help_menu = menubar.actions()[-1].menu()
    assert help_menu is not None
    action = help_menu.actions()[0]
    assert action.shortcut() == QKeySequence(QKeySequence.StandardKey.HelpContents)
    assert action.shortcutContext() == Qt.ShortcutContext.WindowShortcut
    try:
        action.trigger()
        assert urls == [HelpTopic.HOME.url]
        window.show()
        window.activateWindow()
        qt_app.processEvents()
        for expected_count in (2, 3):
            for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                qt_app.sendEvent(window, QKeyEvent(event_type, Qt.Key.Key_F1, Qt.KeyboardModifier.NoModifier))
            assert urls == [HelpTopic.HOME.url] * expected_count
        dialogs.warn.assert_not_called()
        noop.assert_not_called()
    finally:
        window.close()
