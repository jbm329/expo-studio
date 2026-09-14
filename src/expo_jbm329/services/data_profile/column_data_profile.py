"""Column-level profiling utilities for pandas Series objects.

This module provides robust and UI-independent profiling logic for
computing descriptive statistics and simple visualization specs
(histograms, top-N bars, weekday bars, boolean bars).
"""
from __future__ import annotations

import contextlib
from collections.abc import Hashable
from dataclasses import dataclass, field
from numbers import Real
from typing import Any, Literal

import numpy as np
import pandas as pd

from expo_jbm329.services.data_operations.dtypes import SemanticDType, classify_series_dtype

# ============================================================
# Error handling
# ============================================================

errors: Literal["raise", "coerce"] = "coerce"

# ============================================================
# DISPLAY POLICY
# ============================================================

DISPLAY_DTYPE = {
    "int": "int",
    "float": "float",
    "bool": "bool",
    "datetime": "datetime",
    "string": "string",
    "category": "category",
    "other": "other",
}


# =====================================================================
# Plot specification model
# =====================================================================

@dataclass
class PlotSpec:
    """Lightweight descriptor for plotting instructions.

    Attributes:
        kind: One of "hist", "bar_topn", "bar_weekday", "bar_bool", or None.
        bins: Histogram bin edges (floats) for numeric plots.
        counts: Corresponding counts for each bin/bar.
        labels: Category/weekday labels when applicable.
    """
    kind: Literal["hist", "bar_topn", "bar_weekday", "bar_bool"] | None = None
    bins: list[float] | None = None
    counts: list[int] | None = None
    labels: list[str] | None = None


@dataclass
class ColumnProfile:
    """Container for column-level profiling output.

    Attributes:
        name: Column name being profiled.
        semantic_dtype: Semantic data type of the column.
        storage_dtype: Storage data type of the column as reported by pandas.
        stats: Dictionary of computed metrics (e.g., counts, missingness).
        plot: A PlotSpec describing how to visualize the data, if applicable.
    """
    name: str
    semantic_dtype: SemanticDType
    storage_dtype: str
    stats: dict[str, Any] = field(default_factory=dict)
    plot: PlotSpec = field(default_factory=PlotSpec)


# =====================================================================
# Internal helpers
# =====================================================================

def _safe_memory_usage(series: pd.Series) -> int:
    """Compute memory usage (bytes) for a Series with maximum safety.

    Returns 0 only if both deep and non-deep calculations fail.
    """
    try:
        return int(series.memory_usage(deep=True))
    except Exception:
        try:
            return int(series.memory_usage(deep=False))
        except Exception:
            return 0


def _topn_text(series: pd.Series, n: int = 3) -> list[tuple[str, int]]:
    """Compute top-N most common text values (absolute counts only).

    Returns:
        List of (value_as_string, count)
    """
    x = series.dropna().astype(str)
    if x.empty:
        return []

    vc = x.value_counts().head(n)
    return [(str(k), int(v)) for k, v in vc.items()]


def _format_samples(series: pd.Series) -> list[Any]:
    """Return up to three raw example values from the series.

    This function MUST NOT:
    - format values for display
    - infer date-only semantics
    - convert values to strings

    Presentation is handled in the UI layer.
    """
    try:
        non_null = series.dropna()
        if non_null.empty:
            return []

        # Keep original order, unique values
        return list(non_null.unique()[:3])

    except Exception:
        return []


def _any_bool_safe(bools: pd.Series) -> bool:
    """Robust 'any' for a series-like of truthy values.

    Works regardless of pandas dtype, including categorical and nullable booleans.
    """
    try:
        return bool(pd.Series(bools, copy=False).to_numpy(dtype=bool, na_value=False).any())
    except Exception:
        # Last-resort fallback (very robust, slightly slower for huge series)
        return any(bool(x) for x in pd.Series(bools, copy=False).astype(object).tolist())


def _dget_scalar(desc: pd.Series, key: str, default: float = np.nan) -> float:
    """Coerce to float, return default if fails.

    Args:
        desc: Series-like object containing description data.
        key: Key to retrieve from description.
        default: Default value to return if coercion fails.

    Returns:
        Coerced float value or default.
    """
    try:
        val = desc.get(key, default)
        if isinstance(val, Real):
            return float(val)
        return float(default)
    except Exception:
        return float(default)


def _as_float(val: object, default: float = 0.0) -> float:
    """Coerce to float, return default if fails.

    Args:
        val: Value to coerce.
        default: Default value to return if coercion fails.

    Returns:
        Coerced float value or default.
    """
    if isinstance(val, Real):
        return float(val)
    return default


def _name_to_str(value: Hashable | None) -> str:
    """Convert column name to string safely."""
    if value is None:
        return "column"
    # Hashable comes from pandas typing; all objects have __str__ at runtime
    return str(value)


# =====================================================================
# Numeric profiling
# =====================================================================

def _numeric_profile(s: pd.Series) -> tuple[dict[str, Any], PlotSpec]:
    """Perform numeric profiling on a Series.

    Includes:
    - Integer recognition for display
    - Robust histogram
    """
    # Normalize numeric values (coerce errors)
    x = pd.Series(pd.to_numeric(s, errors=errors), index=s.index)
    x = x.replace([np.inf, -np.inf], np.nan).dropna()

    m = int(x.shape[0])
    out: dict[str, Any] = {}
    plot = PlotSpec()

    if m == 0:
        return out, plot

    # Basic descriptive statistics
    desc = x.describe(percentiles=[0.25, 0.5, 0.75])

    out.update({
        "num.min": _dget_scalar(desc, "min"),
        "num.q1": _dget_scalar(desc, "25%"),
        "num.median": _dget_scalar(desc, "50%"),
        "num.q3": _dget_scalar(desc, "75%"),
        "num.max": _dget_scalar(desc, "max"),
        "num.mean": _dget_scalar(desc, "mean"),
        "num.std": _as_float(x.std() if m > 1 else 0.0),
    })

    # Extra metrics
    with contextlib.suppress(Exception):
        med = _as_float(x.median())
        mad = _as_float(np.median(np.abs(x - med)))
        out["num.mad"] = mad

    with contextlib.suppress(Exception):
        out["num.skew"] = _as_float(x.skew())

    with contextlib.suppress(Exception):
        out["num.kurtosis"] = _as_float(x.kurtosis())

    # Zero / negative / positive counts (+ percentages as raw floats for GUI fmt_pct)
    zeros = int((x == 0).sum())
    negs = int((x < 0).sum())
    pos = int((x > 0).sum())

    out.update({
        "num.zeros.n": zeros,
        "num.zeros.pct": zeros / m,
        "num.neg.n": negs,
        "num.neg.pct": negs / m,
        "num.pos.n": pos,
        "num.pos.pct": pos / m,
    })

    # Histogram plot spec
    with contextlib.suppress(Exception):
        arr = x.to_numpy(copy=False)
        # Freedman Diaconis or sqrt rule; we use sqrt(m) bounded to [5, 30]
        bins_count = min(30, max(5, int(np.sqrt(m))))
        counts, bins = np.histogram(arr, bins=bins_count)
        plot.kind = "hist"
        plot.counts = counts.tolist()
        plot.bins = bins.tolist()

    return out, plot


# =====================================================================
# Datetime profiling
# =====================================================================

def _datetime_profile(s: pd.Series):
    """Datetime profiling with date-only detection.

    - min/max
    - span (days or seconds)
    - weekday distribution
    """
    x = pd.to_datetime(s, errors=errors).dropna()
    out: dict[str, Any] = {}
    plot = PlotSpec()

    if x.empty:
        return out, plot

    mn, mx = x.min(), x.max()

    # Keep as string to avoid tz/no-tz repr quirks
    out["dt.min"] = mn
    out["dt.max"] = mx
    out["dt.span.seconds"] = int((mx - mn).total_seconds())

    with contextlib.suppress(Exception):
        wday = x.dt.weekday.value_counts().sort_index()
        plot.kind = "bar_weekday"

        plot.labels = [
            "weekday.mon",
            "weekday.tue",
            "weekday.wed",
            "weekday.thu",
            "weekday.fri",
            "weekday.sat",
            "weekday.sun",
        ]

        plot.counts = [int(wday.get(i, 0)) for i in range(7)]

    return out, plot


# =====================================================================
# Boolean profiling
# =====================================================================

def _bool_profile(s: pd.Series):
    """Profile a boolean series.

    Args:
        s: The boolean series to profile.

    Returns:
        tuple[dict[str, Any], PlotSpec]: The profile results and plot specification.
    """
    x = s.dropna()
    out: dict[str, Any] = {}
    plot = PlotSpec()

    if x.empty:
        return out, plot

    true_n = int(x.eq(True).sum())
    false_n = int(x.eq(False).sum())

    m = int(x.shape[0])

    out.update({
        "bool.true.n": true_n,
        "bool.true.pct": true_n / m,
        "bool.false.n": false_n,
        "bool.false.pct": false_n / m,
    })

    plot.kind = "bar_bool"

    plot.labels = [
        "bool.false",
        "bool.true",
    ]

    plot.counts = [false_n, true_n]

    return out, plot


# =====================================================================
# Text / object / category profiling
# =====================================================================

def _text_or_category_profile(s: pd.Series):
    """Profile textual or categorical data.

    Includes:
    - top-3 frequency table
    - string-length metrics (min/median/max/mean)
    - robust handling of non-string coercion issues.
    """
    out: dict[str, Any] = {}
    plot = PlotSpec()

    # Safe coercion to string
    try:
        x = s.dropna().astype(str)
    except Exception:
        out["note.bytes"] = True
        return out, plot

    m = int(x.shape[0])
    if m == 0:
        return out, plot

    # Top-N frequencies
    with contextlib.suppress(Exception):
        topn = _topn_text(x, 3)
        if topn:
            out["text.topn"] = topn
            plot.kind = "bar_topn"
            plot.labels = [k for k, _ in topn]
            plot.counts = [v for _, v in topn]

    # String length metrics
    with contextlib.suppress(Exception):
        lengths = x.str.len().describe()

        out.update({
            "text.len.min": int(lengths["min"]),
            "text.len.median": int(lengths["50%"]),
            "text.len.max": int(lengths["max"]),
            "text.len.mean": float(lengths["mean"]),
        })

    return out, plot


# =====================================================================
# Public API
# =====================================================================

def profile_series(s: pd.Series, name: str | None = None) -> ColumnProfile:
    """Produce a full profile for a pandas Series.

    The profiling logic dispatches based on dtype:
      • boolean          → _bool_profile
      • numeric          → _numeric_profile
      • datetime         → _datetime_profile
      • object/string    → _text_or_category_profile

    Args:
        s: The pandas Series to profile.
        name: Optional name for the series. Defaults to s.name or "column".

    Returns:
        A ColumnProfile object containing stats and plot specs.

    Base statistics always include:
      • count, missing count, missing percentage
      • unique count, unique percentage
      • memory usage (bytes)
      • sample example values
    """
    final_name = _name_to_str(name if name is not None else s.name)

    n = int(s.shape[0])
    n_missing = int(s.isna().sum())
    n_unique = int(s.nunique(dropna=True))
    mem = _safe_memory_usage(s)

    base: dict[str, Any] = {
        "count.n": n,
        "missing.n": n_missing,
        "missing.pct": (n_missing / n) if n else 0.0,
        "unique.n": n_unique,
        "unique.pct": (n_unique / (n - n_missing)) if (n - n_missing) > 0 else 0.0,
        "memory.bytes": mem,
    }

    # --- SAFE BYTES CHECK (works also for categorical) ---
    # Defuse categorical semantics so the mapping does not yield a Categorical
    s_non_na_obj = s.dropna().astype(object)
    flags = s_non_na_obj.map(lambda v: isinstance(v, (bytes, bytearray)))
    has_bytes = _any_bool_safe(flags)

    if has_bytes:
        return ColumnProfile(
            name=final_name,
            semantic_dtype=SemanticDType.OTHER,
            storage_dtype=s.dtype.name,
            stats={
                "count.n": n,
                "note.bytes": True,
                "note.bytes.dtype": s.dtype.name,
            },
            plot=PlotSpec(),
        )

    # Example values
    with contextlib.suppress(Exception):
        samples = _format_samples(s)
        if samples:
            base["sample.values"] = samples

    semantic_dtype = classify_series_dtype(s)

    if semantic_dtype == "bool":
        type_stats, plot = _bool_profile(s)

    elif semantic_dtype in ("int", "float"):
        type_stats, plot = _numeric_profile(s)

    elif semantic_dtype == "datetime":
        type_stats, plot = _datetime_profile(s)

    elif semantic_dtype == "string":
        type_stats, plot = _text_or_category_profile(s)
        with contextlib.suppress(Exception):
            empty_n = int((s.fillna("").astype(str).str.len() == 0).sum())
            if empty_n:
                base["text.empty.n"] = empty_n

    else:
        type_stats, plot = {}, PlotSpec()

    # Constant?
    with contextlib.suppress(Exception):
        base["constant.flag"] = (n_unique <= 1)

    # If categorical, add transparent metadata (even if displayed as "string")
    with contextlib.suppress(Exception):
        from pandas import CategoricalDtype
        if isinstance(s.dtype, CategoricalDtype):
            dt: CategoricalDtype = s.dtype  # type: ignore
            cats = dt.categories
            base["cat.count"] = len(cats)
            base["cat.ordered"] = bool(getattr(s.dtype, "ordered", False))
            # (Optional but useful) keep raw pandas dtype visible for audit
            base["cat.pandas_dtype"] = s.dtype.name

    semantic_dtype = classify_series_dtype(s)
    return ColumnProfile(
        name=final_name,
        semantic_dtype=semantic_dtype,
        storage_dtype=s.dtype.name,
        stats={**base, **type_stats},
        plot=plot,
    )
