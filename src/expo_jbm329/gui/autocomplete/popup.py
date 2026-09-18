"""Popup widget for the SQL autocomplete.

This module provides a tooltip-style popup window that displays and manages
a list of SQL autocomplete suggestions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtWidgets import QFrame, QListWidget, QListWidgetItem, QPlainTextEdit

if TYPE_CHECKING:
    from PyQt6.QtGui import QKeyEvent


class SqlEditorAutoCompletePopup(QFrame):
    """Passive tooltip-style popup for SQL suggestions.

    This popup displays a list of suggestions and does not take focus,
    allowing the user to continue typing in the editor.

    Attributes:
        editor: The editor widget this popup is associated with.
        list: The list widget displaying the suggestions.
    """

    def __init__(self, editor: QPlainTextEdit, parent=None) -> None:
        """Initialize the popup.

        Args:
            editor: The editor widget to position the popup relative to.
            parent: Optional parent widget.
        """
        super().__init__(editor)
        self.editor = editor

        # Identical to original
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.list = QListWidget(self)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemClicked.connect(self._insert_selected)

        self.resize(240, 200)

    def show_suggestions(self, suggestions: list[str]) -> None:
        """Display the provided suggestions in the popup.

        Positions the popup below the editor's cursor and shows it.

        Args:
            suggestions: A list of string suggestions to display.
        """
        self.list.clear()
        if not suggestions:
            self.hide()
            return

        for s in suggestions:
            QListWidgetItem(s, self.list)
        self.list.setCurrentRow(0)

        try:
            cursor_rect: QRect = self.editor.cursorRect()
            global_pos = self.editor.mapToGlobal(cursor_rect.bottomLeft())
            self.move(global_pos + QPoint(0, 4))
        except Exception:
            pass

        self.show()
        self.editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def handle_key(self, event: QKeyEvent) -> bool:
        """Handle key events for navigating and selecting suggestions.

        Args:
            event: The key event to handle.

        Returns:
            True if the event was handled, False otherwise.
        """
        key = event.key()

        if key in (Qt.Key.Key_Down, Qt.Key.Key_PageDown):
            i = self.list.currentRow()
            self.list.setCurrentRow(min(i + 1, self.list.count() - 1))
            return True

        if key in (Qt.Key.Key_Up, Qt.Key.Key_PageUp):
            i = self.list.currentRow()
            self.list.setCurrentRow(max(i - 1, 0))
            return True

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            self._insert_selected()
            return True

        if key == Qt.Key.Key_Escape:
            self.hide()
            return True

        return False

    def _insert_selected(self) -> None:
        item = self.list.currentItem()
        if not item:
            self.hide()
            return

        text = item.text()
        cursor = self.editor.textCursor()
        full = self.editor.toPlainText()
        pos = cursor.position()

        start = pos - 1
        while start >= 0 and full[start] not in ". \n\t(),;":
            start -= 1
        start += 1

        cursor.setPosition(start, cursor.MoveMode.MoveAnchor)
        cursor.setPosition(pos, cursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(text)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        self.hide()
