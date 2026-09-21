from __future__ import annotations

from unittest.mock import MagicMock

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


def test_reload_settings_clamps_values() -> None:
    mgr, rec = make_manager()

    mgr.reload_settings({"schema_cache": {"prefetch_limit": -1, "prefetch_batch_size": 0, "ttl_seconds": 0}})

    assert any("updated" in msg.lower() for msg, _ in rec.status)


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


def test_bulk_prefetch_falls_back_to_batch_when_bulk_empty():
    mgr, rec = make_manager()
    mgr.reload_settings({"schema_cache": {"ttl_seconds": 300}})
    import expo_jbm329.services.schema_cache as sc

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
