"""Inline value and optional ordering selectors for a reshape metric."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QSizePolicy, QWidget

if TYPE_CHECKING:
    from collections.abc import Sequence


class MetricSourceCell(QWidget):
    """Show paired selectors and enable ordering only when required."""

    def __init__(
        self,
        parent: QWidget,
        source_columns: Sequence[object],
        ordering_positions: Sequence[int],
    ) -> None:
        """Build positional dropdowns without choosing an ordering implicitly.

        Args:
            parent: Metrics table containing this cell.
            source_columns: Original source column labels in positional order.
            ordering_positions: Numeric/datetime positions offered for ordering.
        """
        super().__init__(parent)
        self.requires_order = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.value = QComboBox(self)
        self.value.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.value.setMinimumWidth(0)
        self.value.setAccessibleName(self.tr("Source column"))
        self.value.currentTextChanged.connect(self.value.setToolTip)
        self.order = QComboBox(self)
        self.order.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.order.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.order.setMinimumWidth(0)
        self.order.setAccessibleName(self.tr("Order by"))
        self.order.addItem(self.tr("Select ordering column"), None)
        for position in ordering_positions:
            name = str(source_columns[position])
            self.order.addItem(name, position)
            self.order.setItemData(self.order.count() - 1, name, Qt.ItemDataRole.ToolTipRole)
        self.order.setToolTip(self.order.currentText())
        self.order.currentTextChanged.connect(self.order.setToolTip)
        layout.addWidget(self.value, 1)
        layout.addWidget(self.order, 1)
        self.setFocusProxy(self.value)
        QWidget.setTabOrder(self.value, self.order)
        self.set_order_required(False)

    @property
    def source_position(self) -> int | None:
        """Return the selected value column's positional identity."""
        position = self.value.currentData()
        return position if isinstance(position, int) else None

    @property
    def order_position(self) -> int | None:
        """Return ordering only for metrics that currently require it."""
        position = self.order.currentData()
        return position if self.requires_order and isinstance(position, int) else None

    @property
    def ordering_complete(self) -> bool:
        """Return whether required ordering is explicitly selected."""
        return not self.requires_order or self.order_position is not None

    def set_order_required(self, required: bool) -> None:
        """Enable ordering without discarding the per-metric selection."""
        self.requires_order = required
        self.order.setEnabled(required)
