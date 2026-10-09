"""Correlation Explorer view widget (heatmap, ranked pairs, pair detail)."""

from __future__ import annotations

import html
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

from expo_jbm329.services.analysis.correlation import (
    CONFIDENCE_LEVEL,
    MAX_SELECTED_COLUMNS,
    MIN_OBSERVATIONS,
    MIN_SELECTED_COLUMNS,
    CorrelationError,
    CorrelationMethod,
    CorrelationStrength,
    correlation_strength,
)
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_p_value

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.correlation import (
        CorrelationMatrixResult,
        CorrelationPair,
        CorrelationPairDetail,
    )

# Standard convention for statistical significance, matching the other views.
SIGNIFICANCE_LEVEL = 0.05

# Beyond this many matrix columns, per-cell annotations become unreadable.
MAX_ANNOTATED_COLUMNS = 12
# Annotations on cells darker than this |r| are drawn in white for contrast.
_LIGHT_TEXT_THRESHOLD = 0.6
_ANNOTATION_FONT_SIZE = 7
_SCATTER_POINT_SIZE = 6
_SCATTER_ALPHA = 0.4

_PAIR_COLUMN_X = 0
_PAIR_COLUMN_Y = 1


class CorrelationView(QWidget):
    """Displays a correlation matrix and the detail of one selected pair.

    The ranked pairs table spans the top of the view. The correlation
    heatmap and selected pair's scatterplot sit side by side below it,
    followed by the selected pair's statistics. Clicking a table row emits
    `pair_activated`. The pair detail is updated in place by
    `set_pair_detail` so choosing another pair needn't rebuild the matrix.
    A new matrix result always means a new view instance.
    """

    pair_activated = pyqtSignal(str, str)  # x_column, y_column

    def __init__(
        self,
        result: CorrelationMatrixResult,
        pair_detail: CorrelationPairDetail | None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the Correlation Explorer view.

        Args:
            result: The computed correlation matrix to display.
            pair_detail: The detail of the initially selected pair, or
                `None` to leave the pair panel empty.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._result = result
        self._pair_detail: CorrelationPairDetail | None = None
        self._table: QTableWidget | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._pair_panel = QWidget(self)
        self._pair_layout = QVBoxLayout(self._pair_panel)
        self._pair_layout.setContentsMargins(0, 0, 0, 0)

        self._scatter_panel = QWidget(self._pair_panel)
        self._scatter_layout = QVBoxLayout(self._scatter_panel)
        self._scatter_layout.setContentsMargins(0, 0, 0, 0)

        self._statistics_panel = QWidget(self._pair_panel)
        self._statistics_layout = QVBoxLayout(self._statistics_panel)
        self._statistics_layout.setContentsMargins(0, 0, 0, 0)

        if result.error is not None:
            self._pair_panel.hide()
            layout.addWidget(self._build_centered_label(self.error_text(result.error)))
            return

        charts_section = QWidget(self._pair_panel)
        charts_layout = QVBoxLayout(charts_section)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.addWidget(self._build_section_title(self.tr("Correlation plots"), charts_section))

        charts_splitter = QSplitter(Qt.Orientation.Horizontal, charts_section)
        charts_splitter.setChildrenCollapsible(False)
        charts_splitter.addWidget(self._build_heatmap(result))
        charts_splitter.addWidget(self._scatter_panel)
        charts_layout.addWidget(charts_splitter)

        statistics_section = QWidget(self._pair_panel)
        statistics_layout = QVBoxLayout(statistics_section)
        statistics_layout.setContentsMargins(0, 0, 0, 0)
        statistics_layout.addWidget(self._build_section_title(self.tr("Pair details"), statistics_section))
        statistics_layout.addWidget(self._statistics_panel)

        detail_splitter = QSplitter(Qt.Orientation.Vertical, self._pair_panel)
        detail_splitter.setChildrenCollapsible(False)
        detail_splitter.addWidget(charts_section)
        detail_splitter.addWidget(statistics_section)
        detail_splitter.setStretchFactor(0, 4)
        detail_splitter.setStretchFactor(1, 1)
        detail_splitter.setSizes([500, 140])
        self._pair_layout.addWidget(detail_splitter, 1)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_pairs_panel(result))
        splitter.addWidget(self._pair_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([260, 500])
        layout.addWidget(splitter, 1)

        if pair_detail is not None:
            self.set_pair_detail(pair_detail)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def method(self) -> CorrelationMethod:
        """Return the correlation method of the displayed matrix."""
        return self._result.method

    def columns(self) -> tuple[str, ...]:
        """Return the columns of the displayed matrix in matrix order."""
        return self._result.columns

    def pair_panel(self) -> QWidget:
        """Return the widget holding the pair detail (the pair recompute's overlay target)."""
        return self._pair_panel

    def pair_detail(self) -> CorrelationPairDetail | None:
        """Return the currently displayed pair detail, if any."""
        return self._pair_detail

    def table(self) -> QTableWidget | None:
        """Return the ranked pairs table, or `None` when the matrix has an error."""
        return self._table

    def set_pair_detail(self, detail: CorrelationPairDetail) -> None:
        """Replace the pair panel's content with `detail` and highlight its table row.

        Args:
            detail: The computed pair detail to display.
        """
        self._pair_detail = detail
        self._clear_layout(self._scatter_layout)
        self._clear_layout(self._statistics_layout)

        if detail.error is not None:
            self._statistics_layout.addWidget(
                self._build_centered_label(self.error_text(detail.error), self._statistics_panel)
            )
        else:
            self._scatter_layout.addWidget(self._build_scatterplot(detail))
            self._statistics_layout.addWidget(self._build_pair_statistics(detail))

        self._select_table_row(detail.pair.x_column, detail.pair.y_column)

    def error_text(self, error: CorrelationError) -> str:
        """Return the translated message for a structured correlation error."""
        messages = {
            CorrelationError.NOT_ENOUGH_NUMERIC_COLUMNS: self.tr(
                "A correlation analysis needs at least {minimum} numeric columns."
            ).format(minimum=fmt_int(MIN_SELECTED_COLUMNS)),
            CorrelationError.NOT_ENOUGH_SELECTED_COLUMNS: self.tr("Select at least {minimum} columns.").format(
                minimum=fmt_int(MIN_SELECTED_COLUMNS)
            ),
            CorrelationError.TOO_MANY_SELECTED_COLUMNS: self.tr("Select at most {maximum} columns.").format(
                maximum=fmt_int(MAX_SELECTED_COLUMNS)
            ),
            CorrelationError.INVALID_COLUMN: self.tr("Choose two or more different numeric columns."),
            CorrelationError.NOT_ENOUGH_OBSERVATIONS: self.tr(
                "Fewer than {minimum} rows have values in both columns, so no correlation can be computed."
            ).format(minimum=fmt_int(MIN_OBSERVATIONS)),
            CorrelationError.CONSTANT_INPUT: self.tr(
                "At least one of the columns is constant over the rows with values in both, "
                "so no correlation can be computed."
            ),
        }
        return messages[error]

    def coefficient_symbol(self, method: CorrelationMethod) -> str:
        """Return the translated short symbol for `method`'s coefficient."""
        match method:
            case CorrelationMethod.PEARSON:
                return self.tr("r")
            case CorrelationMethod.SPEARMAN:
                return self.tr("rho")
            case CorrelationMethod.KENDALL:
                return self.tr("tau")

    def method_name(self, method: CorrelationMethod) -> str:
        """Return the translated display name for `method`."""
        match method:
            case CorrelationMethod.PEARSON:
                return self.tr("Pearson")
            case CorrelationMethod.SPEARMAN:
                return self.tr("Spearman")
            case CorrelationMethod.KENDALL:
                return self.tr("Kendall's tau-b")

    def strength_text(self, strength: CorrelationStrength | None) -> str:
        """Return the translated strength label, or "N/A" when undefined."""
        match strength:
            case None:
                return self.tr("N/A")
            case CorrelationStrength.NEGLIGIBLE:
                return self.tr("Negligible")
            case CorrelationStrength.WEAK:
                return self.tr("Weak")
            case CorrelationStrength.MODERATE:
                return self.tr("Moderate")
            case CorrelationStrength.STRONG:
                return self.tr("Strong")

    # ------------------------------------------------------------------
    # Heatmap
    # ------------------------------------------------------------------

    def _build_heatmap(self, result: CorrelationMatrixResult) -> QWidget:
        """Build a matplotlib canvas showing the coefficient matrix."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumSize(260, 220)

        ax = figure.add_subplot(111)
        self._draw_heatmap(figure, ax, result)

        return canvas

    def _draw_heatmap(self, figure: Figure, ax: Axes, result: CorrelationMatrixResult) -> None:
        """Draw the coefficient matrix on a fixed, diverging [-1, 1] color scale."""
        coefficients = np.asarray(result.coefficients, dtype=float)

        # NaN cells (undefined coefficients) are left uncolored by imshow.
        image = ax.imshow(coefficients, cmap="RdBu_r", vmin=-1.0, vmax=1.0)
        figure.colorbar(image, ax=ax)

        labels = list(result.columns)
        ax.set_xticks(range(len(labels)), labels=labels, rotation=90)
        ax.set_yticks(range(len(labels)), labels=labels)
        ax.set_title(self.tr("{method} correlation").format(method=self.method_name(result.method)))

        if len(labels) <= MAX_ANNOTATED_COLUMNS:
            for (row_index, col_index), value in np.ndenumerate(coefficients):
                if math.isfinite(value):
                    ax.text(
                        col_index,
                        row_index,
                        fmt_num(float(value), sig=2),
                        ha="center",
                        va="center",
                        fontsize=_ANNOTATION_FONT_SIZE,
                        color="white" if abs(value) > _LIGHT_TEXT_THRESHOLD else "black",
                    )

    # ------------------------------------------------------------------
    # Ranked pairs table
    # ------------------------------------------------------------------

    def _build_pairs_panel(self, result: CorrelationMatrixResult) -> QWidget:
        """Build the ranked pairs table with its explanatory caption."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(self.tr("<b>Strongest correlations</b>"), panel)
        title.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(title)

        self._table = self._build_table(result, panel)
        layout.addWidget(self._table)

        caption = QLabel(
            self.tr(
                "Pairs are ranked by absolute coefficient. * marks pairs that are significant "
                "(p < {alpha}) after Holm adjustment for {count} tests. Click a row to show the pair below."
            ).format(alpha=fmt_num(SIGNIFICANCE_LEVEL), count=fmt_int(len(result.pairs))),
            panel,
        )
        caption.setWordWrap(True)
        layout.addWidget(caption)

        return panel

    def _build_table(self, result: CorrelationMatrixResult, parent: QWidget) -> QTableWidget:
        """Build the table of every pair, ranked by absolute coefficient."""
        confidence = fmt_int(round(CONFIDENCE_LEVEL * 100))
        headers = [
            self.tr("Variable 1"),
            self.tr("Variable 2"),
            self.coefficient_symbol(result.method),
            self.tr("{confidence}% CI").format(confidence=confidence),
            self.tr("p"),
            self.tr("Holm p"),
            self.tr("n"),
            self.tr("Strength"),
        ]

        table = QTableWidget(parent)
        table.setColumnCount(len(headers))
        table.setRowCount(len(result.pairs))
        table.setHorizontalHeaderLabels(headers)

        vheader = table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)

        for row, pair in enumerate(result.pairs):
            for col, text in enumerate(self._pair_row(pair)):
                item = QTableWidgetItem(text)
                if col > _PAIR_COLUMN_Y:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, col, item)

        table.resizeColumnsToContents()

        hheader = table.horizontalHeader()
        if hheader is not None:
            hheader.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        table.cellClicked.connect(self._on_cell_activated)
        table.cellActivated.connect(self._on_cell_activated)
        return table

    def _pair_row(self, pair: CorrelationPair) -> list[str]:
        """Return the formatted table cells for one pair."""
        significant = not math.isnan(pair.adjusted_p_value) and pair.adjusted_p_value < SIGNIFICANCE_LEVEL
        return [
            pair.x_column,
            pair.y_column,
            fmt_num(pair.coefficient, sig=3),
            self._interval_text(pair),
            fmt_p_value(pair.p_value),
            fmt_p_value(pair.adjusted_p_value) + (" *" if significant else ""),
            fmt_int(pair.n),
            self.strength_text(correlation_strength(pair.coefficient)),
        ]

    def _interval_text(self, pair: CorrelationPair) -> str:
        """Return the formatted confidence interval, or "N/A" when undefined."""
        if math.isnan(pair.ci_low) or math.isnan(pair.ci_high):
            return self.tr("N/A")
        return self.tr("{low} to {high}").format(low=fmt_num(pair.ci_low, sig=3), high=fmt_num(pair.ci_high, sig=3))

    def _on_cell_activated(self, row: int, _column: int) -> None:
        """Emit `pair_activated` for the clicked/activated table row."""
        if not 0 <= row < len(self._result.pairs):
            return
        pair = self._result.pairs[row]
        self.pair_activated.emit(pair.x_column, pair.y_column)

    def _select_table_row(self, x_column: str, y_column: str) -> None:
        """Highlight the row of the ``{x_column, y_column}`` pair, or clear the selection."""
        if self._table is None:
            return
        wanted = {x_column, y_column}
        for row, pair in enumerate(self._result.pairs):
            if {pair.x_column, pair.y_column} == wanted:
                self._table.selectRow(row)
                return
        self._table.clearSelection()

    # ------------------------------------------------------------------
    # Pair detail
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

    def _build_scatterplot(self, detail: CorrelationPairDetail) -> QWidget:
        """Build a matplotlib canvas with the pair's scatterplot and least-squares line."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumSize(260, 200)

        ax = figure.add_subplot(111)
        self._draw_scatterplot(ax, detail)

        return canvas

    def _draw_scatterplot(self, ax: Axes, detail: CorrelationPairDetail) -> None:
        """Draw the (possibly sampled) points and the least-squares line over all rows."""
        ax.scatter(detail.sample_x, detail.sample_y, s=_SCATTER_POINT_SIZE, alpha=_SCATTER_ALPHA)

        x_min, x_max = min(detail.sample_x), max(detail.sample_x)
        ax.plot(
            [x_min, x_max],
            [detail.slope * x_min + detail.intercept, detail.slope * x_max + detail.intercept],
            color="tab:red",
        )
        ax.set_xlabel(detail.pair.x_column)
        ax.set_ylabel(detail.pair.y_column)

    def _build_pair_statistics(self, detail: CorrelationPairDetail) -> QLabel:
        """Build the rich-text label describing the pair's statistics."""
        label = QLabel(self._pair_statistics_text(detail), self._statistics_panel)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        return label

    def _pair_statistics_text(self, detail: CorrelationPairDetail) -> str:
        """Build the pair statistics text, including line and sampling notes."""
        pair = detail.pair
        lines = [
            self.tr("<b>{x}</b> vs <b>{y}</b> ({method})").format(
                x=html.escape(pair.x_column), y=html.escape(pair.y_column), method=self.method_name(detail.method)
            ),
            self.tr("{symbol} = {value} ({strength})").format(
                symbol=self.coefficient_symbol(detail.method),
                value=fmt_num(pair.coefficient, sig=3),
                strength=self.strength_text(correlation_strength(pair.coefficient)),
            ),
            self.tr("{confidence}% CI: {interval}").format(
                confidence=fmt_int(round(CONFIDENCE_LEVEL * 100)), interval=self._interval_text(pair)
            ),
            self.tr("p = {p}, n = {n}").format(p=html.escape(fmt_p_value(pair.p_value)), n=fmt_int(pair.n)),
            "",
            self.tr("Least-squares line: slope {slope}, intercept {intercept}").format(
                slope=fmt_num(detail.slope), intercept=fmt_num(detail.intercept)
            ),
        ]

        if detail.method is not CorrelationMethod.PEARSON:
            lines.append(
                self.tr(
                    "The line is a linear fit shown for reference. {method} measures monotonic, "
                    "not necessarily linear, association."
                ).format(method=self.method_name(detail.method))
            )

        if detail.sampled:
            lines.append(
                self.tr("Showing a random sample of {shown} of {total} points. Statistics use all points.").format(
                    shown=fmt_int(len(detail.sample_x)), total=fmt_int(pair.n)
                )
            )

        return "<br>".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_centered_label(self, text: str, parent: QWidget | None = None) -> QLabel:
        """Build a centered, word-wrapped message label."""
        label = QLabel(text, parent if parent is not None else self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _build_section_title(text: str, parent: QWidget) -> QLabel:
        """Build a bold title for a correlation section."""
        label = QLabel(text, parent)
        label.setStyleSheet("font-weight: bold;")
        return label
