"""Prompt the user for a comparison operator and value and between-range."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TRANSLATE_NOOP
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
from expo_jbm329.utils.i18n_utils import translate

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import BetweenResult, CompareResult
    from expo_jbm329.services.data_profile.semantics import SeriesSemantics

# ----------------------------------------------------------------------
# operator labels
# ----------------------------------------------------------------------

TR_GREATER_THAN = QT_TRANSLATE_NOOP("QtDialogService", "Greater than")
TR_GREATER_OR_EQUAL = QT_TRANSLATE_NOOP("QtDialogService", "Greater than or equal to")
TR_LESS_THAN = QT_TRANSLATE_NOOP("QtDialogService", "Less than")
TR_LESS_OR_EQUAL = QT_TRANSLATE_NOOP("QtDialogService", "Less than or equal to")
TR_EQUAL = QT_TRANSLATE_NOOP("QtDialogService", "Equal to")
TR_NOT_EQUAL = QT_TRANSLATE_NOOP("QtDialogService", "Not equal to")
TR_BOTH_LIMITS = QT_TRANSLATE_NOOP("QtDialogService", "Both limits")
TR_LOWER_LIMIT = QT_TRANSLATE_NOOP("QtDialogService", "Only lower limit")
TR_UPPER_LIMIT = QT_TRANSLATE_NOOP("QtDialogService", "Only upper limit")
TR_NO_LIMITS = QT_TRANSLATE_NOOP("QtDialogService", "No limits")
TR_INCLUSIVITY = QT_TRANSLATE_NOOP("QtDialogService", "Inclusivity:")


def _tr(text: str) -> str:
    """Translate a message in this module's context."""
    return translate("QtDialogService", text)


_OPERATOR_LABELS = {
    ">": _tr(TR_GREATER_THAN),
    ">=": _tr(TR_GREATER_OR_EQUAL),
    "<": _tr(TR_LESS_THAN),
    "<=": _tr(TR_LESS_OR_EQUAL),
    "==": _tr(TR_EQUAL),
    "!=": _tr(TR_NOT_EQUAL),
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
) -> CompareResult:
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

    editor: QDateEdit | QDateTimeEdit | QSpinBox | QDoubleSpinBox

    if semantics.semantic_dtype == "datetime":
        if semantics.is_date_only:
            date_edit = QDateEdit(dlg)
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")
            if isinstance(default_value, datetime):
                date_edit.setDate(default_value.date())
            editor = date_edit
        else:
            datetime_edit = QDateTimeEdit(dlg)
            datetime_edit.setCalendarPopup(True)
            datetime_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
            if isinstance(default_value, datetime):
                datetime_edit.setDateTime(default_value)
            editor = datetime_edit

    elif semantics.semantic_dtype in ("int", "float"):
        if semantics.is_integer_like:
            int_edit = QSpinBox(dlg)
            int_edit.setMinimum(-2_147_483_648)
            int_edit.setMaximum(2_147_483_647)
            if isinstance(default_value, (int, float)):
                int_edit.setValue(int(default_value))
            editor = int_edit
        else:
            float_edit = QDoubleSpinBox(dlg)
            float_edit.setDecimals(6)
            float_edit.setMinimum(-1e12)
            float_edit.setMaximum(1e12)
            if isinstance(default_value, (int, float)):
                float_edit.setValue(float(default_value))
            editor = float_edit

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
    value: object
    if isinstance(editor, QDateEdit):
        d = editor.date()
        value = datetime(d.year(), d.month(), d.day())  # noqa: DTZ001 - calendar-only dialog value
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
) -> BetweenResult:
    """Prompt the user for a between-range."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    layout = QVBoxLayout(dlg)

    # Inclusivity
    incl_map: dict[str, str] = {
        _tr(TR_BOTH_LIMITS): "both",
        _tr(TR_LOWER_LIMIT): "left",
        _tr(TR_UPPER_LIMIT): "right",
        _tr(TR_NO_LIMITS): "neither",
    }
    rev_map = {v: k for k, v in incl_map.items()}

    row_incl = QHBoxLayout()
    row_incl.addWidget(QLabel(_tr(TR_INCLUSIVITY), dlg))
    cmb_incl = QComboBox(dlg)
    cmb_incl.addItems(incl_map.keys())
    if inclusive_default in rev_map:
        cmb_incl.setCurrentText(rev_map[inclusive_default])
    row_incl.addWidget(cmb_incl)
    layout.addLayout(row_incl)

    # Editors
    def _make_editor(default: object) -> QDateEdit | QDateTimeEdit | QSpinBox | QDoubleSpinBox:
        if semantics.semantic_dtype == "datetime":
            if semantics.is_date_only:
                date_edit = QDateEdit(dlg)
                date_edit.setCalendarPopup(True)
                date_edit.setDisplayFormat("yyyy-MM-dd")
                if isinstance(default, datetime):
                    date_edit.setDate(default.date())
                return date_edit
            datetime_edit = QDateTimeEdit(dlg)
            datetime_edit.setCalendarPopup(True)
            datetime_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
            if isinstance(default, datetime):
                datetime_edit.setDateTime(default)
            return datetime_edit

        if semantics.semantic_dtype in ("int", "float"):
            if semantics.is_integer_like:
                int_edit = QSpinBox(dlg)
                int_edit.setMinimum(-2_147_483_648)
                int_edit.setMaximum(2_147_483_647)
                if isinstance(default, (int, float)):
                    int_edit.setValue(int(default))
                return int_edit
            float_edit = QDoubleSpinBox(dlg)
            float_edit.setDecimals(6)
            float_edit.setMinimum(-1e12)
            float_edit.setMaximum(1e12)
            if isinstance(default, (int, float)):
                float_edit.setValue(float(default))
            return float_edit

        msg = "Unsupported semantics"
        raise RuntimeError(msg)

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

    def _read(edit: QDateEdit | QDateTimeEdit | QSpinBox | QDoubleSpinBox) -> object:
        if isinstance(edit, QDateEdit):
            d = edit.date()
            return datetime(d.year(), d.month(), d.day())  # noqa: DTZ001 - calendar-only dialog value
        if isinstance(edit, QDateTimeEdit):
            return edit.dateTime().toPyDateTime()
        return edit.value()

    return {
        "low": _read(low_edit),
        "high": _read(high_edit),
        "inclusive": incl_map[cmb_incl.currentText()],
        "ok": True,
    }
