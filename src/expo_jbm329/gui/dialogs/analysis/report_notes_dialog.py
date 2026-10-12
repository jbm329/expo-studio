"""Choose report components and add a note to an analysis entry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.report import ReportComponent


class ReportNotesDialog(QDialog):
    """Collect selected content and a note for one report entry."""

    def __init__(
        self,
        analysis_label: str,
        parent: QWidget | None = None,
        *,
        components: tuple[ReportComponent, ...] = (),
        selected_components: tuple[str, ...] | None = None,
        note: str = "",
        existing: bool = False,
    ) -> None:
        """Build the component and notes editor.

        Args:
            analysis_label: Display name of the applied analysis.
            parent: Optional parent widget.
            components: Available tables and charts.
            selected_components: Component keys already selected for an existing entry.
            note: Existing report note.
            existing: Whether this dialog edits an existing entry.
        """
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit report entry") if existing else self.tr("Add to report"))
        self.resize(520, 360)
        layout = QVBoxLayout(self)
        heading = QLabel(analysis_label, self)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self._component_choices: dict[str, QCheckBox] = {}
        if components:
            group = QGroupBox(self.tr("Include in report"), self)
            choices_layout = QVBoxLayout(group)
            selected = (
                set(selected_components)
                if selected_components is not None
                else {component.key for component in components}
            )
            for component in components:
                label = self.tr(component.label)
                choice = QCheckBox(label, group)
                choice.setChecked(component.key in selected)
                choice.toggled.connect(self._update_save_enabled)
                self._component_choices[component.key] = choice
                choices_layout.addWidget(choice)
            layout.addWidget(group)
        self._notes = QPlainTextEdit(self)
        self._notes.setPlaceholderText(self.tr("Optional notes about this analysis"))
        self._notes.setPlainText(note)
        notes_label = QLabel(self.tr("Notes"), self)
        notes_label.setBuddy(self._notes)
        layout.addWidget(notes_label)
        layout.addWidget(self._notes, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        self._save_button = QPushButton(self.tr("Save changes") if existing else self.tr("Add to report"), buttons)
        buttons.addButton(self._save_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self._update_save_enabled()
        self._save_button.clicked.connect(self.accept)
        self._remove_requested = False
        if existing:
            remove_button = QPushButton(self.tr("Remove from report"), buttons)
            buttons.addButton(remove_button, QDialogButtonBox.ButtonRole.DestructiveRole)
            remove_button.clicked.connect(self._remove_entry)
        buttons.rejected.connect(self.reject)
        localize_dialog_buttons(buttons)
        layout.addWidget(buttons)

    def notes(self) -> str:
        """Return the plain-text note currently entered."""
        return self._notes.toPlainText()

    def selected_components(self) -> tuple[str, ...]:
        """Return selected stable component identifiers in display order."""
        return tuple(key for key, choice in self._component_choices.items() if choice.isChecked())

    def remove_requested(self) -> bool:
        """Return whether the existing entry should be removed."""
        return self._remove_requested

    def _remove_entry(self) -> None:
        self._remove_requested = True
        self.accept()

    def _update_save_enabled(self) -> None:
        self._save_button.setEnabled(any(choice.isChecked() for choice in self._component_choices.values()))
