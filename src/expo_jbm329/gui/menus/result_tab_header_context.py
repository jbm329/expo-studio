"""Header context model for column-based context menus.

This module defines the immutable context object used when building
context menus for table column headers (QHeaderView).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from expo_jbm329.services.data_profile.capabilities import (
    SeriesCapabilities,
    infer_series_capabilities,
)
from expo_jbm329.services.data_profile.semantics import (
    SeriesSemantics,
    infer_series_semantics,
)

if TYPE_CHECKING:
    import pandas as pd
    from PyQt6.QtWidgets import QTableView


# =====================================================================
# Context object
# =====================================================================


@dataclass(frozen=True)
class ResultTabHeaderContext:
    """Immutable context for header-related operations.

    This is a UI snapshot describing:
    - selection state
    - column identity
    - semantic interpretation
    - allowed user operations
    """

    # UI state
    view: QTableView
    column: int
    column_name: str
    only_one_selected: bool

    # Data interpretation
    semantics: SeriesSemantics
    capabilities: SeriesCapabilities


# =====================================================================
# Context builder
# =====================================================================


def build_header_context(
    *,
    view: QTableView,
    df: pd.DataFrame | None,
    column: int,
    column_name: str,
    only_one_selected: bool,
) -> ResultTabHeaderContext:
    """Build ResultTabHeaderContext for a given table view + column.

    This function is the SINGLE place where:
    - pandas Series is accessed
    - semantics are inferred
    - capabilities are derived

    No UI code and no menu logic belongs here.
    """
    # --------------------------------------------------------------
    # Fallback: no DataFrame
    # --------------------------------------------------------------
    if df is None or column_name not in df.columns:
        empty_semantics = SeriesSemantics(semantic_dtype="other")
        empty_capabilities = SeriesCapabilities()

        return ResultTabHeaderContext(
            view=view,
            column=column,
            column_name=column_name,
            only_one_selected=only_one_selected,
            semantics=empty_semantics,
            capabilities=empty_capabilities,
        )

    # --------------------------------------------------------------
    # Normal case
    # --------------------------------------------------------------
    series = df[column_name]

    semantics = infer_series_semantics(series)
    storage_dtype = series.dtype.name

    capabilities = infer_series_capabilities(semantics, storage_dtype)

    return ResultTabHeaderContext(
        view=view,
        column=column,
        column_name=column_name,
        only_one_selected=only_one_selected,
        semantics=semantics,
        capabilities=capabilities,
    )
