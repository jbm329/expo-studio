"""Stat definition registry for column profiling.

This module defines the *single source of truth* for:
- which statistics exist
- how they are formatted
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


# =====================================================================
# Formatting categories
# =====================================================================
class StatFormat(Enum):
    """How a stat value should be formatted in the UI."""
    INT = auto()
    FLOAT = auto()
    PERCENT = auto()
    BYTES = auto()
    TEXT = auto()
    LIST = auto()
    VALUE = auto()
    HEADER_ONLY = auto()


# =====================================================================
# Stat definition model
# =====================================================================

@dataclass(frozen=True)
class StatDef:
    """Definition of a single statistic.

    Attributes:
        key: Stable internal identifier (never translated).
        fmt: Formatting category.
    """
    key: str
    fmt: StatFormat


# =====================================================================
# Registry of all known statistics
# =====================================================================
STAT_DEFS: dict[str, StatDef] = {

    # -------------------------------------------------
    # Base / global stats
    # -------------------------------------------------
    "count.n": StatDef("count.n", StatFormat.INT),
    "missing.n": StatDef("missing.n", StatFormat.INT),
    "missing.pct": StatDef("missing.pct", StatFormat.PERCENT),
    "unique.n": StatDef("unique.n", StatFormat.INT),
    "unique.pct": StatDef("unique.pct", StatFormat.PERCENT),
    "memory.bytes": StatDef("memory.bytes", StatFormat.BYTES),
    "constant.flag": StatDef("constant.flag", StatFormat.TEXT),

    # -------------------------------------------------
    # Numeric stats
    # -------------------------------------------------
    "num.min": StatDef("num.min", StatFormat.VALUE),
    "num.q1": StatDef("num.q1", StatFormat.FLOAT),
    "num.median": StatDef("num.median", StatFormat.FLOAT),
    "num.q3": StatDef("num.q3", StatFormat.FLOAT),
    "num.max": StatDef("num.max", StatFormat.VALUE),
    "num.mean": StatDef("num.mean", StatFormat.FLOAT),
    "num.std": StatDef("num.std", StatFormat.FLOAT),
    "num.mad": StatDef("num.mad", StatFormat.FLOAT),
    "num.skew": StatDef("num.skew", StatFormat.FLOAT),
    "num.kurtosis": StatDef("num.kurtosis", StatFormat.FLOAT),

    "num.zeros.n": StatDef("num.zeros.n", StatFormat.INT),
    "num.zeros.pct": StatDef("num.zeros.pct", StatFormat.PERCENT),
    "num.neg.n": StatDef("num.neg.n", StatFormat.INT),
    "num.neg.pct": StatDef("num.neg.pct", StatFormat.PERCENT),
    "num.pos.n": StatDef("num.pos.n", StatFormat.INT),
    "num.pos.pct": StatDef("num.pos.pct", StatFormat.PERCENT),

    # -------------------------------------------------
    # Boolean stats
    # -------------------------------------------------
    "bool.true.n": StatDef("bool.true.n", StatFormat.INT),
    "bool.true.pct": StatDef("bool.true.pct", StatFormat.PERCENT),
    "bool.false.n": StatDef("bool.false.n", StatFormat.INT),
    "bool.false.pct": StatDef("bool.false.pct", StatFormat.PERCENT),

    # -------------------------------------------------
    # Text / category stats
    # -------------------------------------------------
    "text.topn": StatDef("text.topn", StatFormat.LIST),
    "text.len.min": StatDef("text.len.min", StatFormat.INT),
    "text.len.median": StatDef("text.len.median", StatFormat.INT),
    "text.len.max": StatDef("text.len.max", StatFormat.INT),
    "text.len.mean": StatDef("text.len.mean", StatFormat.FLOAT),
    "text.empty.n": StatDef("text.empty.n", StatFormat.INT),

    # -------------------------------------------------
    # Datetime stats
    # -------------------------------------------------
    "dt.min": StatDef("dt.min", StatFormat.VALUE),
    "dt.max": StatDef("dt.max", StatFormat.VALUE),
    "dt.span.seconds": StatDef("dt.span.seconds", StatFormat.INT),

    # -------------------------------------------------
    # Category metadata
    # -------------------------------------------------
    "cat.count": StatDef("cat.count", StatFormat.INT),
    "cat.ordered": StatDef("cat.ordered", StatFormat.TEXT),
    "cat.pandas_dtype": StatDef("cat.pandas_dtype", StatFormat.TEXT),

    # -------------------------------------------------
    # Notes / warnings
    # -------------------------------------------------
    "note.bytes": StatDef("note.bytes", StatFormat.TEXT),

    # -------------------------------------------------
    # Samples
    # -------------------------------------------------
    "sample.values": StatDef("sample.values", StatFormat.HEADER_ONLY),

}
