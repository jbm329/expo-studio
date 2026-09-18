"""Presentation helpers for semantic-aware value formatting.

This module contains UI-agnostic helpers that convert *raw values*
into display-friendly strings using SeriesSemantics.

Responsibilities:
- Format values for display based on explicit semantics
- Handle pandas / numpy missing values safely
- Contain NO Qt dependencies
- Contain NO data mutation
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from expo_jbm329.utils.format_utils import fmt_int, fmt_num

if TYPE_CHECKING:
    from expo_jbm329.services.data_profile.semantics import SeriesSemantics


# =====================================================================
# Public API
# =====================================================================
def format_value_for_display(
    value: Any,
    sem: SeriesSemantics | None,
) -> str:
    """Format a single value for display using series semantics.

    This function MUST:
    - never mutate data
    - never infer semantics implicitly
    - never depend on Qt or UI widgets
    - handle pandas missing values safely

    Args:
        value: Raw value from DataFrame / model (may be numpy / pandas scalar).
        sem: SeriesSemantics for the column, or None if unknown.

    Returns:
        A string suitable for UI display.
    """
    # --------------------------------------------------------------
    # Missing values (None, np.nan, pd.NA, NaT)
    # --------------------------------------------------------------
    if value is None or pd.isna(value):
        return ""

    # No semantics available → fallback
    if sem is None:
        return str(value)

    # --------------------------------------------------------------
    # Year: No thousand separators, no decimal part
    # --------------------------------------------------------------
    if sem.is_year_like:
        return _format_year_like(value)

    # --------------------------------------------------------------
    # Datetime: date-only presentation
    # --------------------------------------------------------------
    if sem.semantic_dtype == "datetime" and sem.is_date_only:
        return _format_date_only(value)

    # --------------------------------------------------------------
    # Numeric: integer-like floats (e.g. 2025.0)
    # --------------------------------------------------------------
    if sem.is_integer_like:
        return _format_integer_like(value)

    # Plain float (non-integer)
    if sem.semantic_dtype == "float":
        return _format_float_like(value, decimals=2)

    # Default: string conversion
    return str(value)


# =====================================================================
# Internal helpers
# =====================================================================


def _format_date_only(value: Any) -> str:
    """Format datetime-like values as YYYY-MM-DD."""
    try:
        # Python datetime
        if isinstance(value, _dt.datetime):
            return value.date().isoformat()

        if isinstance(value, _dt.date):
            return value.isoformat()

        # pandas Timestamp / NaT-safe
        if hasattr(value, "to_pydatetime"):
            return value.to_pydatetime().date().isoformat()

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
        pass

    return str(value)


def _format_integer_like(value: Any) -> str:
    """Format integer-like numeric values using locale grouping."""
    try:
        if isinstance(value, (int, float, np.integer, np.floating)):
            return fmt_int(int(value))
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
        pass
    return str(value)


def _format_float_like(value: Any, *, decimals: int = 2) -> str:
    """Format non-integer float values with fixed decimal precision."""
    try:
        if isinstance(value, (float, np.floating)):
            return fmt_num(float(value), sig=decimals)
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
        pass
    return str(value)


def _format_year_like(value: Any) -> str:
    """Format year-like values without thousand separators."""
    try:
        if isinstance(value, (int, float, np.integer, np.floating)):
            return str(int(value))
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
        pass
    return str(value)
