"""Dataframe join and concatenation operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd
from pandas import CategoricalDtype
from pandas.api.types import (
    is_numeric_dtype,
    is_string_dtype,
)

from expo_jbm329.services.data_operations.column_defaults import (
    ColumnFill as UnmatchedFill,
)
from expo_jbm329.services.data_operations.column_defaults import (
    FillColumn as JoinFillColumn,
)
from expo_jbm329.services.data_operations.column_defaults import (
    FillKind as JoinFillKind,
)
from expo_jbm329.services.data_operations.column_defaults import (
    FillValue as JoinFillValue,
)
from expo_jbm329.services.data_operations.column_defaults import (
    describe_fill_column as describe_join_fill_column,
)
from expo_jbm329.services.data_operations.column_defaults import (
    parse_fill,
    prepare_nullable_columns,
    validate_fill,
    validate_fill_column,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "JoinFillColumn",
    "JoinFillKind",
    "JoinFillValue",
    "JoinHow",
    "JoinMetadata",
    "JoinRequest",
    "JoinResult",
    "UnmatchedFill",
    "concat_columns",
    "concat_rows",
    "describe_join_fill_column",
    "detect_join_keys",
    "join_dataframes",
    "join_dataframes_with_status",
    "parse_join_fill",
    "validate_join_fill",
    "validate_join_fill_column",
]

JoinHow = Literal["inner", "left", "right", "outer"]


@dataclass(slots=True)
class JoinMetadata:
    """Metadata describing join quality and characteristics."""

    match_rate: float
    left_only: float
    right_only: float
    cardinality: str
    estimated_rows: int


def parse_join_fill(
    column: JoinFillColumn,
    text: str,
    *,
    decimal_point: str = ".",
) -> UnmatchedFill:
    """Parse custom input and validate its scalar type, range and datetime precision.

    Args:
        column: Source column editor metadata.
        text: Custom input, with text-column whitespace preserved.
        decimal_point: Numeric locale decimal separator; grouping is not accepted.

    Returns:
        A typed default suitable for the join request.

    Raises:
        ValueError: If input is invalid or the dtype supports NULL only.
    """
    try:
        return parse_fill(column, text, decimal_point=decimal_point)
    except ValueError as error:
        message = f"Invalid unmatched-row default for column {column.name!r} ({column.dtype})."
        raise ValueError(message) from error


def validate_join_fill_column(column: JoinFillColumn, fill: UnmatchedFill) -> UnmatchedFill:
    """Validate scalar input from editor metadata without scanning source data."""
    try:
        return validate_fill_column(column, fill)
    except ValueError as error:
        message = f"Invalid unmatched-row default for column {column.name!r} ({column.dtype})."
        raise ValueError(message) from error


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
        status_column_base: Preferred generated status name. Occupied names
            receive a numeric suffix starting at 2.
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
    status_column_base: str = "join_status"


@dataclass(frozen=True)
class JoinResult:
    """Joined dataframe and the identity of its generated provenance column.

    Attributes:
        frame: Merged data, including the generated categorical status.
        status_column: Actual generated name, distinct from all source columns.
    """

    frame: pd.DataFrame
    status_column: str


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
    try:
        return validate_fill(series, fill)
    except ValueError as error:
        message = f"Invalid unmatched-row default for column {series.name!r} ({series.dtype})."
        raise ValueError(message) from error


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
    status_column: str,
) -> None:
    """Fill only missing source rows, preserving source dtype and source NULLs."""
    if not any(value is not None for value in fills.values()):
        return
    missing = result[status_column] == missing_status
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
            series = series.mask(missing, value)
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
    return prepare_nullable_columns(frame, included)


def join_dataframes(cfg: JoinRequest) -> pd.DataFrame:
    """Perform a relational join between two DataFrames.

    Args:
        cfg: Fully specified join configuration.

    Returns:
        The resulting merged dataframe. Use ``join_dataframes_with_status``
        when the generated status column's actual name is needed.

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
    return join_dataframes_with_status(cfg).frame


def _available_column_name(base: str, occupied: set[str]) -> str:
    """Allocate a deterministic name without replacing source or output data."""
    candidate = base
    number = 2
    while candidate in occupied:
        candidate = f"{base} {number}"
        number += 1
    return candidate


def join_dataframes_with_status(cfg: JoinRequest) -> JoinResult:
    """Join dataframes and return the generated status column's explicit identity.

    Args:
        cfg: Join configuration, including a preferred status-column base name.

    Returns:
        Merged frame and its collision-safe categorical status-column name.
        Status categories are ``left_only``, ``right_only`` and ``both``.
        Existing columns and input frames are never overwritten.

    Raises:
        ValueError: If keys, unmatched-row defaults or the status base are invalid.
    """
    if len(cfg.left_on) != len(cfg.right_on):
        msg = f"left_on and right_on must have same length (got {len(cfg.left_on)} vs {len(cfg.right_on)})"
        raise ValueError(msg)
    if not cfg.status_column_base.strip():
        message = "Join status column base must not be empty."
        raise ValueError(message)

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

    source_columns = set(left.columns) | set(right.columns)
    occupied = source_columns.copy()
    # Temporary markers must also avoid names created by pandas' suffixing.
    overlapping = set(left.columns) & set(right.columns)
    occupied.update(f"{column}{suffix}" for column in overlapping for suffix in cfg.suffixes)
    left_marker = _available_column_name("__expo_join_left", occupied)
    occupied.add(left_marker)
    right_marker = _available_column_name("__expo_join_right", occupied)

    left = left.copy(deep=False)
    right = right.copy(deep=False)
    left[left_marker] = np.int8(1)
    right[right_marker] = np.int8(2)
    result = left.merge(
        right,
        left_on=list(cfg.left_on),
        right_on=list(cfg.right_on),
        how=cfg.how,
        suffixes=cfg.suffixes,
    )
    left_present = result.pop(left_marker).notna().to_numpy(dtype=np.int8)
    right_present = result.pop(right_marker).notna().to_numpy(dtype=np.int8)
    status_column = _available_column_name(cfg.status_column_base, source_columns | set(result.columns))
    result[status_column] = pd.Categorical.from_codes(
        left_present + 2 * right_present - 1,
        categories=pd.Index(["left_only", "right_only", "both"]),
    )
    _apply_side_fills(result, cfg.left, cfg.right, left_fill, cfg.suffixes[0], "right_only", status_column)
    _apply_side_fills(result, cfg.right, cfg.left, right_fill, cfg.suffixes[1], "left_only", status_column)
    return JoinResult(frame=result, status_column=status_column)


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
