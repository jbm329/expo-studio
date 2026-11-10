"""Dataframe concatenation services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from expo_jbm329.services.data_operations.column_defaults import (
    ColumnFill,
    FillValue,
    prepare_nullable_columns,
    validate_fill,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


@dataclass
class ConcatRequest:
    """Configuration for concatenating two dataframes.

    Attributes:
        left: The first dataframe.
        right: The second dataframe.
        remove_duplicates: If True, behaves like SQL UNION (deduplicates).
            If False (default), behaves like SQL UNION ALL.
        left_fill: Defaults keyed by columns selected only in the first dataset.
            Values populate second-dataset rows, never existing source NULLs.
        right_fill: Defaults keyed by columns selected only in the second dataset.
            Values populate first-dataset rows, never existing source NULLs.
        left_columns: Included first-dataset columns, or None for all. Source
            order is retained regardless of selection order.
        right_columns: Included second-dataset columns, or None for all.
            Excluded columns do not supply values, but every source row remains.
    """

    left: pd.DataFrame
    right: pd.DataFrame
    remove_duplicates: bool = False
    left_fill: Mapping[str, ColumnFill] = field(default_factory=dict)
    right_fill: Mapping[str, ColumnFill] = field(default_factory=dict)
    left_columns: Sequence[str] | None = None
    right_columns: Sequence[str] | None = None


def _select_columns(frame: pd.DataFrame, columns: Sequence[str] | None) -> pd.DataFrame:
    """Project a source schema in source order without dropping its rows."""
    if columns is None:
        return frame
    if not frame.columns.is_unique:
        message = "Concatenation column selection requires unique column names."
        raise ValueError(message)
    selected = set(columns)
    if len(selected) != len(columns):
        message = "Concatenation column selection must not contain duplicate names."
        raise ValueError(message)
    unknown = selected.difference(frame.columns)
    if unknown:
        message = f"Unknown columns in concatenation selection: {sorted(unknown)!r}."
        raise ValueError(message)
    return frame.loc[:, frame.columns.isin(selected)]


def _validate_fills(
    source: pd.DataFrame,
    other: pd.DataFrame,
    fills: Mapping[str, ColumnFill],
) -> dict[str, FillValue]:
    """Validate defaults against source ownership before constructing output."""
    normalized: dict[str, FillValue] = {}
    for column, fill in fills.items():
        if column not in source.columns or column in other.columns:
            message = f"Absent-column default requires a column owned only by its source dataset: {column!r}."
            raise ValueError(message)
        normalized[column] = validate_fill(source[column], fill)
    return normalized


def _prepare_absent_columns(
    source: pd.DataFrame,
    other: pd.DataFrame,
    columns: Sequence[str],
    fills: Mapping[str, FillValue],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create typed absent segments without overwriting existing source values."""
    prepared = prepare_nullable_columns(source, [column for column in columns if fills.get(column) is None])
    counterpart = other.copy(deep=False)
    for column in columns:
        value = fills.get(column)
        series = prepared[column]
        if value is not None:
            if (
                len(counterpart) > 0
                and isinstance(series.dtype, pd.CategoricalDtype)
                and value not in series.cat.categories
            ):
                series = series.cat.add_categories([value])
                prepared[column] = series
            counterpart[column] = pd.Series(value, index=counterpart.index, dtype=series.dtype)
        elif series.dtype != source[column].dtype:
            counterpart[column] = pd.Series(index=counterpart.index, dtype=series.dtype)
    return prepared, counterpart


def concat_dataframes(req: ConcatRequest) -> pd.DataFrame:
    """Perform a vertical concat (union) of two dataframes.

    Rules:
        * Name-based column union (Pandas default).
        * Optional per-source column selection preserves source column order.
          A column selected on only one side is absent for the other side's rows.
        * Missing columns filled with missing values.
        * One-sided NumPy integers and booleans use matching nullable dtypes
          for NULL defaults and retain their original dtype for non-NULL defaults.
        * Shared columns retain pandas' dtype reconciliation behavior.
        * Defaults populate absent columns only, preserving existing source NULLs.
        * Row order preserved: left-rows first, then right-rows.
        * Index ignored (new sequential index).
        * Optional deduplication (slow -> only done when requested).

    This behavior matches:
        * PowerQuery's default "Append Queries"
        * Pandas.concat
        * Excel PQ Combine
        * SQL UNION ALL (default)

    Args:
        req: The concatenation request configuration.

    Returns:
        The concatenated dataframe.

    Raises:
        ValueError: If selections or defaults are invalid, no output columns
            remain, or column-specific preparation is ambiguous because of
            duplicate column names.
    """
    left = _select_columns(req.left, req.left_columns)
    right = _select_columns(req.right, req.right_columns)
    if len(left.columns) == 0 and len(right.columns) == 0:
        message = "Concatenation requires at least one selected output column."
        raise ValueError(message)

    if not left.columns.equals(right.columns) or req.left_fill or req.right_fill:
        if not left.columns.is_unique or not right.columns.is_unique:
            message = "Concatenation with different column layouts requires unique column names."
            raise ValueError(message)
        left_only = left.columns.difference(right.columns, sort=False).tolist()
        right_only = right.columns.difference(left.columns, sort=False).tolist()
        left_fill = _validate_fills(left, right, req.left_fill)
        right_fill = _validate_fills(right, left, req.right_fill)
        left, right = _prepare_absent_columns(left, right, left_only, left_fill)
        right, left = _prepare_absent_columns(right, left, right_only, right_fill)

    # --- Perform concat ---
    result = pd.concat(
        [left, right],
        axis=0,
        ignore_index=True,
        sort=False,  # preserve column order; don't sort automatically
    )

    # --- Optional deduplicate ---
    if req.remove_duplicates:
        # Pandas drop_duplicates keeps first occurrence, similar to SQL UNION
        result = result.drop_duplicates(ignore_index=True)

    return result
