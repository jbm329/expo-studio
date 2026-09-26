"""Group Comparison view widget."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from expo_jbm329.services.analysis.group_comparison import (
    MAX_GROUPS,
    MIN_GROUPS,
    GroupComparisonError,
    GroupComparisonResult,
    GroupComparisonWarning,
    GroupWarningReason,
)
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_p_value

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from expo_jbm329.services.analysis.group_comparison import (
        GroupSummary,
        MultiGroupComparisonResult,
        PairwiseComparisonResult,
    )

# Standard convention for statistical significance, matching StatisticsView.
_SIGNIFICANCE_LEVEL = 0.05


class GroupComparisonView(QWidget):
    """Displays a `GroupComparisonResult`: per-group summary, boxplot, and test results.

    A fresh instance is built for every computed result (unlike
    `StatisticsView`, which redraws itself in place) - the configuration
    selection determines *what* was computed, so a new result always means
    a wholly new view rather than a redraw of already-present data.
    """

    def __init__(self, result: GroupComparisonResult, parent: QWidget | None = None) -> None:
        """Initialize the Group Comparison view.

        Args:
            result: The computed group comparison to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if result.error is not None:
            layout.addWidget(self._build_error_label(result.error))
            return

        layout.addWidget(self._build_table(result.groups))
        layout.addWidget(self._build_boxplot(result.groups))
        layout.addWidget(self._build_test_results_label(result))

        if result.warnings:
            layout.addWidget(self._build_warnings_label(result.warnings))

    # ------------------------------------------------------------------
    # Error / empty state
    # ------------------------------------------------------------------

    def _build_error_label(self, error: GroupComparisonError) -> QLabel:
        """Build the message shown when no comparison could be computed."""
        label = QLabel(self._error_text(error), self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _error_text(self, error: GroupComparisonError) -> str:
        """Return the translated message for a structured comparison error."""
        messages = {
            GroupComparisonError.NO_NUMERIC_COLUMN: self.tr("This dataset has no numeric column to compare."),
            GroupComparisonError.NO_GROUPING_COLUMN: self.tr(
                "No suitable grouping column was found. A grouping column needs between "
                "{minimum} and {maximum} distinct values."
            ).format(minimum=fmt_int(MIN_GROUPS), maximum=fmt_int(MAX_GROUPS)),
            GroupComparisonError.TOO_FEW_GROUPS: self.tr(
                "The selected grouping column has fewer than {minimum} groups with valid data."
            ).format(minimum=fmt_int(MIN_GROUPS)),
            GroupComparisonError.TOO_MANY_GROUPS: self.tr(
                "The selected grouping column has more than {maximum} distinct values; "
                "choose a column with fewer groups."
            ).format(maximum=fmt_int(MAX_GROUPS)),
        }
        return messages[error]

    # ------------------------------------------------------------------
    # Per-group summary table
    # ------------------------------------------------------------------

    def _build_table(self, groups: tuple[GroupSummary, ...]) -> QTableWidget:
        """Build the per-group descriptive summary and normality table."""
        headers = [
            self.tr("Group"),
            self.tr("Count"),
            self.tr("Mean"),
            self.tr("Median"),
            self.tr("Std Dev"),
            self.tr("Shapiro W"),
            self.tr("Shapiro p"),
            self.tr("Normal?"),
        ]

        table = QTableWidget(self)
        table.setColumnCount(len(headers))
        table.setRowCount(len(groups))
        table.setHorizontalHeaderLabels(headers)

        vheader = table.verticalHeader()
        if vheader is not None:
            vheader.setVisible(False)

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)

        for row, group in enumerate(groups):
            values = [
                group.label,
                fmt_int(group.count),
                fmt_num(group.mean),
                fmt_num(group.median),
                fmt_num(group.std),
                fmt_num(group.shapiro_statistic),
                fmt_p_value(group.shapiro_p_value),
                self._normality_verdict(group),
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

    def _normality_verdict(self, group: GroupSummary) -> str:
        """Return a compact Yes/No/N-A normality verdict for one group."""
        if math.isnan(group.shapiro_p_value):
            return self.tr("N/A")
        if group.shapiro_p_value < _SIGNIFICANCE_LEVEL:
            return self.tr("No")
        return self.tr("Yes")

    # ------------------------------------------------------------------
    # Boxplot (all groups side by side)
    # ------------------------------------------------------------------

    def _build_boxplot(self, groups: tuple[GroupSummary, ...]) -> QWidget:
        """Build a matplotlib canvas with one boxplot per group, side by side."""
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumHeight(260)

        ax = figure.add_subplot(111)
        self._draw_boxplot(ax, groups)

        return canvas

    def _draw_boxplot(self, ax: Axes, groups: tuple[GroupSummary, ...]) -> None:
        """Draw one box per group from each group's precomputed five-number summary."""
        stats = [
            {
                "label": group.label,
                "med": group.median,
                "q1": group.q1,
                "q3": group.q3,
                "whislo": group.minimum,
                "whishi": group.maximum,
                "fliers": [],
            }
            for group in groups
        ]
        ax.bxp(stats, showfliers=False)
        ax.set_title(self.tr("Distribution by group"))

    # ------------------------------------------------------------------
    # Test results
    # ------------------------------------------------------------------

    def _build_test_results_label(self, result: GroupComparisonResult) -> QLabel:
        """Build the rich-text label showing the test statistics and guidance."""
        label = QLabel(self)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)

        if result.pairwise is not None:
            label.setText(self._pairwise_text(result.pairwise, result.groups))
        elif result.multi_group is not None:
            label.setText(self._multi_group_text(result.multi_group, result.groups))

        return label

    def _pairwise_text(self, pairwise: PairwiseComparisonResult, groups: tuple[GroupSummary, ...]) -> str:
        """Build the Welch's t-test / Mann-Whitney U results text."""
        lines = [
            self.tr("<b>Welch's t-test</b> (does not assume equal variances):"),
            self.tr("t = {t}, df = {df}, p = {p}").format(
                t=fmt_num(pairwise.t_statistic),
                df=fmt_num(pairwise.t_degrees_of_freedom),
                p=fmt_p_value(pairwise.t_p_value),
            ),
            self.tr("Mean difference: {diff} (95% CI: {low} to {high})").format(
                diff=fmt_num(pairwise.mean_difference),
                low=fmt_num(pairwise.mean_difference_ci_low),
                high=fmt_num(pairwise.mean_difference_ci_high),
            ),
            self.tr("Cohen's d: {d}").format(d=fmt_num(pairwise.cohens_d)),
            "",
            self.tr("<b>Mann-Whitney U</b>:"),
            self.tr("U = {u}, p = {p}").format(u=fmt_num(pairwise.u_statistic), p=fmt_p_value(pairwise.u_p_value)),
            self.tr("Rank-biserial correlation: {r}").format(r=fmt_num(pairwise.rank_biserial_correlation)),
            "",
            self._normality_guidance(groups),
        ]
        return "<br>".join(lines)

    def _multi_group_text(self, multi: MultiGroupComparisonResult, groups: tuple[GroupSummary, ...]) -> str:
        """Build the one-way ANOVA / Kruskal-Wallis results text."""
        lines = [
            self.tr("<b>One-way ANOVA</b> (assumes equal variances across groups):"),
            self.tr("F = {f}, p = {p}").format(f=fmt_num(multi.f_statistic), p=fmt_p_value(multi.f_p_value)),
            self.tr("Eta²: {eta}").format(eta=fmt_num(multi.eta_squared)),
            "",
            self.tr("<b>Kruskal-Wallis</b> (does not assume equal variances):"),
            self.tr("H = {h}, p = {p}").format(h=fmt_num(multi.h_statistic), p=fmt_p_value(multi.h_p_value)),
            self.tr("Epsilon²: {eps}").format(eps=fmt_num(multi.epsilon_squared)),
            "",
            self._normality_guidance(groups),
        ]
        return "<br>".join(lines)

    def _normality_guidance(self, groups: tuple[GroupSummary, ...]) -> str:
        """Build guidance on which result to trust, based on per-group normality."""
        if self._any_group_non_normal(groups):
            return self.tr(
                "⚠ At least one group's data does not appear normally distributed (or "
                "normality could not be tested) → the non-parametric result above is "
                "likely more reliable."
            )
        return self.tr(
            "→ Every group is consistent with a normal distribution → both results "
            "should agree; the parametric result above is typically more powerful."
        )

    @staticmethod
    def _any_group_non_normal(groups: tuple[GroupSummary, ...]) -> bool:
        """Return True if any group's normality is rejected or could not be tested."""
        return any(math.isnan(group.shapiro_p_value) or group.shapiro_p_value < _SIGNIFICANCE_LEVEL for group in groups)

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------

    def _build_warnings_label(self, group_warnings: tuple[GroupComparisonWarning, ...]) -> QLabel:
        """Build the caveats label listing every non-blocking per-group warning."""
        label = QLabel(self)
        label.setWordWrap(True)
        label.setText("<br>".join(self._warning_text(warning) for warning in group_warnings))
        return label

    def _warning_text(self, warning: GroupComparisonWarning) -> str:
        """Return the translated message for one per-group caveat."""
        if warning.reason is GroupWarningReason.TOO_FEW_FOR_VARIANCE:
            return self.tr(
                "⚠ Group '{label}' has fewer than 2 observations: its standard deviation "
                "and any statistic derived from it could not be computed."
            ).format(label=warning.group_label)
        return self.tr("⚠ Group '{label}' has fewer than 3 observations: its normality could not be tested.").format(
            label=warning.group_label
        )
