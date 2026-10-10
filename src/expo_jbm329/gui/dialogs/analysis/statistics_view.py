"""Descriptive Statistics view widget."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import QT_TRANSLATE_NOOP, Qt, QTimer
from PyQt6.QtGui import QPaintEvent, QResizeEvent
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.services.analysis.group_comparison import MAX_GROUPS
from expo_jbm329.services.analysis.normality import SHAPIRO_LARGE_SAMPLE_THRESHOLD
from expo_jbm329.services.analysis.statistics import (
    DescriptiveSummaryMethod,
    has_summary_recommendation,
    recommended_summary_method,
)
from expo_jbm329.services.analysis.statistics_charts import (
    STATISTICS_CHART_LOCK,
    StatisticsChartLabels,
    draw_boxplot,
    draw_histogram,
)
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_p_value, fmt_pct

if TYPE_CHECKING:
    from collections.abc import Callable

    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.statistics import (
        CategoricalColumnStatistics,
        ColumnDescriptiveStatistics,
        DescriptiveStatisticsResult,
    )

_FIRST_NUMERIC_TABLE_COLUMN = 2
_SIGNIFICANCE_LEVEL = 0.05
_CHART_RETRY_INTERVAL_MS = 25
_EXPORT_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("StatisticsView", "Charts"),
    QT_TRANSLATE_NOOP("StatisticsView", "Fraction (non-missing)"),
    QT_TRANSLATE_NOOP("StatisticsView", "Missing fraction"),
    QT_TRANSLATE_NOOP("StatisticsView", "Valid count"),
    QT_TRANSLATE_NOOP("StatisticsView", "Shapiro-Wilk W"),
    QT_TRANSLATE_NOOP("StatisticsView", "Shapiro-Wilk p-value"),
    QT_TRANSLATE_NOOP("StatisticsView", "Recommended summary"),
)


class SerializedAnalysisCanvas(FigureCanvasQTAgg):
    """Serialize actual Qt rendering without waiting for an export worker."""

    def __init__(self, figure: Figure) -> None:
        """Initialize an object-owned retry timer for rendering and resizing."""
        super().__init__(figure)  # type: ignore[no-untyped-call]
        self._resize_pending = False
        self._draw_pending = False
        self._pixel_ratio_pending = False
        self._chart_builder: Callable[[], None] | None = None
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.setInterval(_CHART_RETRY_INTERVAL_MS)
        self._retry_timer.timeout.connect(self._retry_render)

    def build_chart(self, builder: Callable[[], None]) -> None:
        """Build a chart when rendering is available, without blocking Qt."""
        self._chart_builder = builder
        self._build_pending_chart()

    def _build_pending_chart(self) -> None:
        """Serialize figure mutations with worker and live canvas drawing."""
        if self._chart_builder is None:
            return
        if not STATISTICS_CHART_LOCK.acquire(blocking=False):
            self._defer_render()
            return
        try:
            builder = self._chart_builder
            self._chart_builder = None
            builder()
            self.draw_idle()  # type: ignore[no-untyped-call]
        finally:
            STATISTICS_CHART_LOCK.release()

    def _defer_render(self) -> None:
        """Coalesce retries; QObject ownership cancels them on destruction."""
        if not self._retry_timer.isActive():
            self._retry_timer.start()

    def draw(self) -> None:
        """Protect the actual Agg draw, including draws scheduled by Qt."""
        if not STATISTICS_CHART_LOCK.acquire(blocking=False):
            self._draw_pending = True
            self._defer_render()
            return
        try:
            self._draw_pending = False
            super().draw()  # type: ignore[no-untyped-call]
        finally:
            STATISTICS_CHART_LOCK.release()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        """Defer Qt's figure-size mutation while a worker owns Matplotlib."""
        if not STATISTICS_CHART_LOCK.acquire(blocking=False):
            self._resize_pending = True
            self._defer_render()
            return
        try:
            self._resize_pending = False
            super().resizeEvent(event)  # type: ignore[no-untyped-call]
        finally:
            STATISTICS_CHART_LOCK.release()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Protect deferred drawing and renderer-buffer access during painting."""
        if not STATISTICS_CHART_LOCK.acquire(blocking=False):
            self._defer_render()
            return
        try:
            super().paintEvent(event)  # type: ignore[no-untyped-call]
        finally:
            STATISTICS_CHART_LOCK.release()

    def _update_pixel_ratio(self) -> None:
        """Protect figure DPI changes on show and screen-change events."""
        if not STATISTICS_CHART_LOCK.acquire(blocking=False):
            self._pixel_ratio_pending = True
            self._defer_render()
            return
        try:
            self._pixel_ratio_pending = False
            super()._update_pixel_ratio()
        finally:
            STATISTICS_CHART_LOCK.release()

    def _retry_render(self) -> None:
        """Replay the latest resize and draw, then request another Qt paint."""
        self._build_pending_chart()
        if self._pixel_ratio_pending:
            self._update_pixel_ratio()
        if self._resize_pending:
            self.resizeEvent(QResizeEvent(self.size(), self.size()))
        if self._draw_pending:
            self.draw()
        self.update()


_StatisticsCanvas = SerializedAnalysisCanvas


class StatisticsView(QWidget):
    """Displays a `DescriptiveStatisticsResult` as a per-column stats table.

    Also shows a histogram/boxplot pair for one selected column at a time.
    The numeric table selects the displayed column through
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
        self._rows_by_column = {stats.column: row for row, stats in enumerate(result.columns)}
        self._table: QTableWidget | None = None
        self._figure: Figure | None = None
        self._canvas: _StatisticsCanvas | None = None
        self._pending_distribution: ColumnDescriptiveStatistics | None = None
        self._distribution_timer = QTimer(self)
        self._distribution_timer.setSingleShot(True)
        self._distribution_timer.setInterval(_CHART_RETRY_INTERVAL_MS)
        self._distribution_timer.timeout.connect(self._update_distribution)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not result.columns and not result.categorical_columns:
            layout.addWidget(self._build_empty_label())
            return

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_table_section(result))
        if result.columns:
            splitter.addWidget(self._build_distribution_section())
            splitter.addWidget(self._build_normality_section())
        else:
            splitter.addWidget(self._build_no_numeric_section())
            splitter.addWidget(self._build_no_normality_section())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([250, 350, 120])
        layout.addWidget(splitter, 1)

        if result.columns:
            self.show_distribution_for(result.columns[0].column)

    def _build_empty_label(self) -> QLabel:
        """Build the message shown when no numeric or categorical summaries are available."""
        label = QLabel(self.tr("No numeric columns or eligible categorical columns in this dataset."), self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _build_table_section(self, result: DescriptiveStatisticsResult) -> QWidget:
        """Build the titled descriptive statistics table section."""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_title(self.tr("Descriptive statistics"), container))
        tabs = QTabWidget(container)
        tabs.setStyleSheet(
            "QTabBar::tab { padding: 4px 10px 6px; border: none; border-bottom: 2px solid transparent; }"
            "QTabBar::tab:selected { border-bottom-color: palette(highlight); }"
        )
        if result.columns:
            tabs.addTab(self._build_continuous_page(result), self.tr("Continuous"))
        if result.categorical_columns:
            tabs.addTab(self._build_categorical_page(result.categorical_columns), self.tr("Categorical"))
        layout.addWidget(tabs)
        return container

    def _build_continuous_page(self, result: DescriptiveStatisticsResult) -> QWidget:
        """Show both summaries with recommendation guidance directly below the table."""
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_table(result), 1)
        legend = QLabel(
            self.tr("* marks the summary suggested by Shapiro-Wilk. No star means no recommendation is available."),
            page,
        )
        legend.setTextFormat(Qt.TextFormat.PlainText)
        legend.setWordWrap(True)
        layout.addWidget(legend)
        self._recommendation_label = QLabel(page)
        self._recommendation_label.setTextFormat(Qt.TextFormat.PlainText)
        self._recommendation_label.setWordWrap(True)
        layout.addWidget(self._recommendation_label)
        return page

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
            self.tr("Mean ± SD"),
            self.tr("Median (Q1 to Q3)"),
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
                self._marked_summary(stats, DescriptiveSummaryMethod.MEAN_SD),
                self._marked_summary(stats, DescriptiveSummaryMethod.MEDIAN_IQR),
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
        self._table.cellActivated.connect(self._on_table_cell_clicked)
        return self._table

    def _build_categorical_page(self, columns: tuple[CategoricalColumnStatistics, ...]) -> QWidget:
        """Build the categorical frequency table and explain its level limit."""
        page = QWidget(self)
        layout = QVBoxLayout(page)
        note = QLabel(
            self.tr("Columns with more than {maximum} distinct values are omitted.").format(
                maximum=fmt_int(MAX_GROUPS)
            ),
            page,
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(self._build_categorical_table(columns))
        return page

    def _build_categorical_table(self, columns: tuple[CategoricalColumnStatistics, ...]) -> QTableWidget:
        """Build frequency rows with percentages based on non-missing observations."""
        headers = [
            self.tr("Column"),
            self.tr("Category"),
            self.tr("Count"),
            self.tr("Percent (non-missing)"),
            self.tr("Missing count"),
        ]
        rows: list[list[str]] = []
        for column in columns:
            if not column.frequencies:
                rows.append([column.column, self.tr("No non-missing values"), "0", "", fmt_int(column.missing_count)])
                continue
            for index, frequency in enumerate(column.frequencies):
                rows.append([
                    column.column,
                    frequency.value,
                    fmt_int(frequency.count),
                    fmt_pct(frequency.fraction),
                    fmt_int(column.missing_count) if index == 0 else "",
                ])

        table = QTableWidget(self)
        table.setColumnCount(len(headers))
        table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        for row_index, values in enumerate(rows):
            for column_index, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column_index >= _FIRST_NUMERIC_TABLE_COLUMN:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row_index, column_index, item)
        table.resizeColumnsToContents()
        header = table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        return table

    @staticmethod
    def _summary_text(stats: ColumnDescriptiveStatistics, method: DescriptiveSummaryMethod) -> str:
        """Format the selected baseline summary, or an empty string if it is undefined."""
        if method is DescriptiveSummaryMethod.MEAN_SD:
            if math.isnan(stats.mean) or math.isnan(stats.std):
                return ""
            return f"{fmt_num(stats.mean)} ± {fmt_num(stats.std)}"
        if any(math.isnan(value) for value in (stats.median, stats.q1, stats.q3)):
            return ""
        return f"{fmt_num(stats.median)} ({fmt_num(stats.q1)} to {fmt_num(stats.q3)})"

    @staticmethod
    def _has_recommendation(stats: ColumnDescriptiveStatistics) -> bool:
        """Return whether Shapiro-Wilk provided a usable normality result."""
        return has_summary_recommendation(stats)

    def _marked_summary(self, stats: ColumnDescriptiveStatistics, method: DescriptiveSummaryMethod) -> str:
        """Mark only defined summaries supported by a usable Shapiro-Wilk result."""
        text = self._summary_text(stats, method)
        if text and self._has_recommendation(stats) and recommended_summary_method(stats) is method:
            return f"{text} *"
        return text

    def _recommendation_text(self, stats: ColumnDescriptiveStatistics) -> str:
        """Explain the selected column's suggestion without making a reporting choice."""
        if not self._has_recommendation(stats):
            return self.tr(
                "{column}: Shapiro-Wilk could not provide a recommendation; neither summary is starred."
            ).format(
                column=stats.column,
            )
        method = recommended_summary_method(stats)
        summary = self.tr("Mean ± SD") if method is DescriptiveSummaryMethod.MEAN_SD else self.tr("Median (Q1 to Q3)")
        text = self.tr(
            "{column}: Shapiro-Wilk suggests {summary} as a starting point. This is a guide, not proof of normality."
        ).format(column=stats.column, summary=summary)
        if stats.count > SHAPIRO_LARGE_SAMPLE_THRESHOLD:
            text += " " + self.tr(
                "Sample size exceeds {threshold}. The p-value may not be accurate for very large samples."
            ).format(threshold=fmt_int(SHAPIRO_LARGE_SAMPLE_THRESHOLD))
        return text

    def _on_table_cell_clicked(self, row: int, _column: int) -> None:
        """Select the clicked column and update its distribution details."""
        table = self._table
        if table is None:
            return
        column_item = table.item(row, 0)
        if column_item is None:
            return

        column = column_item.text()
        self.show_distribution_for(column)

    # ------------------------------------------------------------------
    # Distribution chart (histogram + boxplot) for one selected column
    # ------------------------------------------------------------------

    def _build_distribution_section(self) -> QWidget:
        """Build the titled histogram/boxplot section."""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_title(self.tr("Distribution"), container))

        self._distribution_layout = layout

        return container

    def _build_no_numeric_section(self) -> QWidget:
        """Build a placeholder when only categorical summaries are available."""
        label = QLabel(self.tr("No numeric columns are available for distributions."), self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

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

    def _build_no_normality_section(self) -> QWidget:
        """Build a placeholder when normality testing is not applicable."""
        label = QLabel(self.tr("Normality testing applies to continuous variables."), self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

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
        table = self._table
        if stats is None or table is None:
            return

        row = self._rows_by_column[column]
        table.selectRow(row)

        self._normality_label.setText(self._normality_text(stats))
        self._recommendation_label.setText(self._recommendation_text(stats))
        self._pending_distribution = stats
        self._update_distribution()

    def _update_distribution(self) -> None:
        """Apply only the latest selection once Matplotlib is available."""
        stats = self._pending_distribution
        if stats is None:
            return
        if not STATISTICS_CHART_LOCK.acquire(blocking=False):
            if not self._distribution_timer.isActive():
                self._distribution_timer.start()
            return
        try:
            if self._figure is None:
                self._figure = Figure(constrained_layout=True)
                self._canvas = _StatisticsCanvas(self._figure)
                self._distribution_layout.addWidget(self._canvas, 1)
            self._figure.clear()
            ax_hist = self._figure.add_subplot(121)
            ax_box = self._figure.add_subplot(122)
            labels = StatisticsChartLabels(
                histogram=self.tr("Histogram"),
                boxplot=self.tr("Boxplot"),
                no_data=self.tr("No data"),
            )
            draw_histogram(ax_hist, stats, labels)
            draw_boxplot(ax_box, stats, labels)
            self._figure.suptitle(stats.column)
            self._pending_distribution = None
            self._distribution_timer.stop()
        finally:
            STATISTICS_CHART_LOCK.release()
        if self._canvas is not None:
            self._canvas.draw_idle()  # type: ignore[no-untyped-call]

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
        draw_histogram(
            ax,
            stats,
            StatisticsChartLabels(self.tr("Histogram"), self.tr("Boxplot"), self.tr("No data")),
        )

    def _draw_boxplot(self, ax: Axes, stats: ColumnDescriptiveStatistics) -> None:
        """Draw a min/max-whisker boxplot from the existing five-number summary."""
        draw_boxplot(
            ax,
            stats,
            StatisticsChartLabels(self.tr("Histogram"), self.tr("Boxplot"), self.tr("No data")),
        )
