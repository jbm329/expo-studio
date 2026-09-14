from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QStatusBar, QWidget

from expo_jbm329.workbench.controllers.status_bar_controller import StatusBarController


@pytest.fixture
def sb_setup(qt_app):
    parent = QWidget()
    status_bar = QStatusBar(parent)
    ctrl = StatusBarController(parent, status_bar)
    return ctrl, parent, status_bar

def test_init_baseline(sb_setup):
    ctrl, parent, status_bar = sb_setup
    assert ctrl._permanent_status_text == "Välj en anslutning för att ansluta mot databas"
    assert ctrl.status_label.text() == ctrl._permanent_status_text
    assert ctrl.shape_label.text() == "Rader: -  |  Kolumner: -"
    assert not ctrl.progress.isVisible()

def test_set_status_permanent(sb_setup):
    ctrl, _, _ = sb_setup
    ctrl.set_status("Permanent message", timeout_ms=None)
    assert ctrl._permanent_status_text == "Permanent message"
    assert ctrl.status_label.text() == "Permanent message"

from PyQt6.QtCore import QCoreApplication

def test_set_status_transient_with_timeout(sb_setup):
    ctrl, _, status_bar = sb_setup
    ctrl.set_status("Transient message", timeout_ms=10)
    
    # Immediately it should show the transient text
    assert ctrl.status_label.text() == "Transient message"
    
    # Process events to allow timer to fire
    # Since we can't easily wait with qtbot, we use a loop with processEvents
    import time
    start = time.time()
    while ctrl.status_label.text() != ctrl._permanent_status_text and time.time() - start < 1.0:
        QCoreApplication.processEvents()
        time.sleep(0.01)

    assert ctrl.status_label.text() == ctrl._permanent_status_text

def test_restore_baseline(sb_setup):
    ctrl, _, status_bar = sb_setup
    ctrl.set_status("Temp", timeout_ms=0)
    assert ctrl.status_label.text() == "Temp"
    
    ctrl.restore_baseline()
    assert ctrl.status_label.text() == ctrl._permanent_status_text

def test_set_shape_status(sb_setup):
    ctrl, _, _ = sb_setup
    
    # Test with values
    ctrl.set_shape_status(1234, 56)
    # 1234 formatted with space as thousands separator in Swedish-like format used in code
    assert "1 234" in ctrl.shape_label.text()
    assert "56" in ctrl.shape_label.text()
    
    # Test with None (baseline)
    ctrl.set_shape_status(None, None)
    assert ctrl.shape_label.text() == "Rader: -  |  Kolumner: -"

def test_set_status_triggers_timer_when_off_thread(sb_setup, monkeypatch):
    from PyQt6.QtCore import QTimer
    ctrl, _, _ = sb_setup
    
    # Mock QTimer.singleShot to see if it's called
    calls = []
    def mock_single_shot(ms, callback):
        calls.append((ms, callback))
        
    monkeypatch.setattr(QTimer, "singleShot", mock_single_shot)
    
    # We need to trick the controller into thinking we are off-thread.
    # The controller checks: QThread.currentThread() is not app.thread()
    # Since we are in the main thread during tests, we can mock currentThread
    from PyQt6.QtCore import QThread
    original_current = QThread.currentThread
    
    class FakeThread:
        pass
    
    monkeypatch.setattr(QThread, "currentThread", lambda: FakeThread())
    
    ctrl.set_status("Off thread message")
    
    assert len(calls) == 1
    assert calls[0][0] == 0
    # The callback should be a lambda that calls set_status
    callback = calls[0][1]
    
    # Restore currentThread so we can actually call the callback in this thread
    monkeypatch.setattr(QThread, "currentThread", original_current)
    callback()
    
    assert ctrl.status_label.text() == "Off thread message"
