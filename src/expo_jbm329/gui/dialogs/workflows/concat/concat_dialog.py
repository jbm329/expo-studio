"""Concatenation dialog for datasets.

This module provides a dialog for configuring the concatenation of two
datasets (tabs) in the workbench.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
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

from expo_jbm329.app.help_topics import HelpTopic
from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.gui_utils import apply_window_hints_strict

if TYPE_CHECKING:
    from collections.abc import Sequence

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService


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
        dialogs: DialogService | None = None,
    ) -> None:
        """Initialize the concatenation dialog.

        Args:
            parent: The parent widget.
            left_tab_title: The title of the initially selected left tab.
            right_tab_titles: A sequence of available titles for the right tab.
            left_columns: A sequence of column names for the left tab.
            right_columns_map: A mapping of tab titles to their column names.
            dialogs: Service for displaying warnings, defaulting to QtDialogService.
        """
        super().__init__(parent)
        self._dialogs = dialogs if dialogs is not None else QtDialogService()

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

        apply_window_hints_strict(self, min_width=520, fixed_size=True)

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
    def _populate_left_columns(self) -> None:
        self.left_columns_list.clear()
        for col in self._left_cols:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)  # read-only
            self.left_columns_list.addItem(item)

    def _populate_right_columns(self, tab: str) -> None:
        cols = self._right_cols_map.get(tab, [])
        self.right_columns_list.clear()
        for col in cols:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.right_columns_list.addItem(item)

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
        )
