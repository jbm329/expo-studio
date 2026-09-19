"""SQLAlchemy-based SQLite driver implementation."""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import TYPE_CHECKING

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

from expo_jbm329.db.core.interfaces import DriverProtocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.db.core.models import ConnectionConfig

log = logging.getLogger("applogger.db.driver.sqlite")


class SqlAlchemySqliteDriver(DriverProtocol):
    """SQLAlchemy driver for SQLite using pysqlite.

    Features:
        * Uses 'sqlite+pysqlite' URL.
        * Database path comes from cfg.database (':memory:' supported).
        * connect_args['timeout'] is honored as busy_timeout (seconds).
    """

    def __init__(self) -> None:
        """Initialize the SqlAlchemySqliteDriver."""
        self._engines: dict[str, Engine] = {}
        self._lock = threading.Lock()
        self._connect_timeout_s: int | None = None

    def initialize(self, *, timeouts: dict[str, int | None] | None = None) -> None:
        """Initialize the driver with optional timeouts.

        Args:
            timeouts: A dictionary of timeout values.
        """
        login_timeout = timeouts.get("login_timeout_s") if timeouts is not None else None
        self._connect_timeout_s = int(login_timeout) if login_timeout is not None else None

    def dispose(self) -> None:
        """Dispose of the driver and release all cached engines."""
        with self._lock:
            engines = list(self._engines.values())
            self._engines.clear()
        for e in engines:
            with contextlib.suppress(Exception):
                e.dispose()

    def set_query_timeout(self, seconds: int | None) -> None:
        """Set the query timeout for subsequent executions.

        Note:
            SQLite does not have per-statement execution timeout. No-op.

        Args:
            seconds: The timeout in seconds, or None to reset.
        """

    def cancel_execution(self, job_id: str) -> bool:
        """Attempt to cancel an active execution associated with a job id."""
        log.info(
            "SqlAlchemySqliteDriver: cancel requested for active execution "
            "but not implemented in current driver (job_id=%s)",
            job_id,
        )
        return False

    def _url_for(self, cfg: ConnectionConfig) -> URL:
        """Construct a SQLAlchemy URL for the given configuration.

        Args:
            cfg: The connection configuration.

        Returns:
            A SQLAlchemy URL object.
        """
        db_path = cfg.database or ":memory:"
        # If user supplied extra={'uri': 'true', 'cache': 'shared'} it will be passed through
        query = {str(key): str(value) for key, value in (cfg.extra or {}).items()}
        return URL.create("sqlite+pysqlite", database=db_path, query=query)

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
            eng = self._engines.get(key)
            if eng is None:
                connect_args = {}
                if self._connect_timeout_s is not None:
                    connect_args["timeout"] = self._connect_timeout_s
                log.debug("SqlAlchemySqliteDriver: creating SQLAlchemy Engine for SQLite: %s", cfg.name)
                eng = create_engine(url, pool_pre_ping=False, connect_args=connect_args)
                self._engines[key] = eng
            return eng

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

        Args:
            conn: The connection configuration.
            sql: The SQL query string.
            job_id: Optional execution/job identifier used for cancellation tracking.
            cancel_cb: A callback function to check if the operation should be canceled.
            corr_id: The correlation ID for logging purposes.

        Returns:
            A pandas DataFrame containing the query results.
        """
        _ = cancel_cb
        engine = self._get_engine(conn)
        with engine.connect() as cx:
            log.debug(
                "SqlAlchemyMySqlDriver: executing via SQLite for %s (corr=%s, job_id=%s)",
                conn.name,
                corr_id,
                job_id,
            )
            return pd.read_sql(sql, cx)
