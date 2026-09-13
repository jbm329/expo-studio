# tests/test_job_manager.py
from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest

from expo_jbm329.services.job_manager import JobManager, JobMetadata, Worker, run_in_thread


# ---------------------------------------------------------------------------
# FakeSignal — enkel stubb för PyQt-signal
# ---------------------------------------------------------------------------
class FakeSignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, cb, *a, **k):
        self._callbacks.append(cb)

    def emit(self, *args, **kwargs):
        for cb in self._callbacks:
            cb(*args, **kwargs)


# ---------------------------------------------------------------------------
# Fake objects
# ---------------------------------------------------------------------------
class DummyParent:
    def __init__(self):
        self.progress = MagicMock()
        self.progress_label = MagicMock()
        self._sb = MagicMock()

    def statusBar(self):
        return self._sb


class DummyThread:
    def __init__(self):
        self.started = FakeSignal()
        self.finished = FakeSignal()

    def start(self):
        # Do not start a real thread
        pass

    def quit(self):
        pass

    def deleteLater(self):
        pass


# ---------------------------------------------------------------------------
# TEST: Worker.signal injection
# ---------------------------------------------------------------------------
def test_worker_injects_and_emits_signals(monkeypatch):
    calls = {
        "progress": [],
        "result": None,
        "started": 0,
        "finished": 0,
    }

    # Fake function using all injected arguments
    def fn(x, progress_cb=None, job_id=None, job_scope=None, cancel_cb=None):
        progress_cb(25)
        progress_cb(100)
        return f"done-{job_id}-{job_scope}-{x}"

    w = Worker(fn, 123, _job_id="JID", _job_scope="SCOPE")

    # Patch signals to FakeSignals (override instance attributes)
    w.__dict__["started"] = FakeSignal()
    w.__dict__["progress"] = FakeSignal()
    w.__dict__["result"] = FakeSignal()
    w.__dict__["error"] = FakeSignal()
    w.__dict__["finished"] = FakeSignal()

    # Bind callbacks
    w.started.connect(lambda: calls.update(started=calls["started"] + 1))
    w.progress.connect(lambda v: calls["progress"].append(v))
    w.result.connect(lambda v: calls.update(result=v))
    w.finished.connect(lambda: calls.update(finished=calls["finished"] + 1))

    # Prevent worker.run from using real cancel_cb
    w._cancel_func = lambda: False

    w.run()

    assert calls["started"] == 1
    assert calls["progress"] == [25, 100]
    assert calls["result"] == "done-JID-SCOPE-123"
    assert calls["finished"] == 1


def test_worker_fallback_on_typeerror(monkeypatch):
    calls = {"result": None}

    def fn_raw(x):
        return x * 2

    w = Worker(fn_raw, 10, _job_id="X")

    # Override signals
    w.__dict__["started"] = FakeSignal()
    w.__dict__["progress"] = FakeSignal()
    w.__dict__["result"] = FakeSignal()
    w.__dict__["error"] = FakeSignal()
    w.__dict__["finished"] = FakeSignal()

    w.result.connect(lambda v: calls.update(result=v))

    w.run()
    assert calls["result"] == 20


def test_worker_emits_error(monkeypatch):
    calls = {"error": None}

    def fn_fail():
        raise RuntimeError("BOOM")

    w = Worker(fn_fail, _job_id="X")

    # Fake signals
    w.__dict__["started"] = FakeSignal()
    w.__dict__["progress"] = FakeSignal()
    w.__dict__["result"] = FakeSignal()
    w.__dict__["error"] = FakeSignal()
    w.__dict__["finished"] = FakeSignal()

    w.error.connect(lambda msg: calls.update(error=msg))

    w.run()
    assert "BOOM" in calls["error"]


# ---------------------------------------------------------------------------
# TEST: run_in_thread helper
# ---------------------------------------------------------------------------
@patch("expo_jbm329.services.job_manager.QThread", DummyThread)
def test_run_in_thread_returns_thread_and_worker(monkeypatch):
    def fn(x): return x

    monkeypatch.setattr(Worker, "moveToThread", lambda self, t: None)

    thread, worker = run_in_thread(fn, 5)
    assert isinstance(worker, Worker)
    assert isinstance(thread, DummyThread)


# ---------------------------------------------------------------------------
# TEST: JobManager
# ---------------------------------------------------------------------------
@patch("expo_jbm329.services.job_manager.QThread", DummyThread)
def test_jobmanager_run_creates_job(monkeypatch):
    monkeypatch.setattr(Worker, "moveToThread", lambda self, t: None)
    monkeypatch.setattr(Worker, "run", lambda self: None)

    jm = JobManager(parent=DummyParent())

    worker = jm.run(
        parent=None,
        fn=lambda: None,
        started_msg="HELLO",
        foreground=True,
        show_busy=True,
    )

    # IMPORTANT FIX ✨
    def fake_connect(self, w, parent, job_id):
        jm._on_started(parent, job_id)

    monkeypatch.setattr(JobManager, "_connect_worker_signals", fake_connect)

    # Call run() again so patched connect is used
    worker = jm.run(parent=None, fn=lambda: None, started_msg="HELLO")

    # Trigger started
    worker.started.emit()

    meta = next(iter(jm._meta.values()))
    assert meta.started_msg == "HELLO"
    assert jm.active_jobs >= 1
    assert jm.busy_count == 1


@patch("expo_jbm329.services.job_manager.QThread", DummyThread)
def test_jobmanager_cancellation(monkeypatch):
    monkeypatch.setattr(Worker, "moveToThread", lambda self, t: None)
    monkeypatch.setattr(Worker, "run", lambda self: None)

    jm = JobManager()
    worker = jm.run(parent=None, fn=lambda: None)
    job_id = worker._job_id

    assert jm.is_cancelled(job_id) is False
    jm.cancel_job(job_id)
    assert jm.is_cancelled(job_id) is True
    jm.cancel_all()
    assert jm.is_cancelled(job_id) is True


@patch("expo_jbm329.services.job_manager.QThread", DummyThread)
def test_started_hook(monkeypatch):
    monkeypatch.setattr(Worker, "moveToThread", lambda self, t: None)

    jm = JobManager(parent=DummyParent())
    called = {}

    jm.started_hook = lambda parent, meta: called.update(ok=True)

    def fake_connect(self, worker, parent, job_id):
        # Directly simulate the "started" event firing
        jm._on_started(parent, job_id)

    # Patch the CLASS method ⚠️
    monkeypatch.setattr(JobManager, "_connect_worker_signals", fake_connect)

    # Run a second job to use patched connect
    jm.run(parent=None, fn=lambda: None, started_msg="GO")

    assert called == {"ok": True}


@patch("expo_jbm329.services.job_manager.QThread", DummyThread)
def test_progress_hook(monkeypatch):
    # Prevent real Qt behavior
    monkeypatch.setattr(Worker, "moveToThread", lambda self, t: None)
    monkeypatch.setattr(Worker, "run", lambda self: None)

    jm = JobManager(parent=DummyParent())
    values = []

    jm.progress_hook = lambda parent, meta, v: values.append(v)

    import expo_jbm329.services.job_manager as jm_mod

    def fake_connect(self, worker, parent, job_id):
        # Gör jobbet foreground direkt
        jm._set_fg(job_id)
        # Triggera progress
        jm._on_progress(parent, job_id, 42)

    monkeypatch.setattr(jm_mod.JobManager, "_connect_worker_signals", fake_connect)

    jm.run(parent=None, fn=lambda: None)

    assert values == [42]


@patch("expo_jbm329.services.job_manager.QThread", DummyThread)
def test_finished_hook(monkeypatch):
    monkeypatch.setattr(Worker, "moveToThread", lambda self, t: None)
    jm = JobManager(parent=DummyParent())

    ids = []
    jm.finished_hook = lambda parent, meta: ids.append(meta.job_id)

    import expo_jbm329.services.job_manager as jm_mod

    def fake_connect(self, worker, parent, job_id):
        jm._on_finished(parent, job_id)

    monkeypatch.setattr(jm_mod.JobManager, "_connect_worker_signals", fake_connect)

    jm.run(parent=None, fn=lambda: None)

    assert len(ids) == 1


@patch("expo_jbm329.services.job_manager.QThread", DummyThread)
def test_thread_cleanup(monkeypatch):
    monkeypatch.setattr(Worker, "moveToThread", lambda self, t: None)

    jm = JobManager(parent=DummyParent())
    worker = jm.run(parent=None, fn=lambda: None)

    job_id = worker._job_id

    jm._on_thread_finished(job_id)

    assert jm.active_jobs == 0
    assert job_id not in jm._meta
    assert job_id not in jm._cancel_flags
