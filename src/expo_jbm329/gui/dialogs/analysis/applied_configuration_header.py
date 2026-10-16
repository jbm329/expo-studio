"""Compact presentation of an analysis's applied configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from expo_jbm329.gui.dialogs.analysis.section_layout import ANALYSIS_FRAME_MARGINS, apply_analysis_frame

if TYPE_CHECKING:
    from expo_jbm329.services.analysis.presentation import AnalysisPresentation


class AppliedConfigurationHeader(QFrame):
    """Show an analysis title and selectable, structured applied settings."""

    def __init__(self, presentation: AnalysisPresentation, parent: QWidget | None = None) -> None:
        """Build the header without changing the captured configuration.

        Args:
            presentation: Title and ordered fields from the applied result.
            parent: Optional owning widget.
        """
        super().__init__(parent)
        apply_analysis_frame(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*ANALYSIS_FRAME_MARGINS)
        title = QLabel(presentation.title, self)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        fields = QGridLayout()
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setHorizontalSpacing(12)
        fields.setVerticalSpacing(4)
        fields.setColumnStretch(1, 1)
        layout.addLayout(fields)
        for row, field in enumerate(presentation.configuration):
            label = QLabel(field.label, self)
            value = QLabel(field.display_value, self)
            for widget in (label, value):
                widget.setTextFormat(Qt.TextFormat.PlainText)
                widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            fields.addWidget(label, row, 0)
            fields.addWidget(value, row, 1)
