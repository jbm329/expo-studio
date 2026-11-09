"""Dataframe concatenation services."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from expo_jbm329.services.data_operations.column_defaults import prepare_nullable_columns


@dataclass
class ConcatRequest:
    """Configuration for concatenating two dataframes.

    Attributes:
        left: The first dataframe.
        right: The second dataframe.
        remove_duplicates: If True, behaves like SQL UNION (deduplicates).
            If False (default), behaves like SQL UNION ALL.
    """

    left: pd.DataFrame
    right: pd.DataFrame
    remove_duplicates: bool = False


def concat_dataframes(req: ConcatRequest) -> pd.DataFrame:
    """Perform a vertical concat (union) of two dataframes.

    Rules:
        * Name-based column union (Pandas default).
        * Missing columns filled with missing values.
        * One-sided NumPy integers and booleans use matching nullable dtypes.
        * Shared columns retain pandas' dtype reconciliation behavior.
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
        ValueError: If different column layouts contain duplicate column names.
    """
    left = req.left
    right = req.right

    if not left.columns.equals(right.columns):
        if not left.columns.is_unique or not right.columns.is_unique:
            message = "Concatenation with different column layouts requires unique column names."
            raise ValueError(message)
        left_only = left.columns.difference(right.columns, sort=False).tolist()
        right_only = right.columns.difference(left.columns, sort=False).tolist()
        left = prepare_nullable_columns(left, left_only)
        right = prepare_nullable_columns(right, right_only)
        for column in left_only:
            if left[column].dtype != req.left[column].dtype:
                right[column] = pd.Series(index=right.index, dtype=left[column].dtype)
        for column in right_only:
            if right[column].dtype != req.right[column].dtype:
                left[column] = pd.Series(index=left.index, dtype=right[column].dtype)

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
