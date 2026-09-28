"""Dataset Overview view widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.services.analysis.overview import SAMPLE_ROW_LIMIT
from expo_jbm329.services.data_operations.dtypes import SemanticDType
from expo_jbm329.utils.format_utils import fmt_cell, fmt_int, fmt_pct

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.overview import ColumnOverview, DatasetOverviewResult

_RIGHT_ALIGNED = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
# Index of the first right-aligned (numeric) column in the columns table.
_FIRST_NUMERIC_COLUMN = 3
# Keeps the summary text readable before the user drags the splitter.
_SUMMARY_PANEL_MIN_WIDTH = 320


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
        self._columns_table: QTableWidget | None = None
        self._sample_table: QTableWidget | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top_row = QSplitter(Qt.Orientation.Horizontal, self)
        top_row.addWidget(self._build_summary_panel())
        top_row.addWidget(self._build_columns_panel())
        top_row.setStretchFactor(0, 0)
        top_row.setStretchFactor(1, 1)
        top_row.setSizes([_SUMMARY_PANEL_MIN_WIDTH, _SUMMARY_PANEL_MIN_WIDTH * 3])

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(top_row)
        splitter.addWidget(self._build_sample_panel())
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def columns_table(self) -> QTableWidget | None:
        """Return the per-column detail table, or `None` if there are no columns."""
        return self._columns_table

    def sample_table(self) -> QTableWidget | None:
        """Return the sample-rows table, or `None` if there are no rows to show."""
        return self._sample_table

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _build_summary_panel(self) -> QScrollArea:
        """Build the framed, scrollable panel holding the textual dataset facts."""
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(self._build_section_header(self.tr("Summary")))
        layout.addWidget(self._build_summary_label())
        layout.addWidget(self._build_section_header(self.tr("Column types")))
        layout.addWidget(self._build_column_types_label())
        layout.addWidget(self._build_section_header(self.tr("Potential issues")))
        layout.addWidget(self._build_warnings_label())
        layout.addStretch(1)

        panel = QScrollArea(self)
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setFrameShadow(QFrame.Shadow.Sunken)
        panel.setWidgetResizable(True)
        panel.setWidget(content)
        # The labels wrap, so only vertical overflow needs a scrollbar.
        panel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        panel.setMinimumWidth(_SUMMARY_PANEL_MIN_WIDTH)
        return panel

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

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def _build_columns_panel(self) -> QWidget:
        """Build the per-column detail table with its header."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section_header(self.tr("Columns")))

        if not self._result.columns:
            layout.addWidget(self._build_empty_label(self.tr("This dataset has no columns.")))
            return panel

        headers = [
            self.tr("Column"),
            self.tr("Type"),
            self.tr("Storage type"),
            self.tr("Missing"),
            self.tr("Missing %"),
            self.tr("Unique"),
        ]
        table = self._build_table(panel, headers, len(self._result.columns))
        for row, column in enumerate(self._result.columns):
            for index, text in enumerate(self._column_row(column)):
                item = QTableWidgetItem(text)
                if index >= _FIRST_NUMERIC_COLUMN:
                    item.setTextAlignment(_RIGHT_ALIGNED)
                table.setItem(row, index, item)

        self._finish_table(table)
        layout.addWidget(table)
        self._columns_table = table
        return panel

    def _column_row(self, column: ColumnOverview) -> list[str]:
        """Return the formatted table cells for one column summary."""
        return [
            column.column,
            self._dtype_label(column.semantic_dtype),
            column.dtype_name,
            fmt_int(column.missing_count),
            fmt_pct(column.missing_fraction),
            fmt_int(column.unique_count),
        ]

    def _build_sample_panel(self) -> QWidget:
        """Build the raw sample-rows table with its header."""
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        result = self._result
        if result.sample_truncated:
            header = self.tr("Sample (first {count} rows)").format(count=fmt_int(SAMPLE_ROW_LIMIT))
        else:
            header = self.tr("Sample (all {count} rows)").format(count=fmt_int(result.row_count))
        layout.addWidget(self._build_section_header(header))

        if not result.sample_rows:
            layout.addWidget(self._build_empty_label(self.tr("This dataset has no rows to preview.")))
            return panel

        table = self._build_table(panel, list(result.sample_columns), len(result.sample_rows))
        for row, values in enumerate(result.sample_rows):
            for index, value in enumerate(values):
                table.setItem(row, index, QTableWidgetItem(fmt_cell(value)))

        self._finish_table(table)
        layout.addWidget(table)
        self._sample_table = table
        return panel

    @staticmethod
    def _build_table(parent: QWidget, headers: list[str], row_count: int) -> QTableWidget:
        """Build a read-only table pre-sized for `headers` and `row_count`."""
        table = QTableWidget(parent)
        table.setColumnCount(len(headers))
        table.setRowCount(row_count)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        vertical_header = table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
        return table

    @staticmethod
    def _finish_table(table: QTableWidget) -> None:
        """Size the columns to their content, then let the user resize them."""
        table.resizeColumnsToContents()
        header = table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def _build_empty_label(self, text: str) -> QLabel:
        """Build a muted placeholder label for an empty table section."""
        label = QLabel(text, self)
        label.setStyleSheet("color: #666;")
        label.setWordWrap(True)
        return label

    def _dtype_label(self, semantic: SemanticDType) -> str:
        """Return the translated display label for a semantic dtype."""
        labels = {
            SemanticDType.INT: self.tr("Integer"),
            SemanticDType.FLOAT: self.tr("Float"),
            SemanticDType.BOOL: self.tr("Boolean"),
            SemanticDType.DATETIME: self.tr("Datetime"),
            SemanticDType.STRING: self.tr("Text"),
            SemanticDType.CATEGORY: self.tr("Category"),
            SemanticDType.OTHER: self.tr("Other"),
        }
        return labels[semantic]
