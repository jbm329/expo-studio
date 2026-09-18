"""Cache for database schema information (tables, views, columns).

This module provides the SchemaCacheManager class to manage and prefetch schema
metadata for different database connections.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from expo_jbm329.db.base import (
    get_db_name,
    list_all_columns_map,
    list_columns,
    list_tables,
    list_views,
)
from expo_jbm329.db.core.errors import (
    TR_AUTOCOMPLETE_READY,
    TR_AUTOCOMPLETE_READY_BULK,
    TR_BULK_FAILED_TRYING_BATCH,
    TR_LOADING_SCHEMA,
    TR_PREPARING_AUTOCOMPLETE_BATCH,
    TR_PREPARING_AUTOCOMPLETE_BULK,
    TR_SCHEMA_READY,
)
from expo_jbm329.utils.i18n_utils import tr, tr_fmt

ProgressCb = Callable[[int, int], None]  # (done, total)
StatusCb = Callable[[str, int | None], None]  # (text, timeout)
AutocompleteRebuildCb = Callable[[str], None]  # IMPORTANT: now takes connection_name


# =============================================================================
#   DATA STRUCTURES
# =============================================================================
@dataclass
class SchemaCacheEntry:
    """Cache entry for a single connection.

    Attributes:
        db_name: Name of the database.
        tables: List of table metadata.
        views: List of view metadata.
        columns: Mapping of (schema, table) to column metadata.
        loaded_at: Timestamp when the entry was loaded.
    """

    db_name: str = ""
    tables: list[dict[str, str]] = field(default_factory=list)
    views: list[dict[str, str]] = field(default_factory=list)
    columns: dict[tuple[str, str], list[dict[str, str]]] = field(default_factory=dict)
    loaded_at: float = field(default_factory=time.time)


# =============================================================================
#   SCHEMA CACHE MANAGER
# =============================================================================


class SchemaCacheManager:
    """Connection-aware manager for caching database schema metadata.

    Attributes:
        _cache: Dictionary mapping connection names to SchemaCacheEntry objects.
        _warmup_tokens: Dictionary tracking active prefetch operations.
        _status_cb: Callback for status updates.
        _progress_cb: Callback for progress updates.
        _autocomplete_cb: Callback for autocomplete rebuilding.
    """

    def __init__(
        self,
        *,
        status_cb: StatusCb | None = None,
        progress_cb: ProgressCb | None = None,
        autocomplete_cb: AutocompleteRebuildCb | None = None,
        logger: logging.Logger | None = None,
    ):
        """Initialize the schema cache manager.

        Args:
            status_cb: Callback for status updates.
            progress_cb: Callback for progress updates.
            autocomplete_cb: Callback for autocomplete rebuilding.
            logger: Logger instance for logging.
        """
        self._cache: dict[str, SchemaCacheEntry] = {}
        self._warmup_tokens: dict[str, str] = {}

        self._status_cb = status_cb
        self._progress_cb = progress_cb
        self._autocomplete_cb = autocomplete_cb

        self._runner: Callable | None = None

        self._prefetch_limit_default = 600
        self._batch_size_default = 100
        self._ttl_seconds_default = 300
        self._prefetch_limit: int | None = None
        self._batch_size: int | None = None
        self._ttl_seconds: int | None = None
        self._logger = logger or logging.getLogger("applogger.service")

    # -------------------------------------------------------------------------
    # Public properties
    # -------------------------------------------------------------------------

    @property
    def status_cb(self) -> StatusCb | None:
        """Callback for status updates."""
        return self._status_cb

    @status_cb.setter
    def status_cb(self, cb: StatusCb | None) -> None:
        """Set the callback for status updates."""
        self._status_cb = cb

    @property
    def progress_cb(self) -> ProgressCb | None:
        """Callback for progress updates."""
        return self._progress_cb

    @progress_cb.setter
    def progress_cb(self, cb: ProgressCb | None) -> None:
        """Set the callback for progress updates."""
        self._progress_cb = cb

    @property
    def autocomplete_cb(self) -> AutocompleteRebuildCb | None:
        """Callback for autocomplete rebuilding."""
        return self._autocomplete_cb

    @autocomplete_cb.setter
    def autocomplete_cb(self, cb: AutocompleteRebuildCb | None) -> None:
        """Set the callback for autocomplete rebuilding."""
        self._autocomplete_cb = cb

    # ==================================================================
    # Settings
    # ==================================================================

    def reload_settings(self, settings: dict) -> None:
        """Synchronize SchemaCacheManager with updated global settings.

        Things controlled by settings:
            • prefetch_limit
            • batch_size
        """
        try:
            schema_cache = settings.get("schema_cache", {}) or {}
            prefetch_limit = int(schema_cache.get("prefetch_limit", self._prefetch_limit_default))
            batch_size = int(schema_cache.get("prefetch_batch_size", self._batch_size_default))
            ttl_seconds = int(schema_cache.get("ttl_seconds", self._ttl_seconds_default))

            if prefetch_limit < 0:
                prefetch_limit = 0
            if batch_size <= 0:
                batch_size = self._batch_size_default
            if ttl_seconds <= 0:
                ttl_seconds = self._ttl_seconds_default

            self._prefetch_limit = prefetch_limit
            self._batch_size = batch_size
            self._ttl_seconds = ttl_seconds

            self._logger.info(
                "SchemaCacheManager: settings reloaded (prefetch_limit=%s, batch_size=%s, ttl_seconds=%s)",
                self._prefetch_limit,
                self._batch_size,
                self._ttl_seconds,
            )

            if self._status_cb:
                self._status_cb(tr("DbErrors", "Settings for schema cache updated."), 4000)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as e:
            self._logger.exception("SchemaCacheManager: failed to reload settings: %s", e)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    def get_cache_for(self, connection_name: str) -> SchemaCacheEntry | None:
        """Get the cache entry for a given connection."""
        return self._cache.get(connection_name)

    def clear_all(self) -> None:
        """Clear all cached schema data."""
        self._cache.clear()
        self._warmup_tokens.clear()

    def clear_for(self, connection_name: str) -> None:
        """Clear cached schema data for a specific connection."""
        self._cache.pop(connection_name, None)
        self._warmup_tokens.pop(connection_name, None)

    def is_cache_valid(self, connection_name: str) -> bool:
        """Check if the cache for a connection is still valid based on TTL."""
        entry = self._cache.get(connection_name)
        if not entry:
            return False
        return (time.time() - entry.loaded_at) < self._ttl_seconds

    def load_schema(self, connection_name: str, force_refresh: bool = False, corr_id=None) -> SchemaCacheEntry:
        """Load db_name + tables/views. (Columns loaded separately by async prefetch.)."""
        if force_refresh:
            self.clear_for(connection_name)

        if self.is_cache_valid(connection_name):
            return self._cache[connection_name]

        if self._status_cb:
            self._status_cb(tr("DbErrors", TR_LOADING_SCHEMA), 0)

        db_name = get_db_name(connection_name, corr_id=corr_id)
        tables = list_tables(connection_name, corr_id=corr_id) or []
        views = list_views(connection_name, corr_id=corr_id) or []

        entry = SchemaCacheEntry(
            db_name=db_name,
            tables=tables,
            views=views,
            columns={},
            loaded_at=time.time(),
        )
        self._cache[connection_name] = entry

        if self._status_cb:
            self._status_cb(tr("DbErrors", TR_SCHEMA_READY), 4000)

        self._logger.info(
            "SchemaCacheManager: schema loaded: '%s' (%d tables, %d views, corr=%s).",
            connection_name,
            len(tables),
            len(views),
            corr_id,
        )

        return entry

    def set_job_runner(self, runner_callable: Callable, corr_id=None) -> None:
        """Register a callable to run database jobs asynchronously."""
        self._runner = runner_callable
        self._logger.debug("SchemaCacheManager: job runner registered (corr=%s).", corr_id)

    # -----------------------------------------------------------------------------
    # PREFETCH (async)
    # -----------------------------------------------------------------------------
    def prefetch_columns_async(self, connection_name: str, run_job_fn: Callable | None = None, corr_id=None) -> None:
        """Prefetch column metadata for all tables and views in a connection."""
        entry = self._cache.get(connection_name)
        if not entry:
            return

        if run_job_fn is not None:
            self._runner = run_job_fn

        if not self._runner:
            self._logger.warning("SchemaCacheManager: no job runner → batch fallback (corr=%s).", corr_id)
            token = self._make_token(connection_name)
            self._start_batch_prefetch(connection_name, token, corr_id)
            return

        token = self._make_token(connection_name)

        worker = self._runner(
            None,
            lambda conn: list_all_columns_map(conn, corr_id=corr_id),
            connection_name,
            started_msg=tr("DbErrors", TR_PREPARING_AUTOCOMPLETE_BULK),
            corr_id=corr_id,
        )

        worker.result.connect(lambda payload: self._on_bulk_done(connection_name, token, payload, corr_id))
        worker.error.connect(lambda err: self._handle_bulk_error(connection_name, token, err, corr_id))

    # -----------------------------------------------------------------------------
    # INTERNAL HELPERS
    # -----------------------------------------------------------------------------
    def _make_token(self, connection_name: str) -> str:
        token = f"{connection_name}:{time.time()}"
        self._warmup_tokens[connection_name] = token
        return token

    def _token_matches(self, connection_name: str, token: str) -> bool:
        return self._warmup_tokens.get(connection_name) == token

    def _invoke_ui(self, fn: Callable[[], None]) -> None:
        """Run fn() on UI thread using QTimer.singleShot."""
        try:
            from PyQt6.QtCore import QTimer

            QTimer.singleShot(0, fn)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            try:
                fn()
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as ex:
                self._logger.warning("SchemaCacheManager: UI callback failed: %s", ex)

    # -----------------------------------------------------------------------------
    # BULK HANDLER
    # -----------------------------------------------------------------------------
    def _handle_bulk_error(self, connection_name: str, token: str, err: str, corr_id: str | None = None):
        self._logger.warning("SchemaCacheManager: bulk error (conn=%s, corr=%s): %s", connection_name, corr_id, err)

        if self._status_cb:
            self._status_cb(tr("DbErrors", TR_BULK_FAILED_TRYING_BATCH), 5000)

        self._start_batch_prefetch(connection_name, token, corr_id)

    def _normalize_key(self, key: Any) -> tuple[str, str] | None:
        try:
            if isinstance(key, tuple) and len(key) == 2:
                return key
            if isinstance(key, list) and len(key) == 2:
                return key[0], key[1]
            if isinstance(key, str) and "." in key:
                sch, t = key.split(".", 1)
                return sch.strip(), t.strip()
            if isinstance(key, dict):
                sch = key.get("schema")
                t = key.get("name")
                if isinstance(sch, str) and isinstance(t, str):
                    return (sch, t)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            pass
        return None

    def _normalize_bulk_map(self, payload: Any) -> dict[tuple[str, str], list[dict]]:
        if not isinstance(payload, dict):
            return {}

        out = {}
        for raw_key, cols in payload.items():
            key = self._normalize_key(raw_key)
            if not key:
                continue
            try:
                lst = list(cols) if cols else []
                lst = [c for c in lst if isinstance(c, dict)]
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                lst = []
            out[key] = lst
        return out

    def _on_bulk_done(self, connection_name: str, token: str, payload: Any, corr_id: str | None = None) -> None:
        if not self._token_matches(connection_name, token):
            return

        entry = self._cache.get(connection_name)
        if not entry:
            return

        bulk_map = self._normalize_bulk_map(payload)

        if not bulk_map:
            self._logger.warning("SchemaCacheManager: bulk empty → batch fallback (corr=%s).", corr_id)
            self._start_batch_prefetch(connection_name, token, corr_id)
            return

        wanted = {(tbl["schema"], tbl["name"]) for tbl in entry.tables} | {
            (vw["schema"], vw["name"]) for vw in entry.views
        }

        merged = 0
        for key, cols in bulk_map.items():
            if key in wanted:
                entry.columns[key] = cols
                merged += 1

        total_cols = sum(len(v) for v in entry.columns.values())

        self._logger.info(
            "SchemaCacheManager: bulk done (conn=%s, merged=%d/%d, total_columns=%d, corr=%s)",
            connection_name,
            merged,
            len(bulk_map),
            total_cols,
            corr_id,
        )

        if merged == 0:
            self._logger.warning("SchemaCacheManager: bulk merged 0 → batch fallback (corr=%s).", corr_id)
            self._start_batch_prefetch(connection_name, token, corr_id)
            return

        self._logger.debug(
            "SchemaCacheManager: autocomplete_cb is %s for '%s'",
            "SET" if self._autocomplete_cb else "NONE",
            connection_name,
        )

        # UI rebuild (IMPORTANT: pass connection_name)
        if self._autocomplete_cb:
            self._invoke_ui(lambda: self._autocomplete_cb(connection_name))
            self._logger.debug(
                "SchemaCacheManager: autocomplete rebuild (bulk) requested for '%s' (corr=%s).",
                connection_name,
                corr_id,
            )

        if self._status_cb:
            msg = tr_fmt("DbErrors", TR_AUTOCOMPLETE_READY_BULK, count=str(merged))
            self._status_cb(msg, 8000)

        if self._progress_cb:
            self._progress_cb(1, 1)

    # -----------------------------------------------------------------------------
    # BATCH HANDLER
    # -----------------------------------------------------------------------------
    def _start_batch_prefetch(self, connection_name: str, token: str, corr_id: str | None = None):
        entry = self._cache.get(connection_name)
        if not entry:
            return

        missing: list[tuple[str, str]] = []

        for r in entry.tables:
            k = (r["schema"], r["name"])
            if k not in entry.columns:
                missing.append(k)

        for r in entry.views:
            k = (r["schema"], r["name"])
            if k not in entry.columns:
                missing.append(k)

        if not missing:
            if self._progress_cb:
                self._progress_cb(1, 1)
            if self._status_cb:
                self._status_cb(tr("DbErrors", TR_AUTOCOMPLETE_READY), 6000)
            return

        if self._prefetch_limit > 0:
            missing = missing[: self._prefetch_limit]

        total = len(missing)
        if self._progress_cb:
            self._progress_cb(0, total)

        self._logger.debug(
            "SchemaCacheManager: starting batch (objects=%d, batch=%d, corr=%s)", total, self._batch_size, corr_id
        )

        self._run_next_batch(connection_name, token, missing, self._batch_size, 0, total, corr_id)

    def _run_next_batch(
        self,
        connection_name: str,
        token: str,
        remaining: list[tuple[str, str]],
        batch_size: int,
        done: int,
        total: int,
        corr_id: str | None = None,
    ):
        if not remaining:
            if self._autocomplete_cb:
                self._invoke_ui(lambda: self._autocomplete_cb(connection_name))
                self._logger.debug(
                    "SchemaCacheManager: autocomplete rebuild (batch final) for '%s' (corr=%s)",
                    connection_name,
                    corr_id,
                )

            if self._status_cb:
                self._status_cb(tr("DbErrors", TR_AUTOCOMPLETE_READY), 6000)

            if self._progress_cb:
                self._progress_cb(total, total)

            self._logger.info("SchemaCacheManager: batch complete for '%s' (corr=%s)", connection_name, corr_id)
            return

        batch = remaining[:batch_size]
        rest = remaining[batch_size:]

        def batch_job(conn: str, pairs: list[tuple[str, str]]):
            result = {}
            for sch, name in pairs:
                try:
                    cols = list_columns(conn, sch, name, corr_id) or []
                except (
                    AttributeError,
                    ConnectionError,
                    FileNotFoundError,
                    IndexError,
                    KeyError,
                    LookupError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ) as ex:
                    self._logger.warning(
                        "SchemaCacheManager: list columns failed for %s.%s (%s): %s (corr=%s).)",
                        sch,
                        name,
                        conn,
                        ex,
                        corr_id,
                    )
                    cols = []
                result[(sch, name)] = cols
            return result

        if not self._runner:
            self._logger.warning(
                "SchemaCacheManager: no runner → synchronous batch (conn=%s, remaining=%d, corr=%s).",
                connection_name,
                len(remaining),
                corr_id,
            )
            entry = self._cache.get(connection_name)
            if entry:
                out = batch_job(connection_name, batch)
                entry.columns.update(out)
            new_done = done + len(batch)
            if self._progress_cb:
                self._progress_cb(new_done, total)
            self._run_next_batch(connection_name, token, rest, batch_size, new_done, total, corr_id)
            return

        worker = self._runner(
            None,
            batch_job,
            connection_name,
            batch,
            started_msg=tr_fmt("DbErrors", TR_PREPARING_AUTOCOMPLETE_BATCH, done=str(done), total=str(total)),
            corr_id=corr_id,
        )

        def _on_ok(payload):
            entry = self._cache.get(connection_name) or None
            if entry:
                entry.columns.update(payload or {})

            new_done = done + len(batch)

            if self._progress_cb:
                self._progress_cb(new_done, total)

            if self._autocomplete_cb:
                self._invoke_ui(lambda: self._autocomplete_cb(connection_name))
                self._logger.debug(
                    "SchemaCacheManager: autocomplete rebuild (batch increment) for '%s' (corr=%s)",
                    connection_name,
                    corr_id,
                )

            # schedule next batch
            try:
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(
                    0, lambda: self._run_next_batch(connection_name, token, rest, batch_size, new_done, total, corr_id)
                )
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._run_next_batch(connection_name, token, rest, batch_size, new_done, total, corr_id)

        def _on_err(err: str):
            self._logger.warning(
                "SchemaCacheManager: batch error (conn=%s, corr=%s): %s", connection_name, corr_id, err
            )

            # continue anyway
            self._run_next_batch(connection_name, token, rest, batch_size, done + len(batch), total, corr_id)

        worker.result.connect(_on_ok)
        worker.error.connect(_on_err)
