"""Descriptive Statistics view widget."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from expo_jbm329.services.analysis.normality import SHAPIRO_LARGE_SAMPLE_THRESHOLD
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_p_value, fmt_pct

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.statistics import (
        ColumnDescriptiveStatistics,
        DescriptiveStatisticsResult,
    )

# Standard convention for statistical significance in the normality summary.
_SIGNIFICANCE_LEVEL = 0.05


class StatisticsView(QWidget):
    """Displays a `DescriptiveStatisticsResult` as a per-column stats table.

    Also shows a histogram/boxplot pair for one selected column at a time.
    The selected column is driven externally (typically by a config widget
    in the Advanced Analysis workspace's configuration pane) via
    `show_distribution_for()`; this view never re-runs the analysis itself -
    all columns' distribution data is already present in the `result` it
    was built from.
    """

    def __init__(self, result: DescriptiveStatisticsResult, parent: QWidget | None = None) -> None:
        """Initialize the Descriptive Statistics view.

        Args:
            result: The computed descriptive statistics to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._columns_by_name = {stats.column: stats for stats in result.columns}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not result.columns:
            layout.addWidget(self._build_empty_label())
            return

        layout.addWidget(self._build_table(result))
        layout.addWidget(self._build_distribution_section())

        self.show_distribution_for(result.columns[0].column)

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

    # ------------------------------------------------------------------
    # Distribution chart (histogram + boxplot) for one selected column
    # ------------------------------------------------------------------

    def _build_distribution_section(self) -> QWidget:
        """Build the histogram/boxplot canvas and normality summary label."""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self._figure = Figure(constrained_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)  # type: ignore[no-untyped-call]
        self._canvas.setMinimumHeight(260)
        layout.addWidget(self._canvas)

        self._normality_label = QLabel(container)
        self._normality_label.setWordWrap(True)
        layout.addWidget(self._normality_label)

        return container

    def show_distribution_for(self, column: str) -> None:
        """Redraw the histogram/boxplot and normality summary for the given column.

        Args:
            column: Name of the numeric column to display. Must be one of
                the columns this view was built with.
        """
        stats = self._columns_by_name.get(column)
        if stats is None:
            return

        self._figure.clear()
        ax_hist = self._figure.add_subplot(121)
        ax_box = self._figure.add_subplot(122)

        self._draw_histogram(ax_hist, stats)
        self._draw_boxplot(ax_box, stats)

        self._figure.suptitle(column)
        self._canvas.draw_idle()  # type: ignore[no-untyped-call]

        self._normality_label.setText(self._normality_text(stats))

    def _normality_text(self, stats: ColumnDescriptiveStatistics) -> str:
        """Build the Shapiro-Wilk normality test summary text for a column."""
        if math.isnan(stats.shapiro_p_value):
            return self.tr("Not enough data to test for normality.")

        lines = [
            self.tr("Shapiro-Wilk: W = {w}, p = {p}").format(
                w=fmt_num(stats.shapiro_statistic),
                p=fmt_p_value(stats.shapiro_p_value),
            )
        ]

        if stats.shapiro_p_value < _SIGNIFICANCE_LEVEL:
            lines.append(self.tr("→ Significant evidence against normality (α = 0.05)."))  # noqa: RUF001
        else:
            lines.append(self.tr("→ No significant evidence against normality (α = 0.05)."))  # noqa: RUF001

        if stats.count > SHAPIRO_LARGE_SAMPLE_THRESHOLD:
            lines.append(
                self.tr(
                    "⚠ Sample size exceeds {threshold}; the p-value may not be accurate for very large samples."
                ).format(threshold=fmt_int(SHAPIRO_LARGE_SAMPLE_THRESHOLD))
            )

        return "<br>".join(lines)

    def _draw_histogram(self, ax: Axes, stats: ColumnDescriptiveStatistics) -> None:
        """Draw a histogram from pre-computed bin edges/counts."""
        if not stats.histogram_bins or not stats.histogram_counts:
            ax.text(0.5, 0.5, self.tr("No data"), ha="center", va="center", transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
            return

        bins = np.asarray(stats.histogram_bins)
        counts = np.asarray(stats.histogram_counts)
        ax.bar(bins[:-1], counts, width=np.diff(bins), align="edge", edgecolor="#333")
        ax.set_title(self.tr("Histogram"))

    def _draw_boxplot(self, ax: Axes, stats: ColumnDescriptiveStatistics) -> None:
        """Draw a min/max-whisker boxplot from the existing five-number summary."""
        values = (stats.minimum, stats.q1, stats.median, stats.q3, stats.maximum)
        if any(math.isnan(v) for v in values):
            ax.text(0.5, 0.5, self.tr("No data"), ha="center", va="center", transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
            return

        ax.bxp(
            [
                {
                    "med": stats.median,
                    "q1": stats.q1,
                    "q3": stats.q3,
                    "whislo": stats.minimum,
                    "whishi": stats.maximum,
                    "fliers": [],
                }
            ],
            showfliers=False,
        )
        ax.set_title(self.tr("Boxplot"))
