"""Column-level DataFrame operations.

This module contains pure, UI-independent helpers for working with
DataFrame columns, including:

- Mapping UI column indices to DataFrame column names
- Sorting by column
- Dropping, renaming, splitting, and joining columns
- Preserving column order and predictable insertion behavior

Design principles:
- Side-effect free: all functions return new DataFrames
- Explicit error handling (KeyError, IndexError, ValueError)
- No UI dependencies
- High testability and deterministic behavior
"""

from __future__ import annotations

import logging
from typing import Literal

import pandas as pd

from ._internal import drop_column

logger = logging.getLogger("applogger.service")


# =====================================================================
# Core column operations
# =====================================================================


def sort_dataframe(
    df: pd.DataFrame,
    column: str,
    ascending: bool = True,
) -> pd.DataFrame:
    """Return a new DataFrame sorted by a specific column.

    Args:
        df: Source DataFrame.
        column: Column name to sort by.
        ascending: Sort order.

    Returns:
        A sorted copy of the DataFrame.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug(
        "Sorting DataFrame by column '%s', ascending=%s",
        column,
        ascending,
    )

    if column not in df.columns:
        msg = f"Column '{column}' not found."
        raise KeyError(msg)

    return df.sort_values(by=column, ascending=ascending).copy()


def safe_drop_column(
    df: pd.DataFrame,
    view_column_index: int,
) -> pd.DataFrame:
    """Drop a column using a UI column index.

    This is a convenience wrapper that resolves the UI index
    and delegates to the internal drop helper.

    Args:
        df: Source DataFrame.
        view_column_index: Column index as used by the UI.

    Returns:
        A new DataFrame without the selected column.
    """
    column_name = str(df.columns[view_column_index])

    logger.debug(
        "Dropping column via UI index %s -> '%s'",
        view_column_index,
        column_name,
    )

    return drop_column(df, column_name)


def rename_column(
    df: pd.DataFrame,
    old_name: str,
    new_name: str,
) -> pd.DataFrame:
    """Rename a column while preserving column order.

    Rules:
    - Raises KeyError if the old column does not exist.
    - Raises ValueError if the new name already exists
      (unless it is the same as the old name).

    Args:
        df: Source DataFrame.
        old_name: Existing column name.
        new_name: New column name.

    Returns:
        A new DataFrame with the renamed column.
    """
    logger.debug("Renaming column '%s' -> '%s'", old_name, new_name)

    if old_name not in df.columns:
        msg = f"Column '{old_name}' not found."
        raise KeyError(msg)

    new_name = str(new_name)
    if new_name in df.columns and new_name != old_name:
        msg = f"Column '{new_name}' already exists."
        raise ValueError(msg)

    return df.copy().rename(columns={old_name: new_name})


# =====================================================================
# Column composition helpers
# =====================================================================


def split_column(
    df: pd.DataFrame,
    column: str,
    delimiter: str,
    *,
    mode: Literal["first", "last"] = "first",
    keep_original: bool = True,
) -> pd.DataFrame:
    """Split a column into two new string columns using a delimiter.

    Behavior:
    - Always trims whitespace
    - Always returns exactly two columns
    - New columns are inserted immediately after the original column
    - New columns use pandas StringDtype

    Args:
        df: Source DataFrame.
        column: Column to split.
        delimiter: Delimiter string.
        mode: Whether to split on the first or last occurrence.
        keep_original: Whether to keep the original column.

    Returns:
        A new DataFrame with the split columns.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug(
        "Splitting column '%s' delimiter='%s' mode=%s keep_original=%s",
        column,
        delimiter,
        mode,
        keep_original,
    )

    if column not in df.columns:
        msg = f"Column '{column}' not found."
        raise KeyError(msg)

    if delimiter == "":
        msg = "Delimiter must not be empty."
        raise ValueError(msg)

    # Preserve missing values as pd.NA instead of converting them to empty strings.
    s = df[column].astype("string")

    parts = (
        s.str.rsplit(delimiter, n=1, expand=True)
        if mode == "last"
        else s.str.split(delimiter, n=1, expand=True)
    )

    if parts.shape[1] == 1:
        parts[1] = pd.NA

    def _normalize_split_part(series: pd.Series) -> pd.Series:
        """Trim whitespace and normalize empty strings to pandas missing values."""
        return series.astype("string").str.strip().replace("", pd.NA).astype("string")

    left = _normalize_split_part(parts[0])
    right = _normalize_split_part(parts[1])

    new_df = df.copy()
    pos = df.columns.get_loc(column)

    if not isinstance(pos, int):
        msg_0 = f"Expected unique column location for '{column}', got {type(pos).__name__}"
        raise TypeError(msg_0)

    def _unique_name(base: str) -> str:
        if base not in new_df.columns:
            return base

        i = 2
        while f"{base}_{i}" in new_df.columns:
            i += 1

        return f"{base}_{i}"

    name_1 = _unique_name(f"{column}_1")
    name_2 = _unique_name(f"{column}_2")

    if keep_original:
        new_df.insert(pos + 1, name_1, left)
        new_df.insert(pos + 2, name_2, right)
    else:
        new_df = new_df.drop(columns=[column])
        new_df.insert(pos, name_1, left)
        new_df.insert(pos + 1, name_2, right)

    return new_df


def join_columns(
    df: pd.DataFrame,
    columns: list[str],
    *,
    delimiter: str = " ",
    new_name: str | None = None,
    keep_original: bool = True,
) -> pd.DataFrame:
    """Join multiple columns into a single string column.

    Characteristics:
    - Values are trimmed
    - Click/order order is preserved
    - New column is inserted after the last selected column
    - Output uses pandas StringDtype

    Args:
        df: Source DataFrame.
        columns: Columns to join.
        delimiter: Delimiter used between values.
        new_name: Optional name for the new column.
        keep_original: Whether to keep the original columns.

    Returns:
        A new DataFrame with the joined column.

    Raises:
        KeyError: If any column does not exist.
    """
    logger.debug(
        "Joining columns %s delimiter='%s' new_name=%r keep_original=%s",
        columns,
        delimiter,
        new_name,
        keep_original,
    )

    for col in columns:
        if col not in df.columns:
            msg = f"Column '{col}' not found."
            raise KeyError(msg)

    if not new_name:
        new_name = "_".join(columns)

    parts = [df[col].astype("string").fillna("").str.strip() for col in columns]

    joined = parts[0]
    for part in parts[1:]:
        joined = joined + delimiter + part

    new_df = df.copy()

    positions: list[int] = []

    for col in columns:
        loc = df.columns.get_loc(col)
        if not isinstance(loc, int):
            msg = f"Expected unique column location for '{col}', got {type(loc).__name__}"
            raise TypeError(msg)
        positions.append(loc)

    last_pos = max(positions)

    new_df.insert(last_pos + 1, new_name, joined.astype("string"))

    if not keep_original:
        new_df = new_df.drop(columns=columns)

    return new_df
