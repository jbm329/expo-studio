"""On-demand, validated editors for unmatched-row join defaults."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QDateTime, QEvent, QLocale, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QStyledItemDelegate,
    QVBoxLayout,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.services.data_operations.joins import JoinFillColumn, UnmatchedFill, parse_join_fill

if TYPE_CHECKING:
    from PyQt6.QtCore import QAbstractItemModel, QModelIndex
    from PyQt6.QtWidgets import QStyleOptionViewItem, QWidget

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService

FILL_COLUMN_ROLE = int(Qt.ItemDataRole.UserRole) + 1
FILL_VALUE_ROLE = int(Qt.ItemDataRole.UserRole) + 2


def display_join_fill(fill: UnmatchedFill, locale: QLocale, *, null: str, true: str, false: str) -> str:
    """Format a typed default without changing its precision or meaning."""
    value = fill.value
    if value is None:
        return null
    if isinstance(value, bool):
        return true if value else false
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, float):
        return repr(value).replace(".", locale.decimalPoint())
    return str(value)


class JoinFillValueDialog(QDialog):
    """Choose a preset or validate a custom scalar before changing a default."""

    def __init__(
        self,
        parent: QWidget | None,
        column: JoinFillColumn,
        initial: UnmatchedFill,
        dialogs: DialogService,
        *,
        numeric_locale: QLocale | None = None,
    ) -> None:
        """Create a column-specific editor without retaining source data."""
        super().__init__(parent)
        self._column = column
        self._dialogs = dialogs
        self._locale = QLocale(numeric_locale) if numeric_locale is not None else QLocale()
        self.fill = initial
        self.setWindowTitle(self.tr("If no match"))
        root = QVBoxLayout(self)
        heading = QLabel(self.tr("Column: {column} ({dtype})").format(column=column.name, dtype=column.dtype))
        heading.setWordWrap(True)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(heading)
        form = QFormLayout()
        self.choice = QComboBox(self)
        self.choice.addItem(self.tr("NULL"), UnmatchedFill())
        if column.kind in {"integer", "float"}:
            zero = 0 if column.kind == "integer" else 0.0
            self.choice.addItem(str(zero).replace(".", self._locale.decimalPoint()), UnmatchedFill(zero))
        elif column.kind == "boolean":
            self.choice.addItem(self.tr("True"), UnmatchedFill(True))
            self.choice.addItem(self.tr("False"), UnmatchedFill(False))
        if column.kind in {"integer", "float", "text", "datetime"}:
            self.choice.addItem(self.tr("Custom value..."), "custom")
        form.addRow(self.tr("Default:"), self.choice)
        self.custom_value = QLineEdit(self)
        self.custom_value.setText(str(initial.value) if initial.value is not None else "")
        if isinstance(initial.value, float):
            self.custom_value.setText(repr(initial.value).replace(".", self._locale.decimalPoint()))
        if column.kind == "datetime":
            self.custom_value.setPlaceholderText("YYYY-MM-DD HH:MM:SS")
        form.addRow(self.tr("Value:"), self.custom_value)
        self.calendar: QDateTimeEdit | None = None
        self._calendar_format = "yyyy-MM-dd HH:mm:ss" if "[s" in column.dtype else "yyyy-MM-dd HH:mm:ss.zzz"
        if column.kind == "datetime":
            self.calendar = QDateTimeEdit(self)
            self.calendar.setCalendarPopup(True)
            self.calendar.setDisplayFormat(self._calendar_format)
            self.calendar.setDateTime(QDateTime.currentDateTime())
            if initial.value is not None:
                date = QDateTime.fromString(str(initial.value).replace(" ", "T", 1), Qt.DateFormat.ISODateWithMs)
                if date.isValid():
                    self.calendar.setDateTime(date)
            self.calendar.dateTimeChanged.connect(self._on_calendar_changed)
            form.addRow(self.tr("Date/time picker:"), self.calendar)
        root.addLayout(form)
        hint = QLabel(self)
        if column.kind in {"integer", "float"}:
            hint.setText(
                self.tr("Enter a number without grouping separators. Decimal separator: {separator}.").format(
                    separator=self._locale.decimalPoint()
                )
            )
        elif column.kind == "datetime":
            hint.setText(self.tr("Use the column's local time, or enter an ISO date/time with an explicit offset."))
        elif column.kind == "text" and column.dtype == "object":
            hint.setText(self.tr("Text defaults require text-only source values. This is checked when the join runs."))
        hint.setWordWrap(True)
        root.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        localize_dialog_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        index = next(
            (i for i in range(self.choice.count()) if self.choice.itemData(i) == initial),
            self.choice.count() - 1,
        )
        self.choice.setCurrentIndex(index)
        self.choice.currentIndexChanged.connect(self._update_custom_enabled)
        self._update_custom_enabled()
        self.setMinimumWidth(440)

    def _on_calendar_changed(self, value: QDateTime) -> None:
        self.custom_value.setText(value.toString(self._calendar_format))

    def _update_custom_enabled(self) -> None:
        custom = self.choice.currentData() == "custom"
        self.custom_value.setEnabled(custom)
        if self.calendar is not None:
            self.calendar.setEnabled(custom)
        if custom:
            if self.calendar is not None and not self.custom_value.text():
                self.custom_value.setText(self.calendar.dateTime().toString(self._calendar_format))
            self.custom_value.setFocus()

    @override
    def accept(self) -> None:
        """Keep invalid custom values in the editor and notify the user."""
        choice = self.choice.currentData()
        if isinstance(choice, UnmatchedFill):
            self.fill = choice
        else:
            try:
                self.fill = parse_join_fill(
                    self._column, self.custom_value.text(), decimal_point=self._locale.decimalPoint()
                )
            except ValueError:
                self._dialogs.warn(
                    self,
                    self.tr("Invalid default value"),
                    self.tr(
                        "The value is not valid for {column} ({dtype}). Check its type, range, precision and timezone."
                    ).format(column=self._column.name, dtype=self._column.dtype),
                )
                self.custom_value.setFocus()
                return
        super().accept()


class JoinFillDelegate(QStyledItemDelegate):
    """Open a validated value picker on click or keyboard activation."""

    def __init__(self, parent: QWidget, dialogs: DialogService) -> None:
        """Capture the notification service and parent table."""
        super().__init__(parent)
        self._parent_widget = parent
        self._dialogs = dialogs
        self._numeric_locale = QLocale()

    @override
    def editorEvent(
        self,
        event: QEvent | None,
        model: QAbstractItemModel | None,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:
        """Update the model only after a valid default is explicitly accepted."""
        del option
        if model is None or event is None or not index.flags() & Qt.ItemFlag.ItemIsEditable:
            return False
        mouse = (
            isinstance(event, QMouseEvent)
            and event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        )
        keyboard = (
            isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.key()
            in {
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
                Qt.Key.Key_Space,
                Qt.Key.Key_F2,
            }
        )
        if not mouse and not keyboard:
            return False
        column = index.data(FILL_COLUMN_ROLE)
        initial = index.data(FILL_VALUE_ROLE)
        if not isinstance(column, JoinFillColumn) or not isinstance(initial, UnmatchedFill):
            message = "Join default editor metadata is missing."
            raise TypeError(message)
        dialog = JoinFillValueDialog(
            self._parent_widget, column, initial, self._dialogs, numeric_locale=self._numeric_locale
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and not model.setData(index, dialog.fill, FILL_VALUE_ROLE):
            message = "Join default could not be stored in the column model."
            raise RuntimeError(message)
        dialog.deleteLater()
        return True
