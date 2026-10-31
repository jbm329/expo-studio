"""Controller for the SQL autocomplete functionality.

This module manages the interaction between the editor, the completion engine,
and the popup window to provide a smooth SQL autocompletion experience.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QKeyEvent

from .identifiers import identifier_completion, python_index_from_utf16, quote_identifier, split_identifier_prefix
from .popup import SqlEditorAutoCompletePopup

if TYPE_CHECKING:
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
        parent: QObject | None = None,
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
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._debug = bool(debug)
        self._dialect: str | None = None
        self.popup = SqlEditorAutoCompletePopup(editor, format_identifier=self._format_identifier)

    def _format_identifier(self, name: str) -> str:
        return quote_identifier(name, self._dialect)

    # ------------------------------------------------------------------ #
    def install(self) -> None:
        """Install event filters on the editor and popup components."""
        self.editor.installEventFilter(self)
        self.popup.installEventFilter(self)
        self.popup.list.installEventFilter(self)

    def set_schema(self, schema_dict: dict[str, object]) -> None:
        """Update the schema metadata used for suggestions.

        Args:
            schema_dict: A dictionary mapping schema names to table names,
                which in turn map to lists of column names.
        """
        self.completer.set_schema(schema_dict)

    def set_dialect(self, dialect: str | None) -> None:
        """Set the active dialect for suggestions and accepted identifier quoting."""
        self._dialect = dialect

        if self._debug:
            self._logger.debug(
                "SqlAutocompleteController: dialect set to %r",
                self._dialect,
            )

    # ------------------------------------------------------------------ #
    @override
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        """Filter events for the editor and popup.

        Args:
            a0: The object being filtered.
            a1: The event to process.

        Returns:
            True if the event was handled, False otherwise.
        """
        if a1 is not None and a1.type() == QEvent.Type.KeyPress and a0 in (self.editor, self.popup, self.popup.list):
            if not isinstance(a1, QKeyEvent):
                return super().eventFilter(a0, a1)
            return self._handle_keypress(a1)
        return super().eventFilter(a0, a1)

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
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
                Qt.Key.Key_PageUp,
                Qt.Key.Key_PageDown,
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
                self._logger.debug("SqlAutocompleteController: period key detected; scheduling suggestions.")
            QTimer.singleShot(0, self._update_suggestions)
            return False

        # '.' via text
        if text == ".":
            if self._debug:
                self._logger.debug("SqlAutocompleteController: period text detected; scheduling suggestions.")
            QTimer.singleShot(0, self._update_suggestions)
            return False

        # Live filtering when popup open
        if (
            self.popup.isVisible()
            and text.isprintable()
            and not (
                event.modifiers()
                & (
                    Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.AltModifier
                    | Qt.KeyboardModifier.MetaModifier
                )
            )
        ):
            QTimer.singleShot(0, self._update_suggestions)
            return False

        return False

    # ------------------------------------------------------------------ #
    def _extract_prefix(self) -> str | None:
        try:
            cursor = self.editor.textCursor()
            full = self.editor.toPlainText()
            pos = python_index_from_utf16(full, cursor.position())
            context = identifier_completion(full, pos)
            prefix = context.prefix if context is not None else None

            if self._debug:
                self._logger.debug(
                    "SqlAutocompleteController: extracted prefix=%r at cursor_pos=%s",
                    prefix,
                    pos,
                )

        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self._logger.debug(
                "SqlAutocompleteController: prefix extraction failed.",
                exc_info=True,
            )
            return None
        else:
            return prefix

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
            cursor_pos = python_index_from_utf16(sql, cursor.position())

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

        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as e:
            self._logger.debug("SqlAutocompleteController: autocomplete update failed: %s", str(e), exc_info=True)
            self.popup.hide()
            QTimer.singleShot(1000, self._force_suggestions_now)

    # ------------------------------------------------------------------ #
    def _force_suggestions_now(self) -> None:
        try:
            prefix = self._extract_prefix()
            if prefix is None:
                self.popup.hide()
                return
            if not prefix:
                suggestions = self.completer.get_all_objects()
                self._debug_log("<empty>", suggestions)
                self._show_or_hide(suggestions)
                return

            if len(split_identifier_prefix(prefix)) > 1:
                sql = self.editor.toPlainText()
                suggestions = self.completer.get_contextual_suggestions(
                    sql,
                    python_index_from_utf16(sql, self.editor.textCursor().position()),
                    prefix,
                    dialect=self._dialect,
                )
            else:
                suggestions = self.completer.get_global_suggestions(prefix)
            self._debug_log(prefix, suggestions)
            self._show_or_hide(suggestions)

        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as e:
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
