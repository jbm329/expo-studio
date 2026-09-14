# tests/test_schema_cache_manager.py
from __future__ import annotations

import types
import pytest

from expo_jbm329.services.schema_cache import SchemaCacheEntry, SchemaCacheManager


# ---- Helper: capture callbacks ------------------------------------------------
class CbRecorder:
    def __init__(self):
        self.status: list[tuple[str, int | None]] = []     # [(text, timeout_ms)]
        self.progress: list[tuple[int, int]] = []          # [(done, total)]
        self.auto_rebuild_calls: int = 0
        self.auto_rebuild_conns: list[str] = []

    def status_cb(self, text: str, timeout_ms: int | None = None):
        self.status.append((text, timeout_ms))

    def progress_cb(self, done: int, total: int):
        self.progress.append((done, total))

    # New signature: receives connection_name
    def autocomplete_cb(self, conn_name: str):
        self.auto_rebuild_calls += 1
        self.auto_rebuild_conns.append(conn_name)


# ---- Fixture: patch schema_cache module symbols directly ---------------------
@pytest.fixture
def fake_db(monkeypatch):
    """
    Patch the *imported* symbols inside schema_cache where they are used, so no
    real DB I/O occurs and tests are deterministic/synchronous.

    We also force the UI trampoline and (if present) QTimer.singleShot to run
    callbacks immediately.
    """
    import expo_jbm329.services.schema_cache as sc

    # 1) Patch DB calls used by SchemaCacheManager directly in this module
    monkeypatch.setattr(sc, "get_db_name", lambda conn: f"DB_{conn}")
    monkeypatch.setattr(sc, "list_tables", lambda conn: [
        {"schema": "dbo", "name": "A"},
        {"schema": "dbo", "name": "B"},
    ])
    monkeypatch.setattr(sc, "list_views", lambda conn: [
        {"schema": "dbo", "name": "V"},
    ])

    # Bulk payload: two wanted keys + one extra (ignored)
    def fake_list_all_columns_map(conn):
        return {
            ("dbo", "A"): [{"COLUMN_NAME": "id", "DATA_TYPE": "int"}],
            ("dbo", "B"): [{"COLUMN_NAME": "x", "DATA_TYPE": "varchar"}],
            ("dbo", "NOT_INCLUDED"): [{"COLUMN_NAME": "y", "DATA_TYPE": "varchar"}],
        }
    monkeypatch.setattr(sc, "list_all_columns_map", fake_list_all_columns_map)

    # Batch fallback returns a single column
    def fake_list_columns(conn, sch, name):
        return [{"COLUMN_NAME": "c1", "DATA_TYPE": "int"}]
    monkeypatch.setattr(sc, "list_columns", fake_list_columns)

    # 2) Force UI trampoline to run synchronously
    monkeypatch.setattr(SchemaCacheManager, "_invoke_ui", lambda self, fn: fn())

    # 3) If PyQt6 is present, neutralize QTimer.singleShot to call immediately
    try:
        import PyQt6.QtCore as QtCore  # type: ignore

        class _ImmediateQTimer:
            @staticmethod
            def singleShot(ms: int, fn):
                fn()
        monkeypatch.setattr(QtCore, "QTimer", _ImmediateQTimer, raising=True)
    except Exception:
        # If PyQt6 isn't available, schema_cache already falls back to direct call
        pass

    return sc


# ---- Tests -------------------------------------------------------------------
def test_load_schema_status_policy(fake_db):
    rec = CbRecorder()
    mgr = SchemaCacheManager(
        status_cb=rec.status_cb,
        progress_cb=rec.progress_cb,
        autocomplete_cb=rec.autocomplete_cb,
    )
    mgr.reload_settings({"schema_cache": {"ttl_seconds": 300}})
    rec.status.clear()

    entry = mgr.load_schema("Conn1", force_refresh=True)
    assert isinstance(entry, SchemaCacheEntry)

    # First status should be "Laddar schema…" with timeout 0
    assert rec.status[0] == ("Laddar schema…", 0)
    # Second status should be "Schema klart" with timeout 4000
    assert rec.status[1] == ("Schema klart", 4000)
    # No progress during load_schema (progress is for prefetch)
    assert rec.progress == []


def test_load_schema_respects_ttl(fake_db):
    rec = CbRecorder()
    mgr = SchemaCacheManager(
        status_cb=rec.status_cb,
        progress_cb=rec.progress_cb,
        autocomplete_cb=rec.autocomplete_cb,
    )
    mgr.reload_settings({"schema_cache": {"ttl_seconds": 9999}})
    rec.status.clear()

    # First load → expect 2 status messages
    mgr.load_schema("Conn1", force_refresh=True)
    assert len(rec.status) == 2

    # Second load (within TTL) → should NOT emit "Laddar schema…"
    rec.status.clear()
    entry2 = mgr.load_schema("Conn1", force_refresh=False)
    assert isinstance(entry2, SchemaCacheEntry)
    assert rec.status == []


def test_prefetch_bulk_success(fake_db):
    rec = CbRecorder()
    mgr = SchemaCacheManager(
        status_cb=rec.status_cb,
        progress_cb=rec.progress_cb,
        autocomplete_cb=rec.autocomplete_cb,
    )
    mgr.reload_settings({"schema_cache": {"ttl_seconds": 300}})
    rec.status.clear()

    # Load schema first to create the cache entry
    mgr.load_schema("Conn1", force_refresh=True)
    rec.status.clear()
    rec.progress.clear()
    rec.auto_rebuild_calls = 0
    rec.auto_rebuild_conns.clear()

    # Dummy worker that triggers result callback immediately
    class DummyWorker:
        def __init__(self, payload=None):
            self._payload = payload
            self.result = types.SimpleNamespace(connect=lambda cb: cb(self._payload))
            self.error = types.SimpleNamespace(connect=lambda cb: None)

    # run_job_fn ⇒ execute bulk lambda synchronously, wrap into DummyWorker
    def run_job_fn(parent, fn, *args, started_msg=""):
        payload = fn(*args)
        return DummyWorker(payload=payload)

    # Launch bulk prefetch (runner provided inline)
    mgr.prefetch_columns_async("Conn1", run_job_fn)

    # Bulk success ⇒ should trigger autocomplete_cb(conn), status with 8000 ms and progress done(1,1)
    assert rec.auto_rebuild_calls >= 1
    assert "Conn1" in rec.auto_rebuild_conns
    assert any(("Autocomplete för kolumner klar" in s[0] and s[1] == 8000) for s in rec.status)
    assert rec.progress and rec.progress[-1] == (1, 1)


def test_prefetch_batch_flow(fake_db, monkeypatch):
    rec = CbRecorder()
    mgr = SchemaCacheManager(
        status_cb=rec.status_cb,
        progress_cb=rec.progress_cb,
        autocomplete_cb=rec.autocomplete_cb,
    )
    mgr.reload_settings({"schema_cache": {"ttl_seconds": 300}})
    rec.status.clear()

    # Prepare cache for ConnX
    mgr.load_schema("ConnX", force_refresh=True)
    rec.status.clear()
    rec.progress.clear()
    rec.auto_rebuild_calls = 0
    rec.auto_rebuild_conns.clear()

    # Force bulk to return None ⇒ triggers batch fallback
    import expo_jbm329.services.schema_cache as sc
    monkeypatch.setattr(sc, "list_all_columns_map", lambda conn: None)

    # Synchronous runner for batch flow
    class DummyWorker:
        def __init__(self, fn, *a):
            self._fn = fn
            self._args = a
            self.result = types.SimpleNamespace(connect=lambda cb: cb(self._fn(*self._args)))
            self.error = types.SimpleNamespace(connect=lambda cb: None)

    def run_job_fn(parent, fn, *args, started_msg=""):
        return DummyWorker(fn, *args)

    mgr.set_job_runner(run_job_fn)

    # Start prefetch; our sync UI & QTimer patch guarantees deterministic recursion
    mgr.prefetch_columns_async("ConnX", run_job_fn)

    # Expect final status and progress "done"
    assert any(("Autocomplete för kolumner klar." == s[0] and s[1] == 6000) for s in rec.status)
    assert rec.progress and rec.progress[-1][0] == rec.progress[-1][1]
    # And at least one autocomplete rebuild during batch
    assert rec.auto_rebuild_calls >= 1
    assert "ConnX" in rec.auto_rebuild_conns
