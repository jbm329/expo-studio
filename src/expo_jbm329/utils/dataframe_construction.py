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
    columns: list[pd.Series] = []
    for position in range(len(header)):
        check_cancel()
        values = [row[position] for row in data]
        raw = pd.Series(values, dtype=object)
        nonmissing = raw.dropna()
        kind = pd.api.types.infer_dtype(nonmissing, skipna=True)
        column: pd.Series
        if raw.isna().any() and kind == "boolean":
            column = raw.astype("boolean")
        elif raw.isna().any() and kind == "integer":
            minimum = min(nonmissing)
            maximum = max(nonmissing)
            signed = np.iinfo(np.int64)
            unsigned = np.iinfo(np.uint64)
            if signed.min <= minimum and maximum <= signed.max:
                column = raw.astype("Int64")
            elif minimum >= 0 and maximum <= unsigned.max:
                column = raw.astype("UInt64")
            else:
                column = raw
        elif coerce_float:
            column = pd.DataFrame.from_records([(value,) for value in values], coerce_float=True).iloc[:, 0]
        else:
            column = pd.Series(values)
        columns.append(column)
    check_cancel()
    frame = pd.concat(columns, axis=1)
    frame.columns = pd.Index(list(header))
    return frame
