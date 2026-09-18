"""Dialogs for column-level operations.

Includes dialogs for structural transformations on dataframe columns,
such as splitting a column or joining multiple columns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.service.common.window_hints import apply_dialog_window_hints

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import MergeColumnsResult, SplitColumnResult


# ----------------------------------------------------------------------
# Split column
# ----------------------------------------------------------------------
def prompt_split_column(
    parent: QWidget,
    *,
    title: str,
    column: str,
    default_delimiter: str = "-",
    default_keep_original: bool = True,
    default_mode: Literal["first", "last"] = "first",
) -> SplitColumnResult:
    """Prompt the user for column splitting configuration."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    root = QVBoxLayout(dlg)

    # Context
    root.addWidget(
        QLabel(
            QCoreApplication.translate("QtDialogService", "Column: %1").replace("%1", column),
            dlg,
        )
    )

    # Delimiter
    row_delim = QHBoxLayout()
    row_delim.addWidget(
        QLabel(
            QCoreApplication.translate("QtDialogService", "Delimiter / string:"),
            dlg,
        )
    )

    txt_delim = QLineEdit(dlg)
    txt_delim.setText(default_delimiter or "")
    txt_delim.setPlaceholderText(QCoreApplication.translate("QtDialogService", "Example: ; , | space  \\t (tab)"))
    row_delim.addWidget(txt_delim)
    root.addLayout(row_delim)

    # Keep original column
    chk_keep = QCheckBox(
        QCoreApplication.translate("QtDialogService", "Keep original column"),
        dlg,
    )
    chk_keep.setChecked(bool(default_keep_original))
    root.addWidget(chk_keep)

    # Split mode
    root.addWidget(
        QLabel(
            QCoreApplication.translate("QtDialogService", "Split at:"),
            dlg,
        )
    )

    rb_first = QRadioButton(
        QCoreApplication.translate("QtDialogService", "First occurrence"),
        dlg,
    )
    rb_last = QRadioButton(
        QCoreApplication.translate("QtDialogService", "Last occurrence"),
        dlg,
    )

    grp = QButtonGroup(dlg)
    grp.addButton(rb_first)
    grp.addButton(rb_last)

    if default_mode == "last":
        rb_last.setChecked(True)
    else:
        rb_first.setChecked(True)

    row_mode = QHBoxLayout()
    row_mode.addWidget(rb_first)
    row_mode.addWidget(rb_last)
    row_mode.addStretch(1)
    root.addLayout(row_mode)

    # Buttons
    buttons = QDialogButtonBox(parent=dlg)
    buttons.addButton(QDialogButtonBox.StandardButton.Ok)
    buttons.addButton(QDialogButtonBox.StandardButton.Cancel)

    localize_dialog_buttons(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    root.addWidget(buttons)

    # Validation: empty delimiter → disable OK
    btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
    if btn_ok is not None:
        btn_ok.setEnabled(bool(txt_delim.text()))

    def _validate() -> None:
        if btn_ok is not None:
            btn_ok.setEnabled(bool(txt_delim.text()))

    txt_delim.textChanged.connect(_validate)

    apply_dialog_window_hints(dlg, min_width=420)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return {
            "delimiter": "",
            "keep_original": default_keep_original,
            "mode": default_mode,
            "ok": False,
        }

    raw_delim = txt_delim.text()

    # Interpret simple escapes like "\t"
    delimiter = "\t" if raw_delim == r"\t" else raw_delim

    return {
        "delimiter": delimiter,
        "keep_original": chk_keep.isChecked(),
        "mode": "last" if rb_last.isChecked() else "first",
        "ok": True,
    }


# ----------------------------------------------------------------------
# Merge columns
# ----------------------------------------------------------------------


def prompt_merge_columns(
    parent: QWidget,
    *,
    title: str,
    all_columns: list[str],
    default_columns: list[str],
    default_delimiter: str,
    default_new_name: str,
    default_keep_original: bool,
) -> MergeColumnsResult:
    """Prompt the user to select and merge multiple columns."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    root = QVBoxLayout(dlg)

    # --------------------------------------------------
    # Instruction
    # --------------------------------------------------

    root.addWidget(
        QLabel(
            QCoreApplication.translate(
                "QtDialogService",
                "Select columns to merge and define their order:",
            ),
            dlg,
        )
    )

    # --------------------------------------------------
    # Lists layout
    # --------------------------------------------------

    lists_row = QHBoxLayout()

    # -------- Available columns --------

    col_available = QVBoxLayout()
    col_available.addWidget(
        QLabel(
            QCoreApplication.translate("QtDialogService", "Available columns"),
            dlg,
        )
    )

    lst_available = QListWidget(dlg)
    lst_available.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    col_available.addWidget(lst_available)

    # -------- Buttons between lists --------

    col_transfer = QVBoxLayout()
    col_transfer.addStretch(1)

    btn_add = QPushButton(
        QCoreApplication.translate("QtDialogService", ">"),
        dlg,
    )
    btn_remove = QPushButton(
        QCoreApplication.translate("QtDialogService", "<"),
        dlg,
    )

    col_transfer.addWidget(btn_add)
    col_transfer.addWidget(btn_remove)
    col_transfer.addStretch(1)

    # -------- Selected columns --------

    col_selected = QVBoxLayout()
    col_selected.addWidget(
        QLabel(
            QCoreApplication.translate("QtDialogService", "Selected columns (merge order)"),
            dlg,
        )
    )

    lst_selected = QListWidget(dlg)
    lst_selected.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    col_selected.addWidget(lst_selected)

    # -------- Reorder buttons --------

    row_move = QHBoxLayout()
    btn_up = QPushButton(
        QCoreApplication.translate("QtDialogService", "Move up"),
        dlg,
    )
    btn_down = QPushButton(
        QCoreApplication.translate("QtDialogService", "Move down"),
        dlg,
    )
    row_move.addWidget(btn_up)
    row_move.addWidget(btn_down)
    col_selected.addLayout(row_move)

    # -------- Assemble lists row --------

    lists_row.addLayout(col_available, 3)
    lists_row.addLayout(col_transfer, 1)
    lists_row.addLayout(col_selected, 3)

    root.addLayout(lists_row)

    # --------------------------------------------------
    # Populate lists
    # --------------------------------------------------

    default_set = set(default_columns)

    for col in all_columns:
        item = QListWidgetItem(col)
        if col in default_set:
            lst_selected.addItem(item)
        else:
            lst_available.addItem(item)

    # --------------------------------------------------
    # Delimiter
    # --------------------------------------------------

    row_delim = QHBoxLayout()
    row_delim.addWidget(
        QLabel(
            QCoreApplication.translate("QtDialogService", "Delimiter:"),
            dlg,
        )
    )
    txt_delim = QLineEdit(dlg)
    txt_delim.setText(default_delimiter)
    row_delim.addWidget(txt_delim)
    root.addLayout(row_delim)

    # --------------------------------------------------
    # New column name
    # --------------------------------------------------

    row_name = QHBoxLayout()
    row_name.addWidget(
        QLabel(
            QCoreApplication.translate("QtDialogService", "New column name:"),
            dlg,
        )
    )
    txt_name = QLineEdit(dlg)
    txt_name.setText(default_new_name)
    row_name.addWidget(txt_name)
    root.addLayout(row_name)

    # --------------------------------------------------
    # Keep original columns
    # --------------------------------------------------

    chk_keep = QCheckBox(
        QCoreApplication.translate("QtDialogService", "Keep original columns"),
        dlg,
    )
    chk_keep.setChecked(default_keep_original)
    root.addWidget(chk_keep)

    # --------------------------------------------------
    # Buttons
    # --------------------------------------------------

    buttons = QDialogButtonBox(parent=dlg)
    buttons.addButton(QDialogButtonBox.StandardButton.Ok)
    buttons.addButton(QDialogButtonBox.StandardButton.Cancel)

    localize_dialog_buttons(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    root.addWidget(buttons)

    btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _selected_columns() -> list[str]:
        cols: list[str] = []
        for i in range(lst_selected.count()):
            item_x = lst_selected.item(i)
            if item_x is not None:
                cols.append(item_x.text())
        return cols

    def _update_default_name() -> None:
        if not txt_name.isModified():
            cols = _selected_columns()
            if cols:
                txt_name.setText("_".join(cols))

    def _validate() -> None:
        if btn_ok is None:
            return
        btn_ok.setEnabled(lst_selected.count() >= 2 and bool(txt_name.text().strip()) and bool(txt_delim.text()))

    def _add_column() -> None:
        item_x = lst_available.currentItem()
        if item_x is None:
            return
        lst_available.takeItem(lst_available.currentRow())
        lst_selected.addItem(item_x)
        lst_selected.setCurrentItem(item_x)
        _update_default_name()
        _validate()

    def _remove_column() -> None:
        item_x = lst_selected.currentItem()
        if item_x is None:
            return
        lst_selected.takeItem(lst_selected.currentRow())
        lst_available.addItem(item_x)
        lst_available.setCurrentItem(item_x)
        _update_default_name()
        _validate()

    def _move_up() -> None:
        row = lst_selected.currentRow()
        if row <= 0:
            return
        item_x = lst_selected.takeItem(row)
        lst_selected.insertItem(row - 1, item_x)
        lst_selected.setCurrentRow(row - 1)
        _update_default_name()

    def _move_down() -> None:
        row = lst_selected.currentRow()
        if row < 0 or row >= lst_selected.count() - 1:
            return
        item_x = lst_selected.takeItem(row)
        lst_selected.insertItem(row + 1, item_x)
        lst_selected.setCurrentRow(row + 1)
        _update_default_name()

    # --------------------------------------------------
    # Signals
    # --------------------------------------------------

    btn_add.clicked.connect(_add_column)
    btn_remove.clicked.connect(_remove_column)
    btn_up.clicked.connect(_move_up)
    btn_down.clicked.connect(_move_down)

    txt_name.textChanged.connect(_validate)
    txt_delim.textChanged.connect(_validate)

    _validate()

    apply_dialog_window_hints(dlg, min_width=600)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return {
            "columns": [],
            "delimiter": default_delimiter,
            "new_name": default_new_name,
            "keep_original": default_keep_original,
            "ok": False,
        }

    return {
        "columns": _selected_columns(),
        "delimiter": txt_delim.text(),
        "new_name": txt_name.text().strip(),
        "keep_original": chk_keep.isChecked(),
        "ok": True,
    }
