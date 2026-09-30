"""Chi-square test of independence view widget."""

from __future__ import annotations

import html
import math
from typing import TYPE_CHECKING

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView, QLabel, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from expo_jbm329.services.analysis.chi_square import (
    COCHRAN_LOW_EXPECTED_COUNT,
    COCHRAN_MAX_LOW_EXPECTED_FRACTION,
    COCHRAN_MIN_EXPECTED_COUNT,
    ChiSquareError,
    ChiSquareResult,
)
from expo_jbm329.services.analysis.group_comparison import MAX_GROUPS, MIN_GROUPS
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_p_value, fmt_pct

if TYPE_CHECKING:
    from matplotlib.axes import Axes

# Standard convention for statistical significance, matching GroupComparisonView.
_SIGNIFICANCE_LEVEL = 0.05

# Two-sided 5% critical value of the standard normal distribution: an
# adjusted residual beyond it marks a cell deviating significantly from
# independence.
RESIDUAL_SIGNIFICANCE_THRESHOLD = 1.96

# Annotating every heatmap cell becomes unreadable for large tables.
MAX_ANNOTATED_CELLS = 100


class ChiSquareView(QWidget):
    """Displays a `ChiSquareResult`: observed table, residual heatmap, and test results.

    A fresh instance is built for every computed result, matching
    `GroupComparisonView`.
    """

    def __init__(self, result: ChiSquareResult, parent: QWidget | None = None) -> None:
        """Initialize the chi-square view.

        Args:
            result: The computed chi-square test to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if result.error is not None:
            layout.addWidget(self._build_error_label(result.error))
            return

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_table_section(result))
        splitter.addWidget(self._build_heatmap_section(result))
        splitter.addWidget(self._build_results_section(result))
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([250, 350, 170])
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # Error / empty state
    # ------------------------------------------------------------------

    def _build_error_label(self, error: ChiSquareError) -> QLabel:
        """Build the message shown when no test could be computed."""
        label = QLabel(self._error_text(error), self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _error_text(self, error: ChiSquareError) -> str:
        """Return the translated message for a structured chi-square error."""
        messages = {
            ChiSquareError.NOT_ENOUGH_COLUMNS: self.tr(
                "A chi-square test needs two categorical columns, each with between "
                "{minimum} and {maximum} distinct values."
            ).format(minimum=fmt_int(MIN_GROUPS), maximum=fmt_int(MAX_GROUPS)),
            ChiSquareError.INVALID_COLUMN: self.tr("Select two different columns to test for independence."),
            ChiSquareError.TOO_FEW_CATEGORIES: self.tr(
                "Each selected column needs at least {minimum} categories with valid data."
            ).format(minimum=fmt_int(MIN_GROUPS)),
            ChiSquareError.TOO_MANY_CATEGORIES: self.tr(
                "A selected column has more than {maximum} categories. Choose a column with fewer categories."
            ).format(maximum=fmt_int(MAX_GROUPS)),
        }
        return messages[error]

    # ------------------------------------------------------------------
    # Observed contingency table
    # ------------------------------------------------------------------

    def _build_table_section(self, result: ChiSquareResult) -> QWidget:
        """Build the titled observed-count table section."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_title(self.tr("Observed counts"), panel))
        layout.addWidget(self._build_caption_label(result))
        layout.addWidget(self._build_table(result))
        return panel

    def _build_caption_label(self, result: ChiSquareResult) -> QLabel:
        """Build the caption naming which column forms the rows and which the columns."""
        label = QLabel(
            self.tr("Observed counts: {rows} (rows) by {columns} (columns)").format(
                rows=result.row_column,
                columns=result.column_column,
            ),
            self,
        )
        # Column names are user data and must never be interpreted as markup.
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        return label

    def _build_table(self, result: ChiSquareResult) -> QTableWidget:
        """Build the observed contingency table, including row and column totals."""
        total_text = self.tr("Total")
        headers = [result.row_column, *result.column_labels, total_text]

        row_totals = [sum(row) for row in result.observed]
        column_totals = [sum(column) for column in zip(*result.observed, strict=True)]

        rows: list[list[str]] = [
            [label, *(fmt_int(count) for count in counts), fmt_int(row_total)]
            for label, counts, row_total in zip(result.row_labels, result.observed, row_totals, strict=True)
        ]
        rows.append([total_text, *(fmt_int(total) for total in column_totals), fmt_int(result.total)])

        table = QTableWidget(self)
        table.setColumnCount(len(headers))
        table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels(headers)

        vheader = table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)

        for row_index, values in enumerate(rows):
            for col_index, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col_index > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row_index, col_index, item)

        table.resizeColumnsToContents()

        hheader = table.horizontalHeader()
        if hheader is not None:
            hheader.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        return table

    # ------------------------------------------------------------------
    # Adjusted residual heatmap
    # ------------------------------------------------------------------

    def _build_heatmap_section(self, result: ChiSquareResult) -> QWidget:
        """Build the titled adjusted-residual heatmap section."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_title(self.tr("Adjusted residuals"), panel))
        layout.addWidget(self._build_heatmap(result))
        return panel

    def _build_heatmap(self, result: ChiSquareResult) -> QWidget:
        """Build a matplotlib canvas showing the adjusted standardized residuals."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumHeight(260)

        ax = figure.add_subplot(111)
        self._draw_heatmap(figure, ax, result)

        return canvas

    def _draw_heatmap(self, figure: Figure, ax: Axes, result: ChiSquareResult) -> None:
        """Draw the residual heatmap with a symmetric, diverging color scale."""
        residuals = np.asarray(result.adjusted_residuals, dtype=float)
        limit = self.heatmap_color_limit(residuals)

        # NaN cells (undefined residuals) are left uncolored by imshow.
        image = ax.imshow(
            residuals,
            cmap="RdBu_r",
            vmin=-limit,
            vmax=limit,
            aspect="auto",
        )
        figure.colorbar(image, ax=ax)

        ax.set_xticks(range(len(result.column_labels)), labels=list(result.column_labels))
        ax.set_yticks(range(len(result.row_labels)), labels=list(result.row_labels))
        ax.set_xlabel(result.column_column)
        ax.set_ylabel(result.row_column)
        ax.set_title(self.tr("Adjusted standardized residuals"))

        if residuals.size <= MAX_ANNOTATED_CELLS:
            for (row_index, col_index), value in np.ndenumerate(residuals):
                if math.isfinite(value):
                    ax.text(col_index, row_index, fmt_num(float(value), sig=3), ha="center", va="center")

    @staticmethod
    def heatmap_color_limit(residuals: np.ndarray) -> float:
        """Return the symmetric color-scale limit for the residual heatmap.

        Never smaller than the significance threshold, so a table without
        any significant cell is not rendered with saturated colors.

        Args:
            residuals: The adjusted standardized residuals (may contain NaN).

        Returns:
            The absolute limit used for both ends of the color scale.
        """
        finite = np.abs(residuals[np.isfinite(residuals)])
        if finite.size == 0:
            return RESIDUAL_SIGNIFICANCE_THRESHOLD
        return max(float(finite.max()), RESIDUAL_SIGNIFICANCE_THRESHOLD)

    # ------------------------------------------------------------------
    # Test results
    # ------------------------------------------------------------------

    def _build_results_section(self, result: ChiSquareResult) -> QWidget:
        """Build the titled test results and Cochran warning section."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_title(self.tr("Test results"), panel))
        layout.addWidget(self._build_test_results_label(result))
        if result.cochran_violated:
            layout.addWidget(self._build_cochran_warning_label(result))
        return panel

    def _build_test_results_label(self, result: ChiSquareResult) -> QLabel:
        """Build the rich-text label showing the test statistics and interpretation."""
        label = QLabel(self)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(self.test_results_text(result))
        return label

    def test_results_text(self, result: ChiSquareResult) -> str:
        """Build the rich-text results summary for a successfully computed test.

        Args:
            result: A chi-square result without an error.

        Returns:
            The rich-text summary shown below the heatmap.
        """
        if result.yates_correction_applied:
            heading = self.tr("<b>Pearson's chi-square test</b> (with Yates' continuity correction):")
        else:
            heading = self.tr("<b>Pearson's chi-square test</b>:")

        lines = [
            heading,
            self.tr("χ² = {chi2}, df = {df}, p = {p}").format(
                chi2=fmt_num(result.chi2_statistic),
                df=fmt_int(result.degrees_of_freedom),
                p=html.escape(fmt_p_value(result.p_value)),
            ),
            self.tr("Cramér's V: {v}").format(v=fmt_num(result.cramers_v)),
            self.tr("N = {n}").format(n=fmt_int(result.total)),
        ]

        if result.fisher_odds_ratio is not None and result.fisher_p_value is not None:
            lines += [
                "",
                self.tr("<b>Fisher's exact test</b> (exact, reliable even for small samples):"),
                self.tr("Odds ratio = {odds_ratio}, p = {p}").format(
                    odds_ratio=fmt_num(result.fisher_odds_ratio),
                    p=html.escape(fmt_p_value(result.fisher_p_value)),
                ),
            ]

        lines += ["", self._significance_text(result.p_value), self._residual_guidance_text()]
        return "<br>".join(lines)

    def _significance_text(self, p_value: float) -> str:
        """Return the interpretation of the chi-square p-value."""
        if p_value < _SIGNIFICANCE_LEVEL:
            return self.tr("→ p < 0.05: the two variables appear to be associated (not independent).")
        return self.tr("→ p ≥ 0.05: no significant association between the two variables was found.")

    def _residual_guidance_text(self) -> str:
        """Return the explanation of how to read the residual heatmap."""
        return self.tr(
            "Cells with an adjusted residual beyond ±{threshold} deviate significantly from "
            "independence: red cells occur more often than expected, blue cells less often."
        ).format(threshold=fmt_num(RESIDUAL_SIGNIFICANCE_THRESHOLD))

    # ------------------------------------------------------------------
    # Cochran warning
    # ------------------------------------------------------------------

    def _build_cochran_warning_label(self, result: ChiSquareResult) -> QLabel:
        """Build the caveat shown when Cochran's rule of thumb is violated."""
        label = QLabel(self.cochran_warning_text(result), self)
        label.setWordWrap(True)
        return label

    def cochran_warning_text(self, result: ChiSquareResult) -> str:
        """Build the Cochran's-rule warning text.

        Args:
            result: A chi-square result whose `cochran_violated` is True.

        Returns:
            The translated warning, suggesting Fisher's exact test for
            2x2 tables and merging sparse categories otherwise.
        """
        text = self.tr(
            "⚠ {fraction} of expected counts are below {low} and the smallest expected count is {minimum} "
            "(the chi-square approximation needs at most {max_fraction} below {low} and none below {floor}). "
            "The chi-square p-value may be unreliable."
        ).format(
            fraction=fmt_pct(result.low_expected_fraction, decimals=0),
            max_fraction=fmt_pct(COCHRAN_MAX_LOW_EXPECTED_FRACTION, decimals=0),
            low=fmt_num(COCHRAN_LOW_EXPECTED_COUNT),
            minimum=fmt_num(result.min_expected),
            floor=fmt_num(COCHRAN_MIN_EXPECTED_COUNT),
        )
        if result.fisher_p_value is not None:
            return text + " " + self.tr("Prefer Fisher's exact test above.")
        return text + " " + self.tr("Consider merging sparse categories.")

    @staticmethod
    def _build_section_title(text: str, parent: QWidget) -> QLabel:
        """Build a bold title for a chi-square section."""
        label = QLabel(text, parent)
        label.setStyleSheet("font-weight: bold;")
        return label
