"""Database core models for configuration and results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import pandas as pd

EngineKey = Literal["mssql", "postgresql", "mysql", "mariadb", "sqlite", "oracle"]
ProtocolKey = Literal["odbc", "psycopg2", "pymysql", "mysqlconnector", "pytds", "pymssql", "sqlite"]


@dataclass(frozen=True)
class TimeoutConfig:
    """Timeout settings in seconds.

    Attributes:
        login_timeout_s: The login timeout in seconds.
        query_timeout_s: The query timeout in seconds.
    """

    login_timeout_s: int | None = None
    query_timeout_s: int | None = None


@dataclass(frozen=True)
class ConnectionConfig:
    """Connection config abstracting over different protocols.

    Either odbc_connect string or driver-specific fields may be used.

    Attributes:
        name: The name of the connection.
        engine: The database engine key.
        protocol: The driver/protocol key.
        database: The database name.
        server: The server hostname or IP.
        port: The port number.
        user: The username.
        password: The password.
        odbc_connect: Full ODBC connection string.
        dsn: Data Source Name.
        extra: Additional driver-specific options.
    """

    name: str
    engine: EngineKey
    protocol: ProtocolKey
    database: str | None = None
    server: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    odbc_connect: str | None = None
    dsn: str | None = None
    extra: dict[str, object] | None = None


@dataclass
class SqlError:
    """Structured error returned to UI (English source strings).

    Attributes:
        category: Error category (e.g., 'syntax', 'timeout').
        code: Vendor-specific error code.
        message: English error message (key for i18n).
        hint: English hint (key for i18n).
    """

    category: (
        str  # 'syntax'|'missing_proc'|'missing_object'|'permission'|'timeout'|'connection'|'unsupported'|'unknown'
    )
    code: int | None  # vendor-specific error code (e.g., 2812)
    message: str  # English message for logging and i18n key
    hint: str | None = None  # English hint for logging and i18n key


@dataclass
class SqlResult:
    """Safe result shape for any SQL execution.

    Attributes:
        ok: Whether the execution was successful.
        cancelled: Whether execution was cancelled cooperatively.
        data: The query results as a DataFrame.
        error: The error details if execution failed.
        rows: The number of rows affected or returned.
        elapsed_s: Time taken for execution in seconds.
        sql_signature: A signature or hash of the SQL query.
    """

    ok: bool
    cancelled: bool = False
    data: pd.DataFrame | None = None
    error: SqlError | None = None
    rows: int = 0
    elapsed_s: float = 0.0
    sql_signature: str | None = None
