from __future__ import annotations

import logging
import sys
import threading

import pytest

from expo_jbm329.app.logging.crash_hooks import install_crash_hooks


@pytest.fixture
def restore_hooks():
    original_sys = sys.excepthook
    original_threading = threading.excepthook
    yield
    sys.excepthook = original_sys
    threading.excepthook = original_threading


def _raise_value_error() -> None:
    message = "boom"
    raise ValueError(message)


def test_unhandled_exception_is_logged_and_previous_hook_called(restore_hooks, caplog):
    previous_calls = []
    sys.excepthook = lambda *args: previous_calls.append(args)
    logger = logging.getLogger("test.crash_hooks")
    install_crash_hooks(logger)

    try:
        _raise_value_error()
    except ValueError as exc:
        with caplog.at_level(logging.CRITICAL, logger="test.crash_hooks"):
            sys.excepthook(type(exc), exc, exc.__traceback__)

    assert "Unhandled exception" in caplog.text
    assert "ValueError: boom" in caplog.text
    assert len(previous_calls) == 1


def test_unhandled_thread_exception_is_logged(restore_hooks, caplog):
    threading.excepthook = lambda args: None
    logger = logging.getLogger("test.crash_hooks")
    install_crash_hooks(logger)

    def fail():
        message = "thread boom"
        raise RuntimeError(message)

    with caplog.at_level(logging.CRITICAL, logger="test.crash_hooks"):
        thread = threading.Thread(target=fail, name="worker-x")
        thread.start()
        thread.join()

    assert "Unhandled exception in thread worker-x" in caplog.text
    assert "RuntimeError: thread boom" in caplog.text
