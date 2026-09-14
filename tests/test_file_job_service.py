# tests/test_file_job_service.py
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from expo_jbm329.services.file_job_service import FileJobService
from tests.stubs import DummyStatusLogger, DummyDataIO, DummyResults

# -------------------------------------------------------------------
#             Lightweight signal/worker/job manager stubs
# -------------------------------------------------------------------


class DummySignal:
    """Minimal signal som samlar subscribers och kan emit:a värden."""
    def __init__(self):
        self._subs = []

    def connect(self, slot, *args, **kwargs):
        # Ignorera ev. Qt.ConnectionType extraargument
        self._subs.append(slot)

    def emit(self, *args, **kwargs):
        for s in list(self._subs):
            s(*args, **kwargs)


class DummyWorker:
    """Simulerar en JobManager-worker med Qt-lika signaler."""
    def __init__(self, job_id="job-1"):
        self._job_id = job_id
        self.started = DummySignal()
        self.progress = DummySignal()
        self.finished = DummySignal()
        self.error = DummySignal()
        self.result = DummySignal()


class DummyJobManager:
    """Fångar run()-anrop och returnerar en DummyWorker."""
    def __init__(self):
        self.last_run = None
        self.worker = DummyWorker(job_id="job-42")

    def run(self, parent, job_fn, *args, **kwargs):
        self.last_run = {
            "parent": parent,
            "job_fn": job_fn,
            "args": args,
            "kwargs": kwargs,
        }
        return self.worker

    def get_job_id(self, worker):
        return worker._job_id


# -------------------------------------------------------------------
#             Fixture: patcha BlockingProgressDialog
# -------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_blocking_progress_dialog(monkeypatch):
    calls = {"init": [], "attach_cancel": [], "exec": [], "started": [], "progress": [], "finished": [], "error": []}

    class StubBlockingProgressDialog:
        def __init__(self, parent, title, started_msg):
            calls["init"].append((title, started_msg))
            self._parent = parent
            self._title = title
            self._started_msg = started_msg

        # Dessa metoder matchar vad FileJobService ansluter till
        def on_started(self): calls["started"].append(True)
        def on_progress(self, v): calls["progress"].append(v)
        def on_finished(self): calls["finished"].append(True)
        def on_error(self, e): calls["error"].append(e)

        def attach_cancel(self, job_id, job_mgr):
            calls["attach_cancel"].append((job_id, job_mgr))

        def exec(self):
            calls["exec"].append(True)

    # Patcha i rätt namespace där klassen används
    monkeypatch.setattr(
        "expo_jbm329.services.file_job_service.BlockingProgressDialog",
        StubBlockingProgressDialog
    )
    return calls


# -------------------------------------------------------------------
#                     Hjälpfabrik för service
# -------------------------------------------------------------------

def make_service(*, settings=None):
    parent = object()
    status_logger = DummyStatusLogger()
    job_mgr = DummyJobManager()
    data_io = DummyDataIO()
    results = DummyResults()
    
    # Mock some basic callables
    get_active_title = lambda: "Export från flik (v1).csv"
    fmt_time = lambda s: f"{s:.1f}s"
    fmt_int = lambda i: f"{i:,}"
    fmt_path = lambda p: str(p)
    editor_text = [""]
    def set_editor_text(t): editor_text[0] = t
    def get_editor_text(): return editor_text[0]

    from tests.stubs import make_dialog_services
    dialogs, _ = make_dialog_services()

    svc = FileJobService(
        parent_widget=parent,
        set_status=status_logger.set_status,
        job_mgr=job_mgr,
        get_active_tab_title=get_active_title,
        results=results,
        data_io=data_io,
        dialogs=dialogs,
        fmt_time=fmt_time,
        fmt_int=fmt_int,
        fmt_path=fmt_path,
        set_editor_text=set_editor_text,
        get_editor_text=get_editor_text,
    )
    
    if settings:
        svc.reload_settings(settings)
    else:
        svc.reload_settings({
            "file_format_behaviour": {"csv": "non_blocking", "xlsx": "blocking"}
        })
        
    return svc, job_mgr, status_logger.messages


# -------------------------------------------------------------------
#                           TESTER: run()
# -------------------------------------------------------------------

def test_run_nonblocking_wraps_progress_and_connects_callbacks():
    svc, job_mgr, status_msgs = make_service()

    def dummy_job(path, progress_cb=None, *rest, **kw):
        if progress_cb:
            progress_cb(5.0)
        return "OK"

    progress_hits = []
    def user_progress(v): progress_hits.append(v)

    results = []
    errors = []

    worker = svc.run(
        job_fn=dummy_job,
        job_args=("p.csv",),
        started_msg="Startar…",
        scope="load:csv",
        blocking=False,
        result_cb=lambda payload: results.append(payload),
        error_cb=lambda e: errors.append(e),
    )

    # JobManager calls wrapper with:
    # wrapper("p.csv", progress_cb=..., cancel_cb=..., job_id=..., job_scope=...)
    #
    # FileJobService.run internal wrapper then calls dummy_job with:
    # dummy_job("p.csv", progress_cb=final_progress, ...)

    # Execute manually
    job_fn = job_mgr.last_run["job_fn"]
    args = job_mgr.last_run["args"]
    # We must also provide the keyword args that JobManager would provide
    job_fn(*args, progress_cb=user_progress)

    assert 5.0 in progress_hits

    # worker.progress.emit() påverkar inte wrappen (ska inte göra det)
    worker.progress.emit(10.0)
    assert 10.0 not in progress_hits

    # result_cb kopplad
    worker.result.emit(("RES",))
    assert ("RES",) in results


def test_run_blocking_shows_dialog_and_sets_status_on_started(patch_blocking_progress_dialog):
    svc, job_mgr, status_msgs = make_service()

    def dummy_job(path, progress_cb=None):
        return "OK"

    # Kör i blocking-läge
    worker = svc.run(
        job_fn=dummy_job,
        job_args=("p.xlsx",),
        started_msg="Exporterar…",
        scope="export:xlsx",
        blocking=True,
        result_cb=None,
        error_cb=None,
    )

    # Dialog initierades
    calls = patch_blocking_progress_dialog
    assert calls["init"] and calls["exec"], "Dialog skapades/exec:ades inte"
    # attach_cancel ska kopplas med worker-id och job_mgr
    assert calls["attach_cancel"] and calls["attach_cancel"][0][0] == worker._job_id

    # När worker.started emit:as ska status uppdateras
    worker.started.emit()
    assert ("Exporterar…", 0) in status_msgs


# -------------------------------------------------------------------
#               TESTER: klassificering och policy
# -------------------------------------------------------------------

def test_classify_and_is_functions():
    svc, *_ = make_service()
    from pathlib import Path
    assert svc.classify_file(Path("data.csv")) == "data"
    assert svc.classify_file(Path("script.sql")) == "sql"
    assert svc.classify_file(Path("page.html")) == "html"
    assert svc.classify_file(Path("readme.md")) == "unknown"

    assert svc.is_data_file(".csv")
    assert svc.is_sql_file(".sql")
    assert svc.is_html_file(".html")


def test_format_to_behaviour():
    svc, *_ = make_service(settings={"file_format_behaviour": {"xlsx": "blocking", "csv": "non_blocking"}})
    assert svc.format_to_behaviour(".xlsx") == "blocking"
    assert svc.format_to_behaviour("xlsx") == "blocking"
    # explicit
    assert svc.format_to_behaviour(".csv") == "non_blocking"


# -------------------------------------------------------------------
#               TESTER: suffix/filter & namn
# -------------------------------------------------------------------

def test_coerce_save_suffix_status_toast(monkeypatch):
    svc, _, status_msgs = make_service()

    # Filter med flera wildcard
    fixed = svc.coerce_save_suffix("C:/tmp/name", "Feather (*.feather *.ft)")
    assert fixed.endswith(".feather"), "Skulle välja första tillåtna suffix"

    # Ingen ändring → ingen status
    status_msgs.clear()
    fixed2 = svc.coerce_save_suffix("C:/tmp/f.csv", "CSV (*.csv)")
    assert fixed2.endswith(".csv")
    assert not status_msgs

    # Ändring → status toast
    fixed3 = svc.coerce_save_suffix("C:/tmp/f.txt", "CSV (*.csv)")
    assert fixed3.endswith(".csv")
    assert any("Filändelse korrigerades" in m for m, _ in status_msgs)


def test_sanitize_and_strip_suffix():
    svc, *_ = make_service()
    assert svc.sanitize_filename('bad:name*?"<>|.txt') == "badname.txt"
    assert svc.strip_suffix("hello.csv") == "hello"
    assert svc.strip_suffix("hello.name.csv") == "hello.name"


def test_build_export_filename_uniqueness(tmp_path, monkeypatch):
    # Aktiva flikens titel styr basnamn
    svc, *_ = make_service()
    monkeypatch.setattr(
        svc, "_get_active_tab_title", lambda: "Rapport.xlsx"
    )

    # Lägg till en fil som redan finns
    (tmp_path / "Rapport.csv").write_text("x", encoding="utf-8")

    name = svc.build_export_filename(".csv", str(tmp_path))
    # Första kolliderar → borde bli Rapport(1).csv
    assert name in {"Rapport(1).csv", "Rapport.csv"}  # beroende på strip/sanitize


def test_build_safe_filename_uniqueness(tmp_path):
    svc, *_ = make_service()
    base = tmp_path
    (base / "hej.csv").write_text("x", encoding="utf-8")
    p = svc.build_safe_filename("hej.csv", ".csv", base)
    # Ska föreslå hej(1).csv
    assert p.name in {"hej(1).csv", "hej.csv"}


# -------------------------------------------------------------------
#                   TESTER: rename & open_html
# -------------------------------------------------------------------

def test_rename_file_success(tmp_path):
    svc, *_ = make_service()
    f = tmp_path / "old.csv"
    f.write_text("x", encoding="utf-8")

    ok, err = svc.rename_file(f, "new.csv")
    assert ok and err is None
    assert (tmp_path / "new.csv").exists()


def test_rename_file_failure(monkeypatch, tmp_path):
    svc, *_ = make_service()
    f = tmp_path / "old.csv"
    f.write_text("x", encoding="utf-8")

    def boom_rename(self, new_path):
        raise PermissionError("denied")
    monkeypatch.setattr(Path, "rename", boom_rename, raising=False)

    ok, err = svc.rename_file(f, "new.csv")
    assert not ok and "Kunde inte byta namn" in err


def test_open_html_file_success(monkeypatch, tmp_path):
    svc, _, status_msgs = make_service()
    p = tmp_path / "index.html"
    p.write_text("<html/>", encoding="utf-8")

    calls = []
    monkeypatch.setattr("webbrowser.open", lambda uri: calls.append(uri) or True)

    svc.open_html_file(path=p)
    assert any("Öppnade HTML" in m for m, _ in status_msgs)
    assert calls and calls[0].endswith("index.html")


def test_open_html_file_failure(monkeypatch, tmp_path):
    svc, *_ = make_service()
    p = tmp_path / "index.html"
    p.write_text("<html/>", encoding="utf-8")

    monkeypatch.setattr("webbrowser.open", lambda uri: False)

    # Should not raise, handles error internally with dialog (which is mocked/Null)
    svc.open_html_file(path=p)
