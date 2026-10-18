"""Choose report components and add a note to an analysis entry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, Qt
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
        configuration: tuple[str, ...] = (),
        component_translation_context: str | None = None,
        review: tuple[tuple[str, ...], tuple[str, ...]] | None = None,
        action_label: str | None = None,
        unavailable_components: tuple[str, ...] = (),
    ) -> None:
        """Build the component and notes editor.

        Args:
            analysis_label: Display name of the applied analysis.
            parent: Optional parent widget.
            components: Available tables and charts.
            selected_components: Component keys already selected for an existing entry.
            note: Existing report note.
            existing: Whether this dialog edits an existing entry.
            configuration: Plain-text applied settings shown below the title.
            component_translation_context: Optional canonical Qt translation context.
            review: Stored and incoming configuration lines shown during explicit replacement/update.
            action_label: Optional accept-button label for a reviewed result.
            unavailable_components: Previously selected components absent from the incoming result.
        """
        super().__init__(parent)
        if review is None:
            self.setWindowTitle(self.tr("Edit report entry") if existing else self.tr("Add to report"))
        else:
            self.setWindowTitle(self.tr("Review report result"))
        self.resize(520, 360)
        layout = QVBoxLayout(self)
        heading = QLabel(analysis_label, self)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        if configuration:
            settings = QLabel("\n".join(configuration), self)
            settings.setWordWrap(True)
            settings.setTextFormat(Qt.TextFormat.PlainText)
            settings.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(settings)
        if review is not None:
            review_box = QGroupBox(self.tr("Stored and incoming configuration"), self)
            review_layout = QVBoxLayout(review_box)
            for title, lines in zip(
                (self.tr("Stored result"), self.tr("Incoming result")),
                review,
                strict=True,
            ):
                detail = QLabel("\n".join((title, *lines)), review_box)
                detail.setWordWrap(True)
                detail.setTextFormat(Qt.TextFormat.PlainText)
                detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                review_layout.addWidget(detail)
            layout.addWidget(review_box)
        if unavailable_components:
            unavailable_label = QLabel(
                self.tr("Unavailable stored selections: {components}").format(
                    components=", ".join(unavailable_components)
                ),
                self,
            )
            unavailable_label.setWordWrap(True)
            unavailable_label.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(unavailable_label)
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
                label = (
                    QCoreApplication.translate(component_translation_context, component.label)
                    if component_translation_context is not None
                    else self.tr(component.label)
                )
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
        default_action = self.tr("Save changes") if existing else self.tr("Add to report")
        self._save_button = QPushButton(action_label or default_action, buttons)
        buttons.addButton(self._save_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self._update_save_enabled()
        self._save_button.clicked.connect(self.accept)
        self._remove_requested = False
        if existing and review is None:
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
