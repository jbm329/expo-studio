"""Text cleaning and string-based DataFrame operations.

This module contains pure, UI-independent helpers for working with
text-like DataFrame columns. All operations are deterministic and
return new DataFrames.

It provides:
- Cell-level text updates
- Literal and regex-based replacements
- Whitespace normalization
- Character filtering (digits / letters)
- Case transformations
- Safe casting to pandas StringDtype

Design principles:
- Side-effect free (no in-place mutation)
- Predictable StringDtype semantics
- Explicit error handling
- No UI dependencies
"""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

logger = logging.getLogger("applogger.service")


# =====================================================================
# Cell-level operations
# =====================================================================

def set_cell_value_text(
    df: pd.DataFrame,
    column: str,
    row_index: int,
    new_value: Any,
) -> pd.DataFrame:
    """Set the value of a single cell, forcing text semantics.

    Args:
        df: Source DataFrame.
        column: Column name.
        row_index: Zero-based row index.
        new_value: New value to assign.

    Returns:
        A new DataFrame with the updated cell.

    Raises:
        KeyError: If the column does not exist.
        IndexError: If the row index is out of bounds.
    """
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    if row_index < 0 or row_index >= len(df):
        raise IndexError(f"Row index out of range: {row_index}")

    new_df = df.copy()
    s = new_df[column].astype("string")
    s.iat[row_index] = str(new_value)
    new_df[column] = s

    return new_df


# =====================================================================
# Replacement helpers
# =====================================================================

def replace_values(
    df: pd.DataFrame,
    column: str,
    pattern: Any,
    replacement: Any,
    *,
    regex: bool = False,
) -> pd.DataFrame:
    """Replace values in a column using literal or regex-based matching.

    Notes:
        - The column is normalized to pandas StringDtype before replacement.
        - NA values are preserved.
        - Exact replacement is used unless regex=True.

    Args:
        df: Source DataFrame.
        column: Column to modify.
        pattern: Literal value or regex pattern.
        replacement: Replacement value.
        regex: Whether to treat pattern as a regex.

    Returns:
        A new DataFrame with replaced values.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug(
        "replace_values: col='%s' pattern=%r replacement=%r regex=%s",
        column,
        pattern,
        replacement,
        regex,
    )

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    s = df[column].astype("string")

    if regex:
        new_s = s.replace(to_replace=pattern, value=replacement, regex=True)
    else:
        new_s = s.replace(to_replace=pattern, value=replacement)

    new_df = df.copy()
    new_df[column] = new_s.astype("string")

    return new_df


# =====================================================================
# Text normalization
# =====================================================================

def clean_text(
    df: pd.DataFrame,
    column: str,
    *,
    strip: bool = True,
    lower: bool = False,
    upper: bool = False,
    remove: str | None = None,
    case: bool = True,
) -> pd.DataFrame:
    """Apply basic text-cleaning operations to a column.

    Operations are applied in the following order:
        1. strip
        2. lower / upper
        3. literal substring removal

    Args:
        df: Source DataFrame.
        column: Column to clean.
        strip: Whether to strip leading/trailing whitespace.
        lower: Whether to convert text to lowercase.
        upper: Whether to convert text to uppercase.
        remove: Optional literal substring to remove.
        case: Whether to perform case-sensitive removal of substring.

    Returns:
        A new DataFrame with cleaned text.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug(
        "clean_text: col='%s' strip=%s lower=%s upper=%s remove=%r",
        column,
        strip,
        lower,
        upper,
        remove,
    )

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    s = df[column].astype("string")

    if strip:
        s = s.str.strip()
    if lower:
        s = s.str.lower()
    if upper:
        s = s.str.upper()

    if remove:
        if case:
            s = s.str.replace(remove, "", regex=False)
        else:
            s = s.str.replace(
                remove,
                "",
                regex=True,
                flags=re.IGNORECASE,
            )

    new_df = df.copy()
    new_df[column] = s

    return new_df


def normalize_whitespace(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Normalize whitespace in a text column.

    - Collapses multiple whitespace characters into a single space.
    - Strips leading and trailing whitespace.

    Args:
        df: Source DataFrame.
        column: Column to normalize.

    Returns:
        A new DataFrame with normalized whitespace.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug("normalize_whitespace: col='%s'", column)

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    s = (
        df[column]
        .astype("string")
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    new_df = df.copy()
    new_df[column] = s

    return new_df


def strip_chars(df: pd.DataFrame, column: str, chars: str) -> pd.DataFrame:
    """Strip specific characters from the beginning and end of values.

    Equivalent to Python str.strip(chars).

    Args:
        df: Source DataFrame.
        column: Column to modify.
        chars: Characters to strip.

    Returns:
        A new DataFrame with stripped values.

    Raises:
        KeyError: If the column does not exist.
    """
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    new_df = df.copy()
    new_df[column] = new_df[column].astype("string").str.strip(chars)

    return new_df


# =====================================================================
# Character filtering
# =====================================================================

def extract_digits(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Remove all non-digit characters from a column.

    Useful for cleaning phone numbers, IDs, and numeric codes.

    Args:
        df: Source DataFrame.
        column: Column to modify.

    Returns:
        A new DataFrame containing only digits.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug("extract_digits: col='%s'", column)

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    new_df = df.copy()
    new_df[column] = (
        new_df[column]
        .astype("string")
        .str.replace(r"\D+", "", regex=True)
    )

    return new_df


def extract_letters(
    df: pd.DataFrame,
    column: str,
    *,
    keep_swedish: bool = True,
) -> pd.DataFrame:
    """Remove all non-letter characters from a column.

    Args:
        df: Source DataFrame.
        column: Column to modify.
        keep_swedish: Whether to keep ÅÄÖåäö.

    Returns:
        A new DataFrame with letters only.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug(
        "extract_letters: col='%s' keep_swedish=%s",
        column,
        keep_swedish,
    )

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    allowed = r"A-Za-zÅÄÖåäö" if keep_swedish else r"A-Za-z"
    pattern = rf"[^{allowed}]+"

    new_df = df.copy()
    new_df[column] = (
        new_df[column]
        .astype("string")
        .str.replace(pattern, "", regex=True)
    )

    return new_df


# =====================================================================
# Case transformations
# =====================================================================

def to_title_case(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Convert text to title case.

    Args:
        df: Source DataFrame.
        column: Column to modify.

    Returns:
        A new DataFrame with title-cased text.

    Raises:
        KeyError: If the column does not exist.
    """
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    new_df = df.copy()
    new_df[column] = new_df[column].astype("string").str.title()

    return new_df


def capitalize_first(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Capitalize only the first character and lowercase the rest.

    Examples:
        "aNNa" -> "Anna"
        "BO"   -> "Bo"
        <NA>   -> <NA>

    Args:
        df: Source DataFrame.
        column: Column to modify.

    Returns:
        A new DataFrame with transformed values.

    Raises:
        KeyError: If the column does not exist.
    """
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    s = df[column].astype("string")

    def _cap(value: Any) -> Any:
        if value is pd.NA:
            return pd.NA
        if len(value) == 0:
            return value
        return value[0].upper() + value[1:].lower()

    new_df = df.copy()
    new_df[column] = s.apply(_cap).astype("string")

    return new_df


# =====================================================================
# Substring operations
# =====================================================================

def replace_text(
    df: pd.DataFrame,
    column: str,
    old: str,
    new: str,
    *,
    case: bool = True,
) -> pd.DataFrame:
    """Replace occurrences of a substring within a text column.

    Args:
        df: Source DataFrame.
        column: Column to modify.
        old: Substring to search for.
        new: Replacement substring.
        case: Whether the match should be case-sensitive.

    Returns:
        A new DataFrame with modified values.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug(
        "replace_text: col='%s' old=%r new=%r case_sensitive=%s",
        column,
        old,
        new,
        case,
    )

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    s = df[column].astype("string")

    if case:
        out = s.str.replace(old, new, regex=False)
    else:
        out = s.str.replace(old, new, case=False, regex=True)

    new_df = df.copy()
    new_df[column] = out.astype("string")

    return new_df


def insert_text(
    df: pd.DataFrame,
    column: str,
    insert: str,
    position: int,
) -> pd.DataFrame:
    """Insert a substring at a given character position.

    Args:
        df: Source DataFrame.
        column: Column to modify.
        insert: Text to insert.
        position: Zero-based character index (negative allowed).

    Returns:
        A new DataFrame with modified values.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug(
        "insert_text: col='%s' insert=%r position=%s",
        column,
        insert,
        position,
    )

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    s = df[column].astype("string")

    def _insert(value: Any) -> Any:
        if value is pd.NA:
            return pd.NA
        try:
            return value[:position] + insert + value[position:]
        except Exception:
            return value

    new_df = df.copy()
    new_df[column] = s.apply(_insert).astype("string")

    return new_df


# =====================================================================
# Remove text
# =====================================================================

def remove_regex(
    df: pd.DataFrame,
    column: str,
    pattern: str,
) -> pd.DataFrame:
    """Remove substrings matching a regex pattern from a text column.

    Args:
        df: Source DataFrame.
        column: Column to modify.
        pattern: Regular expression pattern to remove.

    Returns:
        A new DataFrame with regex matches removed.

    Raises:
        KeyError: If the column does not exist.
    """
    logger.debug(
        "remove_regex: col='%s' pattern=%r",
        column,
        pattern,
    )

    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")

    new_df = df.copy()
    new_df[column] = (
        new_df[column]
        .astype("string")
        .str.replace(pattern, "", regex=True)
    )

    return new_df



