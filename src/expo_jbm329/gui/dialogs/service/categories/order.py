"""Dialog to set an explicit order for categories."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TRANSLATE_NOOP
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
from expo_jbm329.utils.i18n_utils import translate

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import (
        CategoryOrderResult,
    )


# ------------------------------------------------------------------
# i18n
# ------------------------------------------------------------------
TR_ORDER_CATEGORIES = QT_TRANSLATE_NOOP("CategorySetOrder", "Order categories (drag and drop):")
TR_UP = QT_TRANSLATE_NOOP("CategorySetOrder", "Up")
TR_DOWN = QT_TRANSLATE_NOOP("CategorySetOrder", "Down")
TR_SORT_ALPHABETICALLY = QT_TRANSLATE_NOOP("CategorySetOrder", "Sort alphabetically")
TR_RESTORE_ORDER = QT_TRANSLATE_NOOP("CategorySetOrder", "Restore original order")
TR_ORDERED_CATEGORY = QT_TRANSLATE_NOOP("CategorySetOrder", "Ordered category")
TR_STRICT_MODE = QT_TRANSLATE_NOOP("CategorySetOrder", "Strict mode (unknown values → NA)")
TR_ADD_MISSING_LAST = QT_TRANSLATE_NOOP("CategorySetOrder", "Add missing values last")


def _tr(text: str) -> str:
    """Translate a message in this module's context."""
    return translate("CategorySetOrder", text)


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
            _tr(TR_ORDER_CATEGORIES),
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

    btn_up = QPushButton(_tr(TR_UP), dlg)
    btn_down = QPushButton(_tr(TR_DOWN), dlg)
    btn_alpha = QPushButton(_tr(TR_SORT_ALPHABETICALLY), dlg)
    btn_reset = QPushButton(_tr(TR_RESTORE_ORDER), dlg)

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
        _tr(TR_ORDERED_CATEGORY),
        dlg,
    )
    chk_ordered.setChecked(default_ordered)
    root.addWidget(chk_ordered)

    chk_strict = QCheckBox(
        _tr(TR_STRICT_MODE),
        dlg,
    )
    chk_strict.setChecked(default_strict)
    root.addWidget(chk_strict)

    chk_append = QCheckBox(
        _tr(TR_ADD_MISSING_LAST),
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
