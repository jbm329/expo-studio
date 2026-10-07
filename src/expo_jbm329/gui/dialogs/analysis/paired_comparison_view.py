"""Paired repeated-measures test result view."""

from __future__ import annotations

import html
import math
from typing import TYPE_CHECKING

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from expo_jbm329.services.analysis.paired_comparison import PairedComparisonError, PairedComparisonMethod
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_p_value

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.paired_comparison import PairedComparisonResult


class PairedComparisonView(QWidget):
    """Display occasion summaries, paired charts and test interpretation."""

    def __init__(self, result: PairedComparisonResult, parent: QWidget | None = None) -> None:
        """Initialize the paired comparison result view.

        Args:
            result: Paired comparison result to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if result.error is not None:
            layout.addWidget(self._build_message(self._error_text(result.error)))
            return
        if result.plot_data is None:
            label = self._build_message(self.tr("Select measurement columns and click Apply to run the paired test."))
            label.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(label)
            return

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_table_section(result))
        splitter.addWidget(self._build_chart_section(result))
        splitter.addWidget(self._build_results_section(result))
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([250, 350, 160])
        layout.addWidget(splitter, 1)

    def _build_results_section(self, result: PairedComparisonResult) -> QWidget:
        """Build the statistical results and complete-cohort interpretation."""
        method = result.method
        if method is PairedComparisonMethod.WILCOXON:
            test_name = self.tr("Wilcoxon signed-rank test")
        elif method is PairedComparisonMethod.FRIEDMAN:
            test_name = self.tr("Friedman test")
        else:
            raise ValueError

        summary = [
            self.tr("<b>{test}</b>").format(test=test_name),
            self.tr("Measurement columns: {columns}").format(columns=html.escape(", ".join(result.columns))),
            self.tr("Test statistic = {statistic}, p = {p}").format(
                statistic=fmt_num(result.statistic),
                p=html.escape(fmt_p_value(result.p_value)),
            ),
            self.tr("Complete subjects: {complete} of {total}; excluded for missing values: {excluded}").format(
                complete=fmt_int(result.complete_subjects),
                total=fmt_int(result.total_subjects),
                excluded=fmt_int(result.excluded_subjects),
            ),
        ]
        if method is PairedComparisonMethod.FRIEDMAN and not math.isnan(result.kendall_w):
            summary.append(self.tr("Kendall's W: {effect}").format(effect=fmt_num(result.kendall_w)))
        summary.append(self.tr("Rows are treated as paired subjects across the selected measurement columns."))
        summary.append(self.tr("Occasions follow the selected column order; chronological order is not inferred."))
        summary.append(self.tr("Boxplots use all complete subjects; whiskers show the minimum and maximum."))
        if result.plot_data is not None and result.plot_data.sampled:
            summary.append(
                self.tr("Trajectories show a deterministic sample of {shown} of {total} complete subjects.").format(
                    shown=fmt_int(len(result.plot_data.trajectories)),
                    total=fmt_int(result.complete_subjects),
                )
            )
            summary.append(self.tr("Tables, boxplots and tests use all complete subjects."))
        label = self._build_message("<br>".join(summary))
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        panel, layout = self._build_section(self.tr("Test results"))
        layout.addWidget(label)
        return panel

    def _build_section(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        """Build a titled splitter section using plain-text headings."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title, panel)
        label.setTextFormat(Qt.TextFormat.PlainText)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        layout.addWidget(label)
        return panel, layout

    def _build_table_section(self, result: PairedComparisonResult) -> QWidget:
        """Build one non-editable summary row per selected occasion."""
        panel, layout = self._build_section(self.tr("Measurement summary"))
        table = QTableWidget(len(result.summaries), 7, panel)
        table.setHorizontalHeaderLabels([
            self.tr("Measurement"),
            self.tr("Count"),
            self.tr("Mean"),
            self.tr("Median"),
            self.tr("Std Dev"),
            self.tr("Q1"),
            self.tr("Q3"),
        ])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        header = table.verticalHeader()
        if header is not None:
            header.setVisible(False)
        for row, summary in enumerate(result.summaries):
            values = (
                summary.column,
                fmt_int(summary.count),
                fmt_num(summary.mean),
                fmt_num(summary.median),
                fmt_num(summary.std),
                fmt_num(summary.q1),
                fmt_num(summary.q3),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, column, item)
        table.resizeColumnsToContents()
        layout.addWidget(table)
        return panel

    def _build_chart_section(self, result: PairedComparisonResult) -> QWidget:
        """Render prepared distributions and paired trajectories without processing data."""
        panel, layout = self._build_section(self.tr("Paired measurements"))
        figure = Figure(constrained_layout=True)
        canvas = FigureCanvasQTAgg(figure)  # type: ignore[no-untyped-call]
        canvas.setMinimumHeight(260)
        distribution = figure.add_subplot(121)
        trajectories = figure.add_subplot(122)
        distribution.bxp(
            [
                {
                    "label": summary.column,
                    "med": summary.median,
                    "q1": summary.q1,
                    "q3": summary.q3,
                    "whislo": summary.minimum,
                    "whishi": summary.maximum,
                    "fliers": [],
                }
                for summary in result.summaries
            ],
            showfliers=False,
        )
        distribution.set_title(self.tr("Distribution by occasion"))
        distribution.set_ylabel(self.tr("Value"))
        positions = list(range(1, len(result.columns) + 1))
        if result.plot_data is not None:
            for values in result.plot_data.trajectories:
                trajectories.plot(positions, values, marker=".", color="tab:blue", alpha=0.25, linewidth=0.8)
        trajectories.set_xticks(positions, result.columns)
        trajectories.set_title(self.tr("Subject trajectories"))
        trajectories.set_ylabel(self.tr("Value"))
        for axis in (distribution, trajectories):
            axis.set_xlabel(self.tr("Measurement occasion"))
            axis.tick_params(axis="x", labelrotation=30)
        layout.addWidget(canvas)
        return panel

    def _build_message(self, text: str) -> QLabel:
        """Build a wrapped result or error label."""
        label = QLabel(text, self)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        return label

    def _error_text(self, error: PairedComparisonError) -> str:
        """Translate a structured paired-test error for display."""
        messages = {
            PairedComparisonError.NOT_ENOUGH_COLUMNS: self.tr("Select at least two numeric measurement columns."),
            PairedComparisonError.INVALID_COLUMN: self.tr(
                "The selected measurement columns are not valid numeric columns."
            ),
            PairedComparisonError.NOT_ENOUGH_COMPLETE_SUBJECTS: self.tr(
                "There are not enough subjects with complete measurements for this paired test."
            ),
            PairedComparisonError.NO_DIFFERENCES: self.tr(
                "The two measurements are identical for every complete subject; the Wilcoxon test is undefined."
            ),
            PairedComparisonError.NO_VARIATION: self.tr(
                "The selected measurements do not vary across occasions, so the Friedman test is undefined."
            ),
        }
        return messages[error]
