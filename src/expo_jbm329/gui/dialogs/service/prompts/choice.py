"""Dialogs for prompting the user for choices."""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QRadioButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.gui.dialogs.service.common.localization import (
    localize_dialog_buttons,
    localize_messagebox_buttons,
)
from expo_jbm329.gui.dialogs.service.common.window_hints import apply_dialog_window_hints
from expo_jbm329.gui.dialogs.service.dialog_service import ProfileChoice


# ----------------------------------------------------------------------
# prompt_choice
# ----------------------------------------------------------------------
def prompt_choice(
    parent: QWidget,
    *,
    title: str,
    label: str,
    choices: list[str],
    default_index: int = 0,
    editable: bool = False,
) -> tuple[str, bool]:
    """Prompt the user to select a choice from a list."""
    if not choices:
        return "", False

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    root = QVBoxLayout(dlg)

    root.addWidget(QLabel(label, dlg))

    combo = QComboBox(dlg)
    combo.setEditable(editable)
    combo.addItems(choices)

    ix = max(0, min(default_index, len(choices) - 1))
    combo.setCurrentIndex(ix)

    root.addWidget(combo)

    buttons = QDialogButtonBox(parent=dlg)
    buttons.addButton(QDialogButtonBox.StandardButton.Ok)
    buttons.addButton(QDialogButtonBox.StandardButton.Cancel)

    localize_dialog_buttons(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    root.addWidget(buttons)

    apply_dialog_window_hints(dlg, min_width=360)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    return (combo.currentText(), True) if ok else (choices[ix], False)


# ----------------------------------------------------------------------
# prompt_yes_no
# ----------------------------------------------------------------------


def prompt_yes_no(
    parent: QWidget,
    *,
    title: str,
    text: str,
    informative: str | None = None,
    default_yes: bool = False,
) -> bool:
    """Prompt the user for a yes/no confirmation."""
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setIcon(QMessageBox.Icon.Question)
    msg.setText(text)

    if informative:
        msg.setInformativeText(informative)

    msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    msg.setDefaultButton(QMessageBox.StandardButton.Yes if default_yes else QMessageBox.StandardButton.No)

    localize_messagebox_buttons(msg)
    apply_dialog_window_hints(msg, min_width=300)

    return msg.exec() == QMessageBox.StandardButton.Yes


# ----------------------------------------------------------------------
# confirm_profile_scope
# ----------------------------------------------------------------------


def confirm_profile_scope(
    parent: QWidget,
    *,
    title: str,
    text: str,
    active_tab_text: str,
    all_tabs_text: str,
) -> ProfileChoice:
    """Ask the user what they want to profile when multiple tabs are open."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    root = QVBoxLayout(dlg)
    content = QHBoxLayout()

    # Icon
    icon_label = QLabel(dlg)
    style = dlg.style()
    if style is None:
        return ProfileChoice.CANCEL
    icon = style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion)
    icon_label.setPixmap(icon.pixmap(34, 34))
    icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
    content.addWidget(icon_label)

    # Radio buttons
    rb_layout = QVBoxLayout()

    rb_layout.addWidget(QLabel(text, dlg))

    rb_active = QRadioButton(active_tab_text, dlg)
    rb_all = QRadioButton(all_tabs_text, dlg)

    grp = QButtonGroup(dlg)
    grp.addButton(rb_active)
    grp.addButton(rb_all)

    rb_active.setChecked(True)

    rb_layout.addWidget(rb_active)
    rb_layout.addWidget(rb_all)

    content.addLayout(rb_layout)
    root.addLayout(content)

    buttons = QDialogButtonBox(parent=dlg)
    buttons.addButton(QDialogButtonBox.StandardButton.Ok)
    buttons.addButton(QDialogButtonBox.StandardButton.Cancel)

    localize_dialog_buttons(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    root.addWidget(buttons)

    apply_dialog_window_hints(dlg, min_width=400)

    ok = dlg.exec() == QDialog.DialogCode.Accepted
    if not ok:
        return ProfileChoice.CANCEL

    return ProfileChoice.ALL if rb_all.isChecked() else ProfileChoice.ACTIVE


# ----------------------------------------------------------------------
# confirm_delete
# ----------------------------------------------------------------------


def confirm_delete(
    parent: QWidget,
    *,
    title: str | None = None,
    name: str,
    full_path: str,
    size_hint: str | None = None,
) -> bool:
    """Ask the user to confirm deletion of a file or folder."""
    if title is None:
        title = QCoreApplication.translate("QtDialogService", "Confirm delete")

    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setWindowTitle(title)

    size_str = size_hint or ""
    msg.setText(
        QCoreApplication
        .translate(
            "QtDialogService",
            "Do you want to permanently delete:\n\n%1%2",
        )
        .replace("%1", name)
        .replace("%2", size_str)
    )

    msg.setInformativeText(full_path)

    msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    msg.setDefaultButton(QMessageBox.StandardButton.No)

    localize_messagebox_buttons(msg)
    apply_dialog_window_hints(msg, min_width=400)

    return msg.exec() == QMessageBox.StandardButton.Yes
