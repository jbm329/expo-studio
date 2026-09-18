"""High-level execution and metadata service for database operations.

This class is the core execution engine beneath the public facade
(expo_jbm329.db.base). It provides:

    * Safe SQL execution (never raises into UI)
    * Dialect-aware LIMIT/TOP injection
    * Vendor-specific error classification into Swedish UI messages
    * Structured SqlResult return types
    * Table/view/column metadata listing
    * High-level SELECT builders
    * Bulk column listing where supported by the dialect

DbService does NOT manage:
    * Connection string construction
    * Driver/dialect selection
    * Service lifecycle

These concerns are handled by db.base and the dependency injection registry.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import time
from typing import TYPE_CHECKING

import pandas as pd

from expo_jbm329.db.core.errors import (
    TR_EXEC_DISABLED,
    TR_EXEC_DISABLED_HINT,
    TR_ONLY_SELECT_WITH_EXEC,
    TR_ONLY_SELECT_WITH_EXEC_HINT,
    TR_SQL_EMPTY,
    TR_SQL_EMPTY_HINT,
    TR_UNKNOWN_DATABASE_FAIL,
    TR_UNKNOWN_DATABASE_FAIL_HINT,
    should_log,
)
from expo_jbm329.db.core.models import (
    ConnectionConfig,
    SqlError,
    SqlResult,
    TimeoutConfig,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.db.core.interfaces import DialectProtocol, DriverProtocol

log = logging.getLogger("applogger.db")


# =============================================================================
# Internal helpers
# =============================================================================

def _sig(sql: str) -> str:
    """Return a short deterministic signature for the SQL text (used for throttling)."""
    return hashlib.blake2s(sql.encode("utf-8"), digest_size=6).hexdigest()


def _detect_sql_kind(sql: str) -> str:
    """Roughly classify the SQL statement type.

    Args:
        sql: The SQL query string.

    Returns:
        One of 'select', 'with', 'exec', or 'other'.
    """
    s = (sql or "").lstrip().lower()
    if s.startswith("select"):
        return "select"
    if s.startswith("with"):
        return "with"
    if s.startswith("exec") or s.startswith("execute"):
        return "exec"
    return "other"


# =============================================================================
# DbService - core execution component
# =============================================================================

class DbService:
    """Main SQL execution service.

    Responsibilities:
        * Execute SQL safely using injected driver.
        * Inject TOP/LIMIT clauses via dialect.
        * Produce SqlResult with DataFrame and metadata.
        * Never raise into UI components.
        * Classify vendor errors into Swedish SqlError.
        * Provide metadata (tables/views/columns).
        * Provide high-level SELECT builders.
        * Provide bulk column listing (dialect-dependent).

    DbService instances are created and cached by db.base.
    """

    # -------------------------------------------------------------------------
    # Construction
    # -------------------------------------------------------------------------

    def __init__(
            self,
            driver: DriverProtocol,
            dialect: DialectProtocol,
            timeouts: TimeoutConfig | None = None,
            allow_exec: bool = True,
    ) -> None:
        """Initialize the DbService.

        Args:
            driver: The database driver implementation.
            dialect: The SQL dialect implementation.
            timeouts: Optional timeout configuration.
            allow_exec: Whether to allow EXEC statements. Defaults to True.
        """
        self.driver = driver
        self.dialect = dialect
        self.allow_exec = allow_exec
        self.timeouts = timeouts or TimeoutConfig()

        # Apply timeouts in driver
        self.driver.initialize(timeouts={"login_timeout_s": self.timeouts.login_timeout_s})
        self.driver.set_query_timeout(self.timeouts.query_timeout_s)

    # -------------------------------------------------------------------------
    # Core SQL execution
    # -------------------------------------------------------------------------

    def execute_sql(
        self,
        conn: ConnectionConfig,
        sql: str,
        *,
        top_n: int | None = None,
        corr_id: str | None = None,
        cancel_cb: Callable[[], bool] | None = None,
        job_id: str | None = None,
    ) -> SqlResult:
        """Execute SQL safely and return a SqlResult.

        Steps:
            1. Validate SQL category (support SELECT/WITH/EXEC only).
            2. Inject TOP/LIMIT via dialect (if applicable).
            3. Execute using driver.
            4. Measure execution time.
            5. Package output in SqlResult.
            6. Classify errors on failure.
            7. Throttle log noise per SQL signature.

        Args:
            conn: The connection configuration to use.
            sql: The SQL query string to execute.
            top_n: Optional number of rows to limit the result to.
            corr_id: Optional correlation ID for logging and tracking.
            cancel_cb: Optional cooperative cancellation callback.
            job_id: Optional execution/job identifier used for driver-level cancellation.

        Returns:
            A SqlResult object containing the results or error information.
        """

        def _is_cancelled() -> bool:
            """Return True if cooperative cancellation was requested."""
            if cancel_cb is None:
                return False
            try:
                return bool(cancel_cb())
            except Exception:
                log.debug("DbService: cancel callback failed.", exc_info=True)
                return False

        # ---- Early cancellation ----
        if _is_cancelled():
            return SqlResult(
                ok=False,
                cancelled=True,
            )

        # ---- Validation ----
        if not isinstance(sql, str) or not sql.strip():
            return SqlResult(
                ok=False,
                cancelled=False,
                error=SqlError("syntax", None, TR_SQL_EMPTY, TR_SQL_EMPTY_HINT),
            )

        kind = _detect_sql_kind(sql)
        if kind not in ("select", "with", "exec"):
            return SqlResult(
                ok=False,
                cancelled=False,
                error=SqlError(
                    "unsupported",
                    None,
                    TR_ONLY_SELECT_WITH_EXEC,
                    TR_ONLY_SELECT_WITH_EXEC_HINT,
                ),
            )

        if kind == "exec" and not self.allow_exec:
            return SqlResult(
                ok=False,
                cancelled=False,
                error=SqlError(
                    "unsupported",
                    None,
                    TR_EXEC_DISABLED,
                    TR_EXEC_DISABLED_HINT,
                ),
            )

        # ---- TOP/LIMIT injection ----
        signature = _sig(sql)
        effective_sql = sql
        limit_injected = False

        if isinstance(top_n, int) and top_n > 0:
            try:
                limited = self.dialect.apply_limit(sql, top_n)
                if isinstance(limited, str) and limited.strip() != sql.strip():
                    effective_sql = limited
                    limit_injected = True
                    log.debug("DbService: applied server-side limit n=%s", top_n)
            except Exception as e:
                log.debug("DbService: limit injection failed: %s", e)

        # ---- Cancellation before execution ----
        if _is_cancelled():
            return SqlResult(
                ok=False,
                cancelled=True,
                sql_signature=signature,
            )

        # ---- Execution ----
        start = time.time()
        try:
            log.info(
                "DbService: executing SQL (conn='%s', engine=%s, signature=%s, corr=%s)",
                conn.name,
                self.dialect.name,
                signature,
                corr_id,
            )
            log.debug("SQL:\n%s", effective_sql)

            df = self.driver.execute_df(
                conn,
                effective_sql,
                job_id=job_id,
                cancel_cb=cancel_cb,
                corr_id=corr_id,
            )
            elapsed = time.time() - start

            # If cancellation was requested while the driver was executing, do not
            # treat the returned dataframe as a successful result.
            if _is_cancelled():
                log.info(
                    "DbService: SQL cancelled after execution returned "
                    "(signature=%s, corr=%s, elapsed=%.3fs, job_id=%s)",
                    signature,
                    corr_id,
                    elapsed,
                    job_id,
                )
                return SqlResult(
                    ok=False,
                    cancelled=True,
                    elapsed_s=elapsed,
                    sql_signature=signature,
                )

            row_count = int(df.shape[0]) if isinstance(df, pd.DataFrame) else 0
            log.info(
                "DbService: SQL completed (signature=%s, corr=%s) in %.3fs - %s rows",
                signature,
                corr_id,
                elapsed,
                row_count,
            )

            # Fallback: client-side limiting
            if not limit_injected and isinstance(df, pd.DataFrame) and isinstance(top_n, int):
                df = df.head(top_n)
                row_count = int(df.shape[0])

            return SqlResult(
                ok=True,
                cancelled=False,
                data=df,
                rows=row_count,
                elapsed_s=elapsed,
                sql_signature=signature,
            )

        except Exception as e:
            elapsed = time.time() - start

            # If cancellation is already requested when the driver/DB layer raises,
            # prefer cancelled semantics over generic failure.
            if _is_cancelled():
                log.info(
                    "DbService: SQL cancelled during execution "
                    "(signature=%s, corr=%s, elapsed=%.3fs, job_id=%s)",
                    signature,
                    corr_id,
                    elapsed,
                    job_id,
                )
                return SqlResult(
                    ok=False,
                    cancelled=True,
                    elapsed_s=elapsed,
                    sql_signature=signature,
                )

            err = self._classify_error(e)
            if should_log(signature):
                log.error(
                    "DbService: SQL error (signature=%s, corr=%s): %s %s - %s",
                    signature,
                    corr_id,
                    err.category,
                    err.code or "",
                    err.message,
                )
                if err.category == "unknown":
                    log.debug("DbService: full exception:", exc_info=True)
                else:
                    log.debug("DbService: exception details: %s", e)

            return SqlResult(
                ok=False,
                cancelled=False,
                error=err,
                elapsed_s=elapsed,
                sql_signature=signature,
            )

    # -------------------------------------------------------------------------
    # Metadata operations (tables / views / columns)
    # -------------------------------------------------------------------------

    def list_tables(self, conn: ConnectionConfig, corr_id: str | None = None) -> list[dict[str, str]]:
        """Return a list of tables in the connection.

        Args:
            conn: The connection configuration.
            corr_id: Optional correlation ID for logging.

        Returns:
            A list of dictionaries containing 'schema' and 'name' for each table.
        """
        res = self.execute_sql(conn, self.dialect.sql_list_tables(), corr_id=corr_id)
        if not res.ok:
            msg = f"{res.error.message}\n\n{res.error.hint}" if res.error else "Failed to list tables"
            raise RuntimeError(msg)
        if res.data is None or res.data.empty:
            return []
        df = res.data
        return [
            {"schema": str(r["schema_name"]), "name": str(r["object_name"])}
            for _, r in df.iterrows()
        ]

    def list_views(self, conn: ConnectionConfig, corr_id: str | None = None) -> list[dict[str, str]]:
        """Return a list of views in the connection.

        Args:
            conn: The connection configuration.
            corr_id: Optional correlation ID for logging.

        Returns:
            A list of dictionaries containing 'schema' and 'name' for each view.
        """
        res = self.execute_sql(conn, self.dialect.sql_list_views(), corr_id=corr_id)
        if not res.ok:
            msg = f"{res.error.message}\n\n{res.error.hint}" if res.error else "Failed to list views"
            raise RuntimeError(msg)
        if res.data is None or res.data.empty:
            return []
        df = res.data
        return [
            {"schema": str(r["schema_name"]), "name": str(r["object_name"])}
            for _, r in df.iterrows()
        ]

    def list_columns(
            self,
            conn: ConnectionConfig,
            schema: str,
            object_name: str,
            corr_id: str | None = None,
    ) -> list[dict[str, str]]:
        """Return column metadata for a given table or view.

        Args:
            conn: The connection configuration.
            schema: The schema name.
            object_name: The table or view name.
            corr_id: Optional correlation ID for logging.

        Returns:
            A list of dictionaries containing column metadata (name, type, nullability).
        """
        res = self.execute_sql(conn, self.dialect.sql_list_columns(schema, object_name), corr_id=corr_id)
        if not res.ok:
            msg = f"{res.error.message}\n\n{res.error.hint}" if res.error else "Failed to list columns"
            raise RuntimeError(msg)
        if res.data is None or res.data.empty:
            return []
        df = res.data
        return [
            {
                "COLUMN_NAME": str(r["COLUMN_NAME"]),
                "DATA_TYPE": str(r["DATA_TYPE"]),
                "IS_NULLABLE": str(r["IS_NULLABLE"]),
            }
            for _, r in df.iterrows()
        ]

    # -------------------------------------------------------------------------
    # High-level helpers (DB name, SELECT builders, bulk columns)
    # -------------------------------------------------------------------------

    def get_db_name(self, conn: ConnectionConfig, corr_id: str | None = None) -> str:
        """Return the current database name used by this connection.

        For MSSQL, it uses SELECT DB_NAME() for accurate reporting.
        For other engines, it falls back to ConnectionConfig.database, then the
        logical connection name.

        Args:
            conn: The connection configuration.
            corr_id: Optional correlation ID for logging.

        Returns:
            The name of the database.
        """
        if getattr(self.dialect, "name", "").lower() == "mssql":
            try:
                res = self.execute_sql(conn, "SELECT DB_NAME() AS name", corr_id=corr_id)
                if (
                        res.ok
                        and res.data is not None
                        and not res.data.empty
                        and "name" in res.data.columns
                ):
                    return str(res.data.iloc[0]["name"])
            except Exception:
                pass

        return conn.database or conn.name

    def build_select_star(
            self,
            schema: str,
            object_name: str,
            *,
            top_n: int | None = None,
            corr_id: str | None = None,
    ) -> str:
        """Build a standard SELECT * FROM statement.

        Uses dialect-specific quoting and optional limit injection.

        Args:
            schema: The schema name.
            object_name: The object name.
            top_n: Optional number of rows to limit.
            corr_id: Optional correlation ID for logging.

        Returns:
            A SQL query string.
        """
        qtable = self.dialect.qualify(schema, object_name)
        sql = f"SELECT *\nFROM {qtable};"

        if isinstance(top_n, int) and top_n > 0:
            with contextlib.suppress(Exception):
                sql = self.dialect.apply_limit(sql, top_n)

        return sql

    def build_select_distinct(
        self,
        schema: str,
        object_name: str,
        column_name: str,
    ) -> str:
        """Build a SELECT DISTINCT query using dialect-specific quoting."""
        qtable = self.dialect.qualify(schema, object_name)
        qcolumn = self.dialect.quote_ident(column_name)
        return f"SELECT DISTINCT {qcolumn}\nFROM {qtable};"

    def build_select_columns_auto(
            self,
            conn: ConnectionConfig,
            schema: str,
            object_name: str,
            *,
            top_n: int | None = None,
            with_schema: bool = False,
            corr_id: str | None = None,
    ) -> str:
        """Auto-generate a SELECT statement listing all columns of the object.

        Falls back to SELECT * when metadata is missing.

        Args:
            conn: The connection configuration.
            schema: The schema name.
            object_name: The object name.
            top_n: Optional number of rows to limit.
            with_schema: Whether to prefix column names with the schema/table name.
            corr_id: Optional correlation ID for logging and tracing.

        Returns:
            A SQL query string.
        """
        cols = self.list_columns(conn, schema, object_name, corr_id=corr_id)
        if not cols:
            return self.build_select_star(schema, object_name, top_n=top_n, corr_id=corr_id)
        col_names = [c.get("COLUMN_NAME") for c in cols if c.get("COLUMN_NAME")]

        if not col_names:
            return self.build_select_star(schema, object_name, top_n=top_n, corr_id=corr_id)

        if with_schema:
            prefix = self.dialect.qualify(schema, object_name)
            exprs = [f"{prefix}.{self.dialect.quote_ident(c)}" for c in col_names]
        else:
            exprs = [self.dialect.quote_ident(c) for c in col_names]

        indent = "    "
        proj = f",\n{indent}".join(exprs)
        qtable = self.dialect.qualify(schema, object_name)

        sql = (
            "SELECT\n"
            f"{indent}{proj}\n"
            f"FROM {qtable};"
        )

        if isinstance(top_n, int) and top_n > 0:
            with contextlib.suppress(Exception):
                sql = self.dialect.apply_limit(sql, top_n)

        return sql

    def list_all_columns_map(
            self,
            conn: ConnectionConfig,
            corr_id: str | None = None,
    ) -> dict[tuple[str, str], list[dict[str, str]]]:
        """Return full column metadata for all objects supported by the dialect.

        Uses dialect.sql_all_columns() if implemented and supported.
        Otherwise, raises AttributeError.

        Args:
            conn: The connection configuration.
            corr_id: Optional correlation ID for logging and tracing.

        Returns:
            A mapping from (schema, table) tuples to lists of column metadata.

        Raises:
            AttributeError: If the dialect does not support bulk column listing.
        """
        sql_all_fn = getattr(self.dialect, "sql_all_columns", None)
        if not callable(sql_all_fn):
            raise AttributeError("Dialect does not implement sql_all_columns().")

        stmt = str(sql_all_fn())
        if not stmt:
            raise AttributeError("Dialect does not support whole-database column listing.")

        res = self.execute_sql(conn, stmt, corr_id=corr_id)
        result: dict[tuple[str, str], list[dict[str, str]]] = {}

        if not res.ok:
            msg = f"{res.error.message}\n\n{res.error.hint}" if res.error else "Failed to list all columns"
            raise RuntimeError(msg)

        if res.data is None or res.data.empty:
            return result

        df = res.data
        # Flexible column matching across engines
        schema_col = "TABLE_SCHEMA" if "TABLE_SCHEMA" in df.columns else ("schema" if "schema" in df.columns else None)
        table_col = "TABLE_NAME" if "TABLE_NAME" in df.columns else ("table" if "table" in df.columns else None)
        col_col = "COLUMN_NAME" if "COLUMN_NAME" in df.columns else ("column" if "column" in df.columns else None)
        dt_col = "DATA_TYPE" if "DATA_TYPE" in df.columns else ("data_type" if "data_type" in df.columns else None)
        null_col = "IS_NULLABLE" if "IS_NULLABLE" in df.columns else (
            "is_nullable" if "is_nullable" in df.columns else None)

        if not (schema_col and table_col and col_col):
            return result

        # Build mapping
        for _, row in df.iterrows():
            schema = str(row[schema_col])
            table = str(row[table_col])
            entry = {
                "COLUMN_NAME": str(row[col_col]),
                "DATA_TYPE": str(row[dt_col]) if dt_col and pd.notna(row.get(dt_col)) else "",
                "IS_NULLABLE": str(row[null_col]) if null_col and pd.notna(row.get(null_col)) else "",
            }
            result.setdefault((schema, table), []).append(entry)

        return result

    # -------------------------------------------------------------------------
    # Error classification
    # -------------------------------------------------------------------------

    def _classify_error(self, exc: Exception) -> SqlError:
        """Dispatch to proper engine-specific classifier.

        Args:
            exc: The exception to classify.

        Returns:
            A Swedish SqlError suitable for UI display.
        """
        name = self.dialect.name

        if name == "mssql":
            from expo_jbm329.db.core.errors import classify_mssql
            return classify_mssql(exc)

        if name in ("mysql", "mariadb"):
            from expo_jbm329.db.core.errors import classify_mysql
            return classify_mysql(exc)

        if name == "sqlite":
            from expo_jbm329.db.core.errors import classify_sqlite
            return classify_sqlite(exc)

        return SqlError(
            "unknown",
            None,
            TR_UNKNOWN_DATABASE_FAIL,
            TR_UNKNOWN_DATABASE_FAIL_HINT,
        )

    # -------------------------------------------------------------------------
    # Lifecycle / Disposal
    # -------------------------------------------------------------------------

    def dispose(self) -> None:
        """Dispose any driver or engine resources associated with this service."""
        self.driver.dispose()
