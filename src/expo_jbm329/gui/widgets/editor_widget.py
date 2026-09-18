"""Editor widget for a single SQL editor tab.

This module provides the EditorWidget class, which is responsible for
presenting a SQL editor UI and reflecting the state of an EditorTab.

The widget is intentionally dumb:
- It does not know about other tabs
- It does not know about connections beyond what EditorTab describes
- It does not execute SQL
- It does not manage tab titles

Its sole responsibility is to render editor UI state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.workbench.controllers.editor_controller import EditorController
from expo_jbm329.workbench.controllers.editor_tab_manager import EditorTab, EditorTabState

if TYPE_CHECKING:
    from PyQt6.QtGui import QTextDocument

    from expo_jbm329.gui.autocomplete.controller import SqlAutocompleteController
    from expo_jbm329.gui.autocomplete.engine import SqlAutoCompleter
    from expo_jbm329.workbench.highlighter.sql_highlighter import SqlHighlighter


class EditorWidget(QWidget):
    """UI widget for a single SQL editor tab."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    __slots__ = (
        "_autocomplete",
        "_autocomplete_engine",
        "_editor",
        "_highlighter",
        "editor_controller",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the editor widget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        # --- Core editor ------------------------------------------------
        self._editor = QPlainTextEdit(self)
        self._editor.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._editor.textChanged.connect(self._on_text_changed)

        self.editor_controller = EditorController(self._editor)
        self.editor_controller.install()

        self._highlighter: SqlHighlighter | None = None
        self._autocomplete: SqlAutocompleteController | None = None
        self._autocomplete_engine: SqlAutoCompleter | None = None

        # --- Layout ----------------------------------------------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._editor)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_highlighter(self, highlighter: SqlHighlighter) -> None:
        """Attach and own a SQL syntax highlighter for this editor."""
        self._highlighter = highlighter

    def set_autocomplete_engine(self, engine: SqlAutoCompleter) -> None:
        """Attach and own a SQL autocomplete engine for this editor."""
        self._autocomplete_engine = engine

    def get_autocomplete_engine(self) -> SqlAutoCompleter:
        """Return the autocomplete engine for this editor.

        This method assumes the engine has been set during widget initialization.
        """
        if self._autocomplete_engine is None:
            msg = "Autocomplete engine not initialized for EditorWidget"
            raise RuntimeError(msg)
        return self._autocomplete_engine

    def set_autocomplete(self, autocomplete: SqlAutocompleteController) -> None:
        """Attach and own a SQL autocomplete controller for this editor."""
        self._autocomplete = autocomplete

    def get_autocomplete(self) -> SqlAutocompleteController:
        """Return the autocomplete controller for this editor.

        This method assumes the controller has been set during widget initialization.
        """
        if self._autocomplete is None:
            msg = "Autocomplete controller not initialized for EditorWidget"
            raise RuntimeError(msg)
        return self._autocomplete

    def apply_tab_state(self, tab: EditorTab) -> None:
        """Apply EditorTab state to the widget UI.

        This method is the only place where EditorTabState is translated
        into visual/editor behavior.

        Args:
            tab: The EditorTab whose state should be reflected.
        """
        if tab.state == EditorTabState.BOUND:
            self._apply_bound_state()

        elif tab.state == EditorTabState.UNBOUND:
            self._apply_unbound_state()

        elif tab.state == EditorTabState.DISCONNECTED:
            self._apply_disconnected_state()

        else:
            # Defensive fallback: treat unknown states as disabled
            self._apply_disconnected_state()

    def focus_editor(self) -> None:
        """Give focus to the SQL editor."""
        self._editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def set_read_only(self, read_only: bool) -> None:
        """Explicitly set editor read-only state.

        Args:
            read_only: Whether the editor should be read-only.
        """
        self._editor.setReadOnly(read_only)

    def set_sql_text(self, sql: str) -> None:
        """Replace the editor contents with the given SQL text.

        Args:
            sql: SQL text to display.
        """
        self._editor.setPlainText(sql)

    def get_sql_text(self) -> str:
        """Return the full SQL text from the editor."""
        return self._editor.toPlainText()

    def get_editor(self) -> QPlainTextEdit:
        """Return the underlying text editor widget."""
        return self._editor

    def get_document(self) -> QTextDocument:
        """Return the editor's document (for syntax highlighting)."""
        doc = self._editor.document()
        if doc is None:
            msg = "Editor document is not available."
            raise RuntimeError(msg)
        return doc

    # ------------------------------------------------------------------
    # Internal state handlers
    # ------------------------------------------------------------------

    def _apply_bound_state(self) -> None:
        """Apply UI state for a bound (active) editor tab."""
        self._editor.setReadOnly(False)

    def _apply_unbound_state(self) -> None:
        """Apply UI state for an unbound editor tab."""
        self._editor.setReadOnly(False)

    def _apply_disconnected_state(self) -> None:
        """Apply UI state for a disconnected editor tab."""
        self._editor.setReadOnly(False)

    def _on_text_changed(self) -> None:
        """Handle text change in the editor."""
        if self.editor_controller:
            self.editor_controller.notify_text_changed()
