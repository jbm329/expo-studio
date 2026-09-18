"""SQLAlchemy-based ODBC driver implementation."""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from typing import TYPE_CHECKING, Any

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

from expo_jbm329.db.core.interfaces import DriverProtocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.db.core.models import ConnectionConfig

log = logging.getLogger("applogger.db.driver.odbc")


class SqlAlchemyOdbcDriver(DriverProtocol):
    """SQLAlchemy + pyodbc driver (protocol='odbc').

    Caches Engine per unique connection URL and supports best-effort
    cancellation of active executions via tracked DBAPI cursors.
    """

    def __init__(self) -> None:
        """Initialize the SqlAlchemyOdbcDriver."""
        self._engines: dict[str, Engine] = {}
        self._lock = threading.Lock()
        self._query_timeout_s: int | None = None

        self._active_cursors: dict[str, Any] = {}
        self._active_lock = threading.Lock()

    def initialize(self, *, timeouts: dict | None = None) -> None:
        """Initialize the driver with optional timeouts.

        Args:
            timeouts: A dictionary of timeout values.
        """
        _ = timeouts

    def dispose(self) -> None:
        """Dispose of the driver and release all cached engines."""
        with self._active_lock:
            self._active_cursors.clear()

        with self._lock:
            engines = list(self._engines.values())
            self._engines.clear()

        for engine in engines:
            with contextlib.suppress(Exception):
                engine.dispose()

    def set_query_timeout(self, seconds: int | None) -> None:
        """Set the query timeout for subsequent executions.

        Args:
            seconds: The timeout in seconds, or None to reset.
        """
        self._query_timeout_s = int(seconds) if seconds is not None else None

    def cancel_execution(self, job_id: str) -> bool:
        """Attempt to cancel an active execution associated with a job id.

        Args:
            job_id: Execution/job identifier.

        Returns:
            True if an active cursor was found and cancel was attempted,
            otherwise False.
        """
        if not job_id:
            return False

        with self._active_lock:
            cursor = self._active_cursors.get(job_id)

        if cursor is None:
            return False

        try:
            cancel = getattr(cursor, "cancel", None)
            if callable(cancel):
                cancel()
                log.info(
                    "SqlAlchemyOdbcDriver: cancel requested for active execution (job_id=%s)",
                    job_id,
                )
                return True

            log.warning(
                "SqlAlchemyOdbcDriver: active cursor has no cancel() method (job_id=%s)",
                job_id,
            )
            return False

        except Exception:
            log.debug(
                "SqlAlchemyOdbcDriver: cursor cancel failed (job_id=%s).",
                job_id,
                exc_info=True,
            )
            return False

    def _url_for(self, cfg: ConnectionConfig) -> URL:
        """Construct a SQLAlchemy URL for the given configuration.

        Args:
            cfg: The connection configuration.

        Returns:
            A SQLAlchemy URL object.
        """
        dialect = f"{cfg.engine}+pyodbc"
        if cfg.odbc_connect:
            odbc_connect = cfg.odbc_connect
        else:
            parts: list[str] = []
            if cfg.server:
                server = cfg.server if not cfg.port else f"{cfg.server},{int(cfg.port)}"
                parts.append(f"Server={server};")
            if cfg.database:
                parts.append(f"Database={cfg.database};")
            if cfg.user:
                parts.append(f"UID={cfg.user};")
            if cfg.password:
                parts.append(f"PWD={cfg.password};")
            odbc_connect = "".join(parts)

        return URL.create(dialect, query={"odbc_connect": odbc_connect})

    def _get_engine(self, cfg: ConnectionConfig) -> Engine:
        """Retrieve or create a SQLAlchemy Engine for the given configuration.

        Args:
            cfg: The connection configuration.

        Returns:
            A SQLAlchemy Engine instance.
        """
        url = self._url_for(cfg)
        key = f"{cfg.name}::{url!s}"

        with self._lock:
            engine = self._engines.get(key)
            if engine is None:
                log.debug("SqlAlchemyOdbcDriver: creating SQLAlchemy Engine (redacted URL) for %s", cfg.name)
                engine = create_engine(url, pool_pre_ping=True)
                self._engines[key] = engine
            return engine

    def execute_df(
        self,
        conn: ConnectionConfig,
        sql: str,
        *,
        job_id: str | None = None,
        cancel_cb: Callable[[], bool] | None = None,
        corr_id: str | None = None,
    ) -> pd.DataFrame:
        """Execute a SQL query and return the results as a pandas DataFrame.

        This implementation uses a raw DBAPI connection and cursor instead of
        ``pd.read_sql(...)`` so that the active cursor can be tracked and a
        best-effort cancel can be issued from another thread.

        Args:
            conn: The connection configuration.
            sql: The SQL query string.
            job_id: Optional execution/job identifier used for cancellation tracking.
            cancel_cb: Optional cooperative cancellation callback.
            corr_id: Optional correlation identifier for logging.

        Returns:
            A pandas DataFrame containing the query results.

        Raises:
            Exception: Any DBAPI or execution exception is allowed to bubble up
                to DbService for classification.
        """
        engine = self._get_engine(conn)

        raw_conn: Any | None = None
        cursor: Any | None = None

        stop_event = threading.Event()
        watcher_thread: threading.Thread | None = None

        def _is_cancelled() -> bool:
            """Return True if cooperative cancellation was requested."""
            if cancel_cb is None:
                return False
            try:
                return bool(cancel_cb())
            except Exception:
                log.debug(
                    "SqlAlchemyOdbcDriver: cancel callback failed (corr=%s, job_id=%s).",
                    corr_id,
                    job_id,
                    exc_info=True,
                )
                return False

        def _cancel_watcher() -> None:
            """Watch for cancellation and attempt to cancel the active cursor."""
            while not stop_event.is_set():
                if _is_cancelled():
                    if job_id:
                        cancelled = self.cancel_execution(job_id)
                        log.info(
                            "SqlAlchemyOdbcDriver: watcher observed cancellation "
                            "(corr=%s, job_id=%s, cancel_issued=%s)",
                            corr_id,
                            job_id,
                            cancelled,
                        )
                    return
                time.sleep(0.05)

        if _is_cancelled():
            msg = "SqlAlchemyOdbcDriver: SQL execution cancelled before start."
            raise RuntimeError(msg)

        try:
            raw_conn = engine.raw_connection()

            if self._query_timeout_s is not None:
                try:
                    raw_conn.timeout = int(self._query_timeout_s)
                except Exception:
                    log.debug("SqlAlchemyOdbcDriver: driver does not support per-operation timeout.")

            cursor = raw_conn.cursor()

            if job_id:
                with self._active_lock:
                    self._active_cursors[job_id] = cursor

            if cancel_cb is not None and job_id:
                watcher_thread = threading.Thread(
                    target=_cancel_watcher,
                    name=f"sql-cancel-watch-{job_id}",
                    daemon=True,
                )
                watcher_thread.start()

            log.debug(
                "SqlAlchemyOdbcDriver: executing via ODBC for %s (corr=%s, job_id=%s)",
                conn.name,
                corr_id,
                job_id,
            )

            cursor.execute(sql)

            if _is_cancelled():
                msg = "SqlAlchemyOdbcDriver: SQL execution cancelled after execute()."
                raise RuntimeError(msg)

            rows = cursor.fetchall()
            description = cursor.description or []
            columns = [str(col[0]) for col in description]

            if _is_cancelled():
                msg = "SqlAlchemyOdbcDriver: SQL execution cancelled after fetchall()."
                raise RuntimeError(msg)

            if not rows:
                return pd.DataFrame(columns=columns)

            row_data = [tuple(row) for row in rows]
            return pd.DataFrame.from_records(row_data, columns=columns)

        finally:
            stop_event.set()

            if watcher_thread is not None and watcher_thread.is_alive():
                with contextlib.suppress(Exception):
                    watcher_thread.join(timeout=0.2)

            if job_id:
                with self._active_lock:
                    self._active_cursors.pop(job_id, None)

            if cursor is not None:
                with contextlib.suppress(Exception):
                    cursor.close()

            if raw_conn is not None:
                with contextlib.suppress(Exception):
                    raw_conn.close()
