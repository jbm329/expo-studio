"""Dataset Overview view widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from expo_jbm329.utils.format_utils import fmt_int, fmt_pct

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.overview import DatasetOverviewResult


class OverviewView(QWidget):
    """Displays a `DatasetOverviewResult` as a structural dataset summary."""

    def __init__(self, result: DatasetOverviewResult, parent: QWidget | None = None) -> None:
        """Initialize the Dataset Overview view.

        Args:
            result: The computed dataset overview to display.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._result = result

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._build_summary_label())
        layout.addWidget(self._build_section_header(self.tr("Column types")))
        layout.addWidget(self._build_column_types_label())
        layout.addWidget(self._build_section_header(self.tr("Potential issues")))
        layout.addWidget(self._build_warnings_label())
        layout.addStretch(1)

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _build_summary_label(self) -> QLabel:
        """Build the top-level rows/columns/missing/duplicates summary."""
        r = self._result

        text = (
            f"{self.tr('Rows')}: <b>{fmt_int(r.row_count)}</b> &nbsp;&nbsp; "
            f"{self.tr('Columns')}: <b>{fmt_int(r.column_count)}</b><br>"
            f"{self.tr('Missing values')}: <b>{fmt_pct(r.missing_cell_fraction)}</b> "
            f"({fmt_int(r.missing_cell_count)}) &nbsp;&nbsp; "
            f"{self.tr('Duplicate rows')}: <b>{fmt_int(r.duplicate_row_count)}</b> "
            f"({fmt_pct(r.duplicate_row_fraction)})"
        )
        label = QLabel(text, self)
        label.setWordWrap(True)
        label.setStyleSheet("margin-bottom: 6px;")
        return label

    def _build_column_types_label(self) -> QLabel:
        """Build the column-type breakdown section."""
        r = self._result

        lines = [
            f"{self.tr('Numeric columns')}: <b>{fmt_int(r.numeric_column_count)}</b>",
            f"{self.tr('Categorical columns')}: <b>{fmt_int(r.categorical_column_count)}</b>",
            f"{self.tr('Datetime columns')}: <b>{fmt_int(r.datetime_column_count)}</b>",
            f"{self.tr('Boolean columns')}: <b>{fmt_int(r.boolean_column_count)}</b>",
            f"{self.tr('Other columns')}: <b>{fmt_int(r.other_column_count)}</b>",
        ]
        label = QLabel("<br>".join(lines), self)
        label.setWordWrap(True)
        label.setStyleSheet("margin-bottom: 6px;")
        return label

    def _build_warnings_label(self) -> QLabel:
        """Build the high-missing-columns warning section."""
        if not self._result.high_missing_columns:
            label = QLabel(self.tr("No issues detected."), self)
            label.setStyleSheet("color: #666;")
            return label

        lines = [
            self.tr("⚠ {column} has {pct} missing values.").format(column=column, pct=fmt_pct(fraction))
            for column, fraction in self._result.high_missing_columns
        ]
        label = QLabel("<br>".join(lines), self)
        label.setWordWrap(True)
        label.setStyleSheet("color: #cc6600;")
        return label

    def _build_section_header(self, text: str) -> QLabel:
        """Build a small bold section header label."""
        label = QLabel(text, self)
        label.setStyleSheet("font-weight: bold; margin-top: 4px;")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        return label
