"""Multiline Derived formula editing with shared column completion and lint display."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QHelpEvent, QKeyEvent
from PyQt6.QtWidgets import QPlainTextEdit, QToolTip, QWidget

from expo_jbm329.gui.widgets.expression_editor_support import ColumnCompletionSupport, underline_diagnostics
from expo_jbm329.services.data_operations.derived_column.derived_column_lint import formula_error_span

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PyQt6.QtCore import QObject
    from PyQt6.QtGui import QHideEvent

    from expo_jbm329.services.data_operations.derived_column.derived_column_parser import DerivedColumnFormulaError


class FormulaEditor(QPlainTextEdit):
    """Present grammar-independent completion and positioned formula errors."""

    def __init__(self, names: Sequence[str], parent: QWidget | None = None) -> None:
        """Create an always-visible editor with completion for available columns."""
        super().__init__(parent)
        self._error_tooltip = ""
        self._completion = ColumnCompletionSupport(self, names, enabled=self.isVisible)
        self.completer = self._completion.completer
        self.installEventFilter(self)
        popup = self.completer.popup()
        if popup is not None:
            popup.installEventFilter(self)
        viewport = self.viewport()
        if viewport is not None:
            viewport.installEventFilter(self)

    def set_diagnostic(self, error: DerivedColumnFormulaError | None, message: str = "") -> None:
        """Show a localized formula failure without changing text or selection."""
        span = formula_error_span(self.toPlainText(), error) if error is not None else None
        underline_diagnostics(self, (span,) if span is not None else ())
        self.setStyleSheet("border: 1px solid #d32f2f;" if span is not None else "")
        self._error_tooltip = f"<qt>{html.escape(message)}</qt>" if span is not None else ""
        self.setToolTip(self._error_tooltip)

    @override
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        """Accept suggestions before dialog shortcuts and show escaped lint hints."""
        if (
            (a0 is self or a0 is self.completer.popup())
            and isinstance(a1, QKeyEvent)
            and a1.type() == QEvent.Type.KeyPress
            and self._completion.handle_key(a1.key())
        ):
            return True
        if (
            a0 is self.viewport()
            and isinstance(a1, QHelpEvent)
            and a1.type() == QEvent.Type.ToolTip
            and self._error_tooltip
        ):
            QToolTip.showText(a1.globalPos(), self._error_tooltip, self)
            return True
        return super().eventFilter(a0, a1)

    @override
    def hideEvent(self, a0: QHideEvent | None) -> None:
        """Dismiss suggestions when the dialog is hidden or closed."""
        popup = self.completer.popup()
        if popup is not None:
            popup.hide()
        super().hideEvent(a0)
