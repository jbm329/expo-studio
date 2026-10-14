"""SQLAlchemy-based PostgreSQL driver implementation."""

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

log = logging.getLogger("applogger.db.driver.postgres")


class SqlAlchemyPostgresDriver(DriverProtocol):
    """SQLAlchemy driver for PostgreSQL with pluggable DBAPI.

    Supports:
        * protocol 'psycopg2' -> URL 'postgresql+psycopg2'
        * protocol 'psycopg' -> URL 'postgresql+psycopg'

    Notes:
        * connect_timeout: seconds to wait for initial connection.
        * query_timeout: statement timeout in milliseconds via PostgreSQL options.
    """

    def __init__(self, driver_name: str = "psycopg2") -> None:
        """Initialize the SqlAlchemyPostgresDriver.

        Args:
            driver_name: The name of the DBAPI driver ('psycopg2' or 'psycopg').
        """
        self._driver_name = driver_name
        self._engines: dict[str, Engine] = {}
        self._lock = threading.Lock()
        self._query_timeout_s: int | None = None
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

        Args:
            seconds: The timeout in seconds, or None to reset.
        """
        self._query_timeout_s = int(seconds) if seconds is not None else None

    def cancel_execution(self, job_id: str) -> bool:
        """Attempt to cancel an active execution associated with a job id."""
        log.info(
            "SqlAlchemyPostgresDriver: cancel requested for active execution "
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
        dialect = f"postgresql+{self._driver_name}"
        username = cfg.user or ""
        password = cfg.password or ""
        host = cfg.server or "localhost"
        port = int(cfg.port) if cfg.port else 5432
        database = cfg.database or ""
        query = {str(key): str(value) for key, value in (cfg.extra or {}).items()}
        return URL.create(
            dialect,
            username=username or None,
            password=password or None,
            host=host,
            port=port,
            database=database or None,
            query=query,
        )

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
                connect_args: dict[str, object] = {}
                if self._connect_timeout_s is not None:
                    connect_args["connect_timeout"] = self._connect_timeout_s
                if self._query_timeout_s is not None:
                    connect_args["options"] = f"-c statement_timeout={int(self._query_timeout_s * 1000)}"
                log.debug(
                    "SqlAlchemyPostgresDriver: creating SQLAlchemy Engine for %s (driver=%s)",
                    cfg.name,
                    self._driver_name,
                )
                try:
                    eng = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
                except Exception:
                    log.exception(
                        "SqlAlchemyPostgresDriver: failed to create SQLAlchemy Engine for %s (driver=%s)",
                        cfg.name,
                        self._driver_name,
                    )
                    raise
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
            cancel_cb: A callback function to check if the operation should be cancelled.
            corr_id: The correlation ID for logging purposes.

        Returns:
            A pandas DataFrame containing the query results.
        """
        _ = cancel_cb

        engine = self._get_engine(conn)
        with engine.connect() as cx:
            log.debug(
                "SqlAlchemyPostgresDriver: executing via PostgreSQL driver '%s' for %s (corr=%s, job_id=%s)",
                self._driver_name,
                conn.name,
                corr_id,
                job_id,
            )
            return pd.read_sql(sql, cx)
