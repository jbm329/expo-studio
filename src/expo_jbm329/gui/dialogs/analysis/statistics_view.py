"""Descriptive Statistics view widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_pct

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.statistics import DescriptiveStatisticsResult


class StatisticsView(QWidget):
    """Displays a `DescriptiveStatisticsResult` as a per-column stats table."""

    def __init__(self, result: DescriptiveStatisticsResult, parent: QWidget | None = None) -> None:
        """Initialize the Descriptive Statistics view.

        Args:
            result: The computed descriptive statistics to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not result.columns:
            layout.addWidget(self._build_empty_label())
            return

        layout.addWidget(self._build_table(result))

    def _build_empty_label(self) -> QLabel:
        """Build the message shown when the dataset has no numeric columns."""
        label = QLabel(self.tr("No numeric columns in this dataset."), self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _build_table(self, result: DescriptiveStatisticsResult) -> QTableWidget:
        """Build the per-column statistics table."""
        headers = [
            self.tr("Column"),
            self.tr("Count"),
            self.tr("Missing"),
            self.tr("Mean"),
            self.tr("Median"),
            self.tr("Std Dev"),
            self.tr("Variance"),
            self.tr("Min"),
            self.tr("Max"),
            self.tr("Range"),
            self.tr("Q1"),
            self.tr("Q3"),
            self.tr("IQR"),
            self.tr("Skewness"),
            self.tr("Kurtosis"),
        ]

        table = QTableWidget(self)
        table.setColumnCount(len(headers))
        table.setRowCount(len(result.columns))
        table.setHorizontalHeaderLabels(headers)

        vheader = table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)

        for row, stats in enumerate(result.columns):
            values = [
                stats.column,
                fmt_int(stats.count),
                fmt_pct(stats.missing_fraction),
                fmt_num(stats.mean),
                fmt_num(stats.median),
                fmt_num(stats.std),
                fmt_num(stats.variance),
                fmt_num(stats.minimum),
                fmt_num(stats.maximum),
                fmt_num(stats.range),
                fmt_num(stats.q1),
                fmt_num(stats.q3),
                fmt_num(stats.iqr),
                fmt_num(stats.skewness),
                fmt_num(stats.kurtosis),
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, col, item)

        table.resizeColumnsToContents()

        hheader = table.horizontalHeader()
        if hheader is not None:
            hheader.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        return table
