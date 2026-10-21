"""Datetime conversion prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TRANSLATE_NOOP
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
from expo_jbm329.utils.i18n_utils import translate

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import (
        DateTimeConversionResult,
        DateTimeTarget,
    )
    from expo_jbm329.services.data_operations.datetime_formats import DateFormatKey

# ======================================================================
# i18n
# ======================================================================


TR_INPUT_FORMAT = QT_TRANSLATE_NOOP("DateTimeConversion", "Input format:")
TR_AUTO_DETECT = QT_TRANSLATE_NOOP("DateTimeConversion", "Auto-detect")
TR_ISO_DATE = QT_TRANSLATE_NOOP("DateTimeConversion", "ISO date (2024-03-15)")
TR_ISO_DATETIME = QT_TRANSLATE_NOOP("DateTimeConversion", "ISO datetime (2024-03-15 13:45:00)")
TR_DMY_SLASH = QT_TRANSLATE_NOOP("DateTimeConversion", "DD/MM/YYYY (15/03/2024)")
TR_MDY_SLASH = QT_TRANSLATE_NOOP("DateTimeConversion", "MM/DD/YYYY (03/15/2024)")
TR_DMY_DOT = QT_TRANSLATE_NOOP("DateTimeConversion", "DD.MM.YYYY (15.03.2024)")
TR_YMD_SLASH = QT_TRANSLATE_NOOP("DateTimeConversion", "YYYY/MM/DD (2024/03/15)")
TR_YMD_COMPACT = QT_TRANSLATE_NOOP("DateTimeConversion", "YYYYMMDD (20240315)")
TR_CONVERT_TO = QT_TRANSLATE_NOOP("DateTimeConversion", "Convert to:")
TR_DATE = QT_TRANSLATE_NOOP("DateTimeConversion", "Date (drop time)")
TR_DATETIME = QT_TRANSLATE_NOOP("DateTimeConversion", "Datetime (keep time)")


def _tr(text: str) -> str:
    """Translate a message in this module's context."""
    return translate("DateTimeConversion", text)


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

    root.addWidget(QLabel(_tr(TR_INPUT_FORMAT), dlg))

    cmb_format = QComboBox(dlg)

    format_options: list[tuple[DateFormatKey, str]] = [
        ("auto", _tr(TR_AUTO_DETECT)),
        ("iso_date", _tr(TR_ISO_DATE)),
        ("iso_datetime", _tr(TR_ISO_DATETIME)),
        ("dmy_slash", _tr(TR_DMY_SLASH)),
        ("mdy_slash", _tr(TR_MDY_SLASH)),
        ("dmy_dot", _tr(TR_DMY_DOT)),
        ("ymd_slash", _tr(TR_YMD_SLASH)),
        ("ymd_compact", _tr(TR_YMD_COMPACT)),
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

    root.addWidget(QLabel(_tr(TR_CONVERT_TO), dlg))

    row_target = QHBoxLayout()

    rb_date = QRadioButton(_tr(TR_DATE), dlg)
    rb_datetime = QRadioButton(_tr(TR_DATETIME), dlg)

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
