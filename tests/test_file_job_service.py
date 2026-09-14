from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from expo_jbm329.services.file_job_service import FileJobService
from expo_jbm329.services.job_result import JobResult


class DummySignal:
    def __init__(self):
        self._subs = []

    def connect(self, slot, *args, **kwargs):
        self._subs.append(slot)

    def emit(self, *args, **kwargs):
        for slot in list(self._subs):
            slot(*args, **kwargs)


class DummyWorker:
    def __init__(self, job_id="job-1"):
        self._job_id = job_id
        self.started = DummySignal()
        self.progress = DummySignal()
        self.finished = DummySignal()
        self.error = DummySignal()
        self.result = DummySignal()


class DummyJobManager:
    def __init__(self):
        self.worker = DummyWorker(job_id="job-42")
        self.last_run = None

    def run_target_overlay_operation(self, **kwargs):
        self.last_run = kwargs
        return self.worker

    def get_job_id(self, worker):
        return worker._job_id


class DummyAsyncOps:
    def __init__(self):
        self.job_mgr = DummyJobManager()

    def run_target_overlay_operation(self, **kwargs):
        return self.job_mgr.run_target_overlay_operation(**kwargs)


class DummyResults:
    def __init__(self):
        self.pending = []
        self.bound = []
        self.removed = []
        self.fulfilled = []

    def create_pending_tab(self, **kwargs):
        tab_id = f"tab-{len(self.pending)}"
        view = object()
        handle = SimpleNamespace(tab_id=tab_id, view=view)
        self.pending.append(kwargs | {"tab_id": tab_id, "view": view})
        return handle

    def bind_job_to_tab(self, tab_id, job_id):
        self.bound.append((tab_id, job_id))

    def remove_pending_tab(self, tab_id):
        self.removed.append(tab_id)

    def fulfill_pending_tab(self, tab_id, df):
        self.fulfilled.append((tab_id, df))


class DummyDialogService:
    def __init__(self):
        self.critical_calls = []

    def critical(self, **kwargs):
        self.critical_calls.append(kwargs)


@pytest.fixture
def service():
    status_messages: list[tuple[str, int | None]] = []
    async_ops = DummyAsyncOps()
    results = DummyResults()
    dialogs = DummyDialogService()
    display_dataframe = MagicMock()

    svc = FileJobService(
        parent_widget=object(),
        async_ops=async_ops,
        results=results,
        set_status=lambda msg, timeout: status_messages.append((msg, timeout)),
        get_active_tab_title=lambda: "Export.csv",
        resolve_and_load_df=MagicMock(),
        display_dataframe=display_dataframe,
        dialogs=dialogs,
    )

    return svc, async_ops, results, dialogs, status_messages, display_dataframe


def test_open_data_file_queues_job_and_binds_pending_tab(service):
    svc, async_ops, results, _, _, _ = service

    svc.open_data_file(path="C:\\tmp\\data.csv")

    assert results.pending[0]["title"] == "data.csv"
    assert results.bound[0][0] == "tab-0"
    assert async_ops.job_mgr.last_run["scope"] == "load:csv"
    assert async_ops.job_mgr.last_run["cancelable"] is True


def test_on_data_loaded_fulfills_pending_tab(service):
    svc, _, results, _, status_messages, display_dataframe = service
    payload = JobResult(ok=True, data=pd.DataFrame({"A": [1, 2]}), elapsed=1.5, corr_id="c1")

    svc._on_data_loaded(payload, "C:\\tmp\\data.csv", pending_tab_id="tab-1")

    assert results.fulfilled and results.fulfilled[0][0] == "tab-1"
    assert not display_dataframe.called


def test_on_data_loaded_without_pending_tab_displays_dataframe(service):
    svc, _, results, _, _, display_dataframe = service
    payload = JobResult(ok=True, data=pd.DataFrame({"A": [1]}), elapsed=None, corr_id="c1")

    svc._on_data_loaded(payload, "C:\\tmp\\data.csv", pending_tab_id=None)

    assert not results.fulfilled
    display_dataframe.assert_called_once()


def test_on_data_loaded_cancelled_removes_pending_tab(service):
    svc, _, results, _, status_messages, _ = service
    payload = JobResult(ok=False, cancelled=True, elapsed=None, corr_id="c1")

    svc._on_data_loaded(payload, "C:\\tmp\\data.csv", pending_tab_id="tab-1")

    assert results.removed == ["tab-1"]
    assert any("cancelled" in msg.lower() for msg, _ in status_messages)


def test_on_data_load_error_removes_pending_tab_and_shows_dialog(service):
    svc, _, results, dialogs, status_messages, _ = service

    svc._on_data_load_error("boom", "C:\\tmp\\data.csv", pending_tab_id="tab-1")

    assert results.removed == ["tab-1"]
    assert dialogs.critical_calls
    assert any("failed" in msg.lower() for msg, _ in status_messages)


def test_coerce_save_suffix(service):
    svc, *_ = service

    assert svc.coerce_save_suffix("C:\\tmp\\name", "Feather (*.feather *.ft)").endswith(".feather")
    assert svc.coerce_save_suffix("C:\\tmp\\f.csv", "CSV (*.csv)").endswith(".csv")


def test_sanitize_and_strip_suffix(service):
    svc, *_ = service

    assert svc.sanitize_filename('bad:name*?"<>|.txt') == "badname.txt"
    assert svc.strip_suffix("hello.name.csv") == "hello.name"


def test_build_export_and_safe_filename(service, tmp_path: Path, monkeypatch):
    svc, _, _, _, _, _ = service
    monkeypatch.setattr(svc, "_get_active_tab_title", lambda: "Rapport.xlsx")

    (tmp_path / "Rapport.csv").write_text("x", encoding="utf-8")
    assert svc.build_export_filename(".csv", str(tmp_path)) in {"Rapport(1).csv", "Rapport.csv"}

    (tmp_path / "hej.csv").write_text("x", encoding="utf-8")
    assert svc.build_safe_filename("hej.csv", ".csv", tmp_path).name in {"hej(1).csv", "hej.csv"}


def test_rename_file_success_and_failure(service, tmp_path: Path, monkeypatch):
    svc, _, _, _, status_messages, _ = service
    f = tmp_path / "old.csv"
    f.write_text("x", encoding="utf-8")

    ok, err = svc.rename_file(f, "new.csv")
    assert ok is True
    assert err is None

    def boom(self, new_path):
        raise PermissionError("denied")

    f2 = tmp_path / "old2.csv"
    f2.write_text("x", encoding="utf-8")
    monkeypatch.setattr(Path, "rename", boom, raising=False)

    ok, err = svc.rename_file(f2, "new.csv")
    assert ok is False
    assert err is not None
    assert status_messages


def test_is_shutting_down(service):
    svc, _, _, _, _, _ = service
    assert svc._is_shutting_down() is False
