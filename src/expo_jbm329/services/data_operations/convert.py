"""Data type conversion utilities.

This module contains pure, UI-independent helpers for converting
DataFrame columns between common semantic data types.

It provides:
- Conversion to nullable integer (Int64)
- Conversion to float64
- Conversion to datetime64[ns]
- Conversion to pandas nullable boolean dtype

Design principles:
- Side-effect free: all functions return new DataFrames
- Explicit error handling with clear exceptions
- Predictable pandas dtypes with NA support
- No UI dependencies
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal, cast

import pandas as pd
import pandas.api.types as pdt
from pandas import CategoricalDtype

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger("applogger.service")


# =====================================================================
# Numeric conversions
# =====================================================================


def to_integer(
    df: pd.DataFrame,
    column: str,
    *,
    errors: Literal["raise", "coerce"] = "coerce",
) -> pd.DataFrame:
    """Convert a column to pandas nullable integer dtype (Int64).

    Non-parsable values become <NA> when errors="coerce".

    Args:
        df: Source DataFrame.
        column: Column to convert.
        errors: Error handling strategy.

    Returns:
        A new DataFrame with an Int64 column.

    Raises:
        KeyError: If the column does not exist.
        TypeError: If conversion fails and errors="raise".
    """
    logger.debug("to_integer: col='%s' errors=%s", column, errors)

    if column not in df.columns:
        msg = f"Column '{column}' not found."
        raise KeyError(msg)

    new_df = df.copy()

    try:
        new_df[column] = pd.to_numeric(df[column], errors=errors).astype("Int64")
    except (
        AttributeError,
        ConnectionError,
        FileNotFoundError,
        IndexError,
        KeyError,
        LookupError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        msg = f"Could not convert column '{column}' to Int64: {exc}"
        raise TypeError(msg) from exc

    return new_df


def to_float(
    df: pd.DataFrame,
    column: str,
    *,
    errors: Literal["raise", "coerce"] = "coerce",
) -> pd.DataFrame:
    """Convert a column to float64.

    Non-parsable values become NaN when errors="coerce".

    Args:
        df: Source DataFrame.
        column: Column to convert.
        errors: Error handling strategy.

    Returns:
        A new DataFrame with a float64 column.

    Raises:
        KeyError: If the column does not exist.
        TypeError: If conversion fails and errors="raise".
    """
    logger.debug("to_float: col='%s' errors=%s", column, errors)

    if column not in df.columns:
        msg = f"Column '{column}' not found."
        raise KeyError(msg)

    new_df = df.copy()

    try:
        new_df[column] = pd.to_numeric(
            df[column],
            errors=errors,
        ).astype("float64")
    except (
        AttributeError,
        ConnectionError,
        FileNotFoundError,
        IndexError,
        KeyError,
        LookupError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        msg = f"Could not convert column '{column}' to float64: {exc}"
        raise TypeError(msg) from exc

    return new_df


def to_nullable_float_series(
    series: pd.Series,
    *,
    errors: Literal["raise", "coerce"] = "coerce",
) -> pd.Series:
    """Convert a Series to pandas nullable Float64 dtype.

    Args:
        series: Series to convert.
        errors: Error handling strategy for pd.to_numeric.

    Returns:
        Series converted to pandas nullable Float64 dtype.

    Raises:
        TypeError: If conversion fails and errors="raise".
    """
    try:
        numeric = pd.to_numeric(series, errors=errors)

        if not isinstance(numeric, pd.Series):
            numeric = pd.Series(numeric, index=series.index, name=series.name)

        return numeric.astype("Float64")

    except (
        AttributeError,
        ConnectionError,
        FileNotFoundError,
        IndexError,
        KeyError,
        LookupError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        msg = f"Could not convert Series to Float64: {exc}"
        raise TypeError(msg) from exc


# =====================================================================
# Datetime conversion
# =====================================================================


def to_datetime(
    df: pd.DataFrame,
    column: str,
    *,
    fmt: str | None = None,
    dayfirst: bool = False,
    yearfirst: bool = False,
    errors: Literal["raise", "coerce", "ignore"] = "coerce",
    date_only: bool = False,
) -> pd.DataFrame:
    """Convert a column to pandas datetime64[ns].

    Args:
        df: Source DataFrame.
        column: Column to convert.
        fmt: Optional explicit datetime format.
        dayfirst: Interpret first field as day.
        yearfirst: Interpret first field as year.
        errors: Error handling strategy.
        date_only: Normalize time to 00:00:00.

    Returns:
        A new DataFrame with a datetime64[ns] column.

    Raises:
        KeyError: If the column does not exist.
        TypeError: If conversion fails and errors="raise".
    """
    logger.debug(
        "to_datetime: col='%s' fmt=%r dayfirst=%s yearfirst=%s errors=%s date_only=%s",
        column,
        fmt,
        dayfirst,
        yearfirst,
        errors,
        date_only,
    )

    if column not in df.columns:
        msg = f"Column '{column}' not found."
        raise KeyError(msg)

    new_df = df.copy()
    series = new_df[column]

    try:
        if pdt.is_datetime64_any_dtype(series):
            out = series
        elif fmt is not None:
            # When format is provided, pandas typing does NOT allow errors="ignore"
            errors_fmt = cast("Literal['raise', 'coerce']", errors)

            out = pd.to_datetime(
                series,
                format=fmt,
                errors=errors_fmt,
            )
        else:
            # For Series input, pandas typing does not allow errors="ignore"
            errors_series = cast("Literal['raise', 'coerce']", errors)

            out = pd.to_datetime(
                series,
                errors=errors_series,
                dayfirst=dayfirst,
                yearfirst=yearfirst,
            )

        # Ensure Series output (column semantics)
        if not isinstance(out, pd.Series):
            out = pd.Series(out, index=new_df.index)

        if date_only:
            out = out.dt.normalize()

        new_df[column] = out

    except (
        AttributeError,
        ConnectionError,
        FileNotFoundError,
        IndexError,
        KeyError,
        LookupError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        logger.exception("to_datetime failed col='%s'", column)
        msg = f"Could not convert column '{column}' to datetime64[ns]: {exc}"
        raise TypeError(msg) from exc

    return new_df


# =====================================================================
# Boolean conversion
# =====================================================================


def to_boolean(
    df: pd.DataFrame,
    column: str,
    *,
    true_values: Iterable[str] | None = None,
    false_values: Iterable[str] | None = None,
    errors: Literal["raise", "coerce"] = "coerce",
) -> pd.DataFrame:
    """Convert a column to pandas nullable boolean dtype ("boolean").

    String matching is case-insensitive.

    Args:
        df: Source DataFrame.
        column: Column to convert.
        true_values: Strings mapping to True.
        false_values: Strings mapping to False.
        errors: Error handling strategy.

    Returns:
        A new DataFrame with a boolean column.

    Raises:
        KeyError: If the column does not exist.
        ValueError: If unrecognized values are found and errors="raise".
    """
    logger.debug(
        "to_boolean: col='%s' true_values=%s false_values=%s errors=%s",
        column,
        true_values,
        false_values,
        errors,
    )

    if column not in df.columns:
        msg = f"Column '{column}' not found."
        raise KeyError(msg)

    s = df[column]
    new_df = df.copy()

    # --------------------------------------------------
    # Numeric path: 0 / 1 / NA
    # --------------------------------------------------
    if pdt.is_numeric_dtype(s):
        try:
            x = pd.to_numeric(s, errors="raise")
            mapped = x.map({0: False, 1: True})
            new_df[column] = mapped.astype("boolean")
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            if errors == "raise":
                msg = f"Could not convert numeric column '{column}' to boolean"
                raise ValueError(msg) from exc
            # fall through to NA
        else:
            return new_df

    # --------------------------------------------------
    # String path
    # --------------------------------------------------
    s_str = s.astype("string").str.lower()

    true_set = {"true", "1", "yes", "y", "ja"} if true_values is None else {v.lower() for v in true_values}
    false_set = {"false", "0", "no", "n", "nej"} if false_values is None else {v.lower() for v in false_values}

    result = pd.Series(pd.NA, index=s.index, dtype="boolean")

    mask_true = s_str.isin(true_set)
    mask_false = s_str.isin(false_set)

    result[mask_true] = True
    result[mask_false] = False

    mask_unmatched = ~(mask_true | mask_false)

    if bool(mask_unmatched.any(skipna=True)) and errors == "raise":
        bad = s[mask_unmatched].unique()
        msg = f"Unrecognized boolean values: {bad}"
        raise ValueError(msg)

    new_df[column] = result
    return new_df


# =====================================================================
# String & categorical conversions
# =====================================================================


def to_string(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Cast a column to pandas StringDtype.

    Args:
        df: Source DataFrame.
        column: Column to cast.

    Returns:
        A new DataFrame with StringDtype column.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug("to_string: col='%s'", column)

    if column not in df.columns:
        msg = f"Column '{column}' not found."
        raise KeyError(msg)

    new_df = df.copy()
    new_df[column] = new_df[column].astype("string")

    return new_df


def to_category(
    df: pd.DataFrame,
    column: str,
    *,
    order: Literal["alpha", "freq", "preserve"] = "alpha",
    ordered: bool = False,
    strict: bool = True,
) -> pd.DataFrame:
    """Convert a column to pandas CategoricalDtype.

    Args:
        df: Source DataFrame.
        column: Column to convert.
        order: Category ordering strategy.
            - "alpha": alphabetical order
            - "freq": descending frequency
            - "preserve": first appearance order
        ordered: Whether the categorical is ordered.
        strict: If True, categories are limited to observed values.

    Returns:
        A new DataFrame with a categorical column.

    Raises:
        KeyError: If the column does not exist.
        ValueError: If order is invalid.
    """
    logger.debug(
        "to_category: col='%s' order=%s ordered=%s strict=%s",
        column,
        order,
        ordered,
        strict,
    )

    if column not in df.columns:
        msg = f"Column '{column}' not found."
        raise KeyError(msg)

    s = df[column].astype("string")
    non_null = s.dropna()

    if order == "alpha":
        categories = sorted(pd.unique(non_null))
    elif order == "freq":
        categories = non_null.value_counts().index.tolist()
    elif order == "preserve":
        categories = list(pd.unique(non_null))
    else:
        msg = "order must be one of: 'alpha' | 'freq' | 'preserve'"
        raise ValueError(msg)

    dtype = CategoricalDtype(categories=categories, ordered=ordered)

    cat = pd.Categorical(s, dtype=dtype) if strict else pd.Categorical(s, categories=categories, ordered=ordered)

    new_df = df.copy()
    new_df[column] = pd.Series(cat, index=s.index, name=s.name)

    return new_df
