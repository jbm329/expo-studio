"""Database error classification and throttling utilities.

This module provides tools for mapping raw database exceptions from different
engines into a common `SqlError` model with English
user-facing messages (serving as keys for i18n). It also includes log
throttling to prevent flooding the application logs with repeated
identical errors.
"""

from __future__ import annotations

import re
import time

from PyQt6.QtCore import QT_TRANSLATE_NOOP

from .models import SqlError


class BulkColumnListingNotSupportedError(AttributeError):
    """Raised when a dialect cannot list all columns with a single query."""


_CODE_RE = re.compile(r"\((\d{3,6})(?:\)|,)")
_POSTGRES_SQLSTATE_RE = re.compile(
    r"(?:\bsqlstate[=:\s]*|\bpgcode[=:\s]*|[\[\(])([0-9A-Za-z]{5})(?:[\]\)]|\b)",
    re.IGNORECASE,
)
_ORACLE_CODE_RE = re.compile(r"\bORA-(\d{5})\b", re.IGNORECASE)
_last_err_ts: dict[str, float] = {}

MSSQL_MISSING_PROC = 2812
MSSQL_MISSING_OBJECT = 208
MSSQL_SYNTAX_ERROR = 102
MSSQL_INVALID_COLUMN = 207
MSSQL_UNKNOWN_IDENTIFIER = 4104
MSSQL_AMBIGUOUS_COLUMN = 209

MYSQL_SYNTAX_ERROR = 1064
MYSQL_MISSING_OBJECT = 1146
MYSQL_UNKNOWN_COLUMN = 1054
MYSQL_MISSING_PROC = 1305
MYSQL_ACCESS_DENIED = 1045
MYSQL_UNKNOWN_DATABASE = 1049
MYSQL_LOCK_WAIT_TIMEOUT = 1205
MYSQL_AMBIGUOUS_COLUMN = 1052

POSTGRES_AMBIGUOUS_COLUMN = 42702
POSTGRES_UNDEFINED_TABLE = "42P01"
POSTGRES_UNDEFINED_COLUMN = 42703
POSTGRES_SYNTAX_ERROR = 42601
POSTGRES_UNDEFINED_FUNCTION = 42883
POSTGRES_INVALID_PASSWORD = "28P01"  # noqa: S105 - standard PostgreSQL SQLSTATE code for invalid password
POSTGRES_INVALID_AUTH = 28000
POSTGRES_INVALID_CATALOG = "3D000"
POSTGRES_QUERY_CANCELED = 57014
ORACLE_AMBIGUOUS_COLUMN = 918

# --- i18n markers (pylupdate6-visible) -----------------------------
# MSSQL
TR_STORED_PROCEDURE_NOT_EXISTS_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "The stored procedure does not exist.")
TR_STORED_PROCEDURE_NOT_EXISTS_HINT_MSSQL = QT_TRANSLATE_NOOP(
    "DbErrors", "Check name and schema (ex: EXEC dbo.MyProc ...)."
)
TR_TABLE_OR_VIEW_NOT_EXISTS_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "The table or view does not exist.")
TR_TABLE_OR_VIEW_NOT_EXISTS_HINT_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "Check name and schema (ex: dbo.MyTable).")

TR_SQL_SYNTAX_ERROR_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "SQL syntax error.")
TR_SQL_SYNTAX_ERROR_HINT_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "Check keywords, commas and parentheses.")
TR_PERMISSION_DENIED_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "Permission denied.")
TR_PERMISSION_DENIED_HINT_MSSQL = QT_TRANSLATE_NOOP(
    "DbErrors", "Check SELECT/EXEC permissions or use another connection."
)
TR_TIMEOUT_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "Timeout exceeded.")
TR_TIMEOUT_HINT_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "Try reducing the result set (TOP) or adding filters.")
TR_CONNECTION_FAILED_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "Connection failed.")
TR_CONNECTION_FAILED_HINT_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "Check network, host/port and firewall settings.")
TR_UNKNOWN_COLUMN_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "Unknown column.")
TR_UNKNOWN_COLUMN_HINT_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "Check spelling/alias or qualify the column.")
TR_UNKNOWN_IDENTIFIER_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "Unknown SQL identifier/alias.")
TR_UNKNOWN_IDENTIFIER_HINT_MSSQL = QT_TRANSLATE_NOOP(
    "DbErrors", "Check table/column alias and qualification (schema.table.column)."
)

TR_UNKNOWN_FAILURE_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "Unknown database failure.")
TR_UNKNOWN_FAILURE_HINT_MSSQL = QT_TRANSLATE_NOOP("DbErrors", "Show details in log (DEBUG) or try again.")

# MySQL
TR_DRIVER_MISSING_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Required database driver module is missing.")
TR_DRIVER_MISSING_HINT_MYSQL = QT_TRANSLATE_NOOP(
    "DbErrors", "Install 'pymysql' or 'mysql-connector-python' or check your Python environment."
)
TR_SQL_SYNTAX_ERROR_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "SQL syntax error.")
TR_SQL_SYNTAX_ERROR_HINT_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Check keywords, commas and parentheses.")
TR_TABLE_OR_VIEW_NOT_EXISTS_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "The table or view does not exist.")
TR_TABLE_OR_VIEW_NOT_EXISTS_HINT_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Check database and object name.")
TR_UNKNOWN_COLUMN_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Unknown column.")
TR_UNKNOWN_COLUMN_HINT_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Check spelling/alias or qualify the column.")
TR_STORED_PROCEDURE_NOT_EXISTS_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "The stored procedure does not exist.")
TR_STORED_PROCEDURE_NOT_EXISTS_HINT_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Check name and schema (database).")
TR_PERMISSION_DENIED_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Permission denied.")
TR_PERMISSION_DENIED_HINT_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Check user/password and permissions.")
TR_UNKNOWN_DATABASE_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Unknown database.")
TR_UNKNOWN_DATABASE_HINT_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Check connection 'database' and permissions.")
TR_CONNECTION_FAILED_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Connection failed.")
TR_CONNECTION_FAILED_HINT_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Check network, host/port and firewall settings.")
TR_LOCK_WAIT_TIMEOUT_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Locked table - timeout exceeded.")
TR_LOCK_WAIT_TIMEOUT_HINT_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Try reducing locks or splitting transactions.")
TR_UNKNOWN_DATABASE_FAIL_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Unknown database failure.")
TR_UNKNOWN_DATABASE_FAIL_HINT_MYSQL = QT_TRANSLATE_NOOP("DbErrors", "Show details in log (DEBUG) or try again.")

# SQLite
TR_SQL_SYNTAX_ERROR_SQLITE = QT_TRANSLATE_NOOP("DbErrors", "SQL syntax error.")
TR_SQL_SYNTAX_ERROR_HINT_SQLITE = QT_TRANSLATE_NOOP("DbErrors", "Check keywords, commas and parentheses.")
TR_TABLE_OR_VIEW_NOT_EXISTS_SQLITE = QT_TRANSLATE_NOOP("DbErrors", "The table or view does not exist.")
TR_TABLE_OR_VIEW_NOT_EXISTS_HINT_SQLITE = QT_TRANSLATE_NOOP("DbErrors", "Check file/database and table name.")
TR_UNKNOWN_COLUMN_SQLITE = QT_TRANSLATE_NOOP("DbErrors", "Unknown column.")
TR_UNKNOWN_COLUMN_HINT_SQLITE = QT_TRANSLATE_NOOP("DbErrors", "Check spelling/alias or qualify the column.")
TR_LOCK_WAIT_TIMEOUT_SQLITE = QT_TRANSLATE_NOOP("DbErrors", "Database is locked.")
TR_LOCK_WAIT_TIMEOUT_HINT_SQLITE = QT_TRANSLATE_NOOP("DbErrors", "Try again later or close other database processes.")
TR_UNKNOWN_DATABASE_SQLITE = QT_TRANSLATE_NOOP("DbErrors", "Could not open database file.")
TR_UNKNOWN_DATABASE_HINT_SQLITE = QT_TRANSLATE_NOOP("DbErrors", "Check database file path and permissions.")
TR_UNKNOWN_FAILURE_SQLITE = QT_TRANSLATE_NOOP("DbErrors", "Unknown database failure.")
TR_UNKNOWN_FAILURE_HINT_SQLITE = QT_TRANSLATE_NOOP("DbErrors", "Show details in log (DEBUG) or try again.")

# DuckDB
TR_INVALID_CONFIG_DUCKDB = QT_TRANSLATE_NOOP("DbErrors", "Invalid DuckDB connection configuration.")
TR_INVALID_CONFIG_HINT_DUCKDB = QT_TRANSLATE_NOOP(
    "DbErrors", "Select an existing local DuckDB file. Only read-only connections without extra options are supported."
)
TR_LOCKED_HINT_DUCKDB = QT_TRANSLATE_NOOP(
    "DbErrors", "Close other applications using this DuckDB file in read/write mode and try again."
)
TR_PERMISSION_HINT_DUCKDB = QT_TRANSLATE_NOOP("DbErrors", "Check file permissions. DuckDB connections are read-only.")
TR_DRIVER_MISSING_HINT_DUCKDB = QT_TRANSLATE_NOOP(
    "DbErrors", "Install 'duckdb' and 'duckdb-engine' or check your Python environment."
)

# PostgreSQL
TR_DRIVER_MISSING_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Required database driver module is missing.")
TR_DRIVER_MISSING_HINT_POSTGRES = QT_TRANSLATE_NOOP(
    "DbErrors", "Install 'psycopg' (or 'psycopg[binary]') or check your Python environment."
)
TR_SQL_SYNTAX_ERROR_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "SQL syntax error.")
TR_SQL_SYNTAX_ERROR_HINT_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Check keywords, commas and parentheses.")
TR_TABLE_OR_VIEW_NOT_EXISTS_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "The table or view does not exist.")
TR_TABLE_OR_VIEW_NOT_EXISTS_HINT_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Check schema and table name.")
TR_UNKNOWN_COLUMN_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Unknown column.")
TR_UNKNOWN_COLUMN_HINT_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Check spelling/alias or qualify the column.")
TR_FUNCTION_NOT_EXISTS_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "The function does not exist.")
TR_FUNCTION_NOT_EXISTS_HINT_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Check function name and parameter types.")
TR_PERMISSION_DENIED_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Permission denied.")
TR_PERMISSION_DENIED_HINT_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Check user/password and permissions.")
TR_UNKNOWN_DATABASE_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Unknown database.")
TR_UNKNOWN_DATABASE_HINT_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Check connection 'database' and permissions.")
TR_TIMEOUT_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Timeout exceeded.")
TR_TIMEOUT_HINT_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Try reducing the result set (LIMIT) or adding filters.")
TR_CONNECTION_FAILED_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Connection failed.")
TR_CONNECTION_FAILED_HINT_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Check network, host/port and firewall settings.")
TR_UNKNOWN_DATABASE_FAIL_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Unknown database failure.")
TR_UNKNOWN_DATABASE_FAIL_HINT_POSTGRES = QT_TRANSLATE_NOOP("DbErrors", "Show details in log (DEBUG) or try again.")

# Generic / Internal
TR_SQL_EMPTY = QT_TRANSLATE_NOOP("DbErrors", "SQL statement is empty.")
TR_SQL_EMPTY_HINT = QT_TRANSLATE_NOOP("DbErrors", "Write a SELECT or EXEC.")
TR_ONLY_SELECT_WITH_EXEC = QT_TRANSLATE_NOOP("DbErrors", "Only SELECT, WITH (CTE) and EXEC are supported here.")
TR_ONLY_SELECT_WITH_EXEC_HINT = QT_TRANSLATE_NOOP("DbErrors", "Start with SELECT/WITH or run procedure with EXEC.")
TR_EXEC_DISABLED = QT_TRANSLATE_NOOP("DbErrors", "EXEC is disabled in this mode.")
TR_EXEC_DISABLED_HINT = QT_TRANSLATE_NOOP("DbErrors", "Enable EXEC in settings or run a SELECT.")
TR_UNKNOWN_DATABASE_FAIL = QT_TRANSLATE_NOOP("DbErrors", "Unknown database failure.")
TR_UNKNOWN_DATABASE_FAIL_HINT = QT_TRANSLATE_NOOP("DbErrors", "Show details in log (DEBUG) or try again.")
TR_COULD_NOT_INIT_CONN = QT_TRANSLATE_NOOP("DbErrors", "Could not initialize connection.")
TR_AMBIGUOUS_COLUMN = QT_TRANSLATE_NOOP("DbErrors", "Ambiguous column reference.")
TR_AMBIGUOUS_COLUMN_HINT = QT_TRANSLATE_NOOP("DbErrors", "Qualify the column with its table name or alias.")

# Schema Cache / Autocomplete
TR_PREPARING_AUTOCOMPLETE_BULK = QT_TRANSLATE_NOOP("DbErrors", "Preparing autocomplete (bulk)…")
TR_BULK_FAILED_TRYING_BATCH = QT_TRANSLATE_NOOP("DbErrors", "Could not read schema in bulk - trying batch.")
TR_AUTOCOMPLETE_READY_BULK = QT_TRANSLATE_NOOP("DbErrors", "Autocomplete for columns ready ({count} objects via bulk).")
TR_AUTOCOMPLETE_READY = QT_TRANSLATE_NOOP("DbErrors", "Autocomplete for columns ready.")
TR_PREPARING_AUTOCOMPLETE_BATCH = QT_TRANSLATE_NOOP("DbErrors", "Preparing autocomplete… {done}/{total}")
TR_LOADING_SCHEMA = QT_TRANSLATE_NOOP("DbErrors", "Loading schema…")
TR_SCHEMA_READY = QT_TRANSLATE_NOOP("DbErrors", "Schema ready.")


def should_log(signature: str, window_s: float = 5.0) -> bool:
    """Throttle repeated error logs per SQL signature.

    Args:
        signature: A unique identifier for the error (e.g., the SQL query).
        window_s: The time window in seconds during which repeats are suppressed.

    Returns:
        True if the error should be logged (window has passed), False otherwise.
    """
    t0 = _last_err_ts.get(signature, 0.0)
    t1 = time.time()
    if t1 - t0 >= window_s:
        _last_err_ts[signature] = t1
        return True
    return False


def extract_code(msg: str) -> int | None:
    """Extract a numeric error code from a database error message.

    The code is expected at the start of parenthesized driver details, such as
    ``(208)`` or ``(1052, ...)``.

    Args:
        msg: The raw error message string.

    Returns:
        The extracted integer error code, or None if no code was found.
    """
    m = _CODE_RE.search(msg or "")
    if m:
        try:
            return int(m.group(1))
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
            return None
    return None


def _ambiguous_column_error(code: int | None) -> SqlError:
    """Build the common error shown for ambiguous column references."""
    return SqlError(
        "ambiguous_column",
        code,
        TR_AMBIGUOUS_COLUMN,
        TR_AMBIGUOUS_COLUMN_HINT,
    )


def _postgres_sqlstate(exc: Exception, raw: str) -> str | None:
    """Extract a PostgreSQL SQLSTATE string from driver or wrapped exceptions."""
    current: object | None = exc
    seen: set[int] = set()

    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for attribute in ("sqlstate", "pgcode"):
            value = getattr(current, attribute, None)
            if value is not None and str(value).strip():
                return str(value).strip().upper()
        current = getattr(current, "orig", None)

    match = _POSTGRES_SQLSTATE_RE.search(raw)
    return match.group(1).upper() if match is not None else None


def _postgres_error_code(exc: Exception, raw: str) -> int | None:
    """Extract a numeric PostgreSQL error code if the SQLSTATE is digits."""
    sqlstate = _postgres_sqlstate(exc, raw)
    if sqlstate is not None and sqlstate.isdigit():
        return int(sqlstate)
    return extract_code(raw)


def classify_mssql(exc: Exception) -> SqlError:
    """Map common SQL Server errors to categorized messages.

    Extends with more codes as needed (e.g., 207 invalid column, 8114 conversion).

    Args:
        exc: The original exception from the database driver.

    Returns:
        A `SqlError` object containing the classification and English messages.
    """
    raw = str(exc) or ""
    lo = raw.lower()
    code = extract_code(raw)

    if "ambiguous column name" in lo or code == MSSQL_AMBIGUOUS_COLUMN:
        return _ambiguous_column_error(code or MSSQL_AMBIGUOUS_COLUMN)

    if "could not find stored procedure" in lo or code == MSSQL_MISSING_PROC:
        return SqlError(
            "missing_proc",
            code or MSSQL_MISSING_PROC,
            TR_STORED_PROCEDURE_NOT_EXISTS_MSSQL,
            TR_STORED_PROCEDURE_NOT_EXISTS_HINT_MSSQL,
        )
    if "invalid object name" in lo or code == MSSQL_MISSING_OBJECT:
        return SqlError(
            "missing_object",
            code or MSSQL_MISSING_OBJECT,
            TR_TABLE_OR_VIEW_NOT_EXISTS_MSSQL,
            TR_TABLE_OR_VIEW_NOT_EXISTS_HINT_MSSQL,
        )
    if "incorrect syntax near" in lo or code == MSSQL_SYNTAX_ERROR:
        return SqlError("syntax", code or MSSQL_SYNTAX_ERROR, TR_SQL_SYNTAX_ERROR_MSSQL, TR_SQL_SYNTAX_ERROR_HINT_MSSQL)
    if any(x in lo for x in ("permission", "is denied")) or code in (229, 262):
        return SqlError("permission", code or 229, TR_PERMISSION_DENIED_MSSQL, TR_PERMISSION_DENIED_HINT_MSSQL)
    if "timeout" in lo:
        return SqlError("timeout", code, TR_TIMEOUT_MSSQL, TR_TIMEOUT_HINT_MSSQL)
    if any(
        x in lo for x in ("login failed", "transport-level", "server is not found", "could not open a connection")
    ) or code in (18456, 4060, 53, 17, 11001):
        return SqlError("connection", code, TR_CONNECTION_FAILED_MSSQL, TR_CONNECTION_FAILED_HINT_MSSQL)
    if "invalid column name" in lo or code == MSSQL_INVALID_COLUMN:
        return SqlError("syntax", code or MSSQL_INVALID_COLUMN, TR_UNKNOWN_COLUMN_MSSQL, TR_UNKNOWN_COLUMN_HINT_MSSQL)

    if "multi-part identifier" in lo or code == MSSQL_UNKNOWN_IDENTIFIER:
        return SqlError(
            "syntax", code or MSSQL_UNKNOWN_IDENTIFIER, TR_UNKNOWN_IDENTIFIER_MSSQL, TR_UNKNOWN_IDENTIFIER_HINT_MSSQL
        )

    return SqlError("unknown", code, TR_UNKNOWN_FAILURE_MSSQL, TR_UNKNOWN_FAILURE_HINT_MSSQL)


def classify_mysql(exc: Exception) -> SqlError:
    """Map common MySQL/MariaDB errors to English messages.

    Typical codes mapped:
        1064: Parse error
        1146: Table doesn't exist
        1054: Unknown column
        1305: PROCEDURE ... does not exist
        1045: Access denied
        1049: Unknown database
        1205: Lock wait timeout exceeded

    Args:
        exc: The original exception from the database driver.

    Returns:
        A `SqlError` object containing the classification and English messages.
    """
    raw = str(exc) or ""
    lo = raw.lower()
    code = extract_code(raw)

    if ("column" in lo and "ambiguous" in lo) or code == MYSQL_AMBIGUOUS_COLUMN:
        return _ambiguous_column_error(code or MYSQL_AMBIGUOUS_COLUMN)

    # Missing driver
    if (isinstance(exc, (ModuleNotFoundError, ImportError)) or "no module named" in lo or "cannot import" in lo) and (
        "mysql" in lo or "pymysql" in lo
    ):
        return SqlError(
            "driver_missing",
            None,
            TR_DRIVER_MISSING_MYSQL,
            TR_DRIVER_MISSING_HINT_MYSQL,
        )

    # Parse error / syntax
    if "you have an error in your sql syntax" in lo or code == MYSQL_SYNTAX_ERROR:
        return SqlError("syntax", code or MYSQL_SYNTAX_ERROR, TR_SQL_SYNTAX_ERROR_MYSQL, TR_SQL_SYNTAX_ERROR_HINT_MYSQL)

    # Missing table/view
    if "doesn't exist" in lo and ("table" in lo or code == MYSQL_MISSING_OBJECT):
        return SqlError(
            "missing_object",
            code or MYSQL_MISSING_OBJECT,
            TR_TABLE_OR_VIEW_NOT_EXISTS_MYSQL,
            TR_TABLE_OR_VIEW_NOT_EXISTS_HINT_MYSQL,
        )

    # Unknown column
    if "unknown column" in lo or code == MYSQL_UNKNOWN_COLUMN:
        return SqlError("syntax", code or MYSQL_UNKNOWN_COLUMN, TR_UNKNOWN_COLUMN_MYSQL, TR_UNKNOWN_COLUMN_HINT_MYSQL)

    # Missing procedure
    if ("procedure" in lo and "does not exist" in lo) or code == MYSQL_MISSING_PROC:
        return SqlError(
            "missing_proc",
            code or MYSQL_MISSING_PROC,
            TR_STORED_PROCEDURE_NOT_EXISTS_MYSQL,
            TR_STORED_PROCEDURE_NOT_EXISTS_HINT_MYSQL,
        )

    # Access denied
    if "access denied" in lo or code == MYSQL_ACCESS_DENIED:
        return SqlError(
            "permission",
            code or MYSQL_ACCESS_DENIED,
            TR_PERMISSION_DENIED_MSSQL,
            TR_PERMISSION_DENIED_HINT_MSSQL,
        )

    # Unknown database
    if "unknown database" in lo or code == MYSQL_UNKNOWN_DATABASE:
        return SqlError(
            "connection",
            code or MYSQL_UNKNOWN_DATABASE,
            TR_UNKNOWN_DATABASE_MYSQL,
            TR_UNKNOWN_DATABASE_HINT_MYSQL,
        )

    # Lock wait timeout
    if "lock wait timeout" in lo or code == MYSQL_LOCK_WAIT_TIMEOUT:
        return SqlError(
            "timeout",
            code or MYSQL_LOCK_WAIT_TIMEOUT,
            TR_LOCK_WAIT_TIMEOUT_MYSQL,
            TR_LOCK_WAIT_TIMEOUT_HINT_MYSQL,
        )

    # Connection errors (generic)
    if "can't connect to" in lo or "connection refused" in lo:
        return SqlError("connection", code, TR_CONNECTION_FAILED_MYSQL, TR_CONNECTION_FAILED_HINT_MYSQL)

    return SqlError("unknown", code, TR_UNKNOWN_DATABASE_FAIL_MYSQL, TR_UNKNOWN_DATABASE_FAIL_HINT_MYSQL)


def classify_sqlite(exc: Exception) -> SqlError:
    """Map common SQLite errors to English messages.

    Typical messages handled:
        - 'no such table: ...'
        - 'no such column: ...'
        - 'near "...": syntax error'
        - 'database is locked'

    Args:
        exc: The original exception from the database driver.

    Returns:
        A `SqlError` object containing the classification and English messages.
    """
    raw = str(exc) or ""
    lo = raw.lower()

    if "ambiguous column name" in lo:
        return _ambiguous_column_error(None)

    if "near" in lo and "syntax error" in lo:
        return SqlError("syntax", None, TR_SQL_SYNTAX_ERROR_SQLITE, TR_SQL_SYNTAX_ERROR_HINT_SQLITE)

    if "no such table" in lo:
        return SqlError(
            "missing_object", None, TR_TABLE_OR_VIEW_NOT_EXISTS_SQLITE, TR_TABLE_OR_VIEW_NOT_EXISTS_HINT_SQLITE
        )

    if "no such column" in lo:
        return SqlError("syntax", None, TR_UNKNOWN_COLUMN_SQLITE, TR_UNKNOWN_COLUMN_HINT_SQLITE)

    if "database is locked" in lo or "database locked" in lo:
        return SqlError("timeout", None, TR_LOCK_WAIT_TIMEOUT_SQLITE, TR_LOCK_WAIT_TIMEOUT_HINT_SQLITE)

    if "unable to open database file" in lo:
        return SqlError("connection", None, TR_UNKNOWN_DATABASE_SQLITE, TR_UNKNOWN_DATABASE_HINT_SQLITE)

    return SqlError("unknown", None, TR_UNKNOWN_FAILURE_SQLITE, TR_UNKNOWN_FAILURE_HINT_SQLITE)


def classify_duckdb(exc: Exception) -> SqlError:
    """Map DuckDB and SQLAlchemy-wrapped failures to translated messages.

    Lock detection covers Linux lock conflicts and DuckDB's Windows
    file-sharing marker independently of the localized OS error text.

    Args:
        exc: A configuration, native driver or SQLAlchemy-wrapped exception.

    Returns:
        A categorized error using the existing DbErrors translation context.
    """
    original = getattr(exc, "orig", exc)
    message = str(original).lower()
    error_type = type(original).__name__

    if isinstance(original, ImportError) or (
        ("no module named" in message or "can't load plugin" in message) and "duckdb" in message
    ):
        return SqlError("driver_missing", None, TR_DRIVER_MISSING_MYSQL, TR_DRIVER_MISSING_HINT_DUCKDB)
    if isinstance(original, ValueError):
        return SqlError("connection", None, TR_INVALID_CONFIG_DUCKDB, TR_INVALID_CONFIG_HINT_DUCKDB)
    if "file is already open in" in message or (
        "lock" in message and ("could not set" in message or "conflicting" in message or "locked" in message)
    ):
        return SqlError("connection", None, TR_LOCK_WAIT_TIMEOUT_SQLITE, TR_LOCKED_HINT_DUCKDB)
    if (
        isinstance(original, PermissionError)
        or error_type == "PermissionException"
        or any(text in message for text in ("permission denied", "read-only", "read only", "access denied"))
    ):
        return SqlError("permission", None, TR_PERMISSION_DENIED_MSSQL, TR_PERMISSION_HINT_DUCKDB)
    if isinstance(original, OSError) or error_type in ("IOException", "ConnectionException"):
        return SqlError("connection", None, TR_UNKNOWN_DATABASE_SQLITE, TR_UNKNOWN_DATABASE_HINT_SQLITE)
    if error_type == "BinderException" and "ambiguous" in message and "column" in message:
        return _ambiguous_column_error(None)
    if error_type == "CatalogException":
        if "function" in message and "does not exist" in message:
            return SqlError("missing_proc", None, TR_FUNCTION_NOT_EXISTS_POSTGRES, TR_FUNCTION_NOT_EXISTS_HINT_POSTGRES)
        if any(text in message for text in ("table with name", "view with name", "schema with name")):
            return SqlError(
                "missing_object", None, TR_TABLE_OR_VIEW_NOT_EXISTS_SQLITE, TR_TABLE_OR_VIEW_NOT_EXISTS_HINT_SQLITE
            )
    if (
        error_type == "BinderException"
        and "column" in message
        and ("not found" in message or "does not have" in message)
    ):
        return SqlError("syntax", None, TR_UNKNOWN_COLUMN_SQLITE, TR_UNKNOWN_COLUMN_HINT_SQLITE)
    if error_type in ("ParserException", "BinderException"):
        return SqlError("syntax", None, TR_SQL_SYNTAX_ERROR_SQLITE, TR_SQL_SYNTAX_ERROR_HINT_SQLITE)
    return SqlError("unknown", None, TR_UNKNOWN_DATABASE_FAIL, TR_UNKNOWN_DATABASE_FAIL_HINT)


def classify_postgresql(exc: Exception) -> SqlError:
    """Map common PostgreSQL errors to categorized messages.

    Args:
        exc: The original exception from the database driver.

    Returns:
        A `SqlError` object containing the classification and English messages.
    """
    raw = str(exc) or ""
    lo = raw.lower()
    sqlstate = _postgres_sqlstate(exc, raw)
    code = _postgres_error_code(exc, raw)

    # Missing driver
    if (
        isinstance(exc, (ModuleNotFoundError, ImportError)) or "no module named" in lo or "cannot import" in lo
    ) and "psycopg" in lo:
        return SqlError(
            "driver_missing",
            None,
            TR_DRIVER_MISSING_POSTGRES,
            TR_DRIVER_MISSING_HINT_POSTGRES,
        )

    # Ambiguous column (42702)
    if sqlstate == "42702" or ("column reference" in lo and "ambiguous" in lo) or code == POSTGRES_AMBIGUOUS_COLUMN:
        return _ambiguous_column_error(code or POSTGRES_AMBIGUOUS_COLUMN)

    # Missing table / view / relation (42P01)
    if (
        sqlstate == "42P01"
        or ("relation" in lo and "does not exist" in lo)
        or ("table" in lo and "does not exist" in lo)
    ):
        return SqlError(
            "missing_object",
            code,
            TR_TABLE_OR_VIEW_NOT_EXISTS_POSTGRES,
            TR_TABLE_OR_VIEW_NOT_EXISTS_HINT_POSTGRES,
        )

    # Missing column (42703)
    if sqlstate == "42703" or ("column" in lo and "does not exist" in lo):
        return SqlError(
            "syntax",
            code or 42703,
            TR_UNKNOWN_COLUMN_POSTGRES,
            TR_UNKNOWN_COLUMN_HINT_POSTGRES,
        )

    # Missing function / procedure (42883)
    if sqlstate == "42883" or ("function" in lo and "does not exist" in lo):
        return SqlError(
            "missing_proc",
            code or 42883,
            TR_FUNCTION_NOT_EXISTS_POSTGRES,
            TR_FUNCTION_NOT_EXISTS_HINT_POSTGRES,
        )

    # Syntax error (42601)
    if sqlstate == "42601" or "syntax error" in lo:
        return SqlError(
            "syntax",
            code or 42601,
            TR_SQL_SYNTAX_ERROR_POSTGRES,
            TR_SQL_SYNTAX_ERROR_HINT_POSTGRES,
        )

    # Permission / authentication failed (28P01, 28000, 42501)
    if (
        sqlstate in ("28P01", "28000", "42501")
        or "password authentication failed" in lo
        or "permission denied" in lo
        or "access denied" in lo
    ):
        return SqlError(
            "permission",
            code or (28000 if sqlstate == "28000" else None),
            TR_PERMISSION_DENIED_POSTGRES,
            TR_PERMISSION_DENIED_HINT_POSTGRES,
        )

    # Unknown / missing database (3D000)
    if sqlstate == "3D000" or ("database" in lo and "does not exist" in lo):
        return SqlError(
            "connection",
            code,
            TR_UNKNOWN_DATABASE_POSTGRES,
            TR_UNKNOWN_DATABASE_HINT_POSTGRES,
        )

    # Query timeout / cancelled (57014)
    if (
        sqlstate == "57014"
        or "statement timeout" in lo
        or "canceling statement" in lo
        or "cancelling statement" in lo
        or "query_canceled" in lo
        or "query cancelled" in lo
    ):
        return SqlError(
            "timeout",
            code or 57014,
            TR_TIMEOUT_POSTGRES,
            TR_TIMEOUT_HINT_POSTGRES,
        )

    # Connection failure (08xxx)
    if (
        (sqlstate and sqlstate.startswith("08"))
        or "could not connect" in lo
        or "connection refused" in lo
        or "connection to server" in lo
        or "could not translate host name" in lo
    ):
        return SqlError(
            "connection",
            code,
            TR_CONNECTION_FAILED_POSTGRES,
            TR_CONNECTION_FAILED_HINT_POSTGRES,
        )

    return SqlError("unknown", code, TR_UNKNOWN_DATABASE_FAIL_POSTGRES, TR_UNKNOWN_DATABASE_FAIL_HINT_POSTGRES)


def classify_oracle(exc: Exception) -> SqlError:
    """Map Oracle ambiguous-column errors to the common error model."""
    raw = str(exc) or ""
    match = _ORACLE_CODE_RE.search(raw)
    code = int(match.group(1)) if match is not None else extract_code(raw)
    if "column ambiguously defined" in raw.lower() or code == ORACLE_AMBIGUOUS_COLUMN:
        return _ambiguous_column_error(code or ORACLE_AMBIGUOUS_COLUMN)
    return SqlError("unknown", code, TR_UNKNOWN_DATABASE_FAIL, TR_UNKNOWN_DATABASE_FAIL_HINT)
