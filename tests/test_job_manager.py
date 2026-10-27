from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from expo_jbm329.services.job_manager import JobManager, Worker, run_in_thread


class FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, cb, *args, **kwargs):
        self.callbacks.append(cb)

    def emit(self, *args, **kwargs):
        for cb in list(self.callbacks):
            cb(*args, **kwargs)


class DummyThread:
    def __init__(self):
        self.started = FakeSignal()
        self.finished = FakeSignal()
        self.started_called = False

    def start(self):
        self.started_called = True

    def quit(self):
        pass

    def wait(self, wait_ms):
        return True

    def requestInterruption(self):
        pass

    def deleteLater(self):
        pass

    def setObjectName(self, name):
        pass


def test_worker_injects_and_emits_signals(monkeypatch):
    calls = {"progress": [], "result": None, "started": 0, "finished": 0}

    def fn(x, progress_cb=None, job_id=None, job_scope=None, cancel_cb=None):
        progress_cb(25)
        progress_cb(100)
        return f"done-{job_id}-{job_scope}-{x}"

    w = Worker(fn, 123, job_id="JID", job_scope="SCOPE", corr_id="CORR")
    w.__dict__["started"] = FakeSignal()
    w.__dict__["progress"] = FakeSignal()
    w.__dict__["result"] = FakeSignal()
    w.__dict__["error"] = FakeSignal()
    w.__dict__["finished"] = FakeSignal()
    w._cancel_func = lambda: False

    w.started.connect(lambda: calls.update(started=calls["started"] + 1))
    w.progress.connect(lambda v: calls["progress"].append(v))
    w.result.connect(lambda v: calls.update(result=v))
    w.finished.connect(lambda: calls.update(finished=calls["finished"] + 1))

    w.run()

    assert calls["started"] == 1
    assert calls["progress"] == []
    assert calls["result"] is None


def test_worker_fallback_on_typeerror():
    def fn_raw(x):
        return x * 2

    w = Worker(fn_raw, 10, job_id="X", job_scope=None, corr_id=None)
    w.__dict__["started"] = FakeSignal()
    w.__dict__["progress"] = FakeSignal()
    w.__dict__["result"] = FakeSignal()
    w.__dict__["error"] = FakeSignal()
    w.__dict__["finished"] = FakeSignal()

    w.run()


def test_worker_emits_error():
    def fn_fail():
        raise RuntimeError("BOOM")

    w = Worker(fn_fail, job_id="X", job_scope=None, corr_id=None)
    w.__dict__["started"] = FakeSignal()
    w.__dict__["progress"] = FakeSignal()
    w.__dict__["result"] = FakeSignal()
    w.__dict__["error"] = FakeSignal()
    w.__dict__["finished"] = FakeSignal()

    w.run()


def test_worker_redacts_traceback_logs_when_requested(caplog):
    def fn_fail():
        raise RuntimeError("secret")

    logger = logging.getLogger("test.safe_worker")
    w = Worker(
        fn_fail,
        job_id="X",
        job_scope="reshape:preview",
        corr_id="CORR",
        logger=logger,
        log_error_tracebacks=False,
    )
    caplog.set_level(logging.ERROR, logger="test.safe_worker")

    w.run()

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "exception=RuntimeError" in messages
    assert "secret" not in messages


def test_job_error_signal_redacts_traceback_logs_when_requested(caplog):
    manager = JobManager()
    manager._register_job(
        job_id="JID",
        runner="pool",
        scope="reshape:preview",
        corr_id="CORR",
        log_error_tracebacks=False,
    )
    caplog.set_level(logging.ERROR, logger="applogger.jobs")

    manager._on_job_error("JID", "sensitive traceback detail")

    assert "traceback=redacted" in caplog.text
    assert "sensitive traceback detail" not in caplog.text


@patch("expo_jbm329.services.job_manager.QThread", DummyThread)
def test_run_in_thread_returns_thread_and_worker(monkeypatch):
    monkeypatch.setattr(Worker, "moveToThread", lambda self, t: None)

    thread, worker = run_in_thread(lambda x: x, 5, job_id="J", job_scope=None, corr_id=None)

    assert isinstance(worker, Worker)
    assert isinstance(thread, DummyThread)


@patch("expo_jbm329.services.job_manager.QThread", DummyThread)
def test_jobmanager_run_creates_job(monkeypatch):
    monkeypatch.setattr(Worker, "moveToThread", lambda self, t: None)
    monkeypatch.setattr(Worker, "run", lambda self: None)
    monkeypatch.setattr(JobManager, "_connect_job_lifecycle_signals", lambda self, job_id, job: None)

    jm = JobManager()
    worker = jm.run(lambda: None, scope="s1", corr_id="c1")

    assert isinstance(worker, Worker)
    assert jm.active_jobs == 1
    assert jm.active_job_ids


@patch("expo_jbm329.services.job_manager.QThread", DummyThread)
def test_jobmanager_cancellation(monkeypatch):
    monkeypatch.setattr(Worker, "moveToThread", lambda self, t: None)
    monkeypatch.setattr(Worker, "run", lambda self: None)
    monkeypatch.setattr(JobManager, "_connect_job_lifecycle_signals", lambda self, job_id, job: None)

    jm = JobManager()
    worker = jm.run(lambda: None, scope="s1")
    job_id = worker.job_id

    assert jm.is_cancelled(job_id) is False
    assert jm.cancel_job(job_id) is True
    assert jm.is_cancelled(job_id) is True
    assert jm.cancel_all() == 1


@patch("expo_jbm329.services.job_manager.QThread", DummyThread)
def test_started_error_finished_hooks(monkeypatch):
    monkeypatch.setattr(Worker, "moveToThread", lambda self, t: None)
    monkeypatch.setattr(Worker, "run", lambda self: None)
    monkeypatch.setattr(JobManager, "_connect_job_lifecycle_signals", lambda self, job_id, job: None)

    jm = JobManager()
    jm.run(lambda: None)
    job_id = jm.active_job_ids[0]

    jm._on_job_started(job_id)
    jm._on_job_error(job_id, "boom")
    jm._on_job_finished(job_id)

    assert jm.get_metadata(job_id) is not None

    jm._finalize_job(job_id)
    assert jm.active_jobs == 0
    assert jm.get_metadata(job_id) is None


@patch("expo_jbm329.services.job_manager.QThread", DummyThread)
def test_abort_all_and_shutdown(monkeypatch):
    monkeypatch.setattr(Worker, "moveToThread", lambda self, t: None)
    monkeypatch.setattr(Worker, "run", lambda self: None)
    monkeypatch.setattr(JobManager, "_connect_job_lifecycle_signals", lambda self, job_id, job: None)

    jm = JobManager()
    jm.run(lambda: None)

    assert jm.abort_all() == []
    jm.shutdown()


@pytest.mark.parametrize("job_count", [0, 1])
def test_cancel_all_log_level_depends_on_tracked_jobs(caplog, job_count):
    caplog.set_level(logging.DEBUG)
    manager = JobManager()
    manager._cancel_flags = {f"job-{index}": False for index in range(job_count)}

    assert manager.cancel_all() == job_count

    records = [
        record
        for record in caplog.records
        if record.getMessage().startswith("JobManager: cancellation requested for all jobs")
    ]
    assert len(records) == 1
    assert records[0].levelno == (logging.WARNING if job_count else logging.INFO)
    assert records[0].getMessage().endswith(f"(count={job_count})")
    assert all(manager._cancel_flags.values())


@pytest.mark.parametrize("job_count", [0, 1])
@pytest.mark.parametrize("with_pool", [False, True])
def test_abort_all_log_level_and_idle_pool_cleanup(caplog, job_count, with_pool):
    caplog.set_level(logging.DEBUG)
    manager = JobManager()
    manager._cancel_flags = {f"job-{index}": False for index in range(job_count)}
    manager._jobs = dict.fromkeys(manager._cancel_flags, (None, None))
    pool = MagicMock() if with_pool else None
    manager._pool = pool

    assert manager.abort_all() == []

    records = [record for record in caplog.records if record.getMessage().startswith("JobManager: abort all requested")]
    assert len(records) == 1
    assert records[0].levelno == (logging.WARNING if job_count else logging.INFO)
    assert records[0].getMessage().endswith(f"(count={job_count})")
    if not job_count:
        assert not any(record.levelno >= logging.WARNING for record in caplog.records)
    if pool is not None:
        pool.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
    assert manager._pool is None


def test_worker_reports_import_error_instead_of_propagating():
    # PackageNotFoundError is an ImportError; escaping QThread.run would abort the app.
    from importlib.metadata import PackageNotFoundError

    def fn_fail():
        raise PackageNotFoundError("Pillow")

    w = Worker(fn_fail, job_id="X", job_scope=None, corr_id=None)
    errors = []
    finished = []
    w.__dict__["started"] = FakeSignal()
    w.__dict__["_dispatch_result"] = FakeSignal()
    w.__dict__["_dispatch_error"] = FakeSignal()
    w.__dict__["_dispatch_finished"] = FakeSignal()
    w._dispatch_error.connect(errors.append)
    w._dispatch_finished.connect(lambda: finished.append(True))

    w.run()

    assert len(errors) == 1
    assert "PackageNotFoundError" in errors[0]
    assert finished == [True]
