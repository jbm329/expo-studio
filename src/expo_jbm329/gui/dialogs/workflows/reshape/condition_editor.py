"""Editable condition text and stable per-metric builder state."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QEvent, QPoint, QSignalBlocker, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFocusEvent, QHelpEvent, QKeyEvent, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.services.data_operations.reshape_condition_completion import column_completion
from expo_jbm329.services.data_operations.reshape_condition_lint import (
    ConditionDiagnostic,
    ConditionLintCode,
    lint_condition,
)
from expo_jbm329.services.data_operations.reshape_conditions import ConditionColumn, ConditionGroup, format_condition

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PyQt6.QtCore import QObject
    from PyQt6.QtGui import QHideEvent


class ConditionEditor(QWidget):
    """Own manual text and the last applied builder group for one metric."""

    builder_requested = pyqtSignal()
    validity_changed = pyqtSignal()

    def __init__(self, parent: QWidget, columns: Sequence[ConditionColumn] = ()) -> None:
        """Build the text field and its right-aligned builder button."""
        super().__init__(parent)
        self._applied: ConditionGroup | None = None
        self._expression: str | None = None
        self._columns = tuple(columns)
        self.diagnostics: tuple[ConditionDiagnostic, ...] = ()
        self.lint_pending = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.text = QLineEdit(self)
        self.text.setAccessibleName(self.tr("Condition"))
        self._empty_tooltip = self.tr(
            "Edit condition syntax or use the builder. Syntax and column names are checked; values are not evaluated."
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
        viewport = self.expanded_text.viewport()
        if viewport is not None:
            viewport.installEventFilter(self)
        self._lint_timer = QTimer(self)
        self._lint_timer.setSingleShot(True)
        self._lint_timer.setInterval(200)
        self._lint_timer.timeout.connect(self.validate_now)
        self.text.textChanged.connect(self._sync_expanded_text)
        self.text.textChanged.connect(self._update_collapsed_display)
        self.text.textChanged.connect(self._schedule_lint)
        self.expanded_text.textChanged.connect(self._sync_inline_text)
        names: list[str] = sorted({column.name for column in self._columns if column.available}, key=str.casefold)
        self.completer = QCompleter(names, self)
        self.completer.setWidget(self.expanded_text)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.activated[str].connect(self._insert_completion)
        self.expanded_text.textChanged.connect(self._update_completion)
        self.expanded_text.cursorPositionChanged.connect(self._update_completion)

    def _completion_context(self) -> tuple[str, int]:
        value = self.expanded_text.toPlainText()
        qt_position = self.expanded_text.textCursor().position()
        position = len(value.encode("utf-16-le")[: qt_position * 2].decode("utf-16-le"))
        return value, position

    def _update_completion(self) -> None:
        popup = self.completer.popup()
        if popup is None:
            return
        value, position = self._completion_context()
        context = column_completion(value, position)
        if not self.popup.isVisible() or context is None or self.expanded_text.textCursor().hasSelection():
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
        rectangle = self.expanded_text.cursorRect()
        scrollbar = popup.verticalScrollBar()
        scrollbar_width = scrollbar.sizeHint().width() if scrollbar is not None else 0
        width = max(240, popup.sizeHintForColumn(0) + scrollbar_width + 2 * popup.frameWidth())
        screen = self.expanded_text.screen()
        if screen is not None:
            width = min(width, screen.availableGeometry().width())
        rectangle.setWidth(width)
        self.completer.complete(rectangle)

    def _insert_completion(self, name: str) -> None:
        value, position = self._completion_context()
        context = column_completion(value, position)
        if context is None:
            return
        cursor = self.expanded_text.textCursor()
        cursor.setPosition(self._qt_position(value, context.start))
        cursor.setPosition(self._qt_position(value, context.end), QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText("[" + name.replace("]", "]]") + "]")
        self.expanded_text.setTextCursor(cursor)
        popup = self.completer.popup()
        if popup is not None:
            popup.hide()

    @property
    def condition_valid(self) -> bool:
        """Return whether diagnostics describe the latest text and contain no errors."""
        return not self.lint_pending and not self.diagnostics

    def _schedule_lint(self) -> None:
        self.lint_pending = True
        self.diagnostics = ()
        self._render_diagnostics()
        self.validity_changed.emit()
        if self.text.text().strip():
            self._lint_timer.start()
        else:
            self.validate_now()

    def validate_now(self) -> bool:
        """Validate current text synchronously, including edits awaiting debounce."""
        self._lint_timer.stop()
        self.diagnostics = lint_condition(self.text.text(), self._columns)
        self.lint_pending = False
        self._render_diagnostics()
        self.validity_changed.emit()
        return self.condition_valid

    def _diagnostic_message(self, diagnostic: ConditionDiagnostic) -> str:
        messages = {
            ConditionLintCode.COLUMN: self.tr("Expected a column name enclosed in [brackets]."),
            ConditionLintCode.UNKNOWN_COLUMN: self.tr("Column '{name}' does not exist."),
            ConditionLintCode.AMBIGUOUS_COLUMN: self.tr(
                "Column '{name}' is ambiguous. Rename duplicate columns first."
            ),
            ConditionLintCode.BRACKET: self.tr("Missing closing ] in column name. Escape a literal ] as ]]."),
            ConditionLintCode.QUOTE: self.tr(
                "Unterminated quoted value. Check for a missing or misplaced single quote earlier in the condition. "
                "Escape an apostrophe as ''."
            ),
            ConditionLintCode.OPERATOR: self.tr("Expected =, !=, >, >=, <, <=, IN, NOT IN, IS NULL or IS NOT NULL."),
            ConditionLintCode.VALUE: self.tr("Expected a single-quoted value, for example 'value'."),
            ConditionLintCode.NUMBER_VALUE: self.tr(
                "Expected a number or a single-quoted value, for example 18 or '18'."
            ),
            ConditionLintCode.BOOLEAN_VALUE: self.tr("Expected True, False or a single-quoted value."),
            ConditionLintCode.LIST: self.tr("IN and NOT IN require a nonempty, comma-separated list in parentheses."),
            ConditionLintCode.CLOSE: self.tr("Expected a closing parenthesis )."),
            ConditionLintCode.GROUP_CONNECTOR: self.tr("Expected AND, OR or a closing parenthesis )."),
            ConditionLintCode.UNMATCHED_CLOSE: self.tr(
                "Unmatched closing parenthesis ). Add a matching opening ( or remove this )."
            ),
            ConditionLintCode.EXPRESSION: self.tr("Expected a condition or a parenthesized group."),
            ConditionLintCode.CONNECTOR: self.tr(
                "Expected AND or OR between conditions, or the end of the expression."
            ),
        }
        return messages[diagnostic.code].format(name=diagnostic.name)

    def _error_tooltip(self) -> str:
        return "<qt>" + "<br>".join(html.escape(self._diagnostic_message(item)) for item in self.diagnostics) + "</qt>"

    @staticmethod
    def _qt_position(text: str, position: int) -> int:
        return len(text[:position].encode("utf-16-le")) // 2

    def _render_diagnostics(self) -> None:
        error_style = "border: 1px solid #d32f2f;" if self.diagnostics else ""
        self.text.setStyleSheet(error_style)
        self.expanded_text.setStyleSheet(error_style)
        selections: list[QTextEdit.ExtraSelection] = []
        text = self.expanded_text.toPlainText()
        for diagnostic in self.diagnostics:
            start, end = diagnostic.start, diagnostic.end
            if start == end:
                start = max(0, start - 1)
            cursor = self.expanded_text.textCursor()
            cursor.setPosition(self._qt_position(text, start))
            cursor.setPosition(self._qt_position(text, end), QTextCursor.MoveMode.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            selection.format.setUnderlineColor(QColor("#d32f2f"))
            selections.append(selection)
        self.expanded_text.setExtraSelections(selections)
        self._update_tooltips()

    def _update_tooltips(self) -> None:
        value = self.text.text()
        escaped = html.escape(value).replace("\n", "<br>")
        tooltip = self._error_tooltip() if self.diagnostics else f"<qt>{escaped}</qt>" if value else self._empty_tooltip
        self.text.setToolTip(tooltip)
        self.expanded_text.setToolTip(tooltip)

    @override
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        """Open on deliberate field focus and close on Escape without reverting."""
        app = QApplication.instance()
        completion_popup = self.completer.popup()
        if (
            a0 is self.expanded_text.viewport()
            and isinstance(a1, QHelpEvent)
            and a1.type() == QEvent.Type.ToolTip
            and self.diagnostics
        ):
            QToolTip.showText(a1.globalPos(), self._error_tooltip(), self.expanded_text)
            return True
        if a0 is self.popup and a1 is not None and app is not None:
            if a1.type() == QEvent.Type.Show:
                app.installEventFilter(self)
            elif a1.type() == QEvent.Type.Hide:
                if completion_popup is not None:
                    completion_popup.hide()
                app.removeEventFilter(self)
                self.text.setCursorPosition(0)
        if (
            a1 is not None
            and a1.type() == QEvent.Type.MouseButtonPress
            and self.popup.isVisible()
            and isinstance(a0, QWidget)
            and a0 is not self.popup
            and not self.popup.isAncestorOf(a0)
            and a0 is not completion_popup
            and not (completion_popup is not None and completion_popup.isAncestorOf(a0))
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
            (a0 is self.expanded_text or a0 is completion_popup)
            and isinstance(a1, QKeyEvent)
            and a1.type() == QEvent.Type.KeyPress
        ):
            if completion_popup is not None and completion_popup.isVisible():
                if a1.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab}:
                    self._insert_completion(completion_popup.currentIndex().data())
                    return True
                if a1.key() == Qt.Key.Key_Escape:
                    completion_popup.hide()
                    return True
            elif a0 is self.expanded_text and a1.key() == Qt.Key.Key_Escape:
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
        self._update_tooltips()
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
        self.validate_now()
