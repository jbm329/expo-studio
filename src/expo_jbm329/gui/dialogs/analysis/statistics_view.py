"""Descriptive Statistics view widget."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

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

    column_selected = pyqtSignal(str)

    def __init__(self, result: DescriptiveStatisticsResult, parent: QWidget | None = None) -> None:
        """Initialize the Descriptive Statistics view.

        Args:
            result: The computed descriptive statistics to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._columns_by_name = {stats.column: stats for stats in result.columns}
        self._rows_by_column = {stats.column: row for row, stats in enumerate(result.columns)}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not result.columns:
            layout.addWidget(self._build_empty_label())
            return

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_table_section(result))
        splitter.addWidget(self._build_distribution_section())
        splitter.addWidget(self._build_normality_section())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([250, 350, 120])
        layout.addWidget(splitter, 1)

        self.show_distribution_for(result.columns[0].column)

    def _build_empty_label(self) -> QLabel:
        """Build the message shown when the dataset has no numeric columns."""
        label = QLabel(self.tr("No numeric columns in this dataset."), self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _build_table_section(self, result: DescriptiveStatisticsResult) -> QWidget:
        """Build the titled descriptive statistics table section."""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_title(self.tr("Descriptive statistics"), container))
        layout.addWidget(self._build_table(result))
        return container

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

        self._table = QTableWidget(self)
        self._table.setColumnCount(len(headers))
        self._table.setRowCount(len(result.columns))
        self._table.setHorizontalHeaderLabels(headers)

        vheader = self._table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)

        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)

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
                self._table.setItem(row, col, item)

        self._table.resizeColumnsToContents()

        hheader = self._table.horizontalHeader()
        if hheader is not None:
            hheader.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        self._table.cellClicked.connect(self._on_table_cell_clicked)
        return self._table

    def _on_table_cell_clicked(self, row: int, _column: int) -> None:
        """Select the clicked column and update its distribution details."""
        column_item = self._table.item(row, 0)
        if column_item is None:
            return

        column = column_item.text()
        self.show_distribution_for(column)
        self.column_selected.emit(column)

    # ------------------------------------------------------------------
    # Distribution chart (histogram + boxplot) for one selected column
    # ------------------------------------------------------------------

    def _build_distribution_section(self) -> QWidget:
        """Build the titled histogram/boxplot section."""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_title(self.tr("Distribution"), container))

        self._figure = Figure(constrained_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)  # type: ignore[no-untyped-call]
        layout.addWidget(self._canvas)

        return container

    def _build_normality_section(self) -> QWidget:
        """Build the Shapiro-Wilk normality text section."""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self._normality_label = QLabel(container)
        self._normality_label.setTextFormat(Qt.TextFormat.RichText)
        self._normality_label.setWordWrap(True)
        layout.addWidget(self._normality_label)

        return container

    @staticmethod
    def _build_section_title(text: str, parent: QWidget) -> QLabel:
        """Build a bold title for a statistics view section."""
        label = QLabel(text, parent)
        label.setStyleSheet("font-weight: bold;")
        return label

    def show_distribution_for(self, column: str) -> None:
        """Redraw the histogram/boxplot and normality summary for the given column.

        Args:
            column: Name of the numeric column to display. Must be one of
                the columns this view was built with.
        """
        stats = self._columns_by_name.get(column)
        if stats is None:
            return

        row = self._rows_by_column[column]
        self._table.selectRow(row)

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
            self.tr("<b>Shapiro-Wilk</b>:"),
            self.tr("W = {w}, p = {p}").format(
                w=fmt_num(stats.shapiro_statistic),
                p=fmt_p_value(stats.shapiro_p_value),
            ),
        ]

        if stats.shapiro_p_value < _SIGNIFICANCE_LEVEL:
            lines.append(self.tr("→ Significant evidence against normality (α = 0.05)."))  # noqa: RUF001
        else:
            lines.append(self.tr("→ No significant evidence against normality (α = 0.05)."))  # noqa: RUF001

        if stats.count > SHAPIRO_LARGE_SAMPLE_THRESHOLD:
            lines.append(
                self.tr(
                    "⚠ Sample size exceeds {threshold}. The p-value may not be accurate for very large samples."
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
