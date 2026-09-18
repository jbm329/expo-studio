"""Prompt the user for a comparison operator and value and between-range."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
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
# operator labels
# ----------------------------------------------------------------------

_OPERATOR_LABELS = {
    ">": QCoreApplication.translate("QtDialogService", "Greater than"),
    ">=": QCoreApplication.translate("QtDialogService", "Greater than or equal to"),
    "<": QCoreApplication.translate("QtDialogService", "Less than"),
    "<=": QCoreApplication.translate("QtDialogService", "Less than or equal to"),
    "==": QCoreApplication.translate("QtDialogService", "Equal to"),
    "!=": QCoreApplication.translate("QtDialogService", "Not equal to"),
}

# ----------------------------------------------------------------------
# prompt_compare
# ----------------------------------------------------------------------
def prompt_compare(
    parent: QWidget,
    *,
    title: str,
    label_op: str,
    label_value: str,
    default_op: str,
    default_value: object,
    semantics: SeriesSemantics,
) -> dict:
    """Prompt the user for a comparison operator and value."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    layout = QVBoxLayout(dlg)

    # Operator
    row_op = QHBoxLayout()
    row_op.addWidget(QLabel(label_op, dlg))

    cmb_op = QComboBox(dlg)

    for op, label in _OPERATOR_LABELS.items():
        # Visa endast texten
        cmb_op.addItem(label, userData=op)

    # Sätt default
    for i in range(cmb_op.count()):
        if cmb_op.itemData(i) == default_op:
            cmb_op.setCurrentIndex(i)
            break

    row_op.addWidget(cmb_op)
    layout.addLayout(row_op)

    # Value
    row_val = QHBoxLayout()
    row_val.addWidget(QLabel(label_value, dlg))

    editor: QWidget

    if semantics.semantic_dtype == "datetime":
        if semantics.is_date_only:
            edit = QDateEdit(dlg)
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
            if isinstance(default_value, datetime):
                edit.setDate(default_value.date())
        else:
            edit = QDateTimeEdit(dlg)
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
            if isinstance(default_value, datetime):
                edit.setDateTime(default_value)
        editor = edit

    elif semantics.semantic_dtype in ("int", "float"):
        if semantics.is_integer_like:
            edit = QSpinBox(dlg)
            edit.setMinimum(-2_147_483_648)
            edit.setMaximum(2_147_483_647)
            if isinstance(default_value, (int, float)):
                edit.setValue(int(default_value))
        else:
            edit = QDoubleSpinBox(dlg)
            edit.setDecimals(6)
            edit.setMinimum(-1e12)
            edit.setMaximum(1e12)
            if isinstance(default_value, (int, float)):
                edit.setValue(float(default_value))
        editor = edit

    else:
        return {"ok": False}

    row_val.addWidget(editor)
    layout.addLayout(row_val)

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
        return {"ok": False}

    # Read value
    if isinstance(editor, QDateEdit):
        d = editor.date()
        value = datetime(d.year(), d.month(), d.day())
    elif isinstance(editor, QDateTimeEdit):
        value = editor.dateTime().toPyDateTime()
    else:
        value = editor.value()

    return {
        "op": cmb_op.currentData(),
        "value": value,
        "ok": True,
    }

# ----------------------------------------------------------------------
# prompt_between
# ----------------------------------------------------------------------

def prompt_between(
    parent: QWidget,
    *,
    title: str,
    label_low: str,
    label_high: str,
    default_low: object,
    default_high: object,
    inclusive_default: str,
    semantics: SeriesSemantics,
) -> dict:
    """Prompt the user for a between-range."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    layout = QVBoxLayout(dlg)

    # Inclusivity
    incl_map = {
        QCoreApplication.translate("QtDialogService", "Both limits"): "both",
        QCoreApplication.translate("QtDialogService", "Only lower limit"): "left",
        QCoreApplication.translate("QtDialogService", "Only upper limit"): "right",
        QCoreApplication.translate("QtDialogService", "No limits"): "neither",
    }
    rev_map = {v: k for k, v in incl_map.items()}

    row_incl = QHBoxLayout()
    row_incl.addWidget(QLabel(
        QCoreApplication.translate("QtDialogService", "Inclusivity:"), dlg
    ))
    cmb_incl = QComboBox(dlg)
    cmb_incl.addItems(incl_map.keys())
    if inclusive_default in rev_map:
        cmb_incl.setCurrentText(rev_map[inclusive_default])
    row_incl.addWidget(cmb_incl)
    layout.addLayout(row_incl)

    # Editors
    def _make_editor(default: object) -> QWidget:
        if semantics.semantic_dtype == "datetime":
            if semantics.is_date_only:
                edit = QDateEdit(dlg)
                edit.setCalendarPopup(True)
                edit.setDisplayFormat("yyyy-MM-dd")
                if isinstance(default, datetime):
                    edit.setDate(default.date())
                return edit
            edit = QDateTimeEdit(dlg)
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
            if isinstance(default, datetime):
                edit.setDateTime(default)
            return edit

        if semantics.semantic_dtype in ("int", "float"):
            if semantics.is_integer_like:
                edit = QSpinBox(dlg)
                edit.setMinimum(-2_147_483_648)
                edit.setMaximum(2_147_483_647)
                if isinstance(default, (int, float)):
                    edit.setValue(int(default))
                return edit
            edit = QDoubleSpinBox(dlg)
            edit.setDecimals(6)
            edit.setMinimum(-1e12)
            edit.setMaximum(1e12)
            if isinstance(default, (int, float)):
                edit.setValue(float(default))
            return edit

        raise RuntimeError("Unsupported semantics")

    # Low
    row_low = QHBoxLayout()
    row_low.addWidget(QLabel(label_low, dlg))
    low_edit = _make_editor(default_low)
    row_low.addWidget(low_edit)
    layout.addLayout(row_low)

    # High
    row_high = QHBoxLayout()
    row_high.addWidget(QLabel(label_high, dlg))
    high_edit = _make_editor(default_high)
    row_high.addWidget(high_edit)
    layout.addLayout(row_high)

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
        return {"ok": False}

    def _read(edit: QWidget) -> object:
        if isinstance(edit, QDateEdit):
            d = edit.date()
            return datetime(d.year(), d.month(), d.day())
        if isinstance(edit, QDateTimeEdit):
            return edit.dateTime().toPyDateTime()
        return edit.value()

    return {
        "low": _read(low_edit),
        "high": _read(high_edit),
        "inclusive": incl_map[cmb_incl.currentText()],
        "ok": True,
    }
