"""Datetime conversion prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QComboBox,
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
        DateTimeConversionResult,
        DateTimeTarget,
    )
    from expo_jbm329.services.data_operations.datetime_formats import DateFormatKey

# ======================================================================
# Public API
# ======================================================================


def prompt_datetime_conversion(
    parent: QWidget,
    *,
    title: str,
    default_format_key: DateFormatKey,
    default_target: DateTimeTarget,
) -> DateTimeConversionResult:
    """Show a dialog for datetime conversion.

    The user selects:
    - how the input data is formatted (format_key)
    - what the column should become (date or datetime)

    Returns a DateTimeConversionResult. Never returns None.
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    root = QVBoxLayout(dlg)

    # --------------------------------------------------
    # Format selection
    # --------------------------------------------------

    root.addWidget(QLabel(QCoreApplication.translate("DateTimeConversion", "Input format:"), dlg))

    cmb_format = QComboBox(dlg)

    format_options: list[tuple[DateFormatKey, str]] = [
        ("auto", QCoreApplication.translate("DateTimeConversion", "Auto-detect")),
        ("iso_date", QCoreApplication.translate("DateTimeConversion", "ISO date (2024-03-15)")),
        ("iso_datetime", QCoreApplication.translate("DateTimeConversion", "ISO datetime (2024-03-15 13:45:00)")),
        ("dmy_slash", QCoreApplication.translate("DateTimeConversion", "DD/MM/YYYY (15/03/2024)")),
        ("mdy_slash", QCoreApplication.translate("DateTimeConversion", "MM/DD/YYYY (03/15/2024)")),
        ("dmy_dot", QCoreApplication.translate("DateTimeConversion", "DD.MM.YYYY (15.03.2024)")),
        ("ymd_slash", QCoreApplication.translate("DateTimeConversion", "YYYY/MM/DD (2024/03/15)")),
        ("ymd_compact", QCoreApplication.translate("DateTimeConversion", "YYYYMMDD (20240315)")),
    ]

    for key, label in format_options:
        cmb_format.addItem(label, userData=key)

    # Set default format
    for i in range(cmb_format.count()):
        if cmb_format.itemData(i) == default_format_key:
            cmb_format.setCurrentIndex(i)
            break

    root.addWidget(cmb_format)

    # --------------------------------------------------
    # Target selection (date vs datetime)
    # --------------------------------------------------

    root.addWidget(QLabel(QCoreApplication.translate("DateTimeConversion", "Convert to:"), dlg))

    row_target = QHBoxLayout()

    rb_date = QRadioButton(QCoreApplication.translate("DateTimeConversion", "Date (drop time)"), dlg)
    rb_datetime = QRadioButton(QCoreApplication.translate("DateTimeConversion", "Datetime (keep time)"), dlg)

    if default_target == "date":
        rb_date.setChecked(True)
    else:
        rb_datetime.setChecked(True)

    row_target.addWidget(rb_date)
    row_target.addWidget(rb_datetime)

    root.addLayout(row_target)

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

    apply_dialog_window_hints(dlg, min_width=420)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return {
            "format_key": default_format_key,
            "target": default_target,
            "ok": False,
        }

    format_key: DateFormatKey = cmb_format.currentData()
    target: DateTimeTarget = "date" if rb_date.isChecked() else "datetime"

    return {
        "format_key": format_key,
        "target": target,
        "ok": True,
    }
