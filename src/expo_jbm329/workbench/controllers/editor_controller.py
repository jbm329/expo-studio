"""Controller for the SQL editor widget.

This module provides a small orchestration layer around the editor widget,
handling SQL insertion and retrieval while keeping editor-specific logic out
of the main application flow.
"""

from __future__ import annotations

from collections.abc import Callable
import re

from PyQt6.QtWidgets import QPlainTextEdit


class EditorController:
    """Handle SQL editor interactions for ExpoStudio."""

    def __init__(self, editor: QPlainTextEdit):
        """Initialize the editor controller.

        Args:
            editor: The SQL editor widget managed by this controller.
        """
        self._editor = editor
        self._on_change: Callable[[], None] | None = None
        self._suppress_change: bool = False

    # ------------------------------------------------------------------
    # SQL insert helper
    # ------------------------------------------------------------------
    def insert_sql(self, sql: str) -> None:
        """Insert SQL into the editor at the current cursor position.

        If text is selected, it is replaced. If the editor already contains
        text, the inserted SQL is separated by two newlines.
        """
        cursor = self._editor.textCursor()

        if cursor.hasSelection():
            cursor.removeSelectedText()

        prefix = ""
        if self._editor.toPlainText().strip():
            prefix = "\n\n"

        cursor.insertText(prefix + sql)
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    # ------------------------------------------------------------------
    # SQL retrieval helper
    # ------------------------------------------------------------------
    def get_sql(self, use_selection: bool) -> str | None:
        """Return selected SQL text or the full editor contents.

        Args:
            use_selection: Whether to return the selected text when a selection
                exists.

        Returns:
            The selected text, the full editor contents, or None if empty.
        """
        if use_selection:
            cursor = self._editor.textCursor()
            if cursor.hasSelection():
                txt = cursor.selection().toPlainText().strip()
                return txt or None

        full = self._editor.toPlainText().strip()
        return full or None

    def get_current_line_text(self) -> str:
        """Return the full text of the line containing the cursor."""
        cursor = self._editor.textCursor()
        block = cursor.block()
        return block.text()

    def get_current_line_indent(self) -> str:
        """Return leading whitespace for the current cursor line."""
        line_text = self.get_current_line_text()
        match = re.match(r"[ \t]*", line_text)
        return match.group(0) if match else ""

    # ------------------------------------------------------------------
    # Handle dirty tab state
    # ------------------------------------------------------------------
    def set_on_change(self, callback: Callable[[], None]) -> None:
        """Register a callback to be invoked when the editor text changes."""
        self._on_change = callback

    def suppress_change(self) -> None:
        """Temporarily suppress dirty notifications."""
        self._suppress_change = True

    def resume_change(self) -> None:
        """Re-enable dirty notifications."""
        self._suppress_change = False

    def notify_text_changed(self) -> None:
        """Notify the controller that the editor text has changed."""
        if self._suppress_change:
            return
        if self._on_change:
            self._on_change()
