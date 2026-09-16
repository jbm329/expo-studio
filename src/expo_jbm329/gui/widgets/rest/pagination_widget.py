"""Pagination configuration widget for REST connections."""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QFormLayout, QLineEdit, QWidget


class RestPaginationWidget(QWidget):
    """Compact editor for REST pagination settings."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.pagination_combo = QComboBox()
        self.pagination_combo.addItem("None", userData="none")
        self.pagination_combo.addItem("Page number", userData="page_number")

        self.page_param_edit = QLineEdit()
        self.page_param_edit.setPlaceholderText("page")
        self.start_page_edit = QLineEdit()
        self.start_page_edit.setPlaceholderText("1")
        self.page_size_param_edit = QLineEdit()
        self.page_size_param_edit.setPlaceholderText("pageSize")
        self.page_size_edit = QLineEdit()
        self.page_size_edit.setPlaceholderText("100")
        self.max_pages_edit = QLineEdit()
        self.max_pages_edit.setPlaceholderText("10")

        self.form_layout = QFormLayout(self)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.addRow("Type:", self.pagination_combo)
        self.form_layout.addRow("Page parameter", self.page_param_edit)
        self.form_layout.addRow("Start page", self.start_page_edit)
        self.form_layout.addRow("Page size parameter", self.page_size_param_edit)
        self.form_layout.addRow("Page size", self.page_size_edit)
        self.form_layout.addRow("Max pages", self.max_pages_edit)

        self.apply_visibility()

    def apply_visibility(self) -> None:
        """Show only fields relevant for the current pagination mode."""
        is_page_number = self.pagination_combo.currentData() == "page_number"
        self._set_state(self.page_param_edit, is_page_number)
        self._set_state(self.start_page_edit, is_page_number)
        self._set_state(self.page_size_param_edit, is_page_number)
        self._set_state(self.page_size_edit, is_page_number)
        self._set_state(self.max_pages_edit, is_page_number)

    def _set_state(self, widget: QWidget, visible: bool) -> None:
        widget.setEnabled(visible)
        self._set_field_visible(widget, visible)

    def _set_field_visible(self, widget: QWidget, visible: bool) -> None:
        widget.setVisible(visible)
        label = self.form_layout.labelForField(widget)
        if label is not None:
            label.setVisible(visible)
