"""Prompt the user for a single numeric or datetime value."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QLabel,
    QSpinBox,
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
    from expo_jbm329.services.data_profile.semantics import SeriesSemantics


# ----------------------------------------------------------------------
# prompt_value
# ----------------------------------------------------------------------
def prompt_value(
    parent: QWidget,
    *,
    title: str,
    label: str,
    default: object,
    semantics: SeriesSemantics,
) -> tuple[object | None, bool]:
    """Prompt the user for a single value.

    Widget selection is based solely on SeriesSemantics:
    - datetime → date or datetime widget
    - numeric → int or float widget
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel(label, dlg))

    editor: QDateEdit | QDateTimeEdit | QSpinBox | QDoubleSpinBox

    # --------------------------------------------------
    # Datetime
    # --------------------------------------------------
    if semantics.semantic_dtype == "datetime":
        if semantics.is_date_only:
            date_edit = QDateEdit(dlg)
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")
            if isinstance(default, datetime):
                date_edit.setDate(default.date())
            editor = date_edit
        else:
            datetime_edit = QDateTimeEdit(dlg)
            datetime_edit.setCalendarPopup(True)
            datetime_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
            if isinstance(default, datetime):
                datetime_edit.setDateTime(default)
            editor = datetime_edit

    # --------------------------------------------------
    # Numeric
    # --------------------------------------------------
    elif semantics.semantic_dtype in ("int", "float"):
        if semantics.is_integer_like:
            int_edit = QSpinBox(dlg)
            int_edit.setMinimum(-2_147_483_648)
            int_edit.setMaximum(2_147_483_647)
            if isinstance(default, (int, float)):
                int_edit.setValue(int(default))
            editor = int_edit
        else:
            float_edit = QDoubleSpinBox(dlg)
            float_edit.setDecimals(6)
            float_edit.setMinimum(-1e12)
            float_edit.setMaximum(1e12)
            if isinstance(default, (int, float)):
                float_edit.setValue(float(default))
            editor = float_edit

    else:
        # Unsupported semantic type
        return None, False

    layout.addWidget(editor)

    buttons = QDialogButtonBox(parent=dlg)
    buttons.addButton(QDialogButtonBox.StandardButton.Ok)
    buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
    localize_dialog_buttons(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)

    apply_dialog_window_hints(dlg, min_width=300)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return None, False

    # --------------------------------------------------
    # Read value
    # --------------------------------------------------
    if isinstance(editor, QDateEdit):
        d = editor.date()
        return datetime(d.year(), d.month(), d.day()), True  # noqa: DTZ001 - calendar-only dialog value

    if isinstance(editor, QDateTimeEdit):
        return editor.dateTime().toPyDateTime(), True

    if isinstance(editor, QSpinBox):
        return editor.value(), True

    return editor.value(), True
