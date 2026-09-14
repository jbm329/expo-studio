"""Missing-data handling utilities.

This module contains pure, UI-independent helpers for handling
missing data (NA / NaN) in pandas DataFrames.

It provides:
- Generic fillna for arbitrary values
- Common statistical fill strategies (mean, median, mode)
- Conversion of empty or whitespace-only strings to NA

Design principles:
- Side-effect free: all functions return new DataFrames
- Explicit error handling
- No implicit dtype coercion beyond pandas defaults
- No UI dependencies
"""

from __future__ import annotations

from typing import Any

import pandas as pd


# =====================================================================
# Generic fill helpers
# =====================================================================
def fillna(
    df: pd.DataFrame,
    column: str,
    value: Any,
) -> pd.DataFrame:
    """Fill missing values in a column with a given value.

    Args:
        df: Source DataFrame.
        column: Column to modify.
        value: Value used to fill missing entries.

    Returns:
        A new DataFrame with missing values filled.

    Raises:
        KeyError: If the column does not exist.
    """
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    new_df = df.copy()
    new_df[column] = new_df[column].fillna(value)

    return new_df


# =====================================================================
# Statistical fill strategies
# =====================================================================

def fillna_mean(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Fill missing values with the column mean.

    Intended for numeric columns only.

    Args:
        df: Source DataFrame.
        column: Column to modify.

    Returns:
        A new DataFrame with NA values replaced by the mean.

    Raises:
        KeyError: If the column does not exist.
    """
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    mean_value = df[column].mean()
    return fillna(df, column, mean_value)


def fillna_median(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Fill missing values with the column median.

    Intended for numeric columns only.

    Args:
        df: Source DataFrame.
        column: Column to modify.

    Returns:
        A new DataFrame with NA values replaced by the median.

    Raises:
        KeyError: If the column does not exist.
    """
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    median_value = df[column].median()
    return fillna(df, column, median_value)


def fillna_mode(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Fill NA values with the most frequent value (mode).

    If no mode exists (e.g. all values are NA), this function
    returns a copy of the original DataFrame unchanged.
    """
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    mode = df[column].mode()

    # No mode -> no-op
    if mode.empty:
        return df.copy()

    value = mode.iloc[0]
    return fillna(df, column, value)


# =====================================================================
# String-specific helpers
# =====================================================================

def replace_empty_with_nan(
    df: pd.DataFrame,
    column: str,
) -> pd.DataFrame:
    """Replace empty or whitespace-only strings with NA.

    This function treats:
        - "" (empty string)
        - strings containing only whitespace

    as missing values.

    Args:
        df: Source DataFrame.
        column: Column to modify.

    Returns:
        A new DataFrame with empty strings replaced by NA.

    Raises:
        KeyError: If the column does not exist.
    """
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    s = df[column].replace(r"^\s*$", pd.NA, regex=True)

    new_df = df.copy()
    new_df[column] = s

    return new_df
