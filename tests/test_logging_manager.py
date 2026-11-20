from __future__ import annotations

import io
import logging
from unittest.mock import Mock

import pytest

from expo_jbm329.app.logging import logging_manager
from expo_jbm329.app.logging.logging_manager import LoggingManager


@pytest.fixture
def log_session(tmp_path, monkeypatch):
    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    logger_states = [(logger, logger.level, logger.propagate) for logger in (root, logging.getLogger("applogger.ui"))]
    log_path = tmp_path / "app.log"
    monkeypatch.setattr(logging_manager, "get_log_path", lambda: log_path)
    config = {"handlers": {"file": {"level": "DEBUG"}}}
    monkeypatch.setattr(logging_manager, "read_log_config", lambda: config)
    try:
        yield root, log_path, config
    finally:
        for handler in root.handlers[:]:
            if handler not in previous_handlers:
                root.removeHandler(handler)
                handler.close()
        for handler in previous_handlers:
            root.addHandler(handler)
        for logger, level, propagate in logger_states:
            logger.setLevel(level)
            logger.propagate = propagate


@pytest.mark.parametrize(
    ("platform", "frozen", "requested", "expected"),
    [
        ("win32", True, False, False),
        ("linux", True, False, False),
        ("linux", True, True, True),
        ("win32", True, True, True),
        ("darwin", True, True, False),
        ("win32", False, False, True),
    ],
)
def test_console_output_respects_launch_mode(log_session, monkeypatch, platform, frozen, requested, expected):
    _, log_path, cfg = log_session
    cfg["handlers"]["stdout"] = {"level": "INFO", "formatter": "verbose"}
    stderr = io.StringIO()
    attach = Mock()
    monkeypatch.setattr(logging_manager.sys, "platform", platform)
    monkeypatch.setattr(logging_manager.sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(logging_manager.sys, "stderr", stderr)
    monkeypatch.setattr(logging_manager, "open_parent_console", attach)

    manager = LoggingManager(console_log=requested)
    manager.setup()
    manager.ui_logger.info("mode check")
    logging.getLogger("external").info("filtered third-party message")

    assert ("mode check" in stderr.getvalue()) == expected
    assert ("function test_console_output_respects_launch_mode" in stderr.getvalue()) == expected
    assert "filtered third-party message" not in stderr.getvalue()
    assert "mode check" in log_path.read_text(encoding="utf-8")
    attach.assert_not_called()


def test_missing_console_config_uses_defaults_and_reload_keeps_opt_in(log_session, monkeypatch):
    root, _, cfg = log_session
    stderr = io.StringIO()
    monkeypatch.setattr(logging_manager.sys, "platform", "linux")
    monkeypatch.setattr(logging_manager.sys, "frozen", True, raising=False)
    monkeypatch.setattr(logging_manager.sys, "stderr", stderr)
    cfg["loggers"] = {"applogger.ui": {"level": "DEBUG"}}
    manager = LoggingManager(console_log=True)
    manager.setup()
    old_file = next(handler for handler in root.handlers if isinstance(handler, logging.FileHandler))
    manager.ui_logger.info("below default")
    manager.ui_logger.warning("default warning")
    cfg["handlers"]["stdout"] = {"level": "DEBUG"}
    manager.setup()
    manager.setup()
    manager.ui_logger.debug("after reload")

    assert old_file.stream is None
    assert not stderr.closed
    assert "below default" not in stderr.getvalue()
    assert stderr.getvalue().count("default warning") == 1
    assert stderr.getvalue().count("after reload") == 1


def test_windows_console_stream_owned_by_handler(log_session, monkeypatch):
    first, second = io.StringIO(), io.StringIO()
    attach = Mock(side_effect=[first, second])
    monkeypatch.setattr(logging_manager.sys, "platform", "win32")
    monkeypatch.setattr(logging_manager.sys, "frozen", True, raising=False)
    monkeypatch.setattr(logging_manager.sys, "stderr", None)
    monkeypatch.setattr(logging_manager, "open_parent_console", attach)
    manager = LoggingManager(console_log=True)
    manager.setup()
    manager.ui_logger.warning("attached")
    assert first.getvalue().count("attached") == 1

    manager.setup()
    manager.ui_logger.warning("still attached")

    assert first.closed
    assert second.getvalue().count("still attached") == 1


def test_frozen_windows_redirect_uses_utf8_without_closing_inherited_stderr(log_session, monkeypatch, tmp_path):
    dest = tmp_path / "stderr.txt"
    monkeypatch.setattr(logging_manager.sys, "platform", "win32")
    monkeypatch.setattr(logging_manager.sys, "frozen", True, raising=False)
    with dest.open("w", encoding="cp1252") as stderr:
        monkeypatch.setattr(logging_manager.sys, "stderr", stderr)
        manager = LoggingManager(console_log=True)
        manager.setup()
        manager.ui_logger.warning("Unicode: \u00e5 \u03a9")
        manager.setup()
        manager.ui_logger.warning("still redirected")
        assert not stderr.closed
        assert stderr.encoding == "cp1252"

    output = dest.read_text(encoding="utf-8")
    assert output.count("Unicode: \u00e5 \u03a9") == 1
    assert output.count("still redirected") == 1


@pytest.mark.parametrize("attach_error", [None, OSError("console device unavailable")])
def test_no_windows_console_does_not_break_file_logging(log_session, monkeypatch, attach_error):
    _, log_path, _ = log_session
    attach = Mock(return_value=None, side_effect=attach_error)
    monkeypatch.setattr(logging_manager.sys, "platform", "win32")
    monkeypatch.setattr(logging_manager.sys, "frozen", True, raising=False)
    monkeypatch.setattr(logging_manager.sys, "stderr", None)
    monkeypatch.setattr(logging_manager, "open_parent_console", attach)
    manager = LoggingManager(console_log=True)

    manager.setup()
    manager.ui_logger.warning("file retains warning")

    attach.assert_called_once_with()
    output = log_path.read_text(encoding="utf-8")
    assert "file retains warning" in output
    assert ("failed to initialize console output" in output) == (attach_error is not None)


def test_frozen_without_sinks_does_not_use_last_resort(log_session, monkeypatch):
    _, _, cfg = log_session
    cfg["handlers"].clear()
    stderr = io.StringIO()
    monkeypatch.setattr(logging_manager.sys, "platform", "linux")
    monkeypatch.setattr(logging_manager.sys, "frozen", True, raising=False)
    monkeypatch.setattr(logging_manager.sys, "stderr", stderr)
    manager = LoggingManager()
    manager.setup()
    manager.ui_logger.warning("no configured destination")

    assert stderr.getvalue() == ""
