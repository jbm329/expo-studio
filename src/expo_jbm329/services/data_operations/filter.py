"""Row filtering utilities.

This module contains pure, UI-independent helpers for filtering
rows in pandas DataFrames based on column values, comparisons,
and custom predicates.

It provides:
- Equality and inequality filters
- String containment filters
- NA / not-NA filters
- Numeric and datetime comparisons
- Custom predicate-based filtering

Design principles:
- Side-effect free: all functions return new DataFrames
- Explicit error handling
- Clear separation between numeric, datetime, and text semantics
- No UI dependencies
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pandas as pd
import pandas.api.types as pdt

logger = logging.getLogger("applogger.service")


# =====================================================================
# Basic equality filters
# =====================================================================

def filter_equals(
    df: pd.DataFrame,
    column: str,
    value: Any,
    *,
    case: bool = True,
) -> pd.DataFrame:
    """Return rows where df[column] == value.

    Args:
        df: Source DataFrame.
        column: Column to compare.
        value: Value to match.
        case: Whether comparison is case sensitive (text only).

    Returns:
        Filtered DataFrame.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug(
        "filter_equals: col='%s' value=%r case=%s",
        column,
        value,
        case,
    )

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    s = df[column]

    # --------------------------------------------------
    # Text comparison
    # --------------------------------------------------
    if isinstance(value, str):
        s_str = s.astype("string")

        mask = s_str == value if case else s_str.str.casefold() == value.casefold()

        return df.loc[mask].copy()

    # --------------------------------------------------
    # Fallback: numeric / datetime / bool
    # --------------------------------------------------

    mask: pd.Series[bool] = s == value
    return df.loc[mask].copy()


def filter_not_equals(
    df: pd.DataFrame,
    column: str,
    value: Any,
) -> pd.DataFrame:
    """Return rows where df[column] != value.

    NA-handling:
        - If value is NA, returns rows where column is not NA.

    Args:
        df: Source DataFrame.
        column: Column to compare.
        value: Value to exclude.

    Returns:
        Filtered DataFrame.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug("filter_not_equals: col='%s' value=%r", column, value)

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    s = df[column]

    if pd.isna(value):
        return df.loc[s.notna()].copy()

    return df.loc[s.ne(value)].copy()


# =====================================================================
# String-based filters
# =====================================================================

def filter_contains(
    df: pd.DataFrame,
    column: str,
    substring: str,
    *,
    case: bool = True,
) -> pd.DataFrame:
    """Return rows where the column contains a substring.

    Args:
        df: Source DataFrame.
        column: Column to search.
        substring: Substring to look for.
        case: Whether matching is case-sensitive.

    Returns:
        Filtered DataFrame.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug(
        "filter_contains: col='%s' substring=%r case=%s",
        column,
        substring,
        case,
    )

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    s = df[column].astype("string")

    return df.loc[
        s.str.contains(substring, case=case, na=False)
    ].copy()


# =====================================================================
# NA filters
# =====================================================================

def filter_isna(
    df: pd.DataFrame,
    column: str,
) -> pd.DataFrame:
    """Return rows where df[column] is NA.

    Args:
        df: Source DataFrame.
        column: Column to check.

    Returns:
        Filtered DataFrame.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug("filter_isna: col='%s'", column)

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    return df.loc[df[column].isna()].copy()


def filter_notna(
    df: pd.DataFrame,
    column: str,
) -> pd.DataFrame:
    """Return rows where df[column] is not NA.

    Args:
        df: Source DataFrame.
        column: Column to check.

    Returns:
        Filtered DataFrame.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug("filter_notna: col='%s'", column)

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    return df.loc[df[column].notna()].copy()


# =====================================================================
# Comparison-based filters
# =====================================================================

def filter_compare(
    df: pd.DataFrame,
    column: str,
    op: str,
    value: Any,
) -> pd.DataFrame:
    """Filter rows by comparing a column to a value.

    Supported operators:
        ">", ">=", "<", "<=", "==", "!="

    The column must be numeric or datetime-like.

    Args:
        df: Source DataFrame.
        column: Column to compare.
        op: Comparison operator.
        value: Comparison value.

    Returns:
        Filtered DataFrame.

    Raises:
        KeyError: If the column does not exist.
        TypeError: If the column is not numeric or datetime.
        ValueError: If the operator is invalid.
    """
    logger.debug(
        "filter_compare: col='%s' op='%s' value=%r",
        column,
        op,
        value,
    )

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    s = df[column]

    if pdt.is_numeric_dtype(s):
        compare_value = value

    elif pdt.is_datetime64_any_dtype(s):
        compare_value = pd.to_datetime(value)

    else:
        raise TypeError(
            f"Column '{column}' must be numeric or datetime for filter_compare."
        )

    return df.query(f"`{column}` {op} @compare_value").copy()


def filter_between(
    df: pd.DataFrame,
    column: str,
    low: Any,
    high: Any,
    *,
    inclusive: str = "both",
) -> pd.DataFrame:
    """Filter rows where column values lie between two bounds.

    Supports numeric and datetime columns.

    Args:
        df: Source DataFrame.
        column: Column to compare.
        low: Lower bound.
        high: Upper bound.
        inclusive: Boundary inclusion mode.

    Returns:
        Filtered DataFrame.

    Raises:
        KeyError: If the column does not exist.
        TypeError: If the column is not numeric or datetime.
        ValueError: If inclusive is invalid.
    """
    logger.debug(
        "filter_between: col='%s' low=%r high=%r inclusive=%s",
        column,
        low,
        high,
        inclusive,
    )

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    if inclusive not in {"both", "left", "right", "neither"}:
        raise ValueError(
            "inclusive must be one of: both | left | right | neither"
        )

    s = df[column]

    if pdt.is_datetime64_any_dtype(s):
        low_val = pd.to_datetime(low)
        high_val = pd.to_datetime(high)

    elif pdt.is_numeric_dtype(s):
        low_val = low
        high_val = high

    else:
        raise TypeError(
            f"Column '{column}' must be numeric or datetime for filter_between."
        )

    mask = s.between(low_val, high_val, inclusive=inclusive)

    return df.loc[mask].copy()


# =====================================================================
# Custom predicate
# =====================================================================

def filter_custom(
    df: pd.DataFrame,
    predicate: Callable[[pd.DataFrame], pd.Series],
) -> pd.DataFrame:
    """Filter rows using a custom boolean predicate.

    The predicate must return a boolean pandas Series
    aligned with the DataFrame index.

    Example:
        df2 = filter_custom(df, lambda d: d["age"] > 60)

    Args:
        df: Source DataFrame.
        predicate: Function producing a boolean mask.

    Returns:
        Filtered DataFrame.

    Raises:
        ValueError: If predicate does not return a Series.
    """
    mask = predicate(df)

    if not isinstance(mask, pd.Series):
        raise ValueError(
            "filter_custom predicate must return a pandas Series."
        )

    return df.loc[mask].copy()
