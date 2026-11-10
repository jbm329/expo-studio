"""Concatenation dialog for datasets.

This module provides a dialog for configuring the concatenation of two
datasets (tabs) in the workbench.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PyQt6.QtCore import QLocale, QSignalBlocker, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.app.help_topics import HelpTopic
from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.dialogs.workflows.column_fill_editor import (
    FILL_COLUMN_ROLE,
    FILL_VALUE_ROLE,
    ColumnFillDelegate,
    ColumnFillValueDialog,
    display_fill,
)
from expo_jbm329.gui.gui_utils import apply_window_hints_strict
from expo_jbm329.services.data_operations.column_defaults import (
    ColumnFill,
    FillColumn,
    parse_fill,
    validate_fill_column,
)
from expo_jbm329.utils.i18n_utils import translate

DEFAULT_COLUMN_INDEX = 2

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService


@dataclass
class ConcatDialogResult:
    """Result of the concatenation configuration.

    Attributes:
        left_tab_title: The title of the base dataset tab.
        right_tab_title: The title of the dataset tab to append.
        remove_duplicates: Whether to remove duplicate rows throughout the result.
        left_fill: Defaults for columns selected only in the first dataset.
        right_fill: Defaults for columns selected only in the second dataset.
        left_columns: Included first-dataset columns, or None for all.
        right_columns: Included second-dataset columns, or None for all.
    """

    left_tab_title: str
    right_tab_title: str
    remove_duplicates: bool
    left_fill: dict[str, ColumnFill] = field(default_factory=dict)
    right_fill: dict[str, ColumnFill] = field(default_factory=dict)
    left_columns: Sequence[str] | None = None
    right_columns: Sequence[str] | None = None


class ConcatDialog(QDialog):
    """Concatenation dialog with per-dataset column inclusion.

    Allows the user to select two datasets and view their columns before
    performing a concatenation operation.

    Attributes:
        cb_left_dataset: Dropdown for the left dataset.
        cb_right_dataset: Dropdown for the right dataset.
        exclude_duplicates: Optional whole-result duplicate-row removal.
        left_columns_table: Checkable column/type table for the first dataset.
        right_columns_table: Checkable column/type table for the second dataset.
        left_select_all: Inclusion control for all first-dataset columns.
        right_select_all: Inclusion control for all second-dataset columns.
        left_bulk_kind: Data types targeted by first-dataset bulk defaults.
        left_bulk_button: Applies one default to eligible first-dataset columns.
        right_bulk_kind: Data types targeted by second-dataset bulk defaults.
        right_bulk_button: Applies one default to eligible second-dataset columns.
    """

    def __init__(
        self,
        *,
        parent: QWidget | None,
        left_tab_title: str,
        right_tab_titles: Sequence[str],
        left_columns: Sequence[str],
        right_columns_map: dict[str, Sequence[str]],
        dialogs: DialogService | None = None,
        left_column_metadata: Mapping[str, FillColumn] | None = None,
        right_column_metadata: Mapping[str, Mapping[str, FillColumn]] | None = None,
    ) -> None:
        """Initialize the concatenation dialog.

        Args:
            parent: The parent widget.
            left_tab_title: The title of the initially selected left tab.
            right_tab_titles: A sequence of available titles for the right tab.
            left_columns: A sequence of column names for the left tab.
            right_columns_map: A mapping of tab titles to their column names.
            dialogs: Service for displaying warnings, defaulting to QtDialogService.
            left_column_metadata: Optional dtype-only metadata for first-dataset columns.
            right_column_metadata: Optional metadata keyed by second-dataset title and column.
        """
        super().__init__(parent)
        self._dialogs = dialogs if dialogs is not None else QtDialogService()

        self.setWindowTitle(self.tr("Concatenate datasets"))

        self._left_initial = left_tab_title
        self._right_tabs = list(right_tab_titles)
        self._left_cols = list(left_columns)
        self._right_cols_map = right_columns_map
        self._left_column_metadata = dict(left_column_metadata) if left_column_metadata is not None else {}
        self._right_column_metadata = (
            {title: dict(columns) for title, columns in right_column_metadata.items()}
            if right_column_metadata is not None
            else {}
        )
        self._numeric_locale = QLocale()

        root = QVBoxLayout(self)

        # ======================================================
        # LEFT PANEL
        # ======================================================
        left_box = QGroupBox(self.tr("First dataset"))
        left_layout = QFormLayout(left_box)

        self.cb_left_dataset = QComboBox()
        # Only the preselected dataset = left_tab_title
        self.cb_left_dataset.addItems([left_tab_title])
        self.cb_left_dataset.setCurrentText(left_tab_title)

        self.left_columns_table = self._create_columns_table()
        self.left_bulk_kind, self.left_bulk_button = self._create_bulk_controls()
        self.left_select_all = QCheckBox(self.tr("Select all"), self)
        self.left_select_all.setTristate(True)
        self.left_select_all.clicked.connect(lambda: self._toggle_all(self.left_columns_table))
        self.left_bulk_button.clicked.connect(
            lambda: self._set_bulk_defaults(self.left_columns_table, self.left_bulk_kind)
        )
        self.left_columns_table.itemChanged.connect(self._update_selection_controls)

        left_layout.addRow(self.tr("Dataset:"), self.cb_left_dataset)
        left_layout.addRow(QLabel(self.tr("Columns:")))
        left_layout.addRow(self.left_columns_table)
        left_layout.addRow(self.left_select_all)
        left_bulk_row = QHBoxLayout()
        left_bulk_row.addWidget(self.left_bulk_kind)
        left_bulk_row.addWidget(self.left_bulk_button)
        left_layout.addRow(left_bulk_row)

        # ======================================================
        # RIGHT PANEL
        # ======================================================
        right_box = QGroupBox(self.tr("Second dataset"))
        right_layout = QFormLayout(right_box)

        self.cb_right_dataset = QComboBox()
        self.cb_right_dataset.addItems(list(self._right_tabs))
        self.cb_right_dataset.currentTextChanged.connect(self._on_right_dataset_changed)

        self.right_columns_table = self._create_columns_table()
        self.right_bulk_kind, self.right_bulk_button = self._create_bulk_controls()
        self.right_select_all = QCheckBox(self.tr("Select all"), self)
        self.right_select_all.setTristate(True)
        self.right_select_all.clicked.connect(lambda: self._toggle_all(self.right_columns_table))
        self.right_bulk_button.clicked.connect(
            lambda: self._set_bulk_defaults(self.right_columns_table, self.right_bulk_kind)
        )
        self.right_columns_table.itemChanged.connect(self._update_selection_controls)

        right_layout.addRow(self.tr("Dataset:"), self.cb_right_dataset)
        right_layout.addRow(QLabel(self.tr("Columns:")))
        right_layout.addRow(self.right_columns_table)
        right_layout.addRow(self.right_select_all)
        right_bulk_row = QHBoxLayout()
        right_bulk_row.addWidget(self.right_bulk_kind)
        right_bulk_row.addWidget(self.right_bulk_button)
        right_layout.addRow(right_bulk_row)

        # ======================================================
        # Grid Left + Right
        # ======================================================
        row = QHBoxLayout()
        row.addWidget(left_box)
        row.addWidget(right_box)
        root.addLayout(row)
        selection_hint = QLabel(
            self.tr(
                "Only checked columns supply values. Unchecking a column on one side keeps that dataset's rows, "
                "but uses NULL for them if the column is included on the other side."
            ),
            self,
        )
        selection_hint.setWordWrap(True)
        root.addWidget(selection_hint)

        self.exclude_duplicates = QCheckBox(self.tr("Exclude duplicate rows"), self)
        self.exclude_duplicates.setToolTip(
            self.tr(
                "Remove duplicate rows throughout the combined result, keeping the first occurrence. "
                "Compare all output columns after column selection and defaults."
            )
        )
        root.addWidget(self.exclude_duplicates)

        # ======================================================
        # BUTTONS
        # ======================================================
        btns = QDialogButtonBox(parent=self)
        btns.addButton(QDialogButtonBox.StandardButton.Ok)
        btns.addButton(QDialogButtonBox.StandardButton.Cancel)
        ok_button = btns.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is None:
            message = "Concatenate OK button has not been created."
            raise RuntimeError(message)
        self._ok_button = ok_button

        localize_dialog_buttons(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        help_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Help, self)
        localize_dialog_buttons(help_buttons)
        help_button = help_buttons.button(QDialogButtonBox.StandardButton.Help)
        if help_button is None:
            message = "Concatenate help button has not been created."
            raise RuntimeError(message)
        help_button.setAutoDefault(False)
        help_buttons.helpRequested.connect(self._open_help)
        button_row = QHBoxLayout()
        button_row.addWidget(help_buttons)
        button_row.addStretch(1)
        button_row.addWidget(btns)
        root.addLayout(button_row)

        self._help_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.HelpContents), self)
        self._help_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._help_shortcut.activated.connect(self._open_help)

        apply_window_hints_strict(self, min_width=850)
        self.setMinimumWidth(650)
        self.setSizeGripEnabled(True)

        # Initial population
        self._populate_left_columns()
        self._populate_right_columns(self.cb_right_dataset.currentText())

    def _open_help(self) -> None:
        """Open concatenate guidance without applying or changing the configuration."""
        url = HelpTopic.CONCATENATE_DATASETS.url
        if not QDesktopServices.openUrl(QUrl(url)):
            self._dialogs.warn(
                self,
                self.tr("Unable to open link"),
                self.tr("The user manual could not be opened.\n\n{url}").format(url=url),
            )

    # ---------------------------------------------------------
    # Populate
    # ---------------------------------------------------------
    def _create_columns_table(self) -> QTableWidget:
        table = QTableWidget(0, 3, self)
        table.setHorizontalHeaderLabels([self.tr("Column"), self.tr("Type"), self.tr("If absent")])
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        horizontal_header = table.horizontalHeader()
        vertical_header = table.verticalHeader()
        if horizontal_header is None or vertical_header is None:
            message = "Concatenation column table headers have not been created."
            raise RuntimeError(message)
        vertical_header.hide()
        horizontal_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        horizontal_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        horizontal_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        horizontal_header.resizeSection(2, 170)
        table.setItemDelegateForColumn(
            2,
            ColumnFillDelegate(
                table,
                self._dialogs,
                title=self.tr("If absent"),
                object_hint=self.tr(
                    "Text defaults require text-only source values. This is checked when concatenation runs."
                ),
            ),
        )
        return table

    def _create_bulk_controls(self) -> tuple[QComboBox, QPushButton]:
        kind = QComboBox(self)
        kind.addItem(translate("JoinDialog", "Numeric columns"), "numeric")
        kind.addItem(translate("JoinDialog", "Text columns"), "text")
        button = QPushButton(translate("JoinDialog", "Set defaults..."), self)
        button.setAutoDefault(False)
        return kind, button

    def _populate_columns_table(
        self,
        table: QTableWidget,
        columns: Sequence[str],
        metadata: Mapping[str, FillColumn],
    ) -> None:
        unique = len(set(columns)) == len(columns)
        with QSignalBlocker(table):
            table.setRowCount(len(columns))
            for row, column in enumerate(columns):
                column_metadata = metadata.get(column)
                dtype = column_metadata.dtype if column_metadata is not None else "-"
                for position, text in enumerate((column, dtype, translate("JoinFillValueDialog", "NULL"))):
                    item = QTableWidgetItem(text)
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    item.setToolTip(text)
                    if position == 0:
                        if unique:
                            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        else:
                            item.setToolTip(self.tr("Rename duplicate columns to enable column selection."))
                        item.setCheckState(Qt.CheckState.Checked)
                    elif position == DEFAULT_COLUMN_INDEX:
                        item.setData(FILL_VALUE_ROLE, ColumnFill())
                        column_info = metadata.get(column)
                        if column_info is not None:
                            item.setData(FILL_COLUMN_ROLE, column_info)
                    table.setItem(row, position, item)
        self._update_selection_controls()

    @staticmethod
    def _checked_columns(table: QTableWidget) -> list[str]:
        return [
            item.text()
            for row in range(table.rowCount())
            if (item := table.item(row, 0)) is not None and item.checkState() == Qt.CheckState.Checked
        ]

    def _toggle_all(self, table: QTableWidget) -> None:
        checked = len(self._checked_columns(table))
        state = Qt.CheckState.Unchecked if checked == table.rowCount() else Qt.CheckState.Checked
        with QSignalBlocker(table):
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item is not None:
                    item.setCheckState(state)
        self._update_selection_controls()

    def _update_selection_controls(self) -> None:
        included = 0
        for table, select_all in (
            (self.left_columns_table, self.left_select_all),
            (self.right_columns_table, self.right_select_all),
        ):
            columns = self._checked_columns(table)
            checked = len(columns)
            included += checked
            state = Qt.CheckState.Unchecked
            if checked > 0:
                state = Qt.CheckState.Checked if checked == table.rowCount() else Qt.CheckState.PartiallyChecked
            with QSignalBlocker(select_all):
                select_all.setCheckState(state)
            unique = len(set(columns)) == len(columns)
            select_all.setEnabled(table.rowCount() > 0 and unique)
            select_all.setToolTip("" if unique else self.tr("Rename duplicate columns to enable column selection."))
        self._ok_button.setEnabled(included > 0)
        self._update_default_controls()

    def _update_default_controls(self) -> None:
        selected_left = set(self._checked_columns(self.left_columns_table))
        selected_right = set(self._checked_columns(self.right_columns_table))
        sides = (
            (self.left_columns_table, selected_right, self.left_bulk_kind, self.left_bulk_button),
            (self.right_columns_table, selected_left, self.right_bulk_kind, self.right_bulk_button),
        )
        for table, other_selected, bulk_kind, bulk_button in sides:
            eligible_count = 0
            names = [item.text() for row in range(table.rowCount()) if (item := table.item(row, 0)) is not None]
            unique_names = len(names) == table.rowCount() and len(set(names)) == len(names)
            with QSignalBlocker(table):
                for row in range(table.rowCount()):
                    name_item = table.item(row, 0)
                    fill_item = table.item(row, 2)
                    if name_item is None or fill_item is None:
                        continue
                    column = fill_item.data(FILL_COLUMN_ROLE)
                    eligible = (
                        name_item.checkState() == Qt.CheckState.Checked
                        and name_item.text() not in other_selected
                        and unique_names
                        and isinstance(column, FillColumn)
                        and column.kind != "unsupported"
                    )
                    flags = Qt.ItemFlag.NoItemFlags
                    if eligible:
                        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
                    fill_item.setFlags(flags)
                    fill = fill_item.data(FILL_VALUE_ROLE)
                    if not isinstance(fill, ColumnFill):
                        message = "Concatenation default cell has no typed value."
                        raise TypeError(message)
                    fill_item.setText(
                        display_fill(
                            fill,
                            self._numeric_locale,
                            null=translate("JoinFillValueDialog", "NULL"),
                            true=translate("JoinFillValueDialog", "True"),
                            false=translate("JoinFillValueDialog", "False"),
                        )
                    )
                    if eligible:
                        eligible_count += 1
                        fill_item.setToolTip(self.tr("Click to choose a default for rows from the other dataset."))
                    else:
                        fill_item.setToolTip(
                            self.tr("Defaults apply only to selected columns absent from the other dataset.")
                        )
            bulk_button.setEnabled(eligible_count > 0)
            bulk_kind.setEnabled(eligible_count > 0)

    def _set_bulk_defaults(self, table: QTableWidget, bulk_kind: QComboBox) -> None:
        """Validate all eligible defaults before changing any cell."""
        kinds = {"integer", "float"} if bulk_kind.currentData() == "numeric" else {"text"}
        items: list[tuple[QTableWidgetItem, FillColumn]] = []
        for row in range(table.rowCount()):
            item = table.item(row, 2)
            if item is None or not item.flags() & Qt.ItemFlag.ItemIsEditable:
                continue
            column = item.data(FILL_COLUMN_ROLE)
            if isinstance(column, FillColumn) and column.kind in kinds:
                items.append((item, column))
        if not items:
            self._dialogs.warn(
                self,
                translate("JoinDialog", "No applicable columns"),
                self.tr("Select included columns of this type first."),
            )
            return
        editor = ColumnFillValueDialog(
            self,
            items[0][1],
            ColumnFill(),
            self._dialogs,
            title=self.tr("If absent"),
            object_hint=self.tr(
                "Text defaults require text-only source values. This is checked when concatenation runs."
            ),
            numeric_locale=self._numeric_locale,
        )
        editor.setWindowTitle(translate("JoinDialog", "Set defaults..."))
        accepted = editor.exec() == QDialog.DialogCode.Accepted
        custom = editor.choice.currentData() == "custom"
        text = editor.custom_value.text()
        fill = editor.fill
        editor.deleteLater()
        if not accepted:
            return
        try:
            validated = [
                (
                    item,
                    parse_fill(column, text, decimal_point=self._numeric_locale.decimalPoint())
                    if custom
                    else validate_fill_column(
                        column,
                        ColumnFill(0 if fill.value == 0 and column.kind in {"integer", "float"} else fill.value),
                    ),
                )
                for item, column in items
            ]
        except ValueError:
            self._dialogs.warn(
                self,
                translate("JoinDialog", "Invalid default value"),
                translate("JoinDialog", "The value is not valid for every selected column. No defaults were changed."),
            )
            return
        with QSignalBlocker(table):
            for item, value in validated:
                item.setData(FILL_VALUE_ROLE, value)
        self._update_default_controls()

    def _selected_columns(self, table: QTableWidget) -> list[str] | None:
        columns = self._checked_columns(table)
        return None if len(columns) == table.rowCount() else columns

    def _populate_left_columns(self) -> None:
        self._populate_columns_table(self.left_columns_table, self._left_cols, self._left_column_metadata)

    def _populate_right_columns(self, tab: str) -> None:
        cols = self._right_cols_map.get(tab, [])
        self._populate_columns_table(self.right_columns_table, cols, self._right_column_metadata.get(tab, {}))
        self._reset_fills(self.left_columns_table)
        self._update_selection_controls()

    def _on_right_dataset_changed(self, tab: str) -> None:
        self._populate_right_columns(tab)

    # ---------------------------------------------------------
    # Result extraction
    # ---------------------------------------------------------
    def build_result(self) -> ConcatDialogResult:
        """Build and return the concatenation result based on current selections.

        Returns:
            The configured concatenation result.
        """
        return ConcatDialogResult(
            left_tab_title=self.cb_left_dataset.currentText(),
            right_tab_title=self.cb_right_dataset.currentText(),
            remove_duplicates=self.exclude_duplicates.isChecked(),
            left_columns=self._selected_columns(self.left_columns_table),
            right_columns=self._selected_columns(self.right_columns_table),
            left_fill=self._get_fills(self.left_columns_table, self.right_columns_table),
            right_fill=self._get_fills(self.right_columns_table, self.left_columns_table),
        )

    @staticmethod
    def _reset_fills(table: QTableWidget) -> None:
        with QSignalBlocker(table):
            for row in range(table.rowCount()):
                item = table.item(row, DEFAULT_COLUMN_INDEX)
                if item is not None:
                    item.setData(FILL_VALUE_ROLE, ColumnFill())

    def _get_fills(self, table: QTableWidget, other: QTableWidget) -> dict[str, ColumnFill]:
        other_columns = set(self._checked_columns(other))
        fills: dict[str, ColumnFill] = {}
        for row in range(table.rowCount()):
            name_item = table.item(row, 0)
            fill_item = table.item(row, DEFAULT_COLUMN_INDEX)
            if (
                name_item is None
                or fill_item is None
                or name_item.checkState() != Qt.CheckState.Checked
                or name_item.text() in other_columns
                or not fill_item.flags() & Qt.ItemFlag.ItemIsEditable
            ):
                continue
            value = fill_item.data(FILL_VALUE_ROLE)
            if not isinstance(value, ColumnFill):
                message = "Concatenation default cell has no typed value."
                raise TypeError(message)
            if value.value is not None:
                fills[name_item.text()] = value
        return fills
