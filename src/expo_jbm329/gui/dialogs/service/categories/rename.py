"""Dialog to rename a category."""
from __future__ import annotations

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import (
    localize_dialog_buttons,
)
from expo_jbm329.gui.dialogs.service.common.window_hints import (
    apply_dialog_window_hints,
)
from expo_jbm329.gui.dialogs.service.dialog_service import (
    CategoryRenameResult,
)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------
def prompt_category_rename(
    parent: QWidget,
    *,
    title: str,
    categories: list[str],
    default_old_value: str,
    default_new_value: str,
) -> CategoryRenameResult:
    """Prompt the user to rename a category."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    root = QVBoxLayout(dlg)

    # --------------------------------------------------
    # Old value (dropdown)
    # --------------------------------------------------

    lbl_old = QLabel(QCoreApplication.translate("CategoryRename", "Category:"), dlg)
    cmb_old = QComboBox(dlg)
    cmb_old.addItems(categories)

    if default_old_value in categories:
        cmb_old.setCurrentText(default_old_value)

    row_old = QHBoxLayout()
    row_old.addWidget(lbl_old)
    row_old.addWidget(cmb_old, stretch=1)
    root.addLayout(row_old)

    # --------------------------------------------------
    # New value
    # --------------------------------------------------

    lbl_new = QLabel(QCoreApplication.translate("CategoryRename", "New name:"), dlg)
    txt_new = QLineEdit(dlg)
    txt_new.setText(default_new_value)

    row_new = QHBoxLayout()
    row_new.addWidget(lbl_new)
    row_new.addWidget(txt_new, stretch=1)
    root.addLayout(row_new)

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

    # Disable OK if new name is empty
    btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)

    def _validate() -> None:
        if btn_ok is not None:
            btn_ok.setEnabled(bool(txt_new.text().strip()))

    txt_new.textChanged.connect(_validate)
    _validate()

    apply_dialog_window_hints(dlg, min_width=380)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return {
            "old": default_old_value,
            "new": default_new_value,
            "ok": False,
        }

    return {
        "old": cmb_old.currentText().strip(),
        "new": txt_new.text().strip(),
        "ok": True,
    }
