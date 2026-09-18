"""Dialog to set an explicit order for categories."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import (
    localize_dialog_buttons,
)
from expo_jbm329.gui.dialogs.service.common.window_hints import (
    apply_dialog_window_hints,
)

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import (
        CategoryOrderResult,
    )


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------
def prompt_category_set_order(
    parent: QWidget,
    *,
    title: str,
    default_order_list: list[str],
    default_ordered: bool,
    default_strict: bool,
    default_append_missing_tail: bool,
) -> CategoryOrderResult:
    """Prompt the user to set an explicit order for categories."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    root = QVBoxLayout(dlg)

    # --------------------------------------------------
    # Instruction
    # --------------------------------------------------

    root.addWidget(
        QLabel(
            QCoreApplication.translate("CategorySetOrder", "Order categories (drag and drop):"),
            dlg,
        )
    )

    # --------------------------------------------------
    # Reorder list
    # --------------------------------------------------

    lst = QListWidget(dlg)
    lst.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    for value in default_order_list:
        QListWidgetItem(str(value), lst)

    root.addWidget(lst)

    # --------------------------------------------------
    # Helper buttons
    # --------------------------------------------------

    row_btns = QHBoxLayout()

    btn_up = QPushButton(QCoreApplication.translate("CategorySetOrder", "Up"), dlg)
    btn_down = QPushButton(QCoreApplication.translate("CategorySetOrder", "Down"), dlg)
    btn_alpha = QPushButton(QCoreApplication.translate("CategorySetOrder", "Sort alphabetically"), dlg)
    btn_reset = QPushButton(QCoreApplication.translate("CategorySetOrder", "Restore original order"), dlg)

    row_btns.addWidget(btn_up)
    row_btns.addWidget(btn_down)
    row_btns.addWidget(btn_alpha)
    row_btns.addWidget(btn_reset)
    row_btns.addStretch(1)

    root.addLayout(row_btns)

    def _move_selected(delta: int) -> None:
        row = lst.currentRow()
        if row < 0:
            return
        new_row = max(0, min(lst.count() - 1, row + delta))
        if new_row == row:
            return
        item_x = lst.takeItem(row)
        lst.insertItem(new_row, item_x)
        lst.setCurrentRow(new_row)

    btn_up.clicked.connect(lambda: _move_selected(-1))
    btn_down.clicked.connect(lambda: _move_selected(+1))
    btn_alpha.clicked.connect(lst.sortItems)

    def _reset() -> None:
        lst.clear()
        for value_x in default_order_list:
            QListWidgetItem(str(value_x), lst)

    btn_reset.clicked.connect(_reset)

    # --------------------------------------------------
    # Options
    # --------------------------------------------------

    chk_ordered = QCheckBox(
        QCoreApplication.translate("CategorySetOrder", "Ordered category"),
        dlg,
    )
    chk_ordered.setChecked(default_ordered)
    root.addWidget(chk_ordered)

    chk_strict = QCheckBox(
        QCoreApplication.translate("CategorySetOrder", "Strict mode (unknown values → NA)"),
        dlg,
    )
    chk_strict.setChecked(default_strict)
    root.addWidget(chk_strict)

    chk_append = QCheckBox(
        QCoreApplication.translate("CategorySetOrder", "Add missing values last"),
        dlg,
    )
    chk_append.setChecked(default_append_missing_tail)
    root.addWidget(chk_append)

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

    apply_dialog_window_hints(dlg, min_width=540)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return {
            "order_list": list(default_order_list),
            "ordered": default_ordered,
            "strict": default_strict,
            "append_missing_tail": default_append_missing_tail,
            "ok": False,
        }

    order_list: list[str] = []

    for i in range(lst.count()):
        item = lst.item(i)
        if item is not None:
            order_list.append(item.text())

    return {
        "order_list": order_list,
        "ordered": chk_ordered.isChecked(),
        "strict": chk_strict.isChecked(),
        "append_missing_tail": chk_append.isChecked(),
        "ok": True,
    }
