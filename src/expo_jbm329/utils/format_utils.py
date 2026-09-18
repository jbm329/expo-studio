"""Formatting utilities for the Expo application.

This module provides functions for formatting numbers, bytes, dates,
timedeltas, and paths, often with locale-aware support.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PyQt6.QtCore import QDate, QLocale


# ---------------------------------------------------------------------
#  % formatting
# ---------------------------------------------------------------------
def fmt_pct(x: float, decimals: int = 2) -> str:
    """Format a float as a percentage string (multiplied by 100).

    Args:
        x: The float value to format (e.g. 0.1234 -> "12.34%").
        decimals: Number of decimal places. Defaults to 2.

    Returns:
        The formatted percentage string (e.g., "12.34%").
    """
    try:
        s = f"{x * 100:.{decimals}f}%"
        if QLocale.system().decimalPoint() == ",":
            return s.replace(".", ",")
        return s
    except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        return f"{x * 100:.{decimals}f}%"


# ---------------------------------------------------------------------
#  Bytes formatting
# ---------------------------------------------------------------------

def fmt_bytes(b: int) -> str:
    """Format a byte size using binary units (B, KB, MB, GB, TB).

    Uses 1024-based steps and locale-aware number formatting via QLocale.
    - For bytes (B), formats as an integer with locale-aware grouping.
    - For KB and above, formats with two decimals using the locale's decimal separator.

    Examples:
        sv-SE (Swedish):  2202009 -> "2,10 MB"
        en-US (English):  2202009 -> "2.10 MB"

    Args:
        b: The size in bytes.

    Returns:
        The formatted size string, e.g., "2,10 MB".
    """
    units = ["B", "KB", "MB", "GB", "TB"]
    s = float(b)
    u = 0
    while s >= 1024 and u < len(units) - 1:
        s /= 1024.0
        u += 1

    loc = QLocale.system()

    num_str = loc.toString(int(s)) if u == 0 else loc.toString(s, "f", 2)

    return f"{num_str} {units[u]}"


def fmt_path_size(p: Path | str | None) -> str:
    """Format a file size string for a given path.

    - If the path exists and is a file, returns a formatted byte size
      wrapped in parentheses, e.g. " (2,10 MB)".
    - If the path does not exist, is not a file, or cannot be accessed,
      returns an empty string.

    This helper is intended for UI usage where file size is displayed
    as an optional, human-readable suffix.

    Args:
        p: Path-like object (Path or str).

    Returns:
        Formatted size string like " (2,10 MB)", or empty string if unavailable.
    """
    if not p:
        return ""

    try:
        path = Path(p)
        if not path.exists() or not path.is_file():
            return ""

        size_bytes = path.stat().st_size
    except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        return ""

    return f" ({fmt_bytes(size_bytes)})"


# ---------------------------------------------------------------------
#  Number formatting
# ---------------------------------------------------------------------
def fmt_num(val: float | None, *, sig: int = 4) -> str:
    """Format a numeric value using significant digits.

    - If val is integer-like, return integer using locale formatting.
    - If val is float, round to 'sig' significant digits.
    - If val is None or NaN, return empty string.

    Args:
        val: Numeric value to format.
        sig: Number of significant digits for float formatting. Defaults to 4.

    Returns:
        Formatted value string.
    """
    if val is None:
        return ""

    try:
        xf = float(val)
    except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        return ""

    if np.isnan(xf):
        return ""

    # Integer-like?
    if xf.is_integer():
        return QLocale.system().toString(int(xf))

    # Float formatting with significant digits
    # np.format_float_positional produces clean scientific/positional format
    formatted = np.format_float_positional(
        xf,
        precision=sig,
        unique=False,
        trim="k"
    )

    # Apply locale decimal separator
    if QLocale.system().decimalPoint() == ",":
        formatted = formatted.replace(".", ",")

    return formatted


def fmt_int(n: int) -> str:
    """Format an integer with locale-aware grouping.

    Args:
        n: The integer to format.

    Returns:
        Formatted integer string.
    """
    try:
        return QLocale.system().toString(int(n))
    except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        return f"{int(n):,}".replace(",", " ")


# ---------------------------------------------------------------------
#  Dataframe shape formatting
# ---------------------------------------------------------------------
def fmt_shape(df: pd.DataFrame | None) -> tuple[str, str]:
    """Return formatted (rows, columns) for a DataFrame."""
    try:
        if isinstance(df, pd.DataFrame):
            rows = fmt_int(len(df.index))
            columns = fmt_int(len(df.columns))
        else:
            rows = "?"
            columns = "?"
    except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        rows = "?"
        columns = "?"
    return rows, columns


# ---------------------------------------------------------------------
#  Date / datetime formatting
# ---------------------------------------------------------------------

def fmt_date(dt: datetime.date | datetime.datetime | None) -> str:
    """Format date according to the user's locale (Qt / OS).

    Args:
        dt: Date or datetime object to format.

    Returns:
        Localized date string, or empty string if dt is None.
    """
    if dt is None:
        return ""

    # Normalize to date using a non-optional name
    date_val: datetime.date
    date_val = dt.date() if isinstance(dt, datetime.datetime) else dt

    date = QDate(date_val.year, date_val.month, date_val.day)
    return QLocale().toString(date, QLocale.FormatType.ShortFormat)


def fmt_time(seconds: float) -> str:
    """Format seconds into a time duration string.

    Formats as H:MM:SS if hours > 0, otherwise M:SS.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted duration string.
    """
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------------------------------------------------------------
#  Timedelta formatting
# ---------------------------------------------------------------------
def fmt_timedelta(td: datetime.timedelta | pd.Timedelta | None) -> str:
    """Format timedelta into a human-readable string.

    Args:
        td: Timedelta object to format.

    Returns:
        Formatted string (e.g., "1 d 12:34:56" or "12:34:56").
    """
    if td is None or pd.isna(td):
        return ""

    if isinstance(td, pd.Timedelta):
        td = td.to_pytimedelta()

    days = td.days
    seconds = td.seconds
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)

    if days > 0:
        return f"{days} d {h:02d}:{m:02d}:{s:02d}"
    return f"{h}:{m:02d}:{s:02d}"


# ---------------------------------------------------------------------
#  Category-safe formatting
# ---------------------------------------------------------------------

def fmt_category(val) -> str:
    """Safely format categorical values.

    Handles NaN/None by returning an empty string.

    Args:
        val: The categorical value to format.

    Returns:
        String representation of the value.
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    return str(val)


# ---------------------------------------------------------------------
#  Path format to posix
# ---------------------------------------------------------------------

def fmt_path(p: Any) -> str:
    """Return a POSIX-style string for any path-like input.

    Ensures no backslashes are present. Safe for logging and UI.

    Args:
        p: Path-like input (str or Path).

    Returns:
        POSIX-formatted path string.
    """
    try:
        return Path(p).as_posix()
    except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        s = str(p)
        return s.replace("\\", "/")


def tuple_to_posix(args: tuple) -> tuple:
    """Convert a tuple of mixed args to POSIX-formatted strings.

    Only str or Path entries are converted. Non-path args are unchanged.

    Args:
        args: Tuple of arguments to convert.

    Returns:
        Tuple with POSIX-formatted path strings where applicable.
    """
    out = []
    for a in args:
        if isinstance(a, (str, Path)):
            out.append(fmt_path(a))
        else:
            out.append(a)
    return tuple(out)
