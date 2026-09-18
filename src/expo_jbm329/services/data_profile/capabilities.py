"""User-facing capabilities derived from series semantics.

This module answers the question:
    "What actions make sense for this column in the UI?"

It MUST NOT:
- inspect pandas data
- depend on QTableView
- contain UI text
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from expo_jbm329.services.data_profile.semantics import SeriesSemantics


@dataclass(frozen=True)
class SeriesCapabilities:
    """Describes which operations are valid for a column.

    These are high-level, declarative capabilities used by
    header context menus and other UI components.
    """

    # -----------------------------
    # Text operations
    # -----------------------------
    can_clean_text: bool = False
    can_regex_text: bool = False

    # -----------------------------
    # Numeric operations
    # -----------------------------
    can_fill_numeric: bool = False
    can_filter_numeric: bool = False

    # -----------------------------
    # Datetime operations
    # -----------------------------
    can_filter_datetime: bool = False
    can_strip_time: bool = False

    # -----------------------------
    # Type conversions
    # -----------------------------
    can_convert_to_category: bool = False
    can_convert_to_string: bool = False
    can_convert_to_int: bool = False
    can_convert_to_float: bool = False
    can_convert_to_datetime: bool = False
    can_convert_to_date_only: bool = False
    can_convert_to_bool: bool = False

    # -----------------------------
    # Category operations
    # -----------------------------
    can_edit_categories: bool = False


def infer_series_capabilities(sem: SeriesSemantics, storage_dtype: str) -> SeriesCapabilities:
    """Infer user-facing capabilities from series semantics.

    This function is pure, deterministic and UI-agnostic.
    """
    storage_dtype = storage_dtype.lower()
    return SeriesCapabilities(
        # -----------------------------
        # Text operations
        # -----------------------------
        can_clean_text=sem.semantic_dtype in ("string", "category"),
        can_regex_text=sem.semantic_dtype in ("string", "category"),
        # -----------------------------
        # Numeric operations
        # -----------------------------
        can_fill_numeric=sem.semantic_dtype in ("int", "float"),
        can_filter_numeric=sem.semantic_dtype in ("int", "float"),
        # -----------------------------
        # Datetime operations
        # -----------------------------
        can_filter_datetime=sem.semantic_dtype == "datetime",
        can_strip_time=sem.semantic_dtype == "datetime" and sem.has_time_component,
        # -----------------------------
        # Type conversions
        # -----------------------------
        can_convert_to_int=(sem.can_be_int and not storage_dtype.startswith("int")),
        can_convert_to_float=(sem.can_be_float and not storage_dtype.startswith("float")),
        can_convert_to_datetime=(
            sem.can_be_datetime and not storage_dtype.startswith("datetime64") and not sem.is_year_like
        ),
        can_convert_to_bool=(sem.can_be_bool and storage_dtype != "bool"),
        can_convert_to_string=storage_dtype != "string",
        can_convert_to_category=(
            sem.semantic_dtype in ("string", "category")
            and sem.cardinality_ratio is not None
            and sem.cardinality_ratio < 0.5
            and storage_dtype != "category"
        ),
        # -----------------------------
        # Category operations
        # -----------------------------
        can_edit_categories=sem.semantic_dtype == "category",
    )
