"""Dialogs for category conversion."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
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
        CategoryConversionResult,
    )
    from expo_jbm329.services.data_operations.category_orders import CategoryOrderKey


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------
def prompt_category_conversion(
    parent: QWidget,
    *,
    title: str,
    default_order: CategoryOrderKey,
    default_ordered: bool,
    default_strict: bool,
) -> CategoryConversionResult:
    """Prompt the user for category conversion settings."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    root = QVBoxLayout(dlg)

    # --------------------------------------------------
    # Order selection
    # --------------------------------------------------

    root.addWidget(QLabel(QCoreApplication.translate("CategoryConversion", "Category order:"), dlg))

    rb_alpha = QRadioButton(QCoreApplication.translate("CategoryConversion", "Alphabetically"), dlg)
    rb_freq = QRadioButton(QCoreApplication.translate("CategoryConversion", "By frequency"), dlg)
    rb_preserve = QRadioButton(QCoreApplication.translate("CategoryConversion", "Preserve existing order"), dlg)

    grp = QButtonGroup(dlg)
    grp.addButton(rb_alpha)
    grp.addButton(rb_freq)
    grp.addButton(rb_preserve)

    if default_order == "freq":
        rb_freq.setChecked(True)
    elif default_order == "preserve":
        rb_preserve.setChecked(True)
    else:
        rb_alpha.setChecked(True)

    row_order = QHBoxLayout()
    row_order.addWidget(rb_alpha)
    row_order.addWidget(rb_freq)
    row_order.addWidget(rb_preserve)
    row_order.addStretch(1)
    root.addLayout(row_order)

    # --------------------------------------------------
    # Options
    # --------------------------------------------------

    chk_ordered = QCheckBox(
        QCoreApplication.translate("CategoryConversion", "Categories should be ordered"),
        dlg,
    )
    chk_ordered.setChecked(default_ordered)
    root.addWidget(chk_ordered)

    chk_strict = QCheckBox(
        QCoreApplication.translate("CategoryConversion", "Strict mode (unknown values → NA)"),
        dlg,
    )
    chk_strict.setChecked(default_strict)
    root.addWidget(chk_strict)

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

    apply_dialog_window_hints(dlg, min_width=500)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return {
            "order": default_order,
            "ordered": default_ordered,
            "strict": default_strict,
            "ok": False,
        }
    order: CategoryOrderKey
    if rb_freq.isChecked():
        order = "freq"
    elif rb_preserve.isChecked():
        order = "preserve"
    else:
        order = "alpha"

    return {
        "order": order,
        "ordered": chk_ordered.isChecked(),
        "strict": chk_strict.isChecked(),
        "ok": True,
    }
