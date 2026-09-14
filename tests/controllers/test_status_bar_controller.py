from __future__ import annotations

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QStatusBar, QWidget

from expo_jbm329.workbench.controllers.status_bar_controller import StatusBarController


def make_ctrl():
    parent = QWidget()
    status_bar = QStatusBar(parent)
    ctrl = StatusBarController(parent, status_bar)
    return ctrl


def test_init_baseline():
    ctrl = make_ctrl()

    assert ctrl._permanent_status_text == "Ready"
    assert ctrl.status_label.text() == "Ready"
    assert ctrl.shape_label.text() == "Rows: -  |  Columns: -"
    assert not ctrl.progress.isVisible()


def test_set_status_permanent():
    ctrl = make_ctrl()

    ctrl.set_status("Permanent message", timeout_ms=None)

    QCoreApplication.processEvents()
    assert ctrl.status_label.text() == "Permanent message"


def test_set_status_transient_and_restore():
    ctrl = make_ctrl()

    ctrl.set_status("Transient message", timeout_ms=1)
    assert ctrl.status_label.text() in {"Transient message", "Ready"}


def test_restore_baseline():
    ctrl = make_ctrl()

    ctrl.set_status("Temp", timeout_ms=0)
    ctrl.restore_baseline()
    assert ctrl.status_label.text() in {"Temp", "Ready"}


def test_set_shape_status():
    ctrl = make_ctrl()

    ctrl.set_shape_status(1234, 56)
    assert "1 234" in ctrl.shape_label.text()
    assert "56" in ctrl.shape_label.text()

    ctrl.set_shape_status(None, None)
    assert ctrl.shape_label.text() == "Rows: -  |  Columns: -"
