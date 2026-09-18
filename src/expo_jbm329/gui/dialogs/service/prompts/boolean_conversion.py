"""Boolean conversion prompt."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP
from PyQt6.QtWidgets import (
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
from expo_jbm329.utils.i18n_utils import tr

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import (
        BooleanConversionResult,
    )

# ======================================================================
# i18n keys
# ======================================================================

TR_LABEL_TRUE_VALUES = QT_TR_NOOP("Values interpreted as True (comma-separated):")
TR_LABEL_FALSE_VALUES = QT_TR_NOOP("Values interpreted as False (comma-separated):")
TR_HELP_TEXT = QT_TR_NOOP(
    "Enter values exactly as they appear in the data. "
    "Comparison is case-insensitive\nand ignores surrounding whitespace.\n"
)


# ======================================================================
# Public API
# ======================================================================

def prompt_boolean_conversion(
    parent: QWidget,
    *,
    title: str,
    default_true_values: list[str],
    default_false_values: list[str],
) -> BooleanConversionResult:
    """Show a dialog for boolean conversion.

    The user specifies which values should be interpreted as True or False.
    The dialog always returns a BooleanConversionResult and never None.
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    layout = QVBoxLayout(dlg)

    # --------------------------------------------------
    # Help text
    # --------------------------------------------------

    layout.addWidget(QLabel(tr("BooleanConversion", TR_HELP_TEXT), dlg))

    # --------------------------------------------------
    # True values
    # --------------------------------------------------

    layout.addWidget(QLabel(tr("BooleanConversion", TR_LABEL_TRUE_VALUES), dlg))

    edit_true = QLineEdit(dlg)
    edit_true.setText(", ".join(default_true_values))
    layout.addWidget(edit_true)

    # --------------------------------------------------
    # False values
    # --------------------------------------------------

    layout.addWidget(QLabel(tr("BooleanConversion", TR_LABEL_FALSE_VALUES), dlg))

    edit_false = QLineEdit(dlg)
    edit_false.setText(", ".join(default_false_values))
    layout.addWidget(edit_false)

    # --------------------------------------------------
    # Buttons
    # --------------------------------------------------

    buttons = QDialogButtonBox(parent=dlg)
    buttons.addButton(QDialogButtonBox.StandardButton.Ok)
    buttons.addButton(QDialogButtonBox.StandardButton.Cancel)

    localize_dialog_buttons(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)

    apply_dialog_window_hints(dlg, min_width=420)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return {
            "true_values": list(default_true_values),
            "false_values": list(default_false_values),
            "ok": False,
        }

    def _parse_values(text: str) -> list[str]:
        return [
            v.strip()
            for v in text.split(",")
            if v.strip()
        ]

    true_values = _parse_values(edit_true.text())
    false_values = _parse_values(edit_false.text())

    return {
        "true_values": true_values,
        "false_values": false_values,
        "ok": True,
    }
