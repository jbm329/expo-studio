"""File type classification utilities.

This module centralizes all logic for determining what *kind* of file
a given path represents, based purely on filename and suffix.

Responsibilities:
- Classify files into high-level semantic categories (sql, data, html, unknown)
- Provide stable, UI-agnostic routing signals
- Avoid any I/O, UI, editor, or job-manager dependencies

Design principles:
- Pure functions (deterministic, side-effect free)
- No file access (suffix-based only)
- No UI or job logic
- Single responsibility: classification, nothing else
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------
# Public semantic file type identifiers
# ---------------------------------------------------------------------

FileType = Literal["sql", "data", "html", "unknown"]


# ---------------------------------------------------------------------
# Configuration (centralized and explicit)
# ---------------------------------------------------------------------

SQL_SUFFIXES: tuple[str, ...] = (
    ".sql",
)

DATA_SUFFIXES: tuple[str, ...] = (
    ".df",
    ".pkl",
    ".csv",
    ".xls",
    ".xlsx",
    ".feather",
    ".ft",
    ".parquet",
    ".qvd",
    ".sav",
    ".dta",
)

HTML_SUFFIXES: tuple[str, ...] = (
    ".html",
    ".htm",
)


# ---------------------------------------------------------------------
# Core classification API
# ---------------------------------------------------------------------

def classify_file(path: str | Path) -> FileType:
    """Classify a file path into a semantic file type.

    The classification is based solely on the file suffix and is intended
    for routing decisions in UI controllers and services.

    Args:
        path: File path (string or Path).

    Returns:
        One of:
            - "sql"
            - "data"
            - "html"
            - "unknown"
    """
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix in SQL_SUFFIXES:
        return "sql"

    if suffix in DATA_SUFFIXES:
        return "data"

    if suffix in HTML_SUFFIXES:
        return "html"

    return "unknown"


# ---------------------------------------------------------------------
# Convenience helpers (optional, but explicit)
# ---------------------------------------------------------------------

def is_sql_file(path: str | Path) -> bool:
    """Return True if the path represents a SQL file."""
    return classify_file(path) == "sql"


def is_data_file(path: str | Path) -> bool:
    """Return True if the path represents a data file."""
    return classify_file(path) == "data"


def is_html_file(path: str | Path) -> bool:
    """Return True if the path represents an HTML file."""
    return classify_file(path) == "html"
