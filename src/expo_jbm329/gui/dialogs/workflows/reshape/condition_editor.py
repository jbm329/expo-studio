"""Editable condition text and stable per-metric builder state."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

from expo_jbm329.services.data_operations.reshape_conditions import ConditionGroup, format_condition


class ConditionEditor(QWidget):
    """Own manual text and the last applied builder group for one metric."""

    builder_requested = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        """Build the text field and its right-aligned builder button."""
        super().__init__(parent)
        self._applied: ConditionGroup | None = None
        self._expression: str | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.text = QLineEdit(self)
        self.text.setAccessibleName(self.tr("Condition"))
        self.text.setToolTip(
            self.tr("Edit condition syntax or use the builder. Manual syntax is not validated or executed.")
        )
        self.button = QPushButton("...", self)
        self.button.setAutoDefault(False)
        self.button.setFixedWidth(self.button.sizeHint().height() + 8)
        self.button.setAccessibleName(self.tr("Build condition"))
        layout.addWidget(self.text, 1)
        layout.addWidget(self.button)
        self.button.clicked.connect(self.builder_requested)

    def restorable_group(self) -> ConditionGroup | None:
        """Return applied builder state only if manual text is unchanged."""
        return self._applied if self.text.text() == self._expression else None

    def apply_group(self, group: ConditionGroup) -> None:
        """Replace this editor's text after a successful builder acceptance."""
        expression = format_condition(group)
        self._applied = group
        self._expression = expression
        self.text.setText(expression)
