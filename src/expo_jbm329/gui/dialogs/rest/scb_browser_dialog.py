"""Dialog for browsing SCB tables and selecting variable values."""

from __future__ import annotations

from math import prod
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.gui_utils import apply_window_hints_strict
from expo_jbm329.services.rest.scb.browser import (
    ScbBrowserError,
    ScbTableMetadata,
    fetch_scb_table_metadata,
    fetch_scb_tables,
)
from expo_jbm329.services.rest.scb.service import ScbQueryBuilder, ScbSelection
from expo_jbm329.utils.format_utils import fmt_int

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService


class ScbBrowserDialog(QDialog):
    """Browse SCB tables, select variables and values, and apply a query."""

    def __init__(
        self,
        parent: QWidget | None = None,
        dialogs: DialogService | None = None,
    ) -> None:
        """Initialize the dialog."""
        super().__init__(parent)
        self._dialogs = dialogs or QtDialogService()

        self.setWindowTitle(self.tr("SCB query builder"))
        self.setFixedSize(700, 525)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.result_data: dict[str, object] | None = None

        self.table_label = QLabel(self.tr("Table:"))
        self.table_label.setFixedWidth(90)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("Search table..."))
        self.search_edit.textChanged.connect(self._filter_table_list)
        self.search_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.table_combo = QComboBox()
        self.table_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.table_combo.currentIndexChanged.connect(self._on_table_selected)

        self.language_label = QLabel(self.tr("Language:"))
        self.language_label.setFixedWidth(90)
        self.language_combo = QComboBox()
        self.language_combo.setFixedWidth(125)
        self.language_combo.addItem(self.tr("Swedish"), userData="sv")
        self.language_combo.addItem(self.tr("English"), userData="en")
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)

        self.current_table_label = QLabel(self.tr("No table selected"))
        self.current_table_label.setWordWrap(True)
        self.current_table_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.current_table_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.current_table_label.setFrameShadow(QFrame.Shadow.Sunken)
        self.current_table_label.setMargin(5)
        self.current_table_label.setContentsMargins(0, 15, 0, 15)

        self.variable_list = QListWidget()
        self.variable_list.currentRowChanged.connect(self._on_variable_changed)

        self.value_list = QListWidget()
        self.value_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.value_list.itemChanged.connect(self._on_value_checked)

        self.selection_counter = QLabel(
            self.tr("Selected cells: 0 / {0}").format(fmt_int(ScbQueryBuilder.MAX_SELECTED_CELLS))
        )
        self.selection_counter.setWordWrap(False)
        self.selection_warning = QLabel("")
        self.selection_warning.setWordWrap(False)

        self.select_all_button = QPushButton(self.tr("Select all"))
        self.select_all_button.clicked.connect(self._select_all_values)
        self.clear_selection_button = QPushButton(self.tr("Clear"))
        self.clear_selection_button.clicked.connect(self._clear_selected_values)

        self.apply_button = QPushButton(self.tr("Apply to REST connection"))
        self.apply_button.clicked.connect(self._apply)
        self.cancel_button = QPushButton(self.tr("Cancel"))
        self.cancel_button.clicked.connect(self.reject)

        status_column = QVBoxLayout()
        status_column.setSpacing(2)
        status_column.setContentsMargins(0, 0, 0, 0)
        status_column.addWidget(self.selection_counter)
        status_column.addWidget(self.selection_warning)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addLayout(status_column)
        button_row.addStretch(1)
        button_row.addWidget(self.apply_button)
        button_row.addWidget(self.cancel_button)

        main = QVBoxLayout(self)

        form_grid = QGridLayout()
        form_grid.setContentsMargins(0, 0, 0, 0)
        form_grid.setColumnStretch(1, 1)
        form_grid.setColumnMinimumWidth(0, 90)
        form_grid.addWidget(self.language_label, 0, 0)
        form_grid.addWidget(self.language_combo, 0, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        form_grid.addWidget(self.table_label, 1, 0)
        form_grid.addWidget(self.search_edit, 1, 1)
        form_grid.addWidget(QLabel(""), 2, 0)
        form_grid.addWidget(self.table_combo, 2, 1)
        main.addLayout(form_grid)

        main.addWidget(self.current_table_label)

        variable_labels = QHBoxLayout()
        variable_labels.addWidget(QLabel(self.tr("Variables")), 1)
        variable_value_label = QHBoxLayout()
        variable_value_label.addWidget(QLabel(self.tr("Variable values")), 1)

        body = QHBoxLayout()
        body.addWidget(self.variable_list, 1)
        value_side = QHBoxLayout()
        value_side.addWidget(self.value_list, 1)

        value_actions = QVBoxLayout()
        value_actions.setSpacing(8)
        value_actions.setContentsMargins(0, 0, 0, 0)
        value_actions.addStretch(1)
        value_actions.addWidget(self.select_all_button)
        value_actions.addWidget(self.clear_selection_button)
        value_actions.addStretch(1)

        value_side.addLayout(value_actions)
        body.addLayout(value_side, 2)
        variable_labels.addLayout(variable_value_label, 2)
        main.addLayout(variable_labels)
        main.addLayout(body)
        main.addLayout(button_row)

        apply_window_hints_strict(self, min_width=900, fixed_size=True)

        self._all_tables: list[tuple[str, str]] = []
        self._metadata_by_id: dict[str, ScbTableMetadata] = {}
        self._selected_codes: dict[str, list[str]] = {}
        self._current_variable: str | None = None

        self._refresh_selection_summary()
        self._load_tables()

    def _current_language(self) -> str:
        """Return the selected UI language for SCB requests."""
        return str(self.language_combo.currentData() or "sv")

    def _load_tables(self) -> None:
        """Load the SCB table index."""
        try:
            tables = fetch_scb_tables(lang=self._current_language())
        except ScbBrowserError as exc:
            self._dialogs.critical(self, title=self.tr("SCB browser error"), text=str(exc))

            self.result_data = None
            self.reject()
            return

        sorted_tables = sorted(tables, key=lambda table: table.table_id)
        self._all_tables = [(table.table_id, table.label) for table in sorted_tables]
        self._refresh_table_combo()

        if self.table_combo.count() > 0:
            self.table_combo.setCurrentIndex(0)
            self._on_table_selected(0)

    def _refresh_table_combo(self) -> None:
        """Refresh the searchable table list in the combo box."""
        search_text = self.search_edit.text().strip().lower()
        filtered = [
            (table_id, label)
            for table_id, label in self._all_tables
            if not search_text or search_text in table_id.lower() or search_text in label.lower()
        ]

        self.table_combo.blockSignals(True)
        self.table_combo.clear()
        for table_id, label in filtered:
            self.table_combo.addItem(f"{table_id} - {label}", userData=table_id)
            self.table_combo.setItemData(
                self.table_combo.count() - 1,
                f"{table_id} - {label}",
                Qt.ItemDataRole.ToolTipRole,
            )
        self.table_combo.blockSignals(False)

        if self.table_combo.count() == 0:
            self.current_table_label.setText(self.tr("No matching tables found"))
            self.variable_list.clear()
            self.value_list.clear()

    def _filter_table_list(self) -> None:
        """Filter the table list by typed text."""
        self._refresh_table_combo()
        if self.table_combo.count() > 0:
            self.table_combo.setCurrentIndex(0)
            self._on_table_selected(0)

    def _on_language_changed(self) -> None:
        """Reload browse data when the SCB language changes."""
        self._metadata_by_id.clear()
        self._selected_codes.clear()
        self._current_variable = None
        self.variable_list.clear()
        self.value_list.clear()
        self.current_table_label.setText(self.tr("No table selected"))
        self._refresh_selection_summary()
        self._load_tables()

    def _refresh_selection_summary(self) -> None:
        """Update selected cell count and warning state."""
        table_id = str(self.table_combo.currentData() or "")
        metadata = self._metadata_by_id.get(table_id)
        selected_counts = [
            len(codes)
            for variable in (metadata.variables if metadata is not None else ())
            for codes in [self._selected_codes.get(variable.name, [])]
            if codes
        ]
        selected_cells = prod(selected_counts) if selected_counts else 0
        max_cells = ScbQueryBuilder.MAX_SELECTED_CELLS

        self.selection_counter.setText(
            self.tr("Selected cells: {0} / {1}").format(fmt_int(selected_cells), fmt_int(max_cells))
        )

        if selected_cells > max_cells:
            self.selection_counter.setStyleSheet("color: #ff6b6b; font-weight: bold;")
            self.selection_warning.setText(self.tr("This selection exceeds the SCB limit."))
            self.selection_warning.setStyleSheet("color: #ff6b6b; font-weight: bold;")
            self.apply_button.setEnabled(False)
        elif selected_cells == 0:
            self.selection_counter.setStyleSheet("")
            self.selection_warning.setText("")
            self.apply_button.setEnabled(False)
        else:
            self.selection_counter.setStyleSheet("color: #4caf50; font-weight: bold;")
            self.selection_warning.setText("")
            self.selection_warning.setStyleSheet("color: #4caf50; font-weight: bold;")
            self.apply_button.setEnabled(True)

    def _on_table_selected(self, index: int) -> None:
        """Load metadata for a selected table."""
        if index < 0:
            return
        table_id = str(self.table_combo.itemData(index) or "")
        if not table_id:
            return

        metadata = self._metadata_by_id.get(table_id)
        if metadata is None:
            try:
                metadata = fetch_scb_table_metadata(
                    table_id=table_id,
                    lang=self._current_language(),
                )
            except ScbBrowserError as exc:
                self._dialogs.critical(self, title=self.tr("SCB metadata error"), text=str(exc))
                return
            self._metadata_by_id[table_id] = metadata

        self._selected_codes = {}
        self._current_variable = None
        self.current_table_label.setText(f"{metadata.table_id}: {metadata.label}")
        self.variable_list.clear()
        for variable in metadata.variables:
            item = QListWidgetItem(variable.display_name)
            item.setData(Qt.ItemDataRole.UserRole, variable.name)
            self.variable_list.addItem(item)
        if self.variable_list.count() > 0:
            self.variable_list.setCurrentRow(0)
        self._refresh_selection_summary()

    def _on_variable_changed(self, row: int) -> None:
        """Load selectable values for the selected variable."""
        if row < 0:
            self.value_list.clear()
            return
        item = self.variable_list.item(row)
        if item is None:
            return

        variable_name = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not variable_name:
            return

        table_id = str(self.table_combo.currentData() or "")
        metadata = self._metadata_by_id.get(table_id)
        if metadata is None:
            return

        variable = next((v for v in metadata.variables if v.name == variable_name), None)
        if variable is None:
            return

        self._current_variable = variable.name
        self.value_list.clear()
        for value in variable.values:
            label = value.label.strip() if value.label.strip() else value.code  # noqa: FURB110
            check_item = QListWidgetItem(label)
            check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check_item.setCheckState(
                Qt.CheckState.Checked
                if value.code in self._selected_codes.get(variable.name, [])
                else Qt.CheckState.Unchecked
            )
            check_item.setData(Qt.ItemDataRole.UserRole, value.code)
            self.value_list.addItem(check_item)
        self._refresh_selection_summary()

    def _on_value_checked(self, item: QListWidgetItem) -> None:
        """Store selected value codes for the currently selected variable."""
        if not self._current_variable:
            return

        code = str(item.data(Qt.ItemDataRole.UserRole) or "")
        current = self._selected_codes.setdefault(self._current_variable, [])
        if item.checkState() == Qt.CheckState.Checked and code not in current:
            current.append(code)
        elif item.checkState() != Qt.CheckState.Checked and code in current:
            current.remove(code)

        self._refresh_selection_summary()

    def _select_all_values(self) -> None:
        """Select all values for the current variable."""
        for row in range(self.value_list.count()):
            item = self.value_list.item(row)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked)
        self._refresh_selection_summary()

    def _clear_selected_values(self) -> None:
        """Clear all selected values for the current variable."""
        for row in range(self.value_list.count()):
            item = self.value_list.item(row)
            if item is not None:
                item.setCheckState(Qt.CheckState.Unchecked)
        self._refresh_selection_summary()

    def _apply(self) -> None:
        """Build a query payload from the selected table and values."""
        table_id = str(self.table_combo.currentData() or "")
        if not table_id:
            self._dialogs.warn(
                self,
                title=self.tr("No table selected"),
                text=self.tr("Please select an SCB table first."),
            )
            return

        metadata = self._metadata_by_id.get(table_id)
        if metadata is None:
            self._dialogs.warn(
                self,
                title=self.tr("No metadata loaded"),
                text=self.tr("Please load a table before applying it."),
            )
            return

        selections: list[ScbSelection] = []
        for variable in metadata.variables:
            codes = self._selected_codes.get(variable.name, [])
            if not codes:
                continue
            selections.append(ScbSelection(variable.name, tuple(codes)))

        if not selections:
            self._dialogs.warn(
                self,
                title=self.tr("No values selected"),
                text=self.tr("Select at least one value before applying the query."),
            )
            return

        try:
            builder = ScbQueryBuilder()
            params = builder.build(
                table_id=table_id,
                selections=selections,
                lang=self._current_language(),
            )
            self.result_data = {
                "url": builder.table_url(table_id),
                "query_params": params,
            }
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
        ) as exc:  # pragma: no cover - UI safety net
            self._dialogs.critical(
                self,
                title=self.tr("SCB query error"),
                text=str(exc),
            )
            return

        self.accept()

    def get_result(self) -> dict[str, object] | None:
        """Return the built SCB query data if accepted."""
        return self.result_data
