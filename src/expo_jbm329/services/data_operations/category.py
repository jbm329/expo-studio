"""Categorical data helpers.

This module contains pure, UI-independent helpers for working with
pandas CategoricalDtype columns.

It provides:
- Conversion to categorical with configurable ordering strategies
- Safe renaming of individual categories
- Explicit category reordering
- Removal of unused categories

Design principles:
- Side-effect free: all functions return new DataFrames
- Explicit and predictable category semantics
- Robust handling of category collisions
- No UI dependencies
"""

from __future__ import annotations

import logging
from typing import Any, cast

import pandas as pd
from pandas import CategoricalDtype

from .dtypes import is_categorical_series

logger = logging.getLogger("applogger.service")


# =====================================================================
# Category maintenance
# =====================================================================


def category_remove_unused(
    df: pd.DataFrame,
    column: str,
) -> pd.DataFrame:
    """Remove unused categories from a categorical column.

    No-op if the column is not categorical.

    Args:
        df: Source DataFrame.
        column: Column to clean.

    Returns:
        A new DataFrame with unused categories removed.
    """
    logger.debug("category_remove_unused: col='%s'", column)

    if column not in df.columns:
        msg = f"Column '{column}' not found."
        raise KeyError(msg)

    s = df[column]

    if not is_categorical_series(s):
        return df.copy()

    new_df = df.copy()
    new_df[column] = s.cat.remove_unused_categories()

    return new_df


# =====================================================================
# Category value manipulation
# =====================================================================


def category_rename_single(
    df: pd.DataFrame,
    column: str,
    old: object,
    new: object,
) -> pd.DataFrame:
    """Rename a single category value.

    If renaming causes category collisions, the column is
    temporarily materialized as StringDtype and rebuilt.

    Args:
        df: Source DataFrame.
        column: Target column.
        old: Existing category value.
        new: New category value.

    Returns:
        A new DataFrame with the renamed category.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug(
        "category_rename_single: col='%s' old=%r new=%r",
        column,
        old,
        new,
    )

    if column not in df.columns:
        msg = f"Column '{column}' not found."
        raise KeyError(msg)

    s = df[column]
    replacement_map = cast("Any", {old: new})
    new_s: pd.Series

    if is_categorical_series(s):
        try:
            new_s = s.cat.rename_categories(lambda c: new if c == old else c)
        except (ValueError, TypeError):
            # Collision or invalid mapping -> rebuild categories
            tmp = s.astype("string").replace(replacement_map)
            categories = list(pd.unique(tmp.dropna()))
            dtype = CategoricalDtype(
                categories=categories,
                ordered=getattr(s.dtype, "ordered", False),
            )
            new_s = pd.Series(
                pd.Categorical(tmp, dtype=dtype),
                index=s.index,
                name=s.name,
            )
    else:
        new_s = s.astype("string").replace(replacement_map)

    new_df = df.copy()
    new_df[column] = new_s

    return new_df


# =====================================================================
# Explicit ordering
# =====================================================================


def category_set_order(
    df: pd.DataFrame,
    column: str,
    order_list: list[str],
    *,
    ordered: bool = True,
    strict: bool = True,
    append_missing_tail: bool = True,
) -> pd.DataFrame:
    """Set an explicit category order.

    Args:
        df: Source DataFrame.
        column: Column to reorder.
        order_list: Desired category order.
        ordered: Whether the categorical should be ordered.
        strict: If True, values not in order_list become NA.
        append_missing_tail: If strict=False, append missing
            observed values after order_list.

    Returns:
        A new DataFrame with reordered categories.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug(
        "category_set_order: col='%s' ordered=%s strict=%s append_missing=%s",
        column,
        ordered,
        strict,
        append_missing_tail,
    )

    if column not in df.columns:
        msg = f"Column '{column}' not found."
        raise KeyError(msg)

    s = df[column].astype("string")

    categories: list[str] = []

    for c in order_list:
        if c is None:
            continue

        c_str = str(c).strip()
        if c_str:
            categories.append(c_str)

    if not strict and append_missing_tail:
        extras = [v for v in pd.unique(s.dropna()) if v not in categories]
        categories = categories + extras

    dtype = CategoricalDtype(categories=categories, ordered=ordered)

    new_df = df.copy()
    new_df[column] = pd.Series(
        pd.Categorical(s, dtype=dtype),
        index=s.index,
        name=s.name,
    )

    return new_df
