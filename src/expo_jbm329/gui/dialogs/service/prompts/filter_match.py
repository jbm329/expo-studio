"""Prompt for substring filter options."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
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

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import (
        TextFilterMatchResult,
    )


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------
def prompt_filter_match(
    parent: QWidget,
    *,
    title: str,
    label: str,
    default_value: str,
    default_case_sensitive: bool = True,
) -> TextFilterMatchResult:
    """Prompt for substring filter options."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    layout = QVBoxLayout(dlg)

    layout.addWidget(QLabel(label, dlg))

    txt_value = QLineEdit(dlg)
    txt_value.setText(default_value)
    layout.addWidget(txt_value)

    chk_case = QCheckBox(
        QCoreApplication.translate("TextMatchFilter", "Case sensitive"),
        dlg,
    )
    chk_case.setChecked(default_case_sensitive)
    layout.addWidget(chk_case)

    buttons = QDialogButtonBox(parent=dlg)
    buttons.addButton(QDialogButtonBox.StandardButton.Ok)
    buttons.addButton(QDialogButtonBox.StandardButton.Cancel)

    localize_dialog_buttons(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)

    btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)

    def _validate() -> None:
        if btn_ok is not None:
            btn_ok.setEnabled(bool(txt_value.text().strip()))

    txt_value.textChanged.connect(_validate)
    _validate()

    apply_dialog_window_hints(dlg, min_width=400)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return {
            "value": default_value,
            "case_sensitive": default_case_sensitive,
            "ok": False,
        }

    return {
        "value": txt_value.text(),
        "case_sensitive": chk_case.isChecked(),
        "ok": True,
    }
