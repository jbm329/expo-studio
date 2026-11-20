"""Verify packaged and source console settings behavior."""

import io
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QCoreApplication, QTranslator
from PyQt6.QtWidgets import QApplication, QDialog, QLabel

from expo_jbm329.app.logging.logging_manager import LoggingManager
from expo_jbm329.app.settings.config_store import read_log_config, write_log_config
from expo_jbm329.app.settings.log_config_editor import LogConfigEditor
from expo_jbm329.i18n.language import Language


@pytest.fixture
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers = root.handlers[:]
    loggers = [root, *(logging.getLogger(f"applogger.{name}") for name in ("ui", "service", "jobs", "db"))]
    states = [(logger, logger.level, logger.propagate) for logger in loggers]
    try:
        yield
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            if handler not in handlers:
                handler.close()
        for handler in handlers:
            root.addHandler(handler)
        for logger, level, propagate in states:
            logger.setLevel(level)
            logger.propagate = propagate


@pytest.mark.parametrize(
    ("flag", "available", "reset"), [(False, True, False), (False, True, True), (True, False, False)]
)
def test_hidden_console_preferences_and_activation(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None, flag: bool, available: bool, reset: bool
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr if available else None)
    write_log_config({"handlers": {"stdout": {"level": "ERROR", "formatter": "verbose"}}})
    manager = LoggingManager(console_log=flag)
    manager.setup()
    assert not manager.frozen_console_active
    dialog = LogConfigEditor(dialogs=Mock(), frozen_console_active=manager.frozen_console_active)
    try:
        assert dialog.gb_console.isHidden()
        if reset:
            dialog._on_reset_defaults()
        dialog._on_save()
        assert dialog.result() == QDialog.DialogCode.Accepted
        manager.setup()
        manager.ui_logger.error("must stay quiet")
        assert not manager.frozen_console_active
        assert stderr.getvalue() == ""
        prefs = {"level": "WARNING", "formatter": "default"} if reset else {"level": "ERROR", "formatter": "verbose"}
        assert read_log_config()["handlers"]["stdout"] == prefs
    finally:
        dialog.close()


def test_active_console_save_applies_level_and_format_on_reload(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)
    manager = LoggingManager(console_log=True)
    manager.setup()
    assert manager.frozen_console_active
    dialog = LogConfigEditor(dialogs=Mock(), frozen_console_active=manager.frozen_console_active)
    try:
        assert not dialog.gb_console.isHidden()
        assert dialog.chk_console_enabled.isHidden()
        assert dialog.cb_stdout_level.isEnabled()
        assert dialog.cb_stdout_formatter.isEnabled()
        dialog.cb_stdout_level.setCurrentText("INFO")
        dialog.cb_stdout_formatter.setCurrentText("verbose")
        dialog._on_save()
        manager.setup()
        manager.ui_logger.info("visible after reload")
        assert stderr.getvalue().count("visible after reload") == 1
        assert "test_active_console_save_applies_level_and_format_on_reload" in stderr.getvalue()
    finally:
        dialog.close()


def test_source_console_activation_checkbox_remains_editable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    dialog = LogConfigEditor(dialogs=Mock())
    try:
        assert not dialog.gb_console.isHidden()
        assert not dialog.chk_console_enabled.isHidden()
        dialog.chk_console_enabled.setChecked(False)
        assert not dialog.cb_stdout_level.isEnabled()
        dialog.chk_console_enabled.setChecked(True)
        assert dialog.cb_stdout_level.isEnabled()
    finally:
        dialog.close()


def test_cancel_does_not_save_packaged_console_edits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    original = read_log_config()
    dialog = LogConfigEditor(dialogs=Mock(), frozen_console_active=True)
    try:
        dialog.cb_stdout_level.setCurrentText("DEBUG")
        dialog.cb_stdout_formatter.setCurrentText("verbose")
        dialog.reject()
        assert read_log_config() == original
    finally:
        dialog.close()


@pytest.mark.parametrize("language", list(Language))
def test_console_guidance_fits_localized_dialog(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch, language: Language
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    catalog = Path(__file__).parents[1] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language.value}.qm"
    translator = QTranslator()
    assert translator.load(str(catalog))
    qt_app.installTranslator(translator)
    dialog = LogConfigEditor(dialogs=Mock(), frozen_console_active=True)
    try:
        dialog.show()
        qt_app.processEvents()
        source = "Enabled by --console-log."
        localized = QCoreApplication.translate("LogConfigEditor", source)
        assert (localized == source) == (language == Language.ENGLISH)
        note = next(label for label in dialog.gb_console.findChildren(QLabel) if label.text() == localized)
        assert note.isVisible()
        assert note.height() >= note.heightForWidth(note.width())
        assert dialog.gb_console.rect().contains(note.geometry())
    finally:
        dialog.close()
        qt_app.removeTranslator(translator)
