"""Read SQLAlchemy results without losing nullable integer precision."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from expo_jbm329.utils.dataframe_construction import dataframe_from_raw_values

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.engine import Connection


def read_sql_dataframe(
    sql: str,
    connection: Connection,
    *,
    cancel_cb: Callable[[], bool] | None = None,
) -> pd.DataFrame:
    """Read raw query results and preserve missing-only integer/boolean storage.

    Args:
        sql: Query string passed unchanged to the driver, without bound parameters.
        connection: Open SQLAlchemy connection owned by the caller.
        cancel_cb: Existing cooperative cancellation callback.

    Returns:
        Query results with legacy inference for unrelated columns.

    Raises:
        RuntimeError: If cancellation is requested during preparation.
    """

    def check_cancel() -> None:
        if cancel_cb is not None and cancel_cb():
            msg = "SQL dataframe preparation cancelled."
            raise RuntimeError(msg)

    check_cancel()
    # Omit even empty DBAPI parameters so percent literals are not interpolated.
    with connection.exec_driver_sql(sql, execution_options={"no_parameters": True}) as result:
        header = list(result.keys())
        data = result.fetchall()
        frame = dataframe_from_raw_values(data, header, check_cancel=check_cancel, coerce_float=True)
    for position in range(len(frame.columns)):
        check_cancel()
        column = frame.iloc[:, position]
        if isinstance(column.dtype, pd.DatetimeTZDtype):
            # pandas' SQL reader normalizes inferred timezone-aware datetimes to UTC.
            frame.isetitem(position, pd.to_datetime(column, utc=True).array)
    check_cancel()
    return frame
