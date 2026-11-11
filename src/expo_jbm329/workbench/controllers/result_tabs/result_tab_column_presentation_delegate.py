"""Delegate controlling how column values are displayed."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, override

import numpy as np
import pandas as pd
from PyQt6.QtCore import QModelIndex, QObject, Qt
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from expo_jbm329.services.data_profile.presentation import format_value_for_display
from expo_jbm329.utils.format_utils import fmt_float_fixed, fmt_int

if TYPE_CHECKING:
    from expo_jbm329.services.data_profile.semantics import SeriesSemantics

NumericColumnKind = Literal["integer", "float"]


class ResultTabColumnPresentationDelegate(QStyledItemDelegate):
    """Delegate controlling how column values are displayed."""

    def __init__(
        self,
        *,
        semantics_by_column_index: dict[int, SeriesSemantics],
        numeric_column_kinds: dict[int, NumericColumnKind],
        parent: QObject | None = None,
    ) -> None:
        """Initialize delegate.

        Args:
            semantics_by_column_index: Mapping of column indices to their semantic information.
            numeric_column_kinds: Numeric display kinds determined from column dtypes.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._semantics_by_column_index = semantics_by_column_index
        self._numeric_column_kinds = numeric_column_kinds

    @override
    def initStyleOption(
        self,
        option: QStyleOptionViewItem | None,
        index: QModelIndex,
    ) -> None:
        """Initialize style option with dtype-based numeric and semantic datetime text."""
        super().initStyleOption(option, index)
        if option is None:
            return

        value = index.data(Qt.ItemDataRole.EditRole)
        kind = self._numeric_column_kinds.get(index.column())
        sem = self._semantics_by_column_index.get(index.column())
        if kind is None and sem is None:
            return

        if value is None or pd.isna(value):
            option.text = ""
            return

        if kind == "integer" and isinstance(value, (int, np.integer)):
            option.text = fmt_int(int(value))
            return
        if kind == "float" and isinstance(value, (float, np.floating)):
            option.text = fmt_float_fixed(float(value))
            return

        if sem is None:
            return

        option.text = format_value_for_display(value, sem)
