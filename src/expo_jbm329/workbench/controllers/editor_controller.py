"""Controller for the SQL editor widget.

This module provides a small orchestration layer around the editor widget,
handling SQL insertion and retrieval while keeping editor-specific logic out
of the main application flow.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import override

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QPlainTextEdit


class EditorController(QObject):
    """Handle SQL editor interactions for ExpoStudio."""

    _INDENT_UNIT = "    "
    _CONTINUATION_LINE_PATTERNS = (
        re.compile(r"\bWITH\s+\S+(?:\s*\([^)]*\))?\s+AS\s*$", re.IGNORECASE),
        re.compile(r"\bWHERE\s*$", re.IGNORECASE),
        re.compile(r"\bON\s*$", re.IGNORECASE),
        re.compile(r"\bJOIN\b.*\bON\s*$", re.IGNORECASE),
    )

    def __init__(self, editor: QPlainTextEdit):
        """Initialize the editor controller.

        Args:
            editor: The SQL editor widget managed by this controller.
        """
        super().__init__(editor)
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

    def compute_next_line_indent(self) -> str:
        """Return the indentation to use for a new line at the cursor."""
        base_indent = self.get_current_line_indent()
        line_text = self.get_current_line_text()

        if self._has_unmatched_open_parenthesis(line_text):
            return f"{base_indent}{self._INDENT_UNIT}"

        if self._should_increase_indent_for_sql_continuation(line_text):
            return f"{base_indent}{self._INDENT_UNIT}"

        return base_indent

    @staticmethod
    def _has_unmatched_open_parenthesis(line_text: str) -> bool:
        """Return whether the line has more opening than closing parentheses."""
        return line_text.count("(") > line_text.count(")")

    @classmethod
    def _should_increase_indent_for_sql_continuation(cls, line_text: str) -> bool:
        """Return whether a SQL continuation pattern should add one indent level."""
        stripped_line = line_text.rstrip()
        if not stripped_line:
            return False

        return any(pattern.search(stripped_line) for pattern in cls._CONTINUATION_LINE_PATTERNS)

    def install(self) -> None:
        """Install editor event filtering handled by this controller."""
        self._editor.installEventFilter(self)

    @override
    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        """Handle Enter-key indentation for the managed editor."""
        if obj is self._editor and event is not None and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            if self.handle_keypress(event):
                return True

        return super().eventFilter(obj, event)

    def handle_keypress(self, event: QKeyEvent) -> bool:
        """Handle editor key presses owned by this controller."""
        if event.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return False

        cursor = self._editor.textCursor()
        cursor.insertText(f"\n{self.compute_next_line_indent()}")
        self._editor.setTextCursor(cursor)
        return True

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
