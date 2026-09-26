"""Localization functions for dialogs."""

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication
from PyQt6.QtWidgets import QDialogButtonBox, QMessageBox

TR_OK = QT_TRANSLATE_NOOP("QtDialogService", "OK")
TR_CANCEL = QT_TRANSLATE_NOOP("QtDialogService", "Cancel")
TR_YES = QT_TRANSLATE_NOOP("QtDialogService", "Yes")
TR_NO = QT_TRANSLATE_NOOP("QtDialogService", "No")
TR_CLOSE = QT_TRANSLATE_NOOP("QtDialogService", "Close")


def localize_dialog_buttons(buttons: QDialogButtonBox) -> None:
    """Localize the text of standard buttons in a QDialogButtonBox.

    Args:
        buttons (QDialogButtonBox): The button box to localize.
    """
    mapping = {
        QDialogButtonBox.StandardButton.Ok: TR_OK,
        QDialogButtonBox.StandardButton.Cancel: TR_CANCEL,
        QDialogButtonBox.StandardButton.Yes: TR_YES,
        QDialogButtonBox.StandardButton.No: TR_NO,
        QDialogButtonBox.StandardButton.Close: TR_CLOSE,
    }
    for btn, text in mapping.items():
        b = buttons.button(btn)
        if b:
            b.setText(QCoreApplication.translate("QtDialogService", text))


def localize_messagebox_buttons(msg: QMessageBox) -> None:
    """Localize the text of standard buttons in a QMessageBox.

    Args:
        msg (QMessageBox): The message box to localize.
    """
    for btn, text in (
        (QMessageBox.StandardButton.Ok, TR_OK),
        (QMessageBox.StandardButton.Yes, TR_YES),
        (QMessageBox.StandardButton.No, TR_NO),
    ):
        b = msg.button(btn)
        if b:
            b.setText(QCoreApplication.translate("QtDialogService", text))
