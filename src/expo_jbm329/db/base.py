"""Database API Facade.

This module provides the *public, high-level database API* for the rest of the
application.

It serves as an enterprise-style **facade** on top of:

    * Connection configuration & normalization
    * Dependency injection (drivers + dialects)
    * DbService (query execution, error classification, dialect integration)
    * Metadata helpers (tables/views/columns/etc.)
    * High-level SELECT builders (SELECT *, auto column list, TOP/LIMIT)

All UI/controllers should call THIS module, not the lower-level layers.

Architecture layering:
    workbench/*         -> db/base.py (this facade)
                        -> DbService (execution)
                        -> Dialects (SQL syntax rules)
                        -> Drivers (ODBC/pymysql/sqlite etc.)
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from expo_jbm329.app.settings.config_store import read_connections
from expo_jbm329.db.core.di import ServiceRegistry
from expo_jbm329.db.core.errors import TR_COULD_NOT_INIT_CONN
from expo_jbm329.db.core.models import ConnectionConfig, SqlError, SqlResult, TimeoutConfig
from expo_jbm329.db.dialects.mssql import MssqlDialect
from expo_jbm329.db.dialects.mysql import MySqlDialect
from expo_jbm329.db.dialects.sqlite import SqliteDialect
from expo_jbm329.db.drivers.sa_mysql import SqlAlchemyMySqlDriver
from expo_jbm329.db.drivers.sa_odbc import SqlAlchemyOdbcDriver
from expo_jbm329.db.drivers.sa_sqlite import SqlAlchemySqliteDriver
from expo_jbm329.db.service import DbService

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd

logger = logging.getLogger("applogger.db")

# =============================================================================
# Dependency Injection: Driver + Dialect Registry
# =============================================================================

_registry = ServiceRegistry()

# Drivers
_registry.register_driver("odbc", lambda: SqlAlchemyOdbcDriver())
_registry.register_driver("pymysql", lambda: SqlAlchemyMySqlDriver("pymysql"))
_registry.register_driver("mysqlconnector", lambda: SqlAlchemyMySqlDriver("mysqlconnector"))
_registry.register_driver("sqlite", lambda: SqlAlchemySqliteDriver())

# Dialects
_registry.register_dialect("mysql", lambda: MySqlDialect())
_registry.register_dialect("mariadb", lambda: MySqlDialect())
_registry.register_dialect("mssql", lambda: MssqlDialect())
_registry.register_dialect("sqlite", lambda: SqliteDialect())

# =============================================================================
# Global Service Cache (per connection)
# =============================================================================

_services: dict[str, tuple[DbService, ConnectionConfig]] = {}
_login_timeout_s: int | None = 10
_query_timeout_s: int | None = 30


# =============================================================================
# Timeout Configuration
# =============================================================================


def configure_timeouts(*, login_timeout_s: int | None = None, query_timeout_s: int | None = None) -> None:
    """Configure global default timeouts for newly created DbService instances.

    Args:
        login_timeout_s: Max seconds to wait for establishing a database connection.
        query_timeout_s: Max seconds for individual query execution (driver dependent).

    Raises:
        ValueError: If either timeout value is negative.
    """
    global _login_timeout_s, _query_timeout_s

    if login_timeout_s is not None:
        if login_timeout_s < 0:
            msg = "login_timeout_s cannot be negative."
            raise ValueError(msg)
        _login_timeout_s = int(login_timeout_s)

    if query_timeout_s is not None:
        if query_timeout_s < 0:
            msg = "query_timeout_s cannot be negative."
            raise ValueError(msg)
        _query_timeout_s = int(query_timeout_s)

    logger.debug("DB timeouts configured: login=%s, query=%s", _login_timeout_s, _query_timeout_s)


# =============================================================================
# ConnectionConfig Builder
# =============================================================================


def _build_connection_config(connection_name: str) -> ConnectionConfig:
    """Construct a ConnectionConfig from user configuration.

    Responsibilities:
        * Normalize engine names (mssql/mysql/mariadb/sqlite/postgresql/oracle).
        * Determine protocol (odbc/pymysql/sqlite/mysqlconnector).
        * Build ODBC connection string *only* when protocol == 'odbc'.
        * Keep discrete fields for all non-ODBC drivers.
        * SQLite: treat "database" as file path or ':memory:'; no ODBC used.

    Args:
        connection_name: The name of the connection to build.

    Returns:
        A fully normalized configuration object used by DbService and drivers.

    Raises:
        RuntimeError: If the configuration for the connection is missing.
    """
    conns = read_connections()
    rec = conns.get(connection_name)
    if not isinstance(rec, dict):
        msg = f"Missing config for '{connection_name}'"
        raise RuntimeError(msg)

    # --- Engine normalization -------------------------------------------------
    engine = (rec.get("db_type") or "mssql").lower()
    if engine in ("postgres", "postgresql"):
        engine = "postgresql"
    allowed = ("mssql", "postgresql", "mysql", "mariadb", "sqlite", "oracle")
    if engine not in allowed:
        engine = "mssql"

    # --- Protocol selection ---------------------------------------------------
    protocol = (rec.get("protocol") or ("sqlite" if engine == "sqlite" else "odbc")).lower()

    # --- Common fields --------------------------------------------------------
    server = rec.get("server", "")
    port_raw = rec.get("port", None)
    try:
        port = int(port_raw) if port_raw not in (None, "") else None
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
        port = None

    database = rec.get("database") or None
    user = rec.get("user") or None
    password = rec.get("password") or None
    dsn = rec.get("dsn") or None
    extra = rec.get("extra") or {}

    # --- Protocol-specific connection string handling ------------------------
    odbc_connect = None

    if protocol == "odbc":
        # Build an ODBC connection string (e.g., for SQL Server)
        driver = rec.get("driver", "")
        if driver and not (driver.startswith("{") and driver.endswith("}")):
            driver = "{" + driver + "}"

        odbc_server = server
        if port is not None:
            with contextlib.suppress(Exception):
                odbc_server = f"{server},{int(port)}"

        parts = []
        if driver:
            parts.append(f"Driver={driver};")
        if odbc_server:
            parts.append(f"Server={odbc_server};")
        if database:
            parts.append(f"Database={database};")

        tc = str(rec.get("trusted_connection", "")).lower().strip()
        if tc in ("yes", "true", "1", "y"):
            parts.append("Trusted_Connection=yes;")
        else:
            if user:
                parts.append(f"UID={user};")
            if password:
                parts.append(f"PWD={password};")

        candidate = "".join(parts)
        odbc_connect = candidate or rec.get("odbc_connect") or None

    elif protocol == "sqlite":
        # SQLite uses no ODBC. database is filepath or ':memory:'.
        if not database:
            fp = rec.get("filepath") or rec.get("path")
            if fp:
                database = fp

    else:
        # Non-ODBC protocols: leave odbc_connect=None
        pass

    return ConnectionConfig(
        name=connection_name,
        engine=engine,
        protocol=protocol,
        database=database,
        server=server,
        port=port,
        user=user,
        password=password,
        odbc_connect=odbc_connect,
        dsn=dsn,
        extra=extra,
    )


# =============================================================================
# DbService Factory & Lifetime Management
# =============================================================================


def _get_service_with_config(connection_name: str) -> tuple[DbService, ConnectionConfig]:
    """Retrieve (or create) a DbService instance and its config.

    Ensures:
        * Driver and dialect resolved via DI.
        * Timeout configuration applied.
        * Per-connection service and config cached for reuse.

    Args:
        connection_name: The name of the connection.

    Returns:
        A tuple of (DbService, ConnectionConfig).
    """
    entry = _services.get(connection_name)
    if entry is None:
        cfg = _build_connection_config(connection_name)
        driver = _registry.create_driver(cfg.protocol)
        dialect = _registry.create_dialect(cfg.engine)

        svc = DbService(
            driver=driver,
            dialect=dialect,
            timeouts=TimeoutConfig(_login_timeout_s, _query_timeout_s),
            allow_exec=True,
        )
        entry = (svc, cfg)
        _services[connection_name] = entry

    return entry


def close_connection(connection_name: str) -> None:
    """Dispose the DbService and cached engine(s) for one connection.

    Args:
        connection_name: The name of the connection to close.
    """
    entry = _services.pop(connection_name, None)
    if entry:
        svc, _ = entry
        svc.dispose()


def close_all_connections() -> None:
    """Dispose all active DbService instances across all connections.

    Intended for application shutdown.
    """
    for _, (svc, _) in list(_services.items()):
        svc.dispose()
    _services.clear()


# =============================================================================
# Public Execution API
# =============================================================================


def execute_sql_safe(
    connection_name: str,
    sql_text: str,
    top_n: int | None = None,
    corr_id: str | None = None,
    cancel_cb: Callable[[], bool] | None = None,
    job_id: str | None = None,
) -> SqlResult:
    """Execute a SQL statement and return a SqlResult.

    Args:
        connection_name: Logical connection identifier from user configuration.
        sql_text: Raw SQL text to execute.
        top_n: Optional number of rows to limit (server- or client-side).
        corr_id: Optional correlation ID for logging.
        cancel_cb: Optional cooperative cancellation callback.
        job_id: Optional execution/job identifier.

    Returns:
        Structured, UI-safe result with data frame, metadata, and error object.
    """
    try:
        if cancel_cb is not None and cancel_cb():
            return SqlResult(
                ok=False,
                cancelled=True,
            )

        svc, cfg = _get_service_with_config(connection_name)

        return svc.execute_sql(
            cfg,
            sql_text,
            top_n=top_n,
            corr_id=corr_id,
            cancel_cb=cancel_cb,
            job_id=job_id,
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
    ) as e:
        logger.error(
            "Failed to initialize database service for '%s': %s",
            connection_name,
            e,
        )
        return SqlResult(
            ok=False,
            cancelled=False,
            error=SqlError(
                category="connection",
                code=None,
                message=TR_COULD_NOT_INIT_CONN,
                hint=str(e),
            ),
        )


def fetch_df(connection_name: str, sql: str) -> pd.DataFrame | None:
    """Convenience wrapper returning only the DataFrame part of a query result.

    Prefer using execute_sql_safe() for full error and detail control.

    Args:
        connection_name: The name of the connection.
        sql: The SQL query string.

    Returns:
        A pandas DataFrame if the query was successful, otherwise None.
    """
    res = execute_sql_safe(connection_name, sql, top_n=None)
    return res.data if res.ok else None


# =============================================================================
# Public Metadata API (Facade over DbService)
# =============================================================================


def list_tables(connection_name: str, corr_id: str | None = None) -> list[dict[str, str]]:
    """List all tables for the given connection.

    Args:
        connection_name: The name of the connection.
        corr_id: Optional correlation ID for logging.

    Returns:
        A list of dictionaries with table metadata (schema, name).
    """
    svc, cfg = _get_service_with_config(connection_name)
    return svc.list_tables(cfg, corr_id=corr_id)


def list_views(connection_name: str, corr_id: str | None = None) -> list[dict[str, str]]:
    """List all views for the given connection.

    Args:
        connection_name: The name of the connection.
        corr_id: Optional correlation ID for logging.

    Returns:
        A list of dictionaries with view metadata (schema, name).
    """
    svc, cfg = _get_service_with_config(connection_name)
    return svc.list_views(cfg, corr_id=corr_id)


def list_columns(
    connection_name: str, schema: str, object_name: str, corr_id: str | None = None
) -> list[dict[str, str]]:
    """List all columns for a specific table or view.

    Args:
        connection_name: The name of the connection.
        schema: The schema name.
        object_name: The object name.
        corr_id: Optional correlation ID for logging.

    Returns:
        A list of dictionaries with column metadata.
    """
    svc, cfg = _get_service_with_config(connection_name)
    return svc.list_columns(cfg, schema, object_name, corr_id=corr_id)


# =============================================================================
# High-Level Builders & Extended Metadata (Dialect-aware)
# =============================================================================


def get_db_name(connection_name: str, corr_id: str | None = None) -> str:
    """Return the database name for the connection using dialect-aware rules.

    MSSQL uses DB_NAME(); others return the configured database or connection name.

    Args:
        connection_name: The name of the connection.
        corr_id: Optional correlation ID for logging.

    Returns:
        The database name.
    """
    try:
        svc, cfg = _get_service_with_config(connection_name)
        return svc.get_db_name(cfg, corr_id=corr_id)
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
        # Fallback if initialization fails
        return connection_name


def build_select_star(
    connection_name: str, schema: str, object_name: str, *, top_n: int | None = None, corr_id: str | None = None
) -> str:
    """Build a SELECT * query with dialect quoting and optional TOP/LIMIT.

    Args:
        connection_name: The name of the connection.
        schema: The schema name.
        object_name: The object name.
        top_n: Optional number of rows to limit.
        corr_id: Optional correlation ID for logging.

    Returns:
        The generated SQL text.
    """
    try:
        svc, _ = _get_service_with_config(connection_name)
        return svc.build_select_star(schema, object_name, top_n=top_n, corr_id=corr_id)
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
        # Fallback quoting if service initialization fails
        return f"SELECT * FROM [{schema}].[{object_name}]"


def build_select_distinct(
    connection_name: str,
    schema: str,
    object_name: str,
    column_name: str,
    corr_id: str | None = None,
) -> str:
    """Build a SELECT DISTINCT query with dialect-aware quoting."""
    try:
        svc, _ = _get_service_with_config(connection_name)
        return svc.build_select_distinct(schema, object_name, column_name)
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
        # Fallback (MSSQL-style)
        return f"SELECT DISTINCT [{column_name}]\nFROM [{schema}].[{object_name}]"


def build_select_columns_auto(
    connection_name: str,
    schema: str,
    object_name: str,
    *,
    top_n: int | None = None,
    with_schema: bool = False,
    corr_id: str | None = None,
) -> str:
    """Auto-generate a SELECT statement listing all columns for the object.

    Falls back to SELECT * when metadata is unavailable.

    Args:
        connection_name: The name of the connection.
        schema: The schema name.
        object_name: The object name.
        top_n: Optional number of rows to limit.
        with_schema: Whether to prefix column names with the schema name.
        corr_id: Optional correlation ID for logging and tracing.

    Returns:
        The generated SQL text.
    """
    try:
        svc, cfg = _get_service_with_config(connection_name)
        return svc.build_select_columns_auto(
            conn=cfg,
            schema=schema,
            object_name=object_name,
            top_n=top_n,
            with_schema=with_schema,
            corr_id=corr_id,
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
        return build_select_star(connection_name, schema, object_name, top_n=top_n, corr_id=corr_id)


def list_all_columns_map(
    connection_name: str, corr_id: str | None = None
) -> dict[tuple[str, str], list[dict[str, str]]]:
    """Return a mapping of (schema, table) to lists of column metadata.

    If the dialect does not support whole-database listing, raises AttributeError,
    allowing callers to fall back to per-table batch loading.

    Args:
        connection_name: The name of the connection.
        corr_id: Optional correlation ID for logging and tracing.

    Returns:
        A mapping from (schema, table) tuples to lists of column metadata.

    Raises:
        AttributeError: If the dialect does not support bulk column listing.
    """
    svc, cfg = _get_service_with_config(connection_name)
    return svc.list_all_columns_map(cfg, corr_id=corr_id)
