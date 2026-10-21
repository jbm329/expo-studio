"""Dialog prompts for text-based input."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TRANSLATE_NOOP
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import localize_dialog_buttons
from expo_jbm329.gui.dialogs.service.common.window_hints import apply_dialog_window_hints
from expo_jbm329.utils.i18n_utils import translate, translate_fmt

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import (
        TextInsertResult,
        TextReplaceResult,
        ValueReplaceResult,
    )


# ----------------------------------------------------------------------
# i18n
# ----------------------------------------------------------------------
TR_TEXT_TO_REPLACE = QT_TRANSLATE_NOOP("QtDialogService", "Text/string to replace:")
TR_REPLACE_WITH = QT_TRANSLATE_NOOP("QtDialogService", "Replace with:")
TR_CASE_SENSITIVE = QT_TRANSLATE_NOOP("QtDialogService", "Case sensitive")
TR_TEXT_TO_INSERT = QT_TRANSLATE_NOOP("QtDialogService", "Text to insert:")
TR_POSITION = QT_TRANSLATE_NOOP("QtDialogService", "Position (0-based):")
TR_COLUMN = QT_TRANSLATE_NOOP("QtDialogService", "Column: {column}")
TR_CURRENT_VALUE = QT_TRANSLATE_NOOP("QtDialogService", "Current value: {current_value}")
TR_NEW_VALUE = QT_TRANSLATE_NOOP("QtDialogService", "New value:")
TR_REPLACE_ALL = QT_TRANSLATE_NOOP("QtDialogService", "Replace value in all cells")


def _tr(text: str) -> str:
    """Translate a message in this module's context."""
    return translate("QtDialogService", text)


def _tr_fmt(text: str, **kwargs: object) -> str:
    """Translate and format a message in this module's context."""
    return translate_fmt("QtDialogService", text, **kwargs)


# ----------------------------------------------------------------------
# prompt_text generic
# ----------------------------------------------------------------------
def prompt_text(
    parent: QWidget,
    *,
    title: str,
    label: str,
    default: str | None = None,
) -> tuple[str, bool]:
    """Prompt the user for a single line of text."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    root = QVBoxLayout(dlg)

    root.addWidget(QLabel(label, dlg))

    edit = QLineEdit(dlg)
    edit.setText(default or "")
    root.addWidget(edit)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        parent=dlg,
    )
    localize_dialog_buttons(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    root.addWidget(buttons)

    apply_dialog_window_hints(dlg, min_width=300)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    return (edit.text(), True) if ok else (default or "", False)


# ----------------------------------------------------------------------
# prompt_text_replace
# ----------------------------------------------------------------------


def prompt_text_replace(
    parent: QWidget,
    *,
    title: str,
    default_old: str = "",
    default_new: str = "",
    default_case: bool = True,
) -> TextReplaceResult:
    """Prompt the user for text replacement settings."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    root = QVBoxLayout(dlg)

    # Labels (normalize width)
    lbl_old = QLabel(_tr(TR_TEXT_TO_REPLACE), dlg)
    lbl_new = QLabel(_tr(TR_REPLACE_WITH), dlg)

    max_w = max(lbl_old.sizeHint().width(), lbl_new.sizeHint().width())
    lbl_old.setFixedWidth(max_w)
    lbl_new.setFixedWidth(max_w)

    # Old text
    row_old = QHBoxLayout()
    txt_old = QLineEdit(dlg)
    txt_old.setText(default_old)
    row_old.addWidget(lbl_old)
    row_old.addWidget(txt_old, stretch=1)
    root.addLayout(row_old)

    # New text
    row_new = QHBoxLayout()
    txt_new = QLineEdit(dlg)
    txt_new.setText(default_new)
    row_new.addWidget(lbl_new)
    row_new.addWidget(txt_new, stretch=1)
    root.addLayout(row_new)

    chk_case = QCheckBox(_tr(TR_CASE_SENSITIVE), dlg)
    chk_case.setChecked(default_case)
    root.addWidget(chk_case)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        parent=dlg,
    )
    localize_dialog_buttons(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    root.addWidget(buttons)

    apply_dialog_window_hints(dlg, min_width=500)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return {"old": "", "new": "", "case": default_case, "ok": False}

    return {
        "old": txt_old.text(),
        "new": txt_new.text(),
        "case": chk_case.isChecked(),
        "ok": True,
    }


# ----------------------------------------------------------------------
# prompt_text_insert
# ----------------------------------------------------------------------


def prompt_text_insert(
    parent: QWidget,
    *,
    title: str,
    default_insert: str = "",
    default_position: int = 0,
) -> TextInsertResult:
    """Prompt the user for text insertion settings."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    root = QVBoxLayout(dlg)

    # Insert text
    row_text = QHBoxLayout()
    row_text.addWidget(QLabel(_tr(TR_TEXT_TO_INSERT), dlg))
    txt_insert = QLineEdit(dlg)
    txt_insert.setText(default_insert)
    row_text.addWidget(txt_insert)
    root.addLayout(row_text)

    # Position
    row_pos = QHBoxLayout()
    row_pos.addWidget(QLabel(_tr(TR_POSITION), dlg))
    spin_pos = QSpinBox(dlg)
    spin_pos.setMinimum(-99999)
    spin_pos.setMaximum(99999)
    spin_pos.setValue(default_position)
    row_pos.addWidget(spin_pos)
    root.addLayout(row_pos)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        parent=dlg,
    )
    localize_dialog_buttons(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    root.addWidget(buttons)

    apply_dialog_window_hints(dlg, min_width=450)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return {"insert": "", "position": default_position, "ok": False}

    return {
        "insert": txt_insert.text(),
        "position": int(spin_pos.value()),
        "ok": True,
    }


# ----------------------------------------------------------------------
# prompt_value_replace
# ----------------------------------------------------------------------


def prompt_value_replace(
    parent: QWidget,
    *,
    title: str,
    column: str,
    current_value: str,
    default_new_value: str = "",
    default_replace_all: bool = False,
) -> ValueReplaceResult:
    """Prompt the user to replace a value in a column."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    root = QVBoxLayout(dlg)

    root.addWidget(
        QLabel(
            _tr_fmt(TR_COLUMN, column=column),
            dlg,
        )
    )

    root.addWidget(
        QLabel(
            _tr_fmt(TR_CURRENT_VALUE, current_value=current_value),
            dlg,
        )
    )

    # New value
    row = QHBoxLayout()
    lbl = QLabel(_tr(TR_NEW_VALUE), dlg)
    txt = QLineEdit(dlg)
    txt.setText(default_new_value)

    lbl.setFixedWidth(lbl.sizeHint().width())
    row.addWidget(lbl)
    row.addWidget(txt, stretch=1)
    root.addLayout(row)

    chk_all = QCheckBox(_tr(TR_REPLACE_ALL), dlg)
    chk_all.setChecked(default_replace_all)
    root.addWidget(chk_all)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        parent=dlg,
    )
    localize_dialog_buttons(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    root.addWidget(buttons)

    apply_dialog_window_hints(dlg, min_width=350)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return {
            "new_value": "",
            "replace_all": default_replace_all,
            "ok": False,
        }

    return {
        "new_value": txt.text(),
        "replace_all": chk_all.isChecked(),
        "ok": True,
    }
