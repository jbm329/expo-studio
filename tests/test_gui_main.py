from __future__ import annotations

from unittest.mock import Mock

import pytest

from expo_jbm329 import gui_main


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], ([], False)),
        (["expo", "-platform", "windows"], (["expo", "-platform", "windows"], False)),
        (
            ["expo", "--console-log", "-style", "fusion", "--console-log", "--", "--console-log"],
            (["expo", "-style", "fusion", "--", "--console-log"], True),
        ),
        (
            ["expo", "--console-log=DEBUG", "--", "--console-log"],
            (["expo", "--console-log=DEBUG", "--", "--console-log"], False),
        ),
    ],
)
def test_extract_console_log_flag(argv, expected):
    assert gui_main._extract_console_log_flag(argv) == expected


def test_gui_main_consumes_shipped_option_before_qt_and_passes_it_to_services(monkeypatch):
    qt_application = Mock()
    qt_application.return_value.exec.return_value = 0
    window = Mock()
    monkeypatch.setattr(gui_main, "QApplication", qt_application)
    monkeypatch.setattr(gui_main, "QPixmap", Mock())
    monkeypatch.setattr(gui_main, "QSplashScreen", Mock())
    monkeypatch.setattr(gui_main, "run_bootstrap", Mock())
    monkeypatch.setattr(gui_main, "ExpoStudio", window)
    monkeypatch.setattr(gui_main.sys, "argv", ["expo", "--console-log", "-style", "fusion"])
    monkeypatch.setenv("EXPO_HARD_EXIT_AFTER_QT", "0")

    assert gui_main.gui_main() == 0

    qt_application.assert_called_once_with(["expo", "-style", "fusion"])
    window.return_value.init_services.assert_called_once_with(console_log=True)
