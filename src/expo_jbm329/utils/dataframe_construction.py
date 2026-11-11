"""Precision-safe construction of dataframes from raw source values."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def dataframe_from_raw_values(
    data: Sequence[Sequence[object]],
    header: Sequence[object],
    *,
    check_cancel: Callable[[], None],
    coerce_float: bool = False,
) -> pd.DataFrame:
    """Construct missing-only nullable integers/booleans before float promotion.

    Args:
        data: Raw rows supplied by a source decoder.
        header: Column labels, including any duplicates.
        check_cancel: Source-specific cancellation check, raising on cancellation.
        coerce_float: Use pandas records inference for other columns, including
            SQL's existing Decimal-to-float conversion.

    Returns:
        A frame preserving raw integer precision and unrelated source inference.
    """
    check_cancel()
    if not data or not header:
        return pd.DataFrame(data, columns=list(header))
    raw = pd.DataFrame(data, dtype=object)
    raw.columns = pd.Index(list(header))
    return dataframe_from_raw_columns(raw, check_cancel=check_cancel, coerce_float=coerce_float)


def dataframe_from_raw_columns(
    raw: pd.DataFrame,
    *,
    check_cancel: Callable[[], None],
    coerce_float: bool = False,
) -> pd.DataFrame:
    """Finalize object-backed source columns without a row-tuple round trip.

    Args:
        raw: Object-backed source values before pandas numeric inference.
            Labels (including duplicates) and index are preserved.
        check_cancel: Source-specific check raising on cancellation.
        coerce_float: Retain SQL records inference for Decimal/mixed values.

    Returns:
        A new frame with missing-only nullable integers/booleans.

    Raises:
        ValueError: If a column has already undergone non-object inference.
    """
    check_cancel()
    if any(dtype != np.dtype(object) for dtype in raw.dtypes):
        msg = "Raw dataframe columns must use object storage before inference."
        raise ValueError(msg)
    if raw.empty:
        return raw.copy()
    columns: dict[int, object] = {}
    for position in range(len(raw.columns)):
        check_cancel()
        values = raw.iloc[:, position]
        kind = pd.api.types.infer_dtype(values, skipna=True)
        missing = values.isna()
        column: pd.Series
        if missing.any() and kind == "boolean":
            column = values.astype("boolean")
        elif missing.any() and kind == "integer":
            nonmissing = values.loc[~missing]
            minimum = min(nonmissing)
            maximum = max(nonmissing)
            signed = np.iinfo(np.int64)
            unsigned = np.iinfo(np.uint64)
            if signed.min <= minimum and maximum <= signed.max:
                column = values.astype("Int64")
            elif minimum >= 0 and maximum <= unsigned.max:
                column = values.astype("UInt64")
            else:
                column = values
        elif coerce_float and kind not in {"integer", "boolean", "floating", "string", "bytes", "empty"}:
            column = pd.DataFrame.from_records([(value,) for value in values], coerce_float=True).iloc[:, 0]
        else:
            column = values.infer_objects()
        columns[position] = column.array
    check_cancel()
    frame = pd.DataFrame(columns, index=raw.index)
    frame.columns = raw.columns.copy()
    return frame
