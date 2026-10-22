from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from expo_jbm329.services.schema_cache import SchemaCacheEntry, SchemaCacheManager


class Recorder:
    def __init__(self) -> None:
        self.status: list[tuple[str, int | None]] = []
        self.progress: list[tuple[int, int]] = []
        self.autocomplete: list[str] = []

    def status_cb(self, text: str, timeout_ms: int | None = None) -> None:
        self.status.append((text, timeout_ms))

    def progress_cb(self, done: int, total: int) -> None:
        self.progress.append((done, total))

    def autocomplete_cb(self, conn_name: str) -> None:
        self.autocomplete.append(conn_name)


def make_manager() -> tuple[SchemaCacheManager, Recorder]:
    rec = Recorder()
    mgr = SchemaCacheManager(
        status_cb=rec.status_cb,
        progress_cb=rec.progress_cb,
        autocomplete_cb=rec.autocomplete_cb,
    )
    return mgr, rec


@pytest.mark.parametrize("outcome", ["result", "error"])
def test_stale_batch_callbacks_do_not_modify_reloaded_cache(monkeypatch, outcome):
    manager, recorder = make_manager()
    worker = MagicMock()
    runner = MagicMock(return_value=worker)
    manager.set_job_runner(runner)
    manager._cache["Duck"] = SchemaCacheEntry(tables=[{"schema": "main", "name": "old"}])
    token = manager._make_token("Duck")
    manager._run_next_batch("Duck", token, [("main", "old")], 1, 0, 1)
    callback = getattr(worker, outcome).connect.call_args.args[0]
    manager.clear_for("Duck")
    replacement = SchemaCacheEntry(tables=[{"schema": "main", "name": "new"}])
    manager._cache["Duck"] = replacement
    manager._make_token("Duck")
    callback({("main", "old"): [{"COLUMN_NAME": "stale"}]} if outcome == "result" else "old failure")
    assert replacement.columns == {}
    assert recorder.autocomplete == []
    assert recorder.progress == []
    assert recorder.status == []
    runner.assert_called_once()


def test_stale_bulk_error_does_not_launch_batch_for_new_configuration(monkeypatch):
    manager, recorder = make_manager()
    token = manager._make_token("Duck")
    manager.clear_for("Duck")
    manager._cache["Duck"] = SchemaCacheEntry(tables=[{"schema": "main", "name": "new"}])
    runner = MagicMock()
    manager.set_job_runner(runner)
    manager._make_token("Duck")
    manager._handle_bulk_error("Duck", token, "old failure")
    manager._run_next_batch("Duck", token, [], 1, 1, 1)
    manager._start_batch_prefetch("Duck", token)
    runner.assert_not_called()
    assert recorder.status == []
    assert recorder.progress == []
    assert recorder.autocomplete == []


def test_reload_settings_clamps_values() -> None:
    mgr, rec = make_manager()

    mgr.reload_settings({"schema_cache": {"prefetch_limit": -1, "prefetch_batch_size": 0, "ttl_seconds": 0}})

    assert any("updated" in msg.lower() for msg, _ in rec.status)


def test_bulk_status_uses_db_errors_formatting_wrapper(monkeypatch):
    from expo_jbm329.services import schema_cache
    from expo_jbm329.utils.i18n_utils import translate_fmt

    mgr, rec = make_manager()
    mgr._cache["Conn1"] = SchemaCacheEntry(tables=[{"schema": "dbo", "name": "A"}])
    token = mgr._make_token("Conn1")
    formatter = MagicMock(wraps=translate_fmt)
    monkeypatch.setattr(schema_cache, "translate_fmt", formatter)
    mgr._on_bulk_done("Conn1", token, {("dbo", "A"): [{"COLUMN_NAME": "id"}]})

    formatter.assert_called_once_with("DbErrors", schema_cache.TR_AUTOCOMPLETE_READY_BULK, count="1")
    assert rec.status[-1] == (translate_fmt("DbErrors", schema_cache.TR_AUTOCOMPLETE_READY_BULK, count="1"), 8000)


def test_batch_status_uses_db_errors_formatting_wrapper(monkeypatch):
    from expo_jbm329.services import schema_cache
    from expo_jbm329.utils.i18n_utils import translate_fmt

    mgr, _ = make_manager()
    token = mgr._make_token("Conn1")
    formatter = MagicMock(wraps=translate_fmt)
    monkeypatch.setattr(schema_cache, "translate_fmt", formatter)
    runner = MagicMock()
    mgr.set_job_runner(runner)

    mgr._run_next_batch("Conn1", token, [("dbo", "A")], 1, 2, 3)

    formatter.assert_called_once_with("DbErrors", schema_cache.TR_PREPARING_AUTOCOMPLETE_BATCH, done="2", total="3")
    assert runner.call_args.kwargs["started_msg"] == translate_fmt(
        "DbErrors", schema_cache.TR_PREPARING_AUTOCOMPLETE_BATCH, done="2", total="3"
    )


def test_load_schema_uses_cache_and_status():
    mgr, rec = make_manager()
    mgr.reload_settings({"schema_cache": {"ttl_seconds": 300}})
    import expo_jbm329.services.schema_cache as sc

    sc.get_db_name = MagicMock(return_value="DB_Conn1")
    sc.list_tables = MagicMock(return_value=[{"schema": "dbo", "name": "A"}])
    sc.list_views = MagicMock(return_value=[{"schema": "dbo", "name": "V"}])

    entry = mgr.load_schema("Conn1", force_refresh=True)

    assert isinstance(entry, SchemaCacheEntry)
    assert rec.status[0][1] == 4000
    assert any(timeout == 0 for _, timeout in rec.status) is True
    assert mgr.is_cache_valid("Conn1") is True


def test_load_schema_returns_cached_entry_within_ttl():
    mgr, rec = make_manager()
    mgr.reload_settings({"schema_cache": {"ttl_seconds": 300}})
    import expo_jbm329.services.schema_cache as sc

    sc.get_db_name = MagicMock(return_value="DB_Conn1")
    sc.list_tables = MagicMock(return_value=[{"schema": "dbo", "name": "A"}])
    sc.list_views = MagicMock(return_value=[])

    first = mgr.load_schema("Conn1", force_refresh=True)
    rec.status.clear()
    second = mgr.load_schema("Conn1", force_refresh=False)

    assert first is second
    assert rec.status == []


def test_bulk_prefetch_falls_back_to_batch_when_bulk_empty(monkeypatch):
    mgr, rec = make_manager()
    mgr.reload_settings({"schema_cache": {"ttl_seconds": 300}})
    import expo_jbm329.services.schema_cache as sc

    monkeypatch.setattr(sc, "supports_bulk_column_listing", lambda conn: True)

    sc.get_db_name = MagicMock(return_value="DB_Conn1")
    sc.list_tables = MagicMock(return_value=[{"schema": "dbo", "name": "A"}])
    sc.list_views = MagicMock(return_value=[])
    sc.list_all_columns_map = MagicMock(return_value={})
    sc.list_columns = MagicMock(return_value=[{"COLUMN_NAME": "id", "DATA_TYPE": "int", "IS_NULLABLE": "NO"}])

    mgr.load_schema("Conn1", force_refresh=True)

    class Worker:
        def __init__(self):
            self.result = MagicMock(connect=lambda cb: cb({}))
            self.error = MagicMock(connect=lambda cb: None)

    mgr.set_job_runner(lambda *args, **kwargs: Worker())
    mgr.prefetch_columns_async("Conn1")

    assert rec.status


def test_batch_prefetch_updates_columns_when_no_runner():
    mgr, rec = make_manager()
    mgr.reload_settings({"schema_cache": {"ttl_seconds": 300}})
    import expo_jbm329.services.schema_cache as sc

    sc.get_db_name = MagicMock(return_value="DB_ConnX")
    sc.list_tables = MagicMock(return_value=[{"schema": "dbo", "name": "A"}])
    sc.list_views = MagicMock(return_value=[])
    sc.list_all_columns_map = MagicMock(return_value=None)
    sc.list_columns = MagicMock(return_value=[{"COLUMN_NAME": "id", "DATA_TYPE": "int", "IS_NULLABLE": "NO"}])

    mgr.load_schema("ConnX", force_refresh=True)
    mgr.prefetch_columns_async("ConnX")

    assert rec.progress


def test_prefetch_skips_bulk_job_when_dialect_does_not_support_it(monkeypatch):
    mgr, rec = make_manager()
    mgr.reload_settings({"schema_cache": {"ttl_seconds": 300}})
    import expo_jbm329.services.schema_cache as sc

    monkeypatch.setattr(sc, "get_db_name", MagicMock(return_value="main"))
    monkeypatch.setattr(sc, "list_tables", MagicMock(return_value=[{"schema": "main", "name": "A"}]))
    monkeypatch.setattr(sc, "list_views", MagicMock(return_value=[]))
    bulk = MagicMock(side_effect=AssertionError("bulk must not run"))
    monkeypatch.setattr(sc, "list_all_columns_map", bulk)
    monkeypatch.setattr(sc, "supports_bulk_column_listing", lambda conn: False)
    monkeypatch.setattr(
        sc, "list_columns", MagicMock(return_value=[{"COLUMN_NAME": "id", "DATA_TYPE": "int", "IS_NULLABLE": "NO"}])
    )

    mgr.load_schema("Lite", force_refresh=True)
    rec.status.clear()

    submitted = []

    class Worker:
        def __init__(self, payload):
            self.result = MagicMock(connect=lambda cb: cb(payload))
            self.error = MagicMock(connect=lambda cb: None)

    def runner(_parent, fn, *args, **kwargs):
        submitted.append(fn)
        return Worker(fn(*args))

    mgr.set_job_runner(runner)
    mgr.prefetch_columns_async("Lite")

    bulk.assert_not_called()
    assert submitted
    assert all(fn.__name__ == "batch_job" for fn in submitted)
    assert mgr.get_cache_for("Lite").columns[("main", "A")][0]["COLUMN_NAME"] == "id"
    assert not any("batch" in msg.lower() and "fail" in msg.lower() for msg, _ in rec.status)
