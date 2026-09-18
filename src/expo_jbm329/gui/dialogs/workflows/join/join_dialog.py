"""Join dialog for datasets.

This module provides a dialog for configuring the join operation between two
datasets (tabs) in the workbench, allowing the user to select join keys,
columns to include, and the join type.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.gui_utils import apply_window_hints_strict

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass
class JoinDialogResult:
    """Result of the join configuration.

    Attributes:
        left_tab_title: Title of the left dataset tab.
        right_tab_title: Title of the right dataset tab.
        left_on: List of join keys from the left dataset.
        right_on: List of join keys from the right dataset.
        left_selected_columns: List of columns to include from the left dataset.
        right_selected_columns: List of columns to include from the right dataset.
        join_type: The type of join (inner, left, right, outer).
    """

    left_tab_title: str
    right_tab_title: str
    left_on: list[str]
    right_on: list[str]
    left_selected_columns: list[str]
    right_selected_columns: list[str]
    join_type: Literal["inner", "left", "right", "outer"]


@dataclass
class _SideWidgets:
    cb_dataset: QComboBox
    cb_key: QComboBox
    columns_list: QListWidget
    cb_select_all: QCheckBox


class JoinDialog(QDialog):
    """Symmetric join dialog for datasets.

    Allows the user to select two datasets, choose join keys, select columns,
    and specify the join type (inner, left, right, full).
    """

    def __init__(
        self,
        parent: QWidget | None,
        *,
        all_tab_titles: Sequence[str],
        left_initial: str,
        get_columns_for_tab: dict[str, Sequence[str]],
        suggested_keys: list[str] | None = None,
        joinable_map: dict[tuple[str, str, str], set[str]],
    ) -> None:
        """Initialize the join dialog.

        Args:
            parent: The parent widget.
            all_tab_titles: A sequence of all available tab titles.
            left_initial: The title of the initially selected left tab.
            get_columns_for_tab: A mapping of tab titles to their column names.
            suggested_keys: A list of suggested join keys, if any.
            joinable_map: A mapping of join key combinations to joinability.
        """
        super().__init__(parent)

        self.setWindowTitle(self.tr("Join datasets"))

        # INPUT DATA
        self._all_tabs = list(all_tab_titles)
        self._get_cols = get_columns_for_tab
        self._left_initial = left_initial
        self._suggested_keys = suggested_keys or []
        self._joinable_map = joinable_map

        # ======================================================
        # Widgets
        # ======================================================

        self._left: _SideWidgets
        self._right: _SideWidgets

        # Root layout
        root = QVBoxLayout(self)

        # ======================================================
        # MAIN GRID: Left + Right
        # ======================================================

        grid = QGridLayout()

        # -------------------------
        # Assemble grid
        # -------------------------

        left_box, self._left = self._create_side_panel(self.tr("Left dataset"))
        right_box, self._right = self._create_side_panel(self.tr("Right dataset"))

        self._left.cb_dataset.setCurrentText(self._left_initial)

        for tab in self._all_tabs:
            if tab != self._left_initial:
                self._right.cb_dataset.setCurrentText(tab)
                break

        self._left.cb_dataset.currentTextChanged.connect(lambda: self._on_dataset_changed(self._left, self._right))

        self._right.cb_dataset.currentTextChanged.connect(lambda: self._on_dataset_changed(self._right, self._left))

        self._left.cb_key.currentTextChanged.connect(self._on_left_key_changed)

        self._left.cb_select_all.clicked.connect(lambda: self._toggle_all(self._left))
        self._right.cb_select_all.clicked.connect(lambda: self._toggle_all(self._right))

        grid.addWidget(left_box, 0, 0)
        grid.addWidget(right_box, 0, 1)

        root.addLayout(grid)

        # ======================================================
        # STATUS BANNER
        # ======================================================
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setHidden(True)
        root.addWidget(self.lbl_status)

        # ======================================================
        # JOIN TYPE (horizontal radio buttons)
        # ======================================================

        join_box = QGroupBox(self.tr("Join type"))
        join_h = QHBoxLayout(join_box)

        self.rb_inner = QRadioButton("Inner join")
        self.rb_left = QRadioButton("Left join")
        self.rb_right = QRadioButton("Right join")
        self.rb_full = QRadioButton("Full (outer) join")

        self.rb_inner.setChecked(True)

        join_h.addWidget(self.rb_inner)
        join_h.addWidget(self.rb_left)
        join_h.addWidget(self.rb_right)
        join_h.addWidget(self.rb_full)

        root.addWidget(join_box)

        # ======================================================
        # BUTTONS
        # ======================================================
        btn_row = QHBoxLayout()
        self.btn_preview = QPushButton(self.tr("Preview"))
        self.btn_ok = QPushButton(self.tr("OK"))
        self.btn_cancel = QPushButton(self.tr("Cancel"))

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(self.btn_preview)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_ok)
        btn_row.addWidget(self.btn_cancel)

        root.addLayout(btn_row)

        apply_window_hints_strict(self, min_width=625, fixed_size=True)

        # ======================================================
        # INITIAL POPULATION
        # ======================================================

        self._populate_side(self._left)
        self._populate_side(self._right)
        self._auto_select_join_keys()

        # On change
        self._on_left_key_changed(self._left.cb_key.currentText())

    # ---------------------------------------------------------
    # Create panels
    # ---------------------------------------------------------

    def _create_side_panel(self, title: str) -> tuple[QGroupBox, _SideWidgets]:
        box = QGroupBox(title)
        layout = QFormLayout(box)

        cb_dataset = QComboBox()
        cb_dataset.addItems(sorted(self._all_tabs))

        cb_key = QComboBox()

        columns_list = QListWidget()
        columns_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        cb_select_all = QCheckBox(self.tr("Select all"))
        cb_select_all.setChecked(True)

        layout.addRow(self.tr("Dataset:"), cb_dataset)
        layout.addRow(self.tr("Key:"), cb_key)
        layout.addRow(QLabel(self.tr("Columns to include:")), columns_list)
        layout.addRow("", cb_select_all)

        widgets = _SideWidgets(
            cb_dataset=cb_dataset,
            cb_key=cb_key,
            columns_list=columns_list,
            cb_select_all=cb_select_all,
        )

        return box, widgets

    # ---------------------------------------------------------
    # Populate left/right based on selected dataset
    # ---------------------------------------------------------

    def _populate_side(self, side: _SideWidgets):
        tab = side.cb_dataset.currentText()
        cols = sorted(self._get_cols[tab])

        side.cb_key.blockSignals(True)
        side.cb_key.clear()
        side.cb_key.addItems(cols)
        side.cb_key.blockSignals(False)

        side.columns_list.blockSignals(True)
        side.columns_list.clear()

        for col in cols:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            side.columns_list.addItem(item)

        side.columns_list.blockSignals(False)

        with contextlib.suppress(Exception):
            side.columns_list.itemChanged.disconnect()

        side.columns_list.itemChanged.connect(lambda: self._update_select_all(side))
        self._update_select_all(side)

    # ---------------------------------------------------------
    # ComboBox change handlers
    # ---------------------------------------------------------
    def _on_dataset_changed(self, changed: _SideWidgets, other: _SideWidgets) -> None:
        """Handle dataset change for either left or right side."""
        # 1. Populate the changed side
        self._populate_side(changed)

        # 2. Ensure left/right are not the same dataset
        if changed.cb_dataset.currentText() == other.cb_dataset.currentText():
            for t in self._all_tabs:
                if t != changed.cb_dataset.currentText():
                    other.cb_dataset.setCurrentText(t)
                    break

        # 3. Repopulate the other side (because dataset may have changed)
        self._populate_side(other)

        # 4. Try to auto-select good join keys
        self._auto_select_join_keys()

        # 5. Update enabled/disabled state in right key
        self._on_left_key_changed(self._left.cb_key.currentText())

    # noinspection PyMethodMayBeStatic
    def _set_combobox_item_enabled(self, cb: QComboBox, index: int, enabled: bool, tooltip: str = ""):
        model = cb.model()
        if isinstance(model, QStandardItemModel):
            item = model.item(index)
            if item:
                item.setEnabled(enabled)
                item.setToolTip(tooltip)

    def _on_left_key_changed(self, col: str):
        """Handle change of the left join key.

        Updates the availability of keys in the right dataset based on
        data type compatibility with the selected left key.

        Args:
            col: The newly selected left key column name.
        """
        if not col:
            return

        left_tab = self._left.cb_dataset.currentText()
        right_tab = self._right.cb_dataset.currentText()

        model = self._right.cb_key.model()

        if not isinstance(model, QStandardItemModel):
            return

        any_enabled = False

        right_candidates = self._joinable_map.get((left_tab, col, right_tab), set())

        for i in range(self._right.cb_key.count()):
            right_col = self._right.cb_key.itemText(i)

            enabled = right_col in right_candidates

            self._set_combobox_item_enabled(
                self._right.cb_key,
                i,
                enabled,
                "" if enabled else self.tr("Incompatible types"),
            )

            if enabled:
                any_enabled = True

        self.btn_ok.setEnabled(any_enabled)

        # fallback selection
        if not any_enabled:
            return

        current = self._right.cb_key.currentText()

        # 1. If current is valid, keep it
        if current in right_candidates:
            return

        # 2. Prefer same column name
        if col in right_candidates:
            self._right.cb_key.blockSignals(True)
            self._right.cb_key.setCurrentText(col)
            self._right.cb_key.blockSignals(False)

            return

        # 3. Otherwise pick first valid
        for i in range(self._right.cb_key.count()):
            candidate = self._right.cb_key.itemText(i)
            if candidate in right_candidates:
                self._right.cb_key.blockSignals(True)
                self._right.cb_key.setCurrentIndex(i)
                self._right.cb_key.blockSignals(False)

                return

    # ---------------------------------------------------------
    # Toggle select all columns
    # ---------------------------------------------------------

    def _toggle_all(self, side: _SideWidgets):
        total = side.columns_list.count()
        checked = sum(
            1
            for i in range(total)
            if (item := side.columns_list.item(i)) and item.checkState() == Qt.CheckState.Checked
        )

        new_state = Qt.CheckState.Unchecked if checked == total else Qt.CheckState.Checked

        side.columns_list.blockSignals(True)
        for i in range(total):
            if item := side.columns_list.item(i):
                item.setCheckState(new_state)
        side.columns_list.blockSignals(False)

        self._update_select_all(side)

    # noinspection PyMethodMayBeStatic
    def _update_select_all(self, side: _SideWidgets):
        total = side.columns_list.count()
        checked = sum(
            1
            for i in range(total)
            if (item := side.columns_list.item(i)) and item.checkState() == Qt.CheckState.Checked
        )

        side.cb_select_all.blockSignals(True)

        if checked == 0:
            state = Qt.CheckState.Unchecked
        elif checked == total:
            state = Qt.CheckState.Checked
        else:
            state = Qt.CheckState.PartiallyChecked

        side.cb_select_all.setCheckState(state)
        side.cb_select_all.blockSignals(False)

    # ---------------------------------------------------------
    # Extract result
    # ---------------------------------------------------------
    # noinspection PyMethodMayBeStatic
    def _get_checked(self, lw: QListWidget) -> list[str]:
        cols = []
        for i in range(lw.count()):
            item = lw.item(i)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                cols.append(item.text())
        return cols

    def build_result(self) -> JoinDialogResult:
        """Build and return the join result based on current selections.

        Returns:
            The configured join result.
        """
        left_tab = self._left.cb_dataset.currentText()
        right_tab = self._right.cb_dataset.currentText()

        jt: Literal["inner", "left", "right", "outer"]

        # join-type
        if self.rb_left.isChecked():
            jt = "left"
        elif self.rb_right.isChecked():
            jt = "right"
        elif self.rb_full.isChecked():
            jt = "outer"
        else:
            jt = "inner"

        return JoinDialogResult(
            left_tab_title=left_tab,
            right_tab_title=right_tab,
            # TODO: support multi-key joins (UI + DTO already supports it)
            left_on=[self._left.cb_key.currentText()],
            right_on=[self._right.cb_key.currentText()],
            left_selected_columns=self._get_checked(self._left.columns_list),
            right_selected_columns=self._get_checked(self._right.columns_list),
            join_type=jt,
        )

    # ---------------------------------------------------------
    # Autoselect join keys
    # ---------------------------------------------------------

    def _auto_select_join_keys(self) -> None:

        left_tab = self._left.cb_dataset.currentText()
        right_tab = self._right.cb_dataset.currentText()

        left_cols = list(self._get_cols[left_tab])
        right_cols = list(self._get_cols[right_tab])

        # 1. Exact name match
        common = set(left_cols) & set(right_cols)

        for col in sorted(common):
            right_candidates = self._joinable_map.get((left_tab, col, right_tab), set())
            if col in right_candidates:
                self._left.cb_key.setCurrentText(col)
                self._right.cb_key.setCurrentText(col)
                return

        # 2. First compatible pair

        for left_col in left_cols:
            right_candidates = self._joinable_map.get((left_tab, left_col, right_tab), set())

            for right_col in right_cols:
                if right_col in right_candidates:
                    self._left.cb_key.setCurrentText(left_col)
                    self._right.cb_key.setCurrentText(right_col)
                    return
