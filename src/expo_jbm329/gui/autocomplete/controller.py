"""Controller for the SQL autocomplete functionality.

This module manages the interaction between the editor, the completion engine,
and the popup window to provide a smooth SQL autocompletion experience.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, override

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer

from .popup import SqlEditorAutoCompletePopup

if TYPE_CHECKING:
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QPlainTextEdit

    from .engine import SqlAutoCompleter


class SqlAutocompleteController(QObject):
    """Controller for SQL autocomplete behavior.

    Handles key events from the editor, extracts prefixes, requests suggestions
    from the engine, and manages the visibility and content of the popup.

    Attributes:
        editor: The plain text editor instance.
        completer: The engine that provides SQL suggestions.
        popup: The popup widget that displays suggestions.
        _logger: Logger for debug and error information.
        _debug: Whether to enable debug logging.
    """

    def __init__(
        self,
        editor: QPlainTextEdit,
        completer: SqlAutoCompleter,
        parent=None,
        *,
        debug: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            editor: The editor widget to attach to.
            completer: The engine for suggestions.
            parent: Optional parent QObject.
            debug: Whether to enable debug logging.
            logger: Logger for debug and error information.
        """
        super().__init__(parent)
        self.editor = editor
        self.completer = completer
        self.popup = SqlEditorAutoCompletePopup(editor)
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._debug = bool(debug)
        self._dialect: str | None = None

    # ------------------------------------------------------------------ #
    def install(self) -> None:
        """Install event filters on the editor and popup components."""
        self.editor.installEventFilter(self)
        self.popup.installEventFilter(self)
        self.popup.list.installEventFilter(self)

    def set_schema(self, schema_dict: dict[str, dict[str, list[str]]]) -> None:
        """Update the schema metadata used for suggestions.

        Args:
            schema_dict: A dictionary mapping schema names to table names,
                which in turn map to lists of column names.
        """
        self.completer.set_schema(schema_dict)

    def set_dialect(self, dialect: str | None) -> None:
        """Set the active SQL dialect used for context-aware suggestions."""
        self._dialect = dialect

        if self._debug:
            self._logger.debug(
                "SqlAutocompleteController: dialect set to %r",
                self._dialect,
            )

    # ------------------------------------------------------------------ #
    @override
    def eventFilter(self, obj: Any, event: QEvent) -> bool:
        """Filter events for the editor and popup.

        Args:
            obj: The object being filtered.
            event: The event to process.

        Returns:
            True if the event was handled, False otherwise.
        """
        if event.type() == QEvent.Type.KeyPress and obj in (self.editor, self.popup, self.popup.list):
            return self._handle_keypress(event)
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ #
    def _handle_keypress(self, event: QKeyEvent) -> bool:
        key = event.key()
        text = event.text() or ""

        if self._debug:
            self._logger.debug(
                "SqlAutocompleteController: keypress key=%s text=%r popup_visible=%s",
                key,
                text,
                self.popup.isVisible(),
            )

        # Navigation + accept + escape when popup visible
        if self.popup.isVisible():
            if key in (
                Qt.Key.Key_Up, Qt.Key.Key_Down,
                Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
            ):
                return self.popup.handle_key(event)
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                return self.popup.handle_key(event)
            if key == Qt.Key.Key_Escape:
                return self.popup.handle_key(event)

        # Backspace / delete
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            if self.popup.isVisible():
                QTimer.singleShot(0, self._update_suggestions)
            else:
                self.popup.hide()
            return False

        # Ctrl+Space = global
        if key == Qt.Key.Key_Space and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            QTimer.singleShot(0, self._force_suggestions_now)
            return True

        # Qt6: '.' as Key_Period
        if key == Qt.Key.Key_Period:
            if self._debug:
                self._logger.debug(
                    "SqlAutocompleteController: period key detected; scheduling suggestions."
                )
            QTimer.singleShot(0, self._update_suggestions)
            return False

        # '.' via text
        if text == ".":
            if self._debug:
                self._logger.debug(
                    "SqlAutocompleteController: period text detected; scheduling suggestions."
                )
            QTimer.singleShot(0, self._update_suggestions)
            return False

        # Live filtering when popup open
        if self.popup.isVisible() and (text.isalnum() or text == "_"):
            QTimer.singleShot(0, self._update_suggestions)
            return False

        return False

    # ------------------------------------------------------------------ #
    def _extract_prefix(self) -> str:
        try:
            cursor = self.editor.textCursor()
            pos = cursor.position()
            full = self.editor.toPlainText()

            start = pos - 1
            while start >= 0 and full[start] not in " \n\t(),;":
                start -= 1
            start += 1

            prefix = full[start:pos]

            if self._debug:
                self._logger.debug(
                    "SqlAutocompleteController: extracted prefix=%r at cursor_pos=%s",
                    prefix,
                    pos,
                )

            return prefix
        except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError):
            if self._debug:
                self._logger.debug(
                    "SqlAutocompleteController: prefix extraction failed.",
                    exc_info=True,
                )
            return ""

    # ------------------------------------------------------------------ #
    def _update_suggestions(self) -> None:
        try:
            prefix = self._extract_prefix()
            if not prefix:
                if self._debug:
                    self._logger.debug("SqlAutocompleteController: empty prefix; hiding popup.")
                self.popup.hide()
                return

            cursor = self.editor.textCursor()
            sql = self.editor.toPlainText()
            cursor_pos = cursor.position()

            if self._debug:
                self._logger.debug(
                    "SqlAutocompleteController: updating suggestions prefix=%r cursor_pos=%s dialect=%r sql_len=%s",
                    prefix,
                    cursor_pos,
                    self._dialect,
                    len(sql),
                )

            suggestions = self.completer.get_contextual_suggestions(
                sql,
                cursor_pos,
                prefix,
                dialect=self._dialect,
            )
            self._debug_log(prefix, suggestions)
            self._show_or_hide(suggestions)

        except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError) as e:
            self._logger.debug(
                "SqlAutocompleteController: autocomplete update failed: %s", str(e), exc_info=True
            )
            self.popup.hide()
            QTimer.singleShot(1000, lambda: self._force_suggestions_now())

    # ------------------------------------------------------------------ #
    def _force_suggestions_now(self) -> None:
        try:
            prefix = self._extract_prefix()
            if not prefix:
                suggestions = self.completer.get_all_objects()
                self._debug_log("<empty>", suggestions)
                self._show_or_hide(suggestions)
                return

            suggestions = self.completer.get_global_suggestions(prefix)
            self._debug_log(prefix, suggestions)
            self._show_or_hide(suggestions)

        except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError) as e:
            self._logger.debug("SqlAutocompleteController: forced autocomplete failed: %s", str(e))
            self.popup.hide()

    # ------------------------------------------------------------------ #
    def _show_or_hide(self, suggestions: list[str]) -> None:
        if suggestions:
            self.popup.show_suggestions(suggestions)
        else:
            self.popup.hide()

    def _debug_log(self, prefix: str, suggestions: list[str]) -> None:
        if not self._debug:
            return
        self._logger.debug(
            "SqlAutocompleteController: autocomplete prefix='%s' -> %s suggestion(s): %s",
            prefix,
            len(suggestions),
            suggestions[:10],
        )
