"""SQL editor linting controller.

This module provides debounced syntax linting for SQL editor widgets.
It is intentionally small and UI-focused; the actual SQL parsing/linting logic
lives in expo_jbm329.db.sql_analysis.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QToolTip, QWidget

from expo_jbm329.db.sql_analysis import SqlDiagnostic, lint_syntax

StatusCallback = Callable[[str, int | None], None]


@dataclass(frozen=True)
class RenderedDiagnostic:
    """Diagnostic with resolved editor offsets."""

    diagnostic: SqlDiagnostic
    start: int
    end: int


class SqlLintController(QObject):
    """Debounced SQL linting controller for a QPlainTextEdit.

    The controller listens for editor text changes, waits briefly, runs syntax
    linting with sqlglot, then renders diagnostics as extra selections.

    Attributes:
        editor: SQL editor widget.
        _dialect: Current sqlglot dialect.
        _timer: Debounce timer.
        _logger: Logger instance.
    """

    def __init__(
            self,
            editor: QPlainTextEdit,
            parent: QObject | None = None,
            *,
            delay_ms: int = 700,
            logger: logging.Logger | None = None,
            set_status: StatusCallback | None = None,
    ) -> None:
        """Initialize the lint controller.

        Args:
            editor: SQL editor widget.
            parent: Optional QObject parent.
            delay_ms: Debounce delay after text changes.
            logger: Optional logger.
            set_status: Optional status bar callback.
        """
        super().__init__(parent)
        self.editor = editor
        self._dialect: str | None = None
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._set_status = set_status
        self._rendered_diagnostics: list[RenderedDiagnostic] = []
        self._viewport: QWidget | None = None
        self._disposed = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(100, int(delay_ms)))
        self._timer.timeout.connect(self._run_lint)

    def install(self) -> None:
        """Install linting behavior on the editor."""
        self._disposed = False

        self.editor.textChanged.connect(self.schedule_lint)

        with contextlib.suppress(RuntimeError):
            self._viewport = self.editor.viewport()
            if self._viewport is not None:
                self._viewport.installEventFilter(self)

        with contextlib.suppress(RuntimeError):
            self.editor.destroyed.connect(self._on_editor_destroyed)

    def _on_editor_destroyed(self) -> None:
        """Mark controller disposed when the editor is destroyed by Qt."""
        self._disposed = True
        self._rendered_diagnostics = []
        self._viewport = None
        self._timer.stop()

    def dispose(self) -> None:
        """Detach linting behavior and clear diagnostics."""
        self._disposed = True

        with contextlib.suppress(Exception):
            self.editor.textChanged.disconnect(self.schedule_lint)

        if self._viewport is not None:
            with contextlib.suppress(Exception):
                self._viewport.removeEventFilter(self)

        self._viewport = None
        self._timer.stop()

        with contextlib.suppress(Exception):
            self.clear_diagnostics()

    def set_dialect(self, dialect: str | None) -> None:
        """Set the SQL dialect used for linting.

        Args:
            dialect: sqlglot dialect name, or None.
        """
        self._dialect = dialect
        self.schedule_lint()

    def schedule_lint(self) -> None:
        """Schedule a debounced lint run."""
        self._timer.start()

    def clear_diagnostics(self) -> None:
        """Clear rendered diagnostics from the editor."""
        self._rendered_diagnostics = []

        if self._disposed:
            return

        with contextlib.suppress(RuntimeError):
            self.editor.setExtraSelections([])

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        """Show diagnostic tooltip when hovering over a rendered diagnostic."""
        if self._disposed:
            return False

        if obj is self._viewport and event.type() == QEvent.Type.ToolTip:
            return self._handle_tooltip_event(event)

        return super().eventFilter(obj, event)

    def _run_lint(self) -> None:
        """Run SQL syntax linting and render diagnostics."""
        if self._disposed:
            return

        try:
            sql = self.editor.toPlainText()
        except RuntimeError:
            self._disposed = True
            self._rendered_diagnostics = []
            return

        if not sql or not sql.strip():
            self.clear_diagnostics()
            return

        diagnostics = lint_syntax(sql, self._dialect)

        self._logger.debug(
            "SqlLintController: lint complete (dialect=%s, diagnostics=%s, preview=%s)",
            self._dialect,
            len(diagnostics),
            diagnostics[:3],
        )

        self._render_diagnostics(diagnostics)
        self._publish_status(diagnostics)

    def _render_diagnostics(self, diagnostics: list[SqlDiagnostic]) -> None:
        """Render diagnostics as editor extra selections.

        Args:
            diagnostics: Diagnostics returned by sql_analysis.lint_syntax.
        """
        selections: list[QTextEdit.ExtraSelection] = []
        rendered: list[RenderedDiagnostic] = []

        for diagnostic in diagnostics:
            selection, rendered_diagnostic = self._selection_for_diagnostic(diagnostic)
            if selection is not None:
                selections.append(selection)

            if rendered_diagnostic is not None:
                rendered.append(rendered_diagnostic)

        self._rendered_diagnostics = rendered

        if self._disposed:
            return

        with contextlib.suppress(RuntimeError):
            self.editor.setExtraSelections(selections)

    def _selection_for_diagnostic(
            self,
            diagnostic: SqlDiagnostic,
    ) -> tuple[QTextEdit.ExtraSelection | None, RenderedDiagnostic | None]:
        """Create an ExtraSelection for a diagnostic.

        Args:
            diagnostic: SQL diagnostic.

        Returns:
            Tuple of selection and rendered diagnostic. Values may be None when
            the diagnostic location cannot be mapped.
        """
        line = diagnostic.line if diagnostic.line is not None else 1
        column = diagnostic.column if diagnostic.column is not None else 1
        length = max(1, int(getattr(diagnostic, "length", 1) or 1))

        document = self.editor.document()
        if document is None:
            return None, None

        block = document.findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            return None, None

        block_text_length = max(0, block.length() - 1)
        position_in_block = max(0, min(column - 1, block_text_length))

        start = block.position() + position_in_block
        available = max(0, block_text_length - position_in_block)
        selection_length = max(1, min(length, available if available > 0 else 1))
        end = start + selection_length

        cursor = QTextCursor(block)
        cursor.setPosition(start)

        if available > 0:
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format = self._format_for_diagnostic(diagnostic)

        return selection, RenderedDiagnostic(
            diagnostic=diagnostic,
            start=start,
            end=end,
        )

    def _handle_tooltip_event(self, event: QEvent) -> bool:
        """Handle tooltip events over diagnostics."""
        if self._disposed:
            return False

        pos = getattr(event, "pos", lambda: None)()
        global_pos = getattr(event, "globalPos", lambda: None)()

        if pos is None or global_pos is None:
            return False

        try:
            cursor = self.editor.cursorForPosition(pos)
        except RuntimeError:
            self._disposed = True
            self._rendered_diagnostics = []
            return False

        offset = cursor.position()

        diagnostic = self._diagnostic_at_offset(offset)
        if diagnostic is None:
            QToolTip.hideText()
            return False

        with contextlib.suppress(RuntimeError):
            QToolTip.showText(global_pos, diagnostic.message, self.editor)

        return True

    def _diagnostic_at_offset(self, offset: int) -> SqlDiagnostic | None:
        """Return diagnostic at editor offset, if any."""
        for rendered in self._rendered_diagnostics:
            if rendered.start <= offset <= rendered.end:
                return rendered.diagnostic

        return None

    def _publish_status(self, diagnostics: list[SqlDiagnostic]) -> None:
        """Publish first diagnostic to status bar, if callback is configured."""
        if self._set_status is None:
            return

        first_error = next((d for d in diagnostics if d.severity == "error"), None)
        first_warning = next((d for d in diagnostics if d.severity == "warning"), None)
        diagnostic = first_error or first_warning

        if diagnostic is None:
            return

        prefix = "SQL error"
        if diagnostic.severity == "warning":
            prefix = "SQL warning"
        elif diagnostic.severity == "info":
            prefix = "SQL info"

        location = ""
        if diagnostic.line is not None and diagnostic.column is not None:
            location = f" at line {diagnostic.line}, column {diagnostic.column}"

        self._set_status(
            f"{prefix}{location}: {diagnostic.message}",
            10000,
        )

    @staticmethod
    def _format_for_diagnostic(diagnostic: SqlDiagnostic) -> QTextCharFormat:
        """Create a QTextCharFormat for a diagnostic.

        Args:
            diagnostic: SQL diagnostic.

        Returns:
            Text format used for highlighting.
        """
        fmt = QTextCharFormat()

        color = QColor("#d32f2f")
        if diagnostic.severity == "warning":
            color = QColor("#f57c00")
        elif diagnostic.severity == "info":
            color = QColor("#1976d2")

        fmt.setUnderlineColor(color)
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        fmt.setToolTip(diagnostic.message)

        return fmt
