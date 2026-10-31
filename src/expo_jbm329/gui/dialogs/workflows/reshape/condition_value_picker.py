"""Searchable paged dropdown with retained condition-value selections."""

from __future__ import annotations

import html
from decimal import Decimal

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from expo_jbm329.services.data_operations.reshape_condition_values import ValuePage, ValuePageRequest
from expo_jbm329.services.data_operations.reshape_conditions import ConditionLiteralType, ConditionValue


class ConditionValuePicker(QWidget):
    """Request pages through signals, without accessing source data."""

    page_requested = pyqtSignal(object)  # ValuePageRequest
    invalidated = pyqtSignal()
    changed = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        """Build the dropdown, page navigation, and selected-value review."""
        super().__init__(parent)
        self.column_position: int | None = None
        self.generation = 0
        self.page = 0
        self.multiple = False
        self._literal_type = ConditionLiteralType.QUOTED
        self.loading = False
        self.error = False
        self._has_next = False
        self._selected: dict[ConditionValue, None] = {}
        self._updating = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.button = QPushButton(self)
        self.button.setAutoDefault(False)
        root.addWidget(self.button)
        menu = QMenu(self.button)
        self.button.setMenu(menu)
        action = QWidgetAction(menu)
        panel = QWidget(menu)
        panel.setMinimumWidth(360)
        layout = QVBoxLayout(panel)
        self.search = QLineEdit(panel)
        self.search.setPlaceholderText(self.tr("Search values"))
        self.search.setAccessibleName(self.tr("Search values"))
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.status = QLabel(panel)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.values_list = QListWidget(panel)
        self.values_list.setMaximumHeight(180)
        layout.addWidget(self.values_list)
        navigation = QHBoxLayout()
        self.previous_button = QPushButton(self.tr("Previous"), panel)
        self.next_button = QPushButton(self.tr("Next"), panel)
        self.page_label = QLabel(panel)
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.page_label)
        navigation.addWidget(self.next_button)
        layout.addLayout(navigation)
        layout.addWidget(QLabel(self.tr("Selected values"), panel))
        self.selected_list = QListWidget(panel)
        self.selected_list.setMaximumHeight(100)
        self.selected_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.selected_list)
        self.remove_button = QPushButton(self.tr("Remove selected values"), panel)
        for button in (self.previous_button, self.next_button, self.remove_button):
            button.setAutoDefault(False)
        layout.addWidget(self.remove_button)
        action.setDefaultWidget(panel)
        menu.addAction(action)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dispatch)
        self.search.textChanged.connect(self._search_changed)
        self.previous_button.clicked.connect(self._previous)
        self.next_button.clicked.connect(self._next)
        self.values_list.itemChanged.connect(self._value_toggled)
        self.remove_button.clicked.connect(self._remove_selected)
        self._refresh_selection()
        self._navigation()

    def selected_values(self) -> tuple[ConditionValue, ...]:
        """Return explicit selections in their selection order."""
        return tuple(self._selected)

    def configure(
        self,
        column_position: int | None,
        *,
        multiple: bool,
        enabled: bool,
        values: tuple[ConditionValue, ...] | None = None,
        literal_type: ConditionLiteralType = ConditionLiteralType.QUOTED,
    ) -> None:
        """Invalidate old pages and adapt selection to the new column/operator."""
        changed_column = column_position != self.column_position
        self.invalidate()
        self.column_position = column_position
        self.multiple = multiple
        self._literal_type = literal_type
        if changed_column or not enabled or (not multiple and len(self._selected) > 1):
            self._selected.clear()
        if values is not None:
            self._selected = dict.fromkeys(values)
        if changed_column:
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        self.page = 0
        self.setEnabled(enabled and column_position is not None)
        self._refresh_selection()
        if self.isEnabled():
            self._schedule(0)
        else:
            self.changed.emit()

    def invalidate(self) -> None:
        """Supersede requests immediately, before a search debounce expires."""
        self.generation += 1
        self._timer.stop()
        self.loading = False
        self.error = False
        self.invalidated.emit()

    def receive_page(self, result: ValuePage) -> None:
        """Render a page returned for the current request generation."""
        self.loading = False
        self.error = False
        self._has_next = result.has_next
        self._updating = True
        self.values_list.clear()
        for value in result.entries:
            item = QListWidgetItem(self._label(value))
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setToolTip(self._tooltip(value))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if self._matching_selections(value) else Qt.CheckState.Unchecked)
            self.values_list.addItem(item)
        self._updating = False
        self.status.setText("" if result.entries else self.tr("No matching values."))
        self._navigation()
        self.changed.emit()

    def show_error(self, text: str) -> None:
        """Show an explicit failed-request state instead of an empty result."""
        self.loading = False
        self.error = True
        self.status.setText(text)
        self._navigation()
        self.changed.emit()

    def _label(self, value: ConditionValue) -> str:
        return value.text or self.tr("(empty string)")

    def _tooltip(self, value: ConditionValue) -> str:
        return "<qt>" + html.escape(self._label(value)).replace("\n", "<br>") + "</qt>"

    def _search_changed(self) -> None:
        self.page = 0
        self._schedule(250)

    def _schedule(self, delay: int) -> None:
        self.invalidate()
        self.loading = True
        self._has_next = False
        self.values_list.clear()
        self.status.setText(self.tr("Loading values..."))
        self._navigation()
        self.changed.emit()
        self._timer.start(delay)

    def _dispatch(self) -> None:
        if self.column_position is not None and self.isEnabled():
            self.page_requested.emit(ValuePageRequest(self.column_position, self.search.text(), self.page))

    def _previous(self) -> None:
        if self.page > 0:
            self.page -= 1
            self._schedule(0)

    def _next(self) -> None:
        if self._has_next:
            self.page += 1
            self._schedule(0)

    def _navigation(self) -> None:
        self.previous_button.setEnabled(not self.loading and self.page > 0)
        self.next_button.setEnabled(not self.loading and not self.error and self._has_next)
        self.page_label.setText(self.tr("Page {page}").format(page=self.page + 1))

    def _value_toggled(self, item: QListWidgetItem) -> None:
        if self._updating:
            return
        value = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(value, ConditionValue):
            message = "Condition value item is missing its typed value."
            raise TypeError(message)
        matches = self._matching_selections(value)
        if item.checkState() == Qt.CheckState.Checked:
            if not self.multiple:
                self._selected.clear()
            if not matches or not self.multiple:
                self._selected[value] = None
        else:
            for selected in matches:
                self._selected.pop(selected)
        self._refresh_selection()
        self.changed.emit()

    def _matching_selections(self, value: ConditionValue) -> tuple[ConditionValue, ...]:
        # Imported literals lack picker scalar identities and may use another numeric spelling.
        if self._literal_type == ConditionLiteralType.NUMBER:
            number = Decimal(value.text)
            return tuple(selected for selected in self._selected if Decimal(selected.text) == number)
        return tuple(selected for selected in self._selected if selected.text == value.text)

    def _refresh_selection(self) -> None:
        self._updating = True
        self.selected_list.clear()
        for value in self._selected:
            item = QListWidgetItem(self._label(value))
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setToolTip(self._tooltip(value))
            self.selected_list.addItem(item)
        for index in range(self.values_list.count()):
            page_item = self.values_list.item(index)
            if page_item is not None:
                value = page_item.data(Qt.ItemDataRole.UserRole)
                if not isinstance(value, ConditionValue):
                    message = "Condition value item is missing its typed value."
                    raise TypeError(message)
                page_item.setCheckState(
                    Qt.CheckState.Checked if self._matching_selections(value) else Qt.CheckState.Unchecked
                )
        self._updating = False
        summary = self.tr("Select values ({count} selected)").format(count=len(self._selected))
        self.button.setText(summary)
        self.button.setToolTip(summary)

    def _remove_selected(self) -> None:
        for item in self.selected_list.selectedItems():
            self._selected.pop(item.data(Qt.ItemDataRole.UserRole), None)
        self._refresh_selection()
        self.changed.emit()
