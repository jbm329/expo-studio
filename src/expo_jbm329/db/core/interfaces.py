"""Database core interfaces defining protocols for drivers and dialects."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

import pandas as pd

from .models import ConnectionConfig


@runtime_checkable
class DriverProtocol(Protocol):
    """Protocol defining the interface for database drivers.

    Driver abstracts the transport/protocol (ODBC, psycopg2, PyMySQL, TDS, ...).
    The service controls error handling; drivers just execute and bubble exceptions.
    """

    def initialize(self, *, timeouts: dict | None = None) -> None:
        """Initialize the driver with optional timeouts.

        Args:
            timeouts: A dictionary of timeout values for the driver.
        """
        ...

    def dispose(self) -> None:
        """Dispose of the driver and release any resources."""
        ...

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
            conn: The connection configuration to use.
            sql: The SQL query string to execute.
            job_id: Optional execution/job identifier used for cancellation tracking.
            cancel_cb: Optional cooperative cancellation callback.
            corr_id: Optional correlation identifier for logging.

        Returns:
            A pandas DataFrame containing the query results.
        """
        ...

    def cancel_execution(self, job_id: str) -> bool:
        """Attempt to cancel an active execution associated with a job id.

        Args:
            job_id: The execution/job identifier.

        Returns:
            True if an active execution was found and a cancel request was issued,
            otherwise False.
        """
        ...

    def set_query_timeout(self, seconds: int | None) -> None:
        """Set the query timeout for subsequent executions.

        Args:
            seconds: The timeout in seconds, or None to reset.
        """
        ...


@runtime_checkable
class DialectProtocol(Protocol):
    """Protocol defining the interface for engine-specific SQL dialects."""

    name: str

    def apply_limit(self, sql: str, n: int) -> str:
        """Apply a LIMIT clause to the given SQL query.

        Args:
            sql: The SQL query string.
            n: The number of rows to limit.

        Returns:
            The modified SQL query with the LIMIT clause applied.
        """
        ...

    def quote_ident(self, name: str) -> str:
        """Quote an identifier (e.g., table or column name).

        Args:
            name: The identifier to quote.

        Returns:
            The quoted identifier.
        """
        ...

    def qualify(self, schema: str, object_name: str) -> str:
        """Qualify an object name with a schema.

        Args:
            schema: The schema name.
            object_name: The object name (e.g., table name).

        Returns:
            The fully qualified name.
        """
        ...

    def sql_list_tables(self) -> str:
        """Generate SQL for listing tables.

        Returns:
            A SQL query string to list tables.
        """
        ...

    def sql_list_views(self) -> str:
        """Generate SQL for listing views.

        Returns:
            A SQL query string to list views.
        """
        ...

    def sql_list_columns(self, schema: str, object_name: str) -> str:
        """Generate SQL for listing columns of a table or view.

        Args:
            schema: The schema name.
            object_name: The table or view name.

        Returns:
            A SQL query string to list columns.
        """
        ...

    def sql_all_columns(self) -> str | None:
        """Generate SQL fragment for selecting all columns.

        Returns:
            A SQL fragment string or None if not applicable.
        """
        ...
