"""Shared completion and diagnostic drawing for plain-text expression editors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QCompleter, QPlainTextEdit, QTextEdit

from expo_jbm329.services.data_operations.expression_completion import column_completion

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence


def qt_text_position(text: str, position: int) -> int:
    """Convert a Python character offset to a Qt UTF-16 cursor offset."""
    return len(text[:position].encode("utf-16-le")) // 2


def underline_diagnostics(editor: QPlainTextEdit, spans: Iterable[tuple[int, int]]) -> None:
    """Draw error spans without changing editor text, selection or undo state."""
    selections: list[QTextEdit.ExtraSelection] = []
    text = editor.toPlainText()
    for start, end in spans:
        underline_start = max(0, start - 1) if start == end else start
        cursor = editor.textCursor()
        cursor.setPosition(qt_text_position(text, underline_start))
        cursor.setPosition(qt_text_position(text, end), QTextCursor.MoveMode.KeepAnchor)
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        selection.format.setUnderlineColor(QColor("#d32f2f"))
        selections.append(selection)
    editor.setExtraSelections(selections)


class ColumnCompletionSupport(QObject):
    """Own column completion without imposing formula grammar or editor layout."""

    def __init__(
        self,
        editor: QPlainTextEdit,
        names: Sequence[str],
        *,
        enabled: Callable[[], bool],
    ) -> None:
        """Attach completion to an editor with an owner-supplied visibility gate."""
        super().__init__(editor)
        self._editor = editor
        self._enabled = enabled
        sorted_names: list[str] = sorted(set(names), key=str.casefold)
        self.completer = QCompleter(sorted_names, self)
        self.completer.setWidget(editor)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.activated[str].connect(self.insert)
        editor.textChanged.connect(self.update)
        editor.cursorPositionChanged.connect(self.update)

    def context(self) -> tuple[str, int]:
        """Return editor text and the caret's Python character offset."""
        value = self._editor.toPlainText()
        qt_position = self._editor.textCursor().position()
        position = len(value.encode("utf-16-le")[: qt_position * 2].decode("utf-16-le"))
        return value, position

    def update(self) -> None:
        """Filter column suggestions and place the popup within screen bounds."""
        popup = self.completer.popup()
        if popup is None:
            return
        value, position = self.context()
        context = column_completion(value, position)
        if not self._enabled() or context is None or self._editor.textCursor().hasSelection():
            popup.hide()
            return
        self.completer.setCompletionPrefix(context.prefix)
        if self.completer.completionCount() == 0:
            popup.hide()
            return
        model = self.completer.completionModel()
        if model is None:
            return
        popup.setCurrentIndex(model.index(0, 0))
        rectangle = self._editor.cursorRect()
        scrollbar = popup.verticalScrollBar()
        scrollbar_width = scrollbar.sizeHint().width() if scrollbar is not None else 0
        width = max(240, popup.sizeHintForColumn(0) + scrollbar_width + 2 * popup.frameWidth())
        screen = self._editor.screen()
        if screen is not None:
            width = min(width, screen.availableGeometry().width())
        rectangle.setWidth(width)
        self.completer.complete(rectangle)

    def insert(self, name: str) -> None:
        """Replace only the active reference, escaping literal closing brackets."""
        value, position = self.context()
        context = column_completion(value, position)
        if context is None:
            return
        cursor = self._editor.textCursor()
        cursor.setPosition(qt_text_position(value, context.start))
        cursor.setPosition(qt_text_position(value, context.end), QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText("[" + name.replace("]", "]]") + "]")
        self._editor.setTextCursor(cursor)
        popup = self.completer.popup()
        if popup is not None:
            popup.hide()

    def handle_key(self, key: int) -> bool:
        """Accept or dismiss visible suggestions, leaving other keys untouched."""
        popup = self.completer.popup()
        if popup is None or not popup.isVisible():
            return False
        if key in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab}:
            self.insert(popup.currentIndex().data())
            return True
        if key == Qt.Key.Key_Escape:
            popup.hide()
            return True
        return False
