"""SQLAlchemy-based driver for existing, read-only DuckDB database files."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine
from sqlalchemy.pool import NullPool

from expo_jbm329.db.core.interfaces import DriverProtocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.db.core.models import ConnectionConfig

log = logging.getLogger("applogger.db.driver.duckdb")


class SqlAlchemyDuckDbDriver(DriverProtocol):
    """Read DuckDB files through SQLAlchemy without sharing raw connections.

    Engines are cached, but NullPool closes each native connection after use.
    This keeps query and metadata workers independent and releases file locks
    between operations.
    """

    def __init__(self) -> None:
        """Initialize the engine cache and its lock."""
        self._engines: dict[str, Engine] = {}
        self._lock = threading.Lock()

    def initialize(self, *, timeouts: dict[str, int | None] | None = None) -> None:
        """Log that DuckDB does not support a login timeout."""
        if timeouts is not None and timeouts.get("login_timeout_s") is not None:
            log.debug("DuckDB does not support a login timeout.")

    def set_query_timeout(self, seconds: int | None) -> None:
        """Log that per-statement timeouts are not implemented for DuckDB."""
        if seconds is not None:
            log.debug("DuckDB per-statement timeout is not implemented (requested=%s).", seconds)

    def cancel_execution(self, job_id: str) -> bool:
        """Report that active queries cannot be interrupted by this driver."""
        log.info("DuckDB active query interruption is not implemented (job_id=%s).", job_id)
        return False

    def dispose(self) -> None:
        """Dispose all cached engines."""
        with self._lock:
            engines = list(self._engines.values())
            self._engines.clear()
        for engine in engines:
            engine.dispose()

    def validate_configuration(self, cfg: ConnectionConfig) -> None:
        """Validate local file settings without opening a database connection.

        Args:
            cfg: DuckDB connection configuration to validate.

        Raises:
            ValueError: If protocol, path or extra options are unsupported.
            OSError: If the path is missing, inaccessible or not a regular file.
        """
        self._url_for(cfg)

    def _url_for(self, cfg: ConnectionConfig) -> URL:
        """Validate the configuration and build a URL for an existing file.

        Args:
            cfg: Connection configuration with a local database file path.

        Returns:
            A SQLAlchemy DuckDB URL containing the resolved file path.

        Raises:
            ValueError: If the configuration is not a local read-only connection.
            FileNotFoundError: If the database file does not exist.
            IsADirectoryError: If the path does not identify a regular file.
        """
        if cfg.engine != "duckdb" or cfg.protocol != "duckdb":
            msg = "DuckDB connections require engine='duckdb' and protocol='duckdb'."
            raise ValueError(msg)
        if cfg.extra:
            msg = "DuckDB connections do not support extra options. Read-only access is always enforced."
            raise ValueError(msg)
        database = cfg.database
        if (
            database is None
            or not database.strip()
            or database.startswith(":")
            or database.lower().startswith("md:")
            or "://" in database
        ):
            msg = "DuckDB connections require an existing local database file."
            raise ValueError(msg)
        path = Path(database).expanduser().resolve(strict=True)
        if not path.is_file():
            msg = f"DuckDB database path is not a regular file: {path}"
            raise IsADirectoryError(msg)
        return URL.create("duckdb", database=str(path))

    def _get_engine(self, cfg: ConnectionConfig) -> Engine:
        """Retrieve or create an engine with read-only access enforced."""
        url = self._url_for(cfg)
        key = f"{cfg.name}::{url!s}"
        with self._lock:
            engine = self._engines.get(key)
            if engine is None:
                log.debug("Creating read-only DuckDB SQLAlchemy engine for %s.", cfg.name)
                engine = create_engine(
                    url,
                    connect_args={"read_only": True},
                    poolclass=NullPool,
                )
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
        """Execute SQL on an independent connection and return a dataframe.

        Args:
            conn: Connection configuration.
            sql: SQL query text.
            job_id: Optional execution identifier for logging.
            cancel_cb: Cooperative cancellation callback handled by DbService.
            corr_id: Optional correlation identifier for logging.

        Returns:
            The query result as a dataframe.
        """
        _ = cancel_cb
        engine = self._get_engine(conn)
        with engine.connect() as connection:
            log.debug("Executing DuckDB query for %s (corr=%s, job_id=%s).", conn.name, corr_id, job_id)
            return pd.read_sql(sql, connection)
