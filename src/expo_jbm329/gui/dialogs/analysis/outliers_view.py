"""Outlier Explorer view widget (per-column summary, column detail)."""

from __future__ import annotations

import html
import math
from itertools import pairwise
from typing import TYPE_CHECKING

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.services.analysis.outliers import (
    MAX_THRESHOLD,
    MIN_OBSERVATIONS,
    MIN_THRESHOLD,
    ColumnOutlierStatus,
    OutlierError,
    OutlierMethod,
    max_possible_z_score,
)
from expo_jbm329.utils.format_utils import fmt_cell, fmt_int, fmt_num, fmt_pct

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.outliers import (
        ColumnOutlierSummary,
        ExtremeObservation,
        OutlierColumnDetail,
        OutlierSummaryResult,
    )

_NAME_COLUMN = 0
_RIGHT_ALIGNED = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def _esc(text: str) -> str:
    """Escape `text` for use in rich text."""
    return html.escape(text)


def _new_table(
    headers: list[str],
    row_count: int,
    parent: QWidget,
    *,
    rows_selectable: bool = False,
) -> QTableWidget:
    """Build a read-only table with `headers`."""
    table = QTableWidget(parent)
    table.setColumnCount(len(headers))
    table.setRowCount(row_count)
    table.setHorizontalHeaderLabels(headers)

    vheader = table.verticalHeader()
    if vheader is not None:
        vheader.setVisible(False)

    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    if rows_selectable:
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    else:
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setAlternatingRowColors(True)
    return table


def _finish_table(table: QTableWidget) -> None:
    """Size the columns to their content, then let the user resize them."""
    table.resizeColumnsToContents()
    hheader = table.horizontalHeader()
    if hheader is not None:
        hheader.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)


class OutliersView(QWidget):
    """Displays the outlier screening of every numeric column and one column's detail.

    Four vertically resizable sections show the per-column summary table,
    the selected column's most extreme flagged rows, its histogram and its
    statistics. Clicking a summary row emits `column_activated`. The last
    three sections are updated in place by `set_column_detail` so choosing
    another column needn't rebuild the summary. A new summary result always
    means a new view instance.
    """

    column_activated = pyqtSignal(str)

    def __init__(
        self,
        result: OutlierSummaryResult,
        detail: OutlierColumnDetail | None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the Outlier Explorer view.

        Args:
            result: The computed outlier summary to display.
            detail: The detail of the initially selected column, or
                `None` to leave the detail panel empty.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._result = result
        self._detail: OutlierColumnDetail | None = None
        self._table: QTableWidget | None = None
        self._extremes_table: QTableWidget | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._detail_panel = QWidget(self)
        self._detail_layout = QVBoxLayout(self._detail_panel)
        self._detail_layout.setContentsMargins(0, 0, 0, 0)

        detail_splitter = QSplitter(Qt.Orientation.Vertical, self._detail_panel)
        detail_splitter.setChildrenCollapsible(False)

        self._extremes_panel = QWidget(detail_splitter)
        self._extremes_layout = QVBoxLayout(self._extremes_panel)
        self._extremes_layout.setContentsMargins(0, 0, 0, 0)
        detail_splitter.addWidget(self._extremes_panel)

        self._chart_panel = QWidget(detail_splitter)
        self._chart_layout = QVBoxLayout(self._chart_panel)
        self._chart_layout.setContentsMargins(0, 0, 0, 0)
        detail_splitter.addWidget(self._chart_panel)

        self._statistics_panel = QWidget(detail_splitter)
        self._statistics_layout = QVBoxLayout(self._statistics_panel)
        self._statistics_layout.setContentsMargins(0, 0, 0, 0)
        detail_splitter.addWidget(self._statistics_panel)

        detail_splitter.setStretchFactor(0, 2)
        detail_splitter.setStretchFactor(1, 3)
        detail_splitter.setStretchFactor(2, 1)
        detail_splitter.setSizes([180, 300, 150])
        self._detail_layout.addWidget(detail_splitter)

        if result.error is not None:
            self._detail_panel.hide()
            layout.addWidget(self._build_centered_label(self.error_text(result.error)))
            return

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_summary_panel(result))
        splitter.addWidget(self._detail_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([250, 650])
        layout.addWidget(splitter, 1)

        if detail is not None:
            self.set_column_detail(detail)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def configuration(self) -> tuple[OutlierMethod, float]:
        """Return the ``(method, threshold)`` of the displayed summary."""
        return self._result.method, self._result.threshold

    def detail_panel(self) -> QWidget:
        """Return the widget holding the column detail (the detail recompute's overlay target)."""
        return self._detail_panel

    def column_detail(self) -> OutlierColumnDetail | None:
        """Return the currently displayed column detail, if any."""
        return self._detail

    def table(self) -> QTableWidget | None:
        """Return the per-column summary table, or `None` when the summary has an error."""
        return self._table

    def extremes_table(self) -> QTableWidget | None:
        """Return the displayed detail's observations table, if any."""
        return self._extremes_table

    def set_column_detail(self, detail: OutlierColumnDetail) -> None:
        """Replace the detail panel's content with `detail` and highlight its summary row.

        Args:
            detail: The computed column detail to display.
        """
        self._detail = detail
        self._extremes_table = None
        self._clear_layout(self._extremes_layout)
        self._clear_layout(self._chart_layout)
        self._clear_layout(self._statistics_layout)

        if detail.error is not None:
            self._extremes_panel.hide()
            self._chart_panel.hide()
            self._statistics_panel.show()
            self._statistics_layout.addWidget(
                self._build_centered_label(self.error_text(detail.error), self._statistics_panel)
            )
        else:
            self._extremes_panel.show()
            self._chart_panel.show()
            self._statistics_panel.show()
            self._extremes_layout.addWidget(self._build_extremes_panel(detail))
            self._chart_layout.addWidget(self._build_section_title(self.tr("Distribution"), self._chart_panel))
            self._chart_layout.addWidget(self._build_histogram(detail))
            self._statistics_layout.addWidget(
                self._build_section_title(self.tr("Column details"), self._statistics_panel)
            )
            self._statistics_layout.addWidget(self._build_detail_statistics(detail))

        self._select_table_row(detail.summary.column)

    def error_text(self, error: OutlierError) -> str:
        """Return the translated message for a structured outlier error."""
        match error:
            case OutlierError.NO_NUMERIC_COLUMN:
                return self.tr("An outlier analysis needs at least one numeric column.")
            case OutlierError.INVALID_COLUMN:
                return self.tr("Choose a numeric column.")
            case OutlierError.INVALID_THRESHOLD:
                return self.tr("Choose a threshold between {minimum} and {maximum}.").format(
                    minimum=fmt_num(MIN_THRESHOLD), maximum=fmt_num(MAX_THRESHOLD)
                )

    def method_name(self, method: OutlierMethod) -> str:
        """Return the translated display name for `method`."""
        match method:
            case OutlierMethod.IQR:
                return self.tr("IQR (Tukey's fences)")
            case OutlierMethod.Z_SCORE:
                return self.tr("Z-score")
            case OutlierMethod.MODIFIED_Z_SCORE:
                return self.tr("Modified Z-score")

    def status_text(self, status: ColumnOutlierStatus) -> str:
        """Return the translated short explanation of why a column wasn't screened."""
        match status:
            case ColumnOutlierStatus.NOT_ENOUGH_OBSERVATIONS:
                return self.tr("Too few values")
            case ColumnOutlierStatus.ZERO_SPREAD:
                return self.tr("No spread")

    def score_header(self, method: OutlierMethod) -> str:
        """Return the translated header of the observations table's score column."""
        match method:
            case OutlierMethod.IQR:
                return self.tr("Distance past fence")
            case OutlierMethod.Z_SCORE:
                return self.tr("z")
            case OutlierMethod.MODIFIED_Z_SCORE:
                return self.tr("Modified z")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _build_summary_panel(self, result: OutlierSummaryResult) -> QWidget:
        """Build the totals line, the per-column table and its caption."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_title(self.tr("Columns"), panel))

        totals = QLabel(self._totals_text(result), panel)
        totals.setTextFormat(Qt.TextFormat.RichText)
        totals.setWordWrap(True)
        layout.addWidget(totals)

        table_panel = QFrame(panel)
        table_panel.setFrameShape(QFrame.Shape.NoFrame)
        table_panel.setBackgroundRole(QPalette.ColorRole.Button)
        table_panel.setAutoFillBackground(True)
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self._table = self._build_summary_table(result, table_panel)
        table_layout.addWidget(self._table, 1)

        caption = QLabel(
            self.tr(
                "Flagged values are potential outliers, not necessarily errors - check them before "
                "excluding anything. Click a row to show the column below."
            ),
            table_panel,
        )
        caption.setWordWrap(True)
        caption.setTextFormat(Qt.TextFormat.PlainText)
        table_layout.addWidget(caption)
        layout.addWidget(table_panel, 1)

        return panel

    @staticmethod
    def _build_section_title(text: str, parent: QWidget) -> QLabel:
        """Build a bold title for an outlier section."""
        label = QLabel(text, parent)
        label.setStyleSheet("font-weight: bold;")
        return label

    def _totals_text(self, result: OutlierSummaryResult) -> str:
        """Return the rich-text dataset-wide totals."""
        fraction = result.rows_with_outliers / result.row_count if result.row_count else 0.0
        return self.tr(
            "<b>{method}</b>, threshold {threshold}: {flagged} of {rows} rows ({percent}) "
            "have a potential outlier in at least one of {columns} numeric columns."
        ).format(
            method=self.method_name(result.method),
            threshold=fmt_num(result.threshold),
            flagged=fmt_int(result.rows_with_outliers),
            rows=fmt_int(result.row_count),
            percent=fmt_pct(fraction),
            columns=fmt_int(len(result.columns)),
        )

    def _build_summary_table(self, result: OutlierSummaryResult, parent: QWidget) -> QTableWidget:
        """Build the table of every numeric column, ranked by outlier share."""
        headers = [
            self.tr("Column"),
            self.tr("Values"),
            self.tr("Missing"),
            self.tr("Outliers"),
            self.tr("Share"),
            self.tr("Low"),
            self.tr("High"),
            self.tr("Lower fence"),
            self.tr("Upper fence"),
        ]
        table = _new_table(headers, len(result.columns), parent, rows_selectable=True)

        for row, summary in enumerate(result.columns):
            for col, text in enumerate(self._summary_row(summary)):
                item = QTableWidgetItem(text)
                if col > _NAME_COLUMN:
                    item.setTextAlignment(_RIGHT_ALIGNED)
                table.setItem(row, col, item)

        _finish_table(table)
        table.cellClicked.connect(self._on_cell_activated)
        table.cellActivated.connect(self._on_cell_activated)
        return table

    def _summary_row(self, summary: ColumnOutlierSummary) -> list[str]:
        """Return the formatted table cells for one column."""
        if summary.status is not None:
            status = self.status_text(summary.status)
            return [summary.column, fmt_int(summary.n), fmt_int(summary.missing), status, "", "", "", "", ""]
        return [
            summary.column,
            fmt_int(summary.n),
            fmt_int(summary.missing),
            fmt_int(summary.outlier_count),
            fmt_pct(summary.outlier_fraction),
            fmt_int(summary.low_count),
            fmt_int(summary.high_count),
            fmt_num(summary.lower_fence),
            fmt_num(summary.upper_fence),
        ]

    def _on_cell_activated(self, row: int, _column: int) -> None:
        """Emit `column_activated` for the clicked/activated table row."""
        if not 0 <= row < len(self._result.columns):
            return
        self.column_activated.emit(self._result.columns[row].column)

    def _select_table_row(self, column: str) -> None:
        """Highlight the row of `column`, or clear the selection."""
        if self._table is None:
            return
        for row, summary in enumerate(self._result.columns):
            if summary.column == column:
                self._table.selectRow(row)
                return
        self._table.clearSelection()

    # ------------------------------------------------------------------
    # Column detail
    # ------------------------------------------------------------------

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        """Remove and delete every widget currently in `layout`."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def _build_histogram(self, detail: OutlierColumnDetail) -> QWidget:
        """Build a matplotlib canvas with the column's inlier/outlier histogram."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumSize(240, 160)
        self._draw_histogram(figure.add_subplot(111), detail)
        return canvas

    def _draw_histogram(self, ax: Axes, detail: OutlierColumnDetail) -> None:
        """Draw stacked inlier/outlier bars over shared bins, with the fences marked."""
        ax.set_title(detail.summary.column, fontsize=10)
        edges = detail.histogram_edges
        if not edges:
            return
        lefts = edges[:-1]
        widths = [right - left for left, right in pairwise(edges)]
        ax.bar(lefts, detail.inlier_counts, width=widths, align="edge", label=self.tr("Inside the fences"))
        ax.bar(
            lefts,
            detail.outlier_counts,
            width=widths,
            align="edge",
            bottom=detail.inlier_counts,
            color="tab:red",
            label=self.tr("Potential outliers"),
        )
        for fence in (detail.summary.lower_fence, detail.summary.upper_fence):
            if math.isfinite(fence):
                ax.axvline(fence, color="tab:red", linestyle="--", linewidth=1)
        ax.set_ylabel(self.tr("Count"), fontsize=9)
        ax.tick_params(labelsize=8)
        ax.legend(fontsize=8)

    def _build_detail_statistics(self, detail: OutlierColumnDetail) -> QLabel:
        """Build the rich-text label describing the column's screening."""
        label = QLabel(self._detail_statistics_text(detail), self._detail_panel)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        return label

    def _detail_statistics_text(self, detail: OutlierColumnDetail) -> str:
        """Build the column statistics text with method-specific notes."""
        summary = detail.summary
        lines = [
            self.tr("<b>{column}</b> - {method}, threshold {threshold}").format(
                column=_esc(summary.column),
                method=self.method_name(detail.method),
                threshold=fmt_num(detail.threshold),
            )
        ]

        if summary.status is not None:
            lines.append(self._status_explanation(summary.status))
            return "<br>".join(lines)

        lines += [
            self.tr("Fences: {lower} to {upper}").format(
                lower=fmt_num(summary.lower_fence), upper=fmt_num(summary.upper_fence)
            ),
            self.tr("{count} potential outliers ({percent}): {low} low, {high} high").format(
                count=fmt_int(summary.outlier_count),
                percent=fmt_pct(summary.outlier_fraction),
                low=fmt_int(summary.low_count),
                high=fmt_int(summary.high_count),
            ),
            *self._method_lines(detail),
        ]
        return "<br>".join(lines)

    def _status_explanation(self, status: ColumnOutlierStatus) -> str:
        """Return the translated longer explanation of why a column wasn't screened."""
        match status:
            case ColumnOutlierStatus.NOT_ENOUGH_OBSERVATIONS:
                return self.tr("At least {minimum} values are needed to screen a column.").format(
                    minimum=fmt_int(MIN_OBSERVATIONS)
                )
            case ColumnOutlierStatus.ZERO_SPREAD:
                return self.tr("All values are identical, so no value can stand out.")

    def _method_lines(self, detail: OutlierColumnDetail) -> list[str]:
        """Return the statistics the method's fences are based on, with caveats."""
        match detail.method:
            case OutlierMethod.IQR:
                return [
                    self.tr("Q1 = {q1}, Q3 = {q3}, IQR = {iqr}").format(
                        q1=fmt_num(detail.q1), q3=fmt_num(detail.q3), iqr=fmt_num(detail.scale)
                    )
                ]
            case OutlierMethod.Z_SCORE:
                lines = [
                    self.tr("Mean = {mean}, standard deviation = {std}").format(
                        mean=fmt_num(detail.mean), std=fmt_num(detail.std)
                    ),
                    self.tr(
                        "<i>Extreme values inflate the mean and standard deviation themselves. "
                        "The modified Z-score is more robust.</i>"
                    ),
                ]
                bound = max_possible_z_score(detail.summary.n)
                if bound <= detail.threshold:
                    lines.append(
                        self.tr(
                            "<i>With {count} values no |z| can exceed {bound}, "
                            "so this threshold can't flag anything.</i>"
                        ).format(count=fmt_int(detail.summary.n), bound=fmt_num(bound, sig=3))
                    )
                return lines
            case OutlierMethod.MODIFIED_Z_SCORE:
                lines = [
                    self.tr("Median = {median}, MAD = {mad}").format(
                        median=fmt_num(detail.median), mad=fmt_num(detail.mad)
                    )
                ]
                if detail.mad_fallback:
                    lines.append(
                        self.tr(
                            "<i>The MAD is zero (more than half the values are identical), so the scaled "
                            "mean absolute deviation is used instead.</i>"
                        )
                    )
                return lines

    def _build_extremes_panel(self, detail: OutlierColumnDetail) -> QWidget:
        """Build the table of the most extreme flagged rows with its title."""
        panel = QWidget(self._detail_panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        shown = len(detail.extremes)
        if shown == 0:
            title_text = self.tr("<b>No potential outliers</b>")
        elif shown < detail.summary.outlier_count:
            title_text = self.tr("<b>The {shown} most extreme of {total} potential outliers</b>").format(
                shown=fmt_int(shown), total=fmt_int(detail.summary.outlier_count)
            )
        else:
            title_text = self.tr("<b>Potential outliers, most extreme first</b>")
        title = QLabel(title_text, panel)
        title.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(title)

        if shown:
            self._extremes_table = self._build_extremes_table(detail, panel)
            layout.addWidget(self._extremes_table)
        else:
            layout.addStretch(1)

        return panel

    def _build_extremes_table(self, detail: OutlierColumnDetail, parent: QWidget) -> QTableWidget:
        """Build the table of flagged rows: row number, value, score, then every other column."""
        column = detail.summary.column
        other_indexes = [i for i, name in enumerate(detail.row_columns) if name != column]
        headers = [
            self.tr("Row"),
            column,
            self.score_header(detail.method),
            *(detail.row_columns[i] for i in other_indexes),
        ]
        table = _new_table(headers, len(detail.extremes), parent)
        numeric_cells = 3

        for row, observation in enumerate(detail.extremes):
            for col, text in enumerate(self._extreme_row(observation, other_indexes)):
                item = QTableWidgetItem(text)
                if col < numeric_cells:
                    item.setTextAlignment(_RIGHT_ALIGNED)
                table.setItem(row, col, item)

        _finish_table(table)
        return table

    @staticmethod
    def _extreme_row(observation: ExtremeObservation, other_indexes: list[int]) -> list[str]:
        """Return the formatted table cells for one flagged row."""
        return [
            fmt_int(observation.row_number),
            fmt_num(observation.value),
            fmt_num(observation.score, sig=3),
            *(fmt_cell(observation.row_values[i]) for i in other_indexes),
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_centered_label(self, text: str, parent: QWidget | None = None) -> QLabel:
        """Build a centered, word-wrapped message label."""
        label = QLabel(text, parent if parent is not None else self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label
