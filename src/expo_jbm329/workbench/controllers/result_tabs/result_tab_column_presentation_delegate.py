"""Delegate controlling how column values are displayed."""
from __future__ import annotations

from typing import TYPE_CHECKING, override

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from expo_jbm329.services.data_profile.presentation import format_value_for_display

if TYPE_CHECKING:
    from expo_jbm329.services.data_profile.semantics import SeriesSemantics


class ResultTabColumnPresentationDelegate(QStyledItemDelegate):
    """Delegate controlling how column values are displayed."""

    def __init__(
        self,
        *,
        semantics_by_column_index: dict[int, SeriesSemantics],
        parent=None,
    ) -> None:
        """Initialize delegate.

        Args:
            semantics_by_column_index: Mapping of column indices to their semantic information.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._semantics_by_column_index = semantics_by_column_index

    @override
    def initStyleOption(
        self,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        """Initialize style option with semantic-aware text."""
        super().initStyleOption(option, index)

        value = index.data(Qt.ItemDataRole.EditRole)
        if value is None or pd.isna(value):
            option.text = ""
            return

        sem = self._semantics_by_column_index.get(index.column())
        if sem is None:
            return

        option.text = format_value_for_display(value, sem)
