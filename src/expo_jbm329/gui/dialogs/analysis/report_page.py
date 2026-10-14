"""Workspace for reviewing and curating a report draft."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.services.analysis.categories import AnalysisCategory

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.report import ReportEntry


class ReportPage(QWidget):
    """Present report details and the ordered collection of applied analyses."""

    edit_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)
    move_requested = pyqtSignal(str, int)
    preview_requested = pyqtSignal()
    generate_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the empty report page.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._preview_busy = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        details = QGroupBox(self.tr("Report details"), self)
        form = QFormLayout(details)
        self._title = QLineEdit(details)
        self._title.setPlaceholderText(self.tr("Enter a report title"))
        self._description = QPlainTextEdit(details)
        self._description.setPlaceholderText(self.tr("Describe the purpose of this report"))
        self._description.setMaximumHeight(120)
        title_label = QLabel(self.tr("Title"), details)
        title_label.setBuddy(self._title)
        description_label = QLabel(self.tr("Description"), details)
        description_label.setBuddy(self._description)
        form.addRow(title_label, self._title)
        form.addRow(description_label, self._description)
        layout.addWidget(details)

        analyses = QGroupBox(self.tr("Selected analyses"), self)
        analyses_layout = QVBoxLayout(analyses)
        self._empty_message = QLabel(self.tr("No analyses have been added to this report."), analyses)
        self._empty_message.setWordWrap(True)
        self._empty_message.setTextFormat(Qt.TextFormat.PlainText)
        analyses_layout.addWidget(self._empty_message)
        self._entries = QListWidget(analyses)
        self._entries.setAccessibleName(self.tr("Selected analyses"))
        self._entries.currentRowChanged.connect(self._update_controls)
        analyses_layout.addWidget(self._entries, 1)
        controls = QHBoxLayout()
        self._move_up_button = QPushButton(self.tr("Move up"), analyses)
        self._move_down_button = QPushButton(self.tr("Move down"), analyses)
        self._edit_button = QPushButton(self.tr("Edit entry"), analyses)
        self._remove_button = QPushButton(self.tr("Remove"), analyses)
        for button in (self._move_up_button, self._move_down_button, self._edit_button, self._remove_button):
            controls.addWidget(button)
        self._move_up_button.clicked.connect(lambda: self._emit_move(-1))
        self._move_down_button.clicked.connect(lambda: self._emit_move(1))
        self._edit_button.clicked.connect(self._emit_edit)
        self._remove_button.clicked.connect(self._emit_remove)
        controls.addStretch()
        analyses_layout.addLayout(controls)
        layout.addWidget(analyses, 1)

        footer = QHBoxLayout()
        explanation = QLabel(self.tr("Add analyses, arrange the report, then generate an HTML file."), self)
        explanation.setWordWrap(True)
        footer.addWidget(explanation, 1)
        self._preview_button = QPushButton(self.tr("Preview"), self)
        self._preview_button.setEnabled(False)
        self._preview_button.clicked.connect(self.preview_requested)
        footer.addWidget(self._preview_button)
        self._generate_button = QPushButton(self.tr("Generate HTML report"), self)
        self._generate_button.setEnabled(False)
        self._generate_button.clicked.connect(self.generate_requested)
        footer.addWidget(self._generate_button)
        layout.addLayout(footer)
        self._preview_status = QLabel(self)
        self._preview_status.setWordWrap(True)
        self._preview_status.setTextFormat(Qt.TextFormat.PlainText)
        self._preview_status.hide()
        layout.addWidget(self._preview_status)
        self._update_controls()

    def report_title(self) -> str:
        """Return the plain-text title entered in this window."""
        return self._title.text()

    def report_description(self) -> str:
        """Return the plain-text description entered in this window."""
        return self._description.toPlainText()

    def set_preview_busy(self, busy: bool) -> None:
        """Prevent concurrent preview/save requests while report content is prepared."""
        self._preview_busy = busy
        self._update_controls()

    def set_preview_status(self, text: str) -> None:
        """Present a preview failure or cancellation as literal text."""
        self._preview_status.setText(text)
        self._preview_status.setVisible(bool(text))

    def set_entries(self, entries: tuple[ReportEntry, ...]) -> None:
        """Replace the visible ordered entry list."""
        selected_id = self.selected_entry_id()
        self._entries.blockSignals(True)
        self._entries.clear()
        selected_item: QListWidgetItem | None = None
        category_labels = {
            AnalysisCategory.OVERVIEW: "Overview",
            AnalysisCategory.STATISTICS: "Statistics",
            AnalysisCategory.HYPOTHESIS_TESTS: "Hypothesis Tests",
            AnalysisCategory.CORRELATION: "Correlation",
            AnalysisCategory.REGRESSION: "Regression",
            AnalysisCategory.OUTLIERS: "Outliers",
            AnalysisCategory.CLUSTERING: "Clustering",
            AnalysisCategory.PCA: "PCA",
            AnalysisCategory.TIME_SERIES: "Time Series",
        }
        for entry in entries:
            item = QListWidgetItem(
                f"{self.tr(category_labels[entry.category])} - {entry.dataset_name}",
                self._entries,
            )
            item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
            item.setToolTip(
                self.tr("{rows} rows x {columns} columns - {date}").format(
                    rows=entry.dataset_rows, columns=entry.dataset_columns, date=entry.analysis_date
                )
            )
            if entry.entry_id == selected_id:
                selected_item = item
        if selected_item is not None:
            self._entries.setCurrentItem(selected_item)
        elif entries:
            self._entries.setCurrentRow(0)
        self._entries.blockSignals(False)
        self._empty_message.setVisible(not entries)
        self._update_controls()

    def selected_entry_id(self) -> str | None:
        """Return the stable ID for the selected row, if any."""
        item = self._entries.currentItem()
        if item is None:
            return None
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        return entry_id if isinstance(entry_id, str) else None

    def select_entry(self, entry_id: str) -> None:
        """Select an entry by stable ID."""
        for row in range(self._entries.count()):
            item = self._entries.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == entry_id:
                self._entries.setCurrentRow(row)
                return

    def _emit_edit(self) -> None:
        entry_id = self.selected_entry_id()
        if entry_id is not None:
            self.edit_requested.emit(entry_id)

    def _emit_remove(self) -> None:
        entry_id = self.selected_entry_id()
        if entry_id is not None:
            self.remove_requested.emit(entry_id)

    def _emit_move(self, offset: int) -> None:
        entry_id = self.selected_entry_id()
        if entry_id is not None:
            self.move_requested.emit(entry_id, offset)

    def _update_controls(self, _row: int = -1) -> None:
        row = self._entries.currentRow()
        has_selection = row >= 0
        self._move_up_button.setEnabled(has_selection and row > 0)
        self._move_down_button.setEnabled(has_selection and row < self._entries.count() - 1)
        self._edit_button.setEnabled(has_selection)
        self._remove_button.setEnabled(has_selection)
        self._preview_button.setEnabled(self._entries.count() > 0 and not self._preview_busy)
        self._generate_button.setEnabled(self._entries.count() > 0 and not self._preview_busy)
