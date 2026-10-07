"""Descriptive Statistics configuration widget (column picker)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QWidget

from expo_jbm329.services.analysis.statistics import DescriptiveSummaryMethod, recommended_summary_method

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.statistics import DescriptiveStatisticsResult


class StatisticsConfigWidget(QWidget):
    """Lets the user pick a numeric column and its baseline summary method.

    Purely a GUI-thread concern: all columns' distribution data is already
    present in the `DescriptiveStatisticsResult` this widget is built from,
    so changing either selection never triggers a new background computation.
    Each numeric column keeps its own summary choice.
    """

    column_changed = pyqtSignal(str)
    summary_method_changed = pyqtSignal(str, str)

    def __init__(self, result: DescriptiveStatisticsResult, parent: QWidget | None = None) -> None:
        """Initialize the configuration widget.

        Args:
            result: The computed descriptive statistics, used to populate
                the column picker.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._columns_by_name = {stats.column: stats for stats in result.columns}
        self._summary_methods = {stats.column: recommended_summary_method(stats) for stats in result.columns}

        layout = QFormLayout(self)

        self._column_combo = QComboBox(self)
        for stats in result.columns:
            self._column_combo.addItem(stats.column)

        self._summary_method_combo = QComboBox(self)
        self._summary_method_combo.addItem(
            self.tr("Mean ± SD"),
            DescriptiveSummaryMethod.MEAN_SD.value,
        )
        self._summary_method_combo.addItem(
            self.tr("Median (Q1 to Q3)"),
            DescriptiveSummaryMethod.MEDIAN_IQR.value,
        )
        self._recommendation_label = QLabel(self)
        self._recommendation_label.setWordWrap(True)

        layout.addRow(QLabel(self.tr("Column"), self), self._column_combo)
        layout.addRow(QLabel(self.tr("Reported summary"), self), self._summary_method_combo)
        layout.addRow(self._recommendation_label)

        self._column_combo.currentTextChanged.connect(self._on_current_text_changed)
        self._summary_method_combo.currentIndexChanged.connect(self._on_summary_method_changed)
        if result.columns:
            self._sync_summary_method()

    def _on_current_text_changed(self, text: str) -> None:
        """Select the column's summary option and notify the paired view."""
        if text:
            self._sync_summary_method()
            self.column_changed.emit(text)

    def _on_summary_method_changed(self, _index: int) -> None:
        """Store and emit the per-column presentation method."""
        column = self.selected_column()
        method = self.selected_summary_method()
        if column is None or method is None:
            return
        self._summary_methods[column] = method
        self.summary_method_changed.emit(column, method.value)

    def _sync_summary_method(self) -> None:
        """Select the stored method and explain its Shapiro-Wilk recommendation."""
        column = self.selected_column()
        if column is None:
            return
        stats = self._columns_by_name[column]
        method = self._summary_methods[column]
        index = self._summary_method_combo.findData(method.value)
        with QSignalBlocker(self._summary_method_combo):
            self._summary_method_combo.setCurrentIndex(index)

        if math.isnan(stats.shapiro_p_value):
            text = self.tr(
                "Shapiro-Wilk could not provide a recommendation. "
                "Median (IQR) is selected by default; you can override it."
            )
        else:
            recommendation = recommended_summary_method(stats)
            recommended = (
                self.tr("Mean ± SD") if recommendation is DescriptiveSummaryMethod.MEAN_SD else self.tr("Median (IQR)")
            )
            text = self.tr(
                "Shapiro-Wilk suggests {summary} as a starting point. "
                "This is a guide, not proof of normality; you can override it."
            ).format(summary=recommended)
        self._recommendation_label.setText(text)

    def selected_column(self) -> str | None:
        """Return the currently selected column name, if any."""
        text = self._column_combo.currentText()
        return text or None

    def selected_summary_method(self) -> DescriptiveSummaryMethod | None:
        """Return the selected column's current summary method."""
        value = self._summary_method_combo.currentData()
        return DescriptiveSummaryMethod(value) if value is not None else None

    def set_selected_column(self, column: str) -> None:
        """Update the selected column without emitting a redundant change.

        Args:
            column: Numeric column to select.
        """
        index = self._column_combo.findText(column)
        if index < 0:
            return

        with QSignalBlocker(self._column_combo):
            self._column_combo.setCurrentIndex(index)
        self._sync_summary_method()

    def summary_method(self, column: str) -> DescriptiveSummaryMethod | None:
        """Return the stored summary method for `column`, if available."""
        return self._summary_methods.get(column)
