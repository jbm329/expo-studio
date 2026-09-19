"""Data type inspection and classification utilities.

This module centralizes all logic related to inspecting, classifying,
and reasoning about pandas Series and DataFrame column dtypes.

It provides:
- Semantic dtype classification (int, float, bool, datetime, string, other)
- Robust checks for text-like and categorical data
- UI-facing helpers that operate on view-column indices
- Defensive behavior to avoid crashes during dtype introspection

Design principles:
- No UI dependencies
- No mutation of input DataFrames
- Clear semantic separation between *dtype* and *meaning*
- Safe fallbacks for mixed or unexpected pandas dtypes
"""

from __future__ import annotations

from enum import StrEnum

import pandas as pd
import pandas.api.types as pdt
from pandas import CategoricalDtype


class SemanticDType(StrEnum):
    """Semantic dtype classification for pandas Series and DataFrames.

    This enum provides a simplified representation of common data types
    encountered in data analysis, suitable for UI and profiling purposes.
    """

    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    DATETIME = "datetime"
    STRING = "string"
    CATEGORY = "category"
    OTHER = "other"


# =====================================================================
# High-level dtype classification
# =====================================================================
def classify_series_dtype(s: pd.Series) -> SemanticDType:
    """Classify a pandas Series into a simplified semantic dtype.

    The classification is intended for UI logic and profiling,
    not for low-level pandas internals.

    Args:
        s: The pandas Series to classify.

    Returns:
        One of:
            - "int"
            - "float"
            - "bool"
            - "datetime"
            - "string"
            - "category"
            - "other"
    """
    # Category
    if isinstance(s.dtype, CategoricalDtype):
        return SemanticDType.CATEGORY

    # Integer (nullable Int64 included)
    if pdt.is_integer_dtype(s):
        return SemanticDType.INT

    # Float (including float columns that conceptually contain integers)
    if pdt.is_float_dtype(s):
        return SemanticDType.FLOAT

    # Boolean (nullable boolean included)
    if pdt.is_bool_dtype(s):
        return SemanticDType.BOOL

    # Datetime (any resolution)
    if pdt.is_datetime64_any_dtype(s):
        return SemanticDType.DATETIME

    # Maybe bool
    if pdt.is_object_dtype(s):
        sample = s.dropna().head(500)
        if not sample.empty and sample.map(lambda v: isinstance(v, bool)).all():
            return SemanticDType.BOOL

    # Semantic text-like or maybe datetime

    if is_text_like_dtype(s):
        return SemanticDType.STRING

    return SemanticDType.OTHER


# =====================================================================
# Semantic dtype helpers
# =====================================================================


def is_text_like_dtype(series: pd.Series) -> bool:
    """Check whether a Series is semantically text-like.

    Returns True for:
    - pandas StringDtype
    - object dtype
    - CategoricalDtype with string-like categories

    This is a semantic definition used by both UI logic and profiling.

    Args:
        series: pandas Series to inspect.

    Returns:
        True if the Series should be treated as text.
    """
    try:
        if pdt.is_string_dtype(series):
            return True

        if isinstance(series.dtype, CategoricalDtype):
            from typing import cast

            cat_dtype = cast("CategoricalDtype", series.dtype)
            cats = cat_dtype.categories
            return pdt.is_string_dtype(cats) or pdt.is_object_dtype(cats)

        if pdt.is_object_dtype(series):
            sample = series[series.notna()].head(1000)
            return bool(sample.map(lambda v: isinstance(v, str)).all())

        return False

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
    ):
        return False


def is_categorical_series(series: pd.Series) -> bool:
    """Check whether a Series has a categorical dtype.

    Args:
        series: pandas Series to inspect.

    Returns:
        True if the Series is categorical.
    """
    return classify_series_dtype(series) == SemanticDType.CATEGORY


def is_numeric_series(series: pd.Series, *, include_bool: bool = False) -> bool:
    """Check whether a Series should be treated as numeric.

    Args:
        series: Series to inspect.
        include_bool: Whether boolean columns should count as numeric.

    Returns:
        True if the Series is semantically numeric.
    """
    semantic = classify_series_dtype(series)

    if semantic in {SemanticDType.INT, SemanticDType.FLOAT}:
        return True

    return bool(include_bool and semantic == SemanticDType.BOOL)


def get_numeric_columns(
    df: pd.DataFrame,
    *,
    include_bool: bool = False,
) -> list[str]:
    """Return columns that should be treated as numeric.

    Args:
        df: DataFrame to inspect.
        include_bool: Whether boolean columns should count as numeric.

    Returns:
        Column names classified as numeric.
    """
    numeric_columns: list[str] = []

    for idx, column in enumerate(df.columns):
        series = df.iloc[:, idx]

        if is_numeric_series(series, include_bool=include_bool):
            numeric_columns.append(str(column))

    return numeric_columns
