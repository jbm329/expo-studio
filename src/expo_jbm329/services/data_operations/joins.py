"""Dataframe join and concatenation operations."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd
from pandas import CategoricalDtype
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_float_dtype,
    is_integer_dtype,
    is_numeric_dtype,
    is_object_dtype,
    is_string_dtype,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

JoinHow = Literal["inner", "left", "right", "outer"]
JoinFillValue = int | float | bool | str | datetime | pd.Timestamp | None

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


@dataclass(slots=True)
class JoinMetadata:
    """Metadata describing join quality and characteristics."""

    match_rate: float
    left_only: float
    right_only: float
    cardinality: str
    estimated_rows: int


@dataclass(frozen=True, slots=True)
class UnmatchedFill:
    """Default for a missing source row, with None representing NULL."""

    value: JoinFillValue = None


@dataclass(frozen=True)
class JoinRequest:
    """Immutable join configuration passed from UI/controller layer.

    Attributes:
        left: Left dataframe.
        right: Right dataframe.
        left_on: Column names to join on in the left dataframe.
        right_on: Column names to join on in the right dataframe.
        how: Join type: 'inner', 'left', 'right', 'outer'.
        suffixes: Suffixes for conflicting column names.
        left_columns: Included left columns to prepare for missing values.
            None prepares all columns. Join keys are always prepared.
        right_columns: Included right columns to prepare for missing values.
            None prepares all columns. This does not filter the merge output.
        left_fill: Defaults keyed by left source column name.
        right_fill: Defaults keyed by right source column name.
    """

    left: pd.DataFrame
    right: pd.DataFrame
    left_on: Sequence[str]
    right_on: Sequence[str]
    how: JoinHow = "inner"
    suffixes: tuple[str, str] = ("_left", "_right")
    left_columns: Sequence[str] | None = None
    right_columns: Sequence[str] | None = None
    left_fill: Mapping[str, UnmatchedFill] = field(default_factory=dict)
    right_fill: Mapping[str, UnmatchedFill] = field(default_factory=dict)


def _normalize_datetime_fill(series: pd.Series, timestamp: pd.Timestamp) -> pd.Timestamp:
    """Reject missing, ambiguous and precision-losing datetime defaults."""
    dtype = series.dtype
    message = f"Invalid unmatched-row default for column {series.name!r} ({dtype})."
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


def validate_join_fill(series: pd.Series, fill: UnmatchedFill) -> JoinFillValue:
    """Validate and normalize an unmatched-row default for a source column.

    Args:
        series: Source column, including its dtype.
        fill: Requested default; None leaves join-created missing values intact.

    Returns:
        A compatible scalar, with datetimes normalized to the source timezone.

    Raises:
        ValueError: If the default is incompatible, out of range, or loses precision.
    """
    value = fill.value
    if value is None:
        return None
    dtype = series.dtype
    message = f"Invalid unmatched-row default for column {series.name!r} ({dtype})."
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
    if isinstance(dtype, CategoricalDtype) or is_object_dtype(dtype) or is_string_dtype(dtype):
        if not isinstance(value, str):
            raise ValueError(message)
        if isinstance(dtype, CategoricalDtype) or not is_object_dtype(dtype):
            return value
        if not all(isinstance(item, str) for item in series.dropna()):
            raise ValueError(message)
        return value
    raise ValueError(message)


def _validate_side_fills(
    frame: pd.DataFrame,
    columns: Sequence[str] | None,
    keys: Sequence[str],
    fills: Mapping[str, UnmatchedFill],
    *,
    can_be_missing: bool,
) -> dict[str, JoinFillValue]:
    """Validate defaults against source column identity and join configuration."""
    included = set(frame.columns if columns is None else columns)
    normalized: dict[str, JoinFillValue] = {}
    for column, fill in fills.items():
        if column not in frame.columns or column not in included or column in keys or not can_be_missing:
            message = f"Unmatched-row default is not available for column {column!r} in this join configuration."
            raise ValueError(message)
        normalized[column] = validate_join_fill(frame[column], fill)
    return normalized


def _apply_side_fills(
    result: pd.DataFrame,
    source: pd.DataFrame,
    other: pd.DataFrame,
    fills: Mapping[str, JoinFillValue],
    suffix: str,
    missing_status: Literal["left_only", "right_only"],
) -> None:
    """Fill only missing source rows, preserving source dtype and source NULLs."""
    if not any(value is not None for value in fills.values()):
        return
    missing = result["join_status"] == missing_status
    has_missing = missing.any()
    for column, value in fills.items():
        if value is None:
            continue
        output_column = f"{column}{suffix}" if column in other.columns else column
        if output_column not in result.columns or not result.columns.is_unique:
            message = f"Cannot identify join output column for unmatched-row default {column!r}."
            raise ValueError(message)
        series = result[output_column].copy()
        if has_missing:
            if isinstance(series.dtype, CategoricalDtype) and value not in series.cat.categories:
                series = series.cat.add_categories([value])
            series.loc[missing] = value
        source_dtype = source[column].dtype
        if isinstance(source_dtype, np.dtype) and source_dtype.kind in {"i", "u", "b"}:
            series = series.astype(source_dtype)
        result[output_column] = series


def _prepare_nullable_columns(
    frame: pd.DataFrame,
    columns: Sequence[str] | None,
    keys: Sequence[str],
) -> pd.DataFrame:
    """Prepare integer and boolean columns without mutating the source frame."""
    included = set(frame.columns if columns is None else columns) | set(keys)
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


def join_dataframes(cfg: JoinRequest) -> pd.DataFrame:
    """Perform a relational join between two DataFrames.

    Args:
        cfg: Fully specified join configuration.

    Returns:
        The resulting merged dataframe.

    Note:
        * Keys are aligned 1:1 (left_on[i] corresponds to right_on[i]).
        * Multi-key joins are supported.
        * Included integer and boolean columns on a side that can be missing
          use nullable dtypes before merging, even when all rows match.
        * Integer widths, signedness and existing extension dtypes are preserved.
        * Defaults apply only to join-created missing rows, never source NULLs.

    Raises:
        ValueError: If keys or unmatched-row defaults are invalid.
    """
    if len(cfg.left_on) != len(cfg.right_on):
        msg = f"left_on and right_on must have same length (got {len(cfg.left_on)} vs {len(cfg.right_on)})"
        raise ValueError(msg)

    left = cfg.left
    right = cfg.right
    left_fill = _validate_side_fills(
        left, cfg.left_columns, cfg.left_on, cfg.left_fill, can_be_missing=cfg.how in {"right", "outer"}
    )
    right_fill = _validate_side_fills(
        right, cfg.right_columns, cfg.right_on, cfg.right_fill, can_be_missing=cfg.how in {"left", "outer"}
    )
    if cfg.how in {"right", "outer"}:
        left = _prepare_nullable_columns(left, cfg.left_columns, cfg.left_on)
    if cfg.how in {"left", "outer"}:
        right = _prepare_nullable_columns(right, cfg.right_columns, cfg.right_on)

    result = left.merge(
        right,
        left_on=list(cfg.left_on),
        right_on=list(cfg.right_on),
        how=cfg.how,
        suffixes=cfg.suffixes,
        indicator="join_status",
    )
    _apply_side_fills(result, cfg.left, cfg.right, left_fill, cfg.suffixes[0], "right_only")
    _apply_side_fills(result, cfg.right, cfg.left, right_fill, cfg.suffixes[1], "left_only")
    return result


def detect_join_keys(left: pd.DataFrame, right: pd.DataFrame) -> list[str]:
    """Detect potential join keys based on matching column names AND compatible dtypes.

    Args:
        left: First dataframe.
        right: Second dataframe.

    Returns:
        Column names suitable as join keys.

    Note:
        This is a heuristic:
        * Column names must match.
        * Dtypes must be compatible (numeric with numeric, string with string).
        * More rules can be added as needed.
    """
    matches: list[str] = []

    for col in left.columns:
        if col not in right.columns:
            continue

        l_col = left[col]
        r_col = right[col]

        # Numeric to numeric
        if is_numeric_dtype(l_col) and is_numeric_dtype(r_col):
            matches.append(col)
            continue

        # String to string
        if is_string_dtype(l_col) and is_string_dtype(r_col):
            matches.append(col)
            continue

        # Categorical or object-like text
        if isinstance(l_col.dtype, CategoricalDtype) and isinstance(r_col.dtype, CategoricalDtype):
            matches.append(col)
            continue

        if l_col.dtype == "object" and r_col.dtype == "object":
            matches.append(col)
            continue

    return matches


def concat_rows(*frames: pd.DataFrame, join: Literal["outer", "inner"] = "outer") -> pd.DataFrame:
    """Concatenate multiple dataframes row-wise (append).

    Args:
        *frames: Dataframes to concatenate.
        join: Column alignment strategy.

    Returns:
        Combined dataframe with reset index.
    """
    if not frames:
        msg = "No dataframes were provided for concat_rows()."
        raise ValueError(msg)

    return pd.concat(frames, axis=0, join=join).reset_index(drop=True)


def concat_columns(*frames: pd.DataFrame, join: Literal["outer", "inner"] = "outer") -> pd.DataFrame:
    """Concatenate multiple dataframes column-wise.

    Args:
        *frames: Dataframes to concatenate.
        join: Row alignment strategy.

    Returns:
        Combined dataframe by columns.
    """
    if not frames:
        msg = "No dataframes were provided for concat_columns()."
        raise ValueError(msg)

    return pd.concat(frames, axis=1, join=join)
