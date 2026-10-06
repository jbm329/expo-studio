"""Paired repeated-measures test result view."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from expo_jbm329.services.analysis.paired_comparison import PairedComparisonError, PairedComparisonMethod
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_p_value

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.paired_comparison import PairedComparisonResult


class PairedComparisonView(QWidget):
    """Displays the paired test, its p-value and the complete-subject count."""

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

        method = result.method
        if method is PairedComparisonMethod.WILCOXON:
            test_name = self.tr("Wilcoxon signed-rank test")
        elif method is PairedComparisonMethod.FRIEDMAN:
            test_name = self.tr("Friedman test")
        else:
            raise ValueError

        summary = [
            self.tr("<b>{test}</b>").format(test=test_name),
            self.tr("Measurement columns: {columns}").format(columns=", ".join(result.columns)),
            self.tr("Test statistic = {statistic}, p = {p}").format(
                statistic=fmt_num(result.statistic),
                p=fmt_p_value(result.p_value),
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
        label = self._build_message("<br>".join(summary))
        label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(label)

    def _build_message(self, text: str) -> QLabel:
        """Build a wrapped result or error label."""
        label = QLabel(text, self)
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
