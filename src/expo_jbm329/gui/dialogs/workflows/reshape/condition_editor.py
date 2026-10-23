"""Editable condition text and stable per-metric builder state."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QEvent, QPoint, QSignalBlocker, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFocusEvent, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.services.data_operations.reshape_conditions import ConditionGroup, format_condition

if TYPE_CHECKING:
    from PyQt6.QtCore import QObject
    from PyQt6.QtGui import QHideEvent


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
        self._empty_tooltip = self.tr(
            "Edit condition syntax or use the builder. Manual syntax is not validated or executed."
        )
        self.text.setToolTip(self._empty_tooltip)
        self.button = QPushButton("...", self)
        self.button.setAutoDefault(False)
        self.button.setFixedWidth(self.button.sizeHint().height() + 8)
        self.button.setAccessibleName(self.tr("Build condition"))
        self.button.setToolTip(self.tr("Condition builder"))
        layout.addWidget(self.text, 1)
        layout.addWidget(self.button)
        self.button.clicked.connect(self.builder_requested)
        self.popup = QFrame(self, Qt.WindowType.Popup)
        self.popup.setFrameShape(QFrame.Shape.StyledPanel)
        popup_layout = QVBoxLayout(self.popup)
        popup_layout.setContentsMargins(4, 4, 4, 4)
        self.expanded_text = QPlainTextEdit(self.popup)
        self.expanded_text.setAccessibleName(self.text.accessibleName())
        self.expanded_text.setToolTip(self.text.toolTip())
        popup_layout.addWidget(self.expanded_text)
        self._open_timer = QTimer(self)
        self._open_timer.setSingleShot(True)
        self._open_timer.timeout.connect(self._show_popup)
        self.text.installEventFilter(self)
        self.popup.installEventFilter(self)
        self.expanded_text.installEventFilter(self)
        self.text.textChanged.connect(self._sync_expanded_text)
        self.text.textChanged.connect(self._update_collapsed_display)
        self.expanded_text.textChanged.connect(self._sync_inline_text)

    @override
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        """Open on deliberate field focus and close on Escape without reverting."""
        app = QApplication.instance()
        if a0 is self.popup and a1 is not None and app is not None:
            if a1.type() == QEvent.Type.Show:
                app.installEventFilter(self)
            elif a1.type() == QEvent.Type.Hide:
                app.removeEventFilter(self)
                self.text.setCursorPosition(0)
        if (
            a1 is not None
            and a1.type() == QEvent.Type.MouseButtonPress
            and self.popup.isVisible()
            and isinstance(a0, QWidget)
            and a0 is not self.popup
            and not self.popup.isAncestorOf(a0)
        ):
            self.popup.hide()
        if (
            a0 is self.text
            and a1 is not None
            and (
                a1.type() == QEvent.Type.MouseButtonPress
                or (
                    isinstance(a1, QFocusEvent)
                    and a1.type() == QEvent.Type.FocusIn
                    and a1.reason() != Qt.FocusReason.PopupFocusReason
                )
            )
        ):
            self._open_timer.start(0)
        if (
            a0 is self.expanded_text
            and isinstance(a1, QKeyEvent)
            and a1.type() == QEvent.Type.KeyPress
            and a1.key() == Qt.Key.Key_Escape
        ):
            self.popup.hide()
            return True
        return super().eventFilter(a0, a1)

    @override
    def hideEvent(self, a0: QHideEvent | None) -> None:
        """Dismiss the owned overlay when its metric or dialog is hidden."""
        self._open_timer.stop()
        self.popup.hide()
        super().hideEvent(a0)

    def _show_popup(self) -> None:
        if not self.isVisible() or not self.text.hasFocus() or self.popup.isVisible():
            return
        self._sync_expanded_text()
        screen = self.text.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        width = min(max(self.text.width(), 480), available.width())
        height = min(180, available.height())
        anchor = self.text.mapToGlobal(QPoint(0, 0))
        x = max(available.left(), min(anchor.x(), available.right() - width + 1))
        y = max(available.top(), min(anchor.y(), available.bottom() - height + 1))
        self.popup.setGeometry(x, y, width, height)
        cursor = self.expanded_text.textCursor()
        cursor.setPosition(self.text.cursorPosition())
        if self.text.hasSelectedText():
            cursor.setPosition(self.text.selectionStart())
            cursor.setPosition(self.text.selectionStart() + len(self.text.selectedText()), cursor.MoveMode.KeepAnchor)
        self.expanded_text.setTextCursor(cursor)
        self.popup.show()
        self.expanded_text.setFocus(Qt.FocusReason.PopupFocusReason)

    def _update_collapsed_display(self) -> None:
        value = self.text.text()
        escaped = html.escape(value).replace("\n", "<br>")
        tooltip = f"<qt>{escaped}</qt>" if value else self._empty_tooltip
        self.text.setToolTip(tooltip)
        self.expanded_text.setToolTip(tooltip)
        self.text.setCursorPosition(0)

    def _sync_expanded_text(self) -> None:
        value = self.text.text()
        if value != self.expanded_text.toPlainText():
            with QSignalBlocker(self.expanded_text):
                self.expanded_text.setPlainText(value)

    def _sync_inline_text(self) -> None:
        value = self.expanded_text.toPlainText()
        if value != self.text.text():
            self.text.setText(value)

    def restorable_group(self) -> ConditionGroup | None:
        """Return applied builder state only if manual text is unchanged."""
        return self._applied if self.text.text() == self._expression else None

    def apply_group(self, group: ConditionGroup) -> None:
        """Replace this editor's text after a successful builder acceptance."""
        expression = format_condition(group)
        self._applied = group
        self._expression = expression
        self.text.setText(expression)
