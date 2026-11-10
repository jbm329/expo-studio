"""Qt-free scalar defaults and precision-safe nullable column preparation."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd
from pandas import CategoricalDtype
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_float_dtype,
    is_integer_dtype,
    is_object_dtype,
    is_string_dtype,
)

if TYPE_CHECKING:
    from collections.abc import Collection

FillValue = int | float | bool | str | datetime | pd.Timestamp | None
FillKind = Literal["integer", "float", "boolean", "text", "datetime", "unsupported"]

_NULLABLE_INTEGER_DTYPES: dict[
    str, Literal["Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64"]
] = {
    "int8": "Int8",
    "int16": "Int16",
    "int32": "Int32",
    "int64": "Int64",
    "uint8": "UInt8",
    "uint16": "UInt16",
    "uint32": "UInt32",
    "uint64": "UInt64",
}


@dataclass(frozen=True, slots=True)
class ColumnFill:
    """Default for generated missing values, with None representing NULL."""

    value: FillValue = None


@dataclass(frozen=True, slots=True)
class FillColumn:
    """Row-independent metadata for editing a column's default.

    Object columns offer text input; full source-content validation remains in
    the worker, avoiding dataframe scans while opening or editing a dialog.
    """

    name: str
    dtype: str
    kind: FillKind


def describe_fill_column(series: pd.Series) -> FillColumn:
    """Describe available editors from the dtype without scanning source values."""
    dtype = series.dtype
    kind: FillKind
    if isinstance(dtype, CategoricalDtype):
        kind = "text"
    elif isinstance(dtype, pd.SparseDtype):
        kind = "unsupported"
    elif is_bool_dtype(dtype):
        kind = "boolean"
    elif is_integer_dtype(dtype):
        kind = "integer"
    elif is_float_dtype(dtype):
        kind = "float"
    elif is_datetime64_any_dtype(dtype) and (isinstance(dtype, (np.dtype, pd.DatetimeTZDtype))):
        kind = "datetime"
    elif is_object_dtype(dtype) or is_string_dtype(dtype):
        kind = "text"
    else:
        kind = "unsupported"
    return FillColumn(str(series.name), str(dtype), kind)


def parse_fill(
    column: FillColumn,
    text: str,
    *,
    decimal_point: str = ".",
) -> ColumnFill:
    """Parse custom input and validate its scalar type, range and datetime precision.

    Args:
        column: Source column editor metadata.
        text: Custom input, with text-column whitespace preserved.
        decimal_point: Numeric locale decimal separator; grouping is not accepted.

    Returns:
        A typed default suitable for a data operation.

    Raises:
        ValueError: If input is invalid or the dtype supports NULL only.
    """
    value: FillValue
    message = f"Invalid default value for column {column.name!r} ({column.dtype})."
    match column.kind:
        case "integer":
            if re.fullmatch(r"[+-]?[0-9]+", text.strip()) is None:
                raise ValueError(message)
            value = int(text)
        case "float":
            if decimal_point != "." and "." in text:
                raise ValueError(message)
            numeric_text = text.strip().replace(decimal_point, ".")
            if re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", numeric_text) is None:
                raise ValueError(message)
            value = float(numeric_text)
            try:
                exact = Decimal(numeric_text)
            except InvalidOperation as error:
                raise ValueError(message) from error
            if value == 0.0 and exact != 0:
                raise ValueError(message)
        case "text":
            value = text
        case "datetime":
            value = text.strip()
        case _:
            raise ValueError(message)
    return validate_fill_column(column, ColumnFill(value))


def validate_fill_column(column: FillColumn, fill: ColumnFill) -> ColumnFill:
    """Validate scalar input from editor metadata without scanning source data."""
    schema = pd.Series([], name=column.name, dtype=column.dtype)
    return ColumnFill(validate_fill(schema, fill))


def _normalize_datetime_fill(series: pd.Series, timestamp: pd.Timestamp) -> pd.Timestamp:
    """Reject missing, ambiguous and precision-losing datetime defaults."""
    dtype = series.dtype
    message = f"Invalid default value for column {series.name!r} ({dtype})."
    if pd.isna(timestamp):
        raise ValueError(message)
    resolution: str
    if isinstance(dtype, pd.DatetimeTZDtype):
        localized = (
            timestamp.tz_localize(dtype.tz, ambiguous="NaT", nonexistent="NaT")
            if timestamp.tz is None
            else timestamp.tz_convert(dtype.tz)
        )
        if not isinstance(localized, pd.Timestamp):
            raise TypeError(message)
        timestamp = localized
        resolution = dtype.unit
    else:
        if timestamp.tz is not None:
            raise ValueError(message)
        resolution = np.datetime_data(str(dtype))[0]
    match resolution:
        case "s" | "ms" | "us" | "ns" as unit:
            return timestamp.as_unit(unit, round_ok=False)
        case _:
            raise ValueError(message)


def validate_fill(series: pd.Series, fill: ColumnFill) -> FillValue:
    """Validate and normalize a default for a source column.

    Args:
        series: Source column, including its dtype.
        fill: Requested default; None leaves generated missing values intact.

    Returns:
        A compatible scalar, with datetimes normalized to the source timezone.

    Raises:
        ValueError: If the default is incompatible, out of range, or loses precision.
    """
    value = fill.value
    if value is None:
        return None
    dtype = series.dtype
    message = f"Invalid default value for column {series.name!r} ({dtype})."
    if isinstance(dtype, CategoricalDtype) or is_object_dtype(dtype) or is_string_dtype(dtype):
        if not isinstance(value, str):
            raise ValueError(message)
        if is_object_dtype(dtype) and not all(isinstance(item, str) for item in series.dropna()):
            raise ValueError(message)
        return value
    if is_bool_dtype(dtype):
        if not isinstance(value, bool):
            raise ValueError(message)
        return value
    if is_integer_dtype(dtype):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(message)
        bounds = np.iinfo(np.dtype(str(dtype).lower().replace("[pyarrow]", "")))
        if not int(bounds.min) <= value <= int(bounds.max):
            raise ValueError(message)
        return value
    if is_float_dtype(dtype):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(message)
        try:
            normalized = float(value)
        except OverflowError as error:
            raise ValueError(message) from error
        numpy_dtype = (
            np.dtype(f"float{dtype.pyarrow_dtype.bit_width}")
            if isinstance(dtype, pd.ArrowDtype)
            else np.dtype(str(dtype).lower())
        )
        bounds_float = np.finfo(numpy_dtype)
        if (
            not math.isfinite(normalized)
            or abs(normalized) > float(bounds_float.max)
            or 0 < abs(normalized) < float(bounds_float.smallest_subnormal)
        ):
            raise ValueError(message)
        return normalized
    if is_datetime64_any_dtype(dtype):
        if not isinstance(value, (str, datetime, pd.Timestamp)):
            raise ValueError(message)
        try:
            return _normalize_datetime_fill(series, pd.Timestamp(value))
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError(message) from error
    raise ValueError(message)


def prepare_nullable_columns(
    frame: pd.DataFrame,
    columns: Collection[str] | None = None,
) -> pd.DataFrame:
    """Prepare selected NumPy integer and boolean columns without mutating inputs.

    Args:
        frame: Source dataframe.
        columns: Columns to prepare; None prepares all columns.

    Returns:
        A shallow copy with new nullable arrays for selected NumPy integer and
        boolean columns. Other columns and existing extension dtypes are unchanged.
    """
    included = set(frame.columns if columns is None else columns)
    prepared = frame.copy(deep=False)
    for column in frame.columns:
        if column not in included:
            continue
        dtype = frame[column].dtype
        if not isinstance(dtype, np.dtype):
            continue
        if dtype.kind == "b":
            prepared[column] = frame[column].astype("boolean")
        elif dtype.kind in {"i", "u"}:
            prepared[column] = frame[column].astype(_NULLABLE_INTEGER_DTYPES[dtype.name])
    return prepared
