"""Preview of the note collected when adding an analysis to a report."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons


class ReportNotesDialog(QDialog):
    """Allow inspection of the notes workflow without collecting an analysis."""

    def __init__(self, analysis_label: str, parent: QWidget | None = None) -> None:
        """Build the notes preview.

        Args:
            analysis_label: Display name of the analysis being previewed.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle(self.tr("Add to report"))
        self.resize(520, 360)
        layout = QVBoxLayout(self)
        heading = QLabel(analysis_label, self)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self._notes = QPlainTextEdit(self)
        self._notes.setPlaceholderText(self.tr("Optional notes about this analysis"))
        label = QLabel(self.tr("Notes"), self)
        label.setBuddy(self._notes)
        layout.addWidget(label)
        layout.addWidget(self._notes, 1)
        explanation = QLabel(
            self.tr("Layout preview only. Adding an analysis to the report is not implemented yet."),
            self,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        add_button = QPushButton(self.tr("Add to report"), buttons)
        buttons.addButton(add_button, QDialogButtonBox.ButtonRole.ActionRole)
        add_button.setEnabled(False)
        add_button.setToolTip(self.tr("Not implemented yet. No analysis or note will be saved."))
        buttons.rejected.connect(self.reject)
        localize_dialog_buttons(buttons)
        layout.addWidget(buttons)

    def notes(self) -> str:
        """Return the plain-text note currently entered in the preview."""
        return self._notes.toPlainText()
