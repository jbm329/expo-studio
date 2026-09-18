"""SQLAlchemy-based MySQL/MariaDB driver implementation."""

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

log = logging.getLogger("applogger.db.driver.mysql")


class SqlAlchemyMySqlDriver(DriverProtocol):
    """SQLAlchemy driver for MySQL/MariaDB with pluggable DBAPI.

    Supports:
        * protocol 'pymysql' -> URL 'mysql+pymysql' or 'mariadb+pymysql'
        * protocol 'mysqlconnector' -> URL 'mysql+mysqlconnector' or 'mariadb+mysqlconnector'

    Notes:
        * connect_timeout: seconds to wait for initial connection.
        * read_timeout/write_timeout: I/O timeouts (not server execution limits).
    """

    def __init__(self, driver_name: str) -> None:
        """Initialize the SqlAlchemyMySqlDriver.

        Args:
            driver_name: The name of the DBAPI driver ('pymysql' or 'mysqlconnector').
        """
        self._driver_name = driver_name  # 'pymysql' or 'mysqlconnector'
        self._engines: dict[str, Engine] = {}
        self._lock = threading.Lock()
        self._query_timeout_s: int | None = None
        self._connect_timeout_s: int | None = None

    def initialize(self, *, timeouts: dict | None = None) -> None:
        """Initialize the driver with optional timeouts.

        Args:
            timeouts: A dictionary of timeout values.
        """
        # We treat login/connect timeout via connect_args later in _get_engine.
        self._connect_timeout_s = (
            int(timeouts.get("login_timeout_s")) if (timeouts and timeouts.get("login_timeout_s") is not None) else None
        )

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
            MySQL DBAPIs don't expose per-statement "execution" timeout uniformly.
            We'll pass read/write timeouts as a best effort via connect_args.

        Args:
            seconds: The timeout in seconds, or None to reset.
        """
        self._query_timeout_s = int(seconds) if seconds is not None else None

    def cancel_execution(self, job_id: str) -> bool:
        """Attempt to cancel an active execution associated with a job id."""
        log.info(
            "SqlAlchemyMySqlDriver: cancel requested for active execution "
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
        # Choose 'mysql' or 'mariadb' dialect name
        base = "mariadb" if cfg.engine == "mariadb" else "mysql"
        dialect = f"{base}+{self._driver_name}"
        username = cfg.user or ""
        password = cfg.password or ""
        host = cfg.server or "localhost"
        port = int(cfg.port) if cfg.port else 3306
        database = cfg.database or ""
        return URL.create(
            dialect,
            username=username or None,
            password=password or None,
            host=host,
            port=port,
            database=database or None,
            query=cfg.extra or {},
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
                connect_args = {}
                if self._connect_timeout_s is not None:
                    # Standard MySQL connect timeout
                    connect_args["connect_timeout"] = self._connect_timeout_s
                if self._query_timeout_s is not None:
                    # Network I/O timeouts (best effort)
                    connect_args["read_timeout"] = self._query_timeout_s
                    connect_args["write_timeout"] = self._query_timeout_s
                log.debug(
                    "SqlAlchemyMySqlDriver: creating SQLAlchemy Engine for %s (driver=%s)", cfg.name, self._driver_name
                )
                eng = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
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
                "SqlAlchemyMySqlDriver: executing via MySQL driver '%s' for %s (corr=%s, job_id=%s)",
                self._driver_name,
                conn.name,
                corr_id,
                job_id,
            )
            return pd.read_sql(sql, cx)
