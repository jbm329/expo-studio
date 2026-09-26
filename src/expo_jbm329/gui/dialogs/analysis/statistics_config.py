"""Descriptive Statistics configuration widget (column picker)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QWidget

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.statistics import DescriptiveStatisticsResult


class StatisticsConfigWidget(QWidget):
    """Lets the user pick which numeric column's distribution to display.

    Purely a GUI-thread concern: all columns' distribution data is already
    present in the `DescriptiveStatisticsResult` this widget is built from,
    so changing the selection never triggers a new background computation -
    it only tells the paired `StatisticsView` which column to redraw.
    """

    column_changed = pyqtSignal(str)

    def __init__(self, result: DescriptiveStatisticsResult, parent: QWidget | None = None) -> None:
        """Initialize the configuration widget.

        Args:
            result: The computed descriptive statistics, used to populate
                the column picker.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        layout = QFormLayout(self)

        self._column_combo = QComboBox(self)
        for stats in result.columns:
            self._column_combo.addItem(stats.column)

        self._column_combo.currentTextChanged.connect(self._on_current_text_changed)

        layout.addRow(QLabel(self.tr("Column"), self), self._column_combo)

    def _on_current_text_changed(self, text: str) -> None:
        """Emit column_changed, ignoring the transient empty-combo state."""
        if text:
            self.column_changed.emit(text)

    def selected_column(self) -> str | None:
        """Return the currently selected column name, if any."""
        text = self._column_combo.currentText()
        return text or None
