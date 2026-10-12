"""Report workspace preview, without report collection or file generation."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ReportPage(QWidget):
    """Present the planned report layout while processing is unavailable."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the empty report page.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
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
        self._empty_message = QLabel(
            self.tr("No analyses have been added. Report collection will be available in a later step."),
            analyses,
        )
        self._empty_message.setWordWrap(True)
        self._empty_message.setTextFormat(Qt.TextFormat.PlainText)
        analyses_layout.addWidget(self._empty_message)
        self._entries = QListWidget(analyses)
        self._entries.setAccessibleName(self.tr("Selected analyses"))
        analyses_layout.addWidget(self._entries, 1)
        controls = QHBoxLayout()
        for text in (self.tr("Move up"), self.tr("Move down"), self.tr("Edit note"), self.tr("Remove")):
            controls.addWidget(self._preview_button(text, analyses))
        controls.addStretch()
        analyses_layout.addLayout(controls)
        layout.addWidget(analyses, 1)

        footer = QHBoxLayout()
        explanation = QLabel(
            self.tr("Layout preview only. Adding analyses and generating files are not implemented yet."),
            self,
        )
        explanation.setWordWrap(True)
        footer.addWidget(explanation, 1)
        footer.addWidget(self._preview_button(self.tr("Generate HTML report"), self))
        layout.addLayout(footer)

    def _preview_button(self, text: str, parent: QWidget) -> QPushButton:
        """Build a disabled processing control with an explicit explanation."""
        button = QPushButton(text, parent)
        button.setEnabled(False)
        button.setToolTip(self.tr("Not implemented yet. This step previews the report layout only."))
        return button

    def report_title(self) -> str:
        """Return the plain-text title entered in this window."""
        return self._title.text()

    def report_description(self) -> str:
        """Return the plain-text description entered in this window."""
        return self._description.toPlainText()
