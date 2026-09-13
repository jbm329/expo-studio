"""Semantic interpretation of data.

This module answers the question:
    "What does this column look like semantically?"

It MUST NOT:
- contain UI logic
- contain menu logic
- perform data mutation
"""

from __future__ import annotations

import datetime as _dt
import warnings
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from expo_jbm329.services.data_operations.dtypes import classify_series_dtype

errors: Literal["raise", "coerce"] = "coerce"


@dataclass(frozen=True)
class SeriesSemantics:
    """Semantic interpretation of a pandas Series.

    This describes *what the data looks like*, not how it is stored
    and not how it should be displayed.
    """

    semantic_dtype: str

    # Numeric semantics
    is_integer_like: bool = False
    is_year_like: bool = False

    # Datetime semantics
    has_time_component: bool = False
    is_date_only: bool = False

    # Text semantics
    cardinality_ratio: float | None = None

    # Sample size (non-null)
    sample_size: int | None = None

    #  convertibility (pure analysis results)
    can_be_int: bool = False
    can_be_float: bool = False
    can_be_datetime: bool = False
    can_be_bool: bool = False


def infer_series_semantics(s: pd.Series) -> SeriesSemantics:
    """Infer semantic properties of a pandas Series.

    This function MUST:
    - never mutate data
    - never convert dtype
    - be deterministic
    - be safe for large Series
    """
    semantic_dtype = classify_series_dtype(s)
    can_be_int = False
    can_be_float = False
    can_be_datetime = False
    can_be_bool = False
    
    non_null = s.dropna()
    sample_size = len(non_null)
    x_num: pd.Series | None = None

    if non_null.empty:
        # No semantic inference possible without non-null values
        return SeriesSemantics(semantic_dtype=semantic_dtype)

    # --------------------------------------------------------------
    # Shared parsing
    # --------------------------------------------------------------

    try:
        with warnings.catch_warnings(record=False):
            warnings.simplefilter("ignore", UserWarning)
            x_raw = pd.to_numeric(non_null, errors="raise")

        x_num = x_raw if isinstance(x_raw, pd.Series) else pd.Series(x_raw, index=non_null.index)

    except Exception:
        pass

    if x_num is not None:
        can_be_float = True
        can_be_int = bool((x_num % 1 == 0).all())
    else:
        can_be_float = False
        can_be_int = False

    # ------------------------------------------------------------------
    # Numeric semantics
    # ------------------------------------------------------------------
    is_integer_like = False
    is_year_like = False

    # Is it a year?

    if x_num is not None:
        is_integer_like = bool((x_num % 1 == 0).all())

        if can_be_int:
            xmin = int(x_num.min())
            xmax = int(x_num.max())
            is_year_like = 1800 <= xmin <= 2200 and 1800 <= xmax <= 2200

    # ------------------------------------------------------------------
    # Datetime semantics
    # ------------------------------------------------------------------
    has_time_component = False
    is_date_only = False

    if semantic_dtype == "datetime":
        x = pd.to_datetime(non_null, errors=errors)

        if not x.empty:
            times = x.dt.time
            has_time_component = bool((times != _dt.time(0, 0, 0)).any())
            # date-only means all times are exactly midnight
            is_date_only = not has_time_component

    # Can be datetime?
    try:
        with warnings.catch_warnings(record=False):
            warnings.simplefilter("ignore", UserWarning)

            sample = non_null.iloc[: min(100, sample_size)]
            parsed = pd.to_datetime(sample, errors=errors)
            success_ratio = parsed.notna().mean()

            can_be_datetime = bool(success_ratio > 0.9)

    except Exception:
        pass

    # ------------------------------------------------------------------
    # Bool semantics
    # ------------------------------------------------------------------

    # Can be bool?
    try:
        # Try string interpretation
        lowered = non_null.astype(str).str.lower()
        if lowered.isin({"true", "false", "0", "1", "yes", "no"}).all():
            can_be_bool = True
        elif x_num is not None:
            can_be_bool = bool(x_num.isin({0, 1}).all())

    except Exception:
        pass

    # ------------------------------------------------------------------
    # Text semantics
    # ------------------------------------------------------------------
    cardinality_ratio: float | None = None

    if semantic_dtype in ("string", "category"):        
        cardinality_ratio = non_null.nunique() / sample_size   

    return SeriesSemantics(
        semantic_dtype=semantic_dtype,

        # Numeric
        is_integer_like=is_integer_like,
        is_year_like=is_year_like,

        # Datetime
        has_time_component=has_time_component,
        is_date_only=is_date_only,

        # Text
        cardinality_ratio=cardinality_ratio,
        sample_size=sample_size,

        # Convertibility
        can_be_int=can_be_int,
        can_be_float=can_be_float,
        can_be_datetime=can_be_datetime,
        can_be_bool=can_be_bool,
    )
