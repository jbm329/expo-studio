"""Concatenation dialog for datasets.

This module provides a dialog for configuring the concatenation of two
datasets (tabs) in the workbench.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.gui_utils import apply_window_hints_strict

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass
class ConcatDialogResult:
    """Result of the concatenation configuration.

    Attributes:
        left_tab_title: The title of the base dataset tab.
        right_tab_title: The title of the dataset tab to append.
        remove_duplicates: Whether to remove duplicate rows (reserved for future).
    """

    left_tab_title: str
    right_tab_title: str
    remove_duplicates: bool


class ConcatDialog(QDialog):
    """Minimal concatenation dialog for datasets.

    Allows the user to select two datasets and view their columns before
    performing a concatenation operation.

    Attributes:
        cb_left_dataset: Dropdown for the left dataset.
        cb_right_dataset: Dropdown for the right dataset.
        left_columns_list: List widget showing columns of the left dataset.
        right_columns_list: List widget showing columns of the right dataset.
    """

    def __init__(
        self,
        *,
        parent: QWidget | None,
        left_tab_title: str,
        right_tab_titles: Sequence[str],
        left_columns: Sequence[str],
        right_columns_map: dict[str, Sequence[str]],
    ) -> None:
        """Initialize the concatenation dialog.

        Args:
            parent: The parent widget.
            left_tab_title: The title of the initially selected left tab.
            right_tab_titles: A sequence of available titles for the right tab.
            left_columns: A sequence of column names for the left tab.
            right_columns_map: A mapping of tab titles to their column names.
        """
        super().__init__(parent)

        self.setWindowTitle(self.tr("Concatenate datasets"))

        self._left_initial = left_tab_title
        self._right_tabs = list(right_tab_titles)
        self._left_cols = list(left_columns)
        self._right_cols_map = right_columns_map

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

        self.left_columns_list = QListWidget()
        self.left_columns_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        left_layout.addRow(self.tr("Dataset:"), self.cb_left_dataset)
        left_layout.addRow(QLabel(self.tr("Columns:")), self.left_columns_list)

        # ======================================================
        # RIGHT PANEL
        # ======================================================
        right_box = QGroupBox(self.tr("Second dataset"))
        right_layout = QFormLayout(right_box)

        self.cb_right_dataset = QComboBox()
        self.cb_right_dataset.addItems(list(self._right_tabs))
        self.cb_right_dataset.currentTextChanged.connect(self._on_right_dataset_changed)

        self.right_columns_list = QListWidget()
        self.right_columns_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        right_layout.addRow(self.tr("Dataset:"), self.cb_right_dataset)
        right_layout.addRow(QLabel(self.tr("Columns:")), self.right_columns_list)

        # ======================================================
        # Grid Left + Right
        # ======================================================
        row = QHBoxLayout()
        row.addWidget(left_box)
        row.addWidget(right_box)
        root.addLayout(row)

        # ======================================================
        # BUTTONS
        # ======================================================
        btns = QDialogButtonBox(parent=self)
        btns.addButton(QDialogButtonBox.StandardButton.Ok)
        btns.addButton(QDialogButtonBox.StandardButton.Cancel)

        localize_dialog_buttons(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        apply_window_hints_strict(self, min_width=520, fixed_size=True)

        # Initial population
        self._populate_left_columns()
        self._populate_right_columns(self.cb_right_dataset.currentText())

    # ---------------------------------------------------------
    # Populate
    # ---------------------------------------------------------
    def _populate_left_columns(self):
        self.left_columns_list.clear()
        for col in self._left_cols:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)  # read-only
            self.left_columns_list.addItem(item)

    def _populate_right_columns(self, tab: str):
        cols = self._right_cols_map.get(tab, [])
        self.right_columns_list.clear()
        for col in cols:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.right_columns_list.addItem(item)

    def _on_right_dataset_changed(self, tab: str):
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
        )
