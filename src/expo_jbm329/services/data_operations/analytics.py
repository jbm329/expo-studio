"""Lightweight DataFrame analytics helpers.

This module provides small, UI-independent helper functions for
basic DataFrame analytics and inspection.

It is intentionally lightweight and focused on:
- High-level summaries
- Missing-data statistics
- Column profiling

Design principles:
- Side-effect free: all functions return new DataFrames
- Thin wrappers around pandas primitives
- No UI dependencies
- Predictable, test-friendly output
"""

from __future__ import annotations

import logging

import pandas as pd

from expo_jbm329.services.data_profile.column_data_profile import profile_series

logger = logging.getLogger("applogger.service")


# =====================================================================
# Summary helpers
# =====================================================================
def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """Return a transposed summary of the DataFrame.

    For empty DataFrames (no columns), an empty DataFrame is returned.
    """
    if df.shape[1] == 0:
        return pd.DataFrame()

    return df.describe(include="all").T


# =====================================================================
# Missing-data statistics
# =====================================================================

def null_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Return null counts and percentages per column.

    The resulting DataFrame contains:
        - nulls: absolute count of missing values
        - pct_null: percentage of missing values

    Args:
        df: Source DataFrame.

    Returns:
        A DataFrame indexed by column name with null statistics.
    """
    total_rows = len(df)

    data = {
        "nulls": df.isna().sum(),
        "pct_null": (df.isna().sum() / total_rows * 100)
        if total_rows > 0
        else 0.0,
    }

    return pd.DataFrame(data)


# =====================================================================
# Column profiling
# =====================================================================

def get_column_profile(
    df: pd.DataFrame,
    column: str,
):
    """Return a profile object for a DataFrame column.

    This function delegates to `profile_series` and exists primarily
    to keep the profiling API stable and decoupled from UI and
    transformation logic.

    Args:
        df: Source DataFrame.
        column: Column name to profile.

    Returns:
        A ColumnProfile object as returned by `profile_series`.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug("get_column_profile: col='%s'", column)

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    return profile_series(df[column], name=column)
