"""Concatenation dialog for datasets.

This module provides a dialog for configuring the concatenation of two
datasets (tabs) in the workbench.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PyQt6.QtCore import QSignalBlocker, Qt, QUrl
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.app.help_topics import HelpTopic
from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.gui_utils import apply_window_hints_strict

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.services.data_operations.column_defaults import ColumnFill, FillColumn


@dataclass
class ConcatDialogResult:
    """Result of the concatenation configuration.

    Attributes:
        left_tab_title: The title of the base dataset tab.
        right_tab_title: The title of the dataset tab to append.
        remove_duplicates: Whether to remove duplicate rows (reserved for future).
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
        left_columns_table: Checkable column/type table for the first dataset.
        right_columns_table: Checkable column/type table for the second dataset.
        left_select_all: Inclusion control for all first-dataset columns.
        right_select_all: Inclusion control for all second-dataset columns.
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
        self.left_select_all = QCheckBox(self.tr("Select all"), self)
        self.left_select_all.setTristate(True)
        self.left_select_all.clicked.connect(lambda: self._toggle_all(self.left_columns_table))
        self.left_columns_table.itemChanged.connect(self._update_selection_controls)

        left_layout.addRow(self.tr("Dataset:"), self.cb_left_dataset)
        left_layout.addRow(QLabel(self.tr("Columns:")))
        left_layout.addRow(self.left_select_all)
        left_layout.addRow(self.left_columns_table)

        # ======================================================
        # RIGHT PANEL
        # ======================================================
        right_box = QGroupBox(self.tr("Second dataset"))
        right_layout = QFormLayout(right_box)

        self.cb_right_dataset = QComboBox()
        self.cb_right_dataset.addItems(list(self._right_tabs))
        self.cb_right_dataset.currentTextChanged.connect(self._on_right_dataset_changed)

        self.right_columns_table = self._create_columns_table()
        self.right_select_all = QCheckBox(self.tr("Select all"), self)
        self.right_select_all.setTristate(True)
        self.right_select_all.clicked.connect(lambda: self._toggle_all(self.right_columns_table))
        self.right_columns_table.itemChanged.connect(self._update_selection_controls)

        right_layout.addRow(self.tr("Dataset:"), self.cb_right_dataset)
        right_layout.addRow(QLabel(self.tr("Columns:")))
        right_layout.addRow(self.right_select_all)
        right_layout.addRow(self.right_columns_table)

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
        table = QTableWidget(0, 2, self)
        table.setHorizontalHeaderLabels([self.tr("Column"), self.tr("Type")])
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
        return table

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
                for position, text in enumerate((column, dtype)):
                    item = QTableWidgetItem(text)
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    item.setToolTip(text)
                    if position == 0:
                        if unique:
                            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        else:
                            item.setToolTip(self.tr("Rename duplicate columns to enable column selection."))
                        item.setCheckState(Qt.CheckState.Checked)
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

    def _selected_columns(self, table: QTableWidget) -> list[str] | None:
        columns = self._checked_columns(table)
        return None if len(columns) == table.rowCount() else columns

    def _populate_left_columns(self) -> None:
        self._populate_columns_table(self.left_columns_table, self._left_cols, self._left_column_metadata)

    def _populate_right_columns(self, tab: str) -> None:
        cols = self._right_cols_map.get(tab, [])
        self._populate_columns_table(self.right_columns_table, cols, self._right_column_metadata.get(tab, {}))

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
            remove_duplicates=False,  # MVP, will expand later
            left_columns=self._selected_columns(self.left_columns_table),
            right_columns=self._selected_columns(self.right_columns_table),
        )
