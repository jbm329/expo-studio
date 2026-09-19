from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QWidget

from expo_jbm329.workbench.controllers.async_operation_controller import (
    AsyncOperationController,
)


class DummyJob:
    def __init__(self) -> None:
        self.progress = SimpleNamespace(connect=MagicMock())
        self.result = SimpleNamespace(connect=MagicMock())
        self.error = SimpleNamespace(connect=MagicMock())
        self.finished = SimpleNamespace(connect=MagicMock())


class DummyJobManager:
    def __init__(self) -> None:
        self.run_calls: list[object] = []
        self.run_pool_calls: list[object] = []
        self.cancel_calls: list[object] = []
        self.job = DummyJob()

    def run(self, work, **kwargs):
        self.run_calls.append((work, kwargs))
        return self.job

    def run_pool(self, work, **kwargs):
        self.run_pool_calls.append((work, kwargs))
        return self.job

    def get_job_id(self, job):
        return "job-1"

    def cancel_job(self, job_id):
        self.cancel_calls.append(job_id)
        return True


class DummyBusy:
    def __init__(self) -> None:
        self.show_calls: list[object] = []
        self.hide_calls: list[object] = []
        self.progress_calls: list[object] = []

    def show(self, *args, **kwargs):
        self.show_calls.append((args, kwargs))

    def hide(self, target):
        self.hide_calls.append(target)

    def set_progress(self, target, value):
        self.progress_calls.append((target, value))


class DummyDialogService:
    def __init__(self) -> None:
        self.warn_calls: list[object] = []

    def warn(self, parent, title, text):
        self.warn_calls.append((parent, title, text))


class DummyView(QWidget):
    pass


@pytest.fixture
def controller():
    return AsyncOperationController(
        parent=DummyView(),
        job_mgr=DummyJobManager(),
        busy=DummyBusy(),
        dialogs=DummyDialogService(),
    )


def test_job_mgr_property_returns_injected_manager(controller):
    assert controller.job_mgr is controller._job_mgr


def test_run_operation_uses_thread_backend_and_wires_handlers(controller):
    on_result = MagicMock()
    on_finished = MagicMock()
    on_progress = MagicMock()
    on_error = MagicMock()
    work = MagicMock(return_value="ok")

    job = controller.run_operation(
        work=work,
        on_result=on_result,
        on_finished=on_finished,
        on_progress=on_progress,
        on_error=on_error,
        busy_message="Working",
        scope="scope-a",
        runner="thread",
        target=DummyView(),
        show_overlay=False,
    )

    assert job is controller._job_mgr.job
    assert controller._job_mgr.run_calls
    assert not controller._job_mgr.run_pool_calls

    progress_cb = controller._job_mgr.job.progress.connect.call_args[0][0]
    result_cb = controller._job_mgr.job.result.connect.call_args[0][0]
    error_cb = controller._job_mgr.job.error.connect.call_args[0][0]
    finished_cb = controller._job_mgr.job.finished.connect.call_args[0][0]

    progress_cb(7)
    result_cb("done")
    error_cb("traceback")
    finished_cb()

    on_progress.assert_called_with(7)
    on_result.assert_called_with("done")
    on_error.assert_called_with("traceback")
    on_finished.assert_called_with()


def test_run_operation_uses_pool_backend(controller):
    controller.run_operation(
        work=lambda: None,
        on_result=lambda _: None,
        busy_message="Working",
        scope="scope-b",
        runner="pool",
        target=DummyView(),
        show_overlay=False,
    )

    assert controller._job_mgr.run_pool_calls


def test_run_target_overlay_operation_shows_overlay(controller):
    target = DummyView()
    controller.run_target_overlay_operation(
        target=target,
        work=lambda: "ok",
        on_result=lambda _: None,
        busy_message="Working",
        scope="scope-c",
    )

    assert controller._busy.show_calls
