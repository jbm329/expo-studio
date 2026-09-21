from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QTableView, QWidget

from expo_jbm329.workbench.controllers.busy_overlay_controller import (
    BusyOverlayController,
)


class DummySignal:
    def __init__(self) -> None:
        self.connected = []

    def connect(self, callback):
        self.connected.append(callback)

    def disconnect(self):
        self.connected.clear()


class DummyOverlay:
    def __init__(self, target, message="", indeterminate=True) -> None:
        self.target = target
        self.message = message
        self.indeterminate = indeterminate
        self.cancel_requested = DummySignal()
        self.show_calls = []
        self.progress_calls = []
        self.hidden = False
        self.raised = False

    def show_overlay(self, **kwargs):
        self.show_calls.append(kwargs)

    def raise_(self):
        self.raised = True

    def hide_overlay(self):
        self.hidden = True

    def set_progress(self, value):
        self.progress_calls.append(value)

    def isVisible(self):
        return not self.hidden


class DummyDialogService:
    def __init__(self) -> None:
        self.warn_calls = []

    def warn(self, parent, title, text):
        self.warn_calls.append((parent, title, text))


class DummyParent(QWidget):
    pass


class DummyView(QTableView):
    def __init__(self) -> None:
        super().__init__()
        self._viewport = QWidget()

    def viewport(self):
        return self._viewport


@pytest.fixture
def controller(monkeypatch):
    created = []

    def overlay_factory(target, message="", indeterminate=True):
        overlay = DummyOverlay(target, message=message, indeterminate=indeterminate)
        created.append(overlay)
        return overlay

    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.busy_overlay_controller.BusyOverlayWidget",
        overlay_factory,
    )
    dialogs = DummyDialogService()
    parent = DummyParent()
    return BusyOverlayController(parent=parent, dialogs=dialogs)


def test_attach_reuses_overlay(controller):
    target = QWidget()

    first = controller.attach(target, message="Hello", indeterminate=False)
    second = controller.attach(target, message="Other", indeterminate=True)

    assert first is second
    assert first.message == "Hello"
    assert first.indeterminate is False


def test_show_hide_progress_and_visibility(controller, monkeypatch):
    target = QWidget()
    process_events = MagicMock()
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.busy_overlay_controller.QApplication.processEvents",
        process_events,
    )

    controller.show(
        target,
        message="Working",
        indeterminate=False,
        cancelable=True,
        timeout_ms=100,
    )

    overlay = controller._overlays[target]
    assert overlay.show_calls[-1]["message"] == "Working"
    assert overlay.show_calls[-1]["show_cancel_button"] is True
    assert overlay.raised is True
    assert process_events.called
    assert controller.is_visible(target) is True

    controller.set_progress(target, 42)
    assert overlay.progress_calls == [42]

    controller.hide(target)
    assert overlay.hidden is True
    assert controller.is_visible(target) is False


def test_watchdog_warns_and_hides(controller, monkeypatch):
    target = QWidget()
    monkeypatch.setattr(QTimer, "start", lambda self: None)

    controller.show(target, message="Working", timeout_ms=1)
    assert target in controller._watchdogs

    watchdog = controller._watchdogs[target]
    callback = watchdog.timeout
    assert callback is not None

    controller._watchdogs[target].timeout.disconnect()
    controller._watchdogs[target].timeout.connect(lambda: None)

    controller._start_watchdog(target, 1)
    assert target in controller._watchdogs


def test_show_for_view_uses_viewport(controller):
    view = DummyView()

    controller.show_for_view(view, message="View", indeterminate=True)

    assert view.viewport() in controller._overlays
