from __future__ import annotations

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QDialogButtonBox, QMessageBox

from expo_jbm329.gui.dialogs.service.common.localization import (
    TR_CANCEL,
    TR_CLOSE,
    TR_NO,
    TR_OK,
    TR_YES,
    localize_dialog_buttons,
    localize_messagebox_buttons,
)


def _translated(text: str) -> str:
    return QCoreApplication.translate("QtDialogService", text)


def test_localize_dialog_buttons_sets_close_button_text():
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)

    localize_dialog_buttons(buttons)

    close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
    assert close_button is not None
    assert close_button.text() == _translated(TR_CLOSE)


def test_localize_dialog_buttons_sets_ok_cancel_yes_no_text():
    standard_buttons = (
        QDialogButtonBox.StandardButton.Ok
        | QDialogButtonBox.StandardButton.Cancel
        | QDialogButtonBox.StandardButton.Yes
        | QDialogButtonBox.StandardButton.No
    )
    buttons = QDialogButtonBox(standard_buttons)

    localize_dialog_buttons(buttons)

    assert buttons.button(QDialogButtonBox.StandardButton.Ok).text() == _translated(TR_OK)
    assert buttons.button(QDialogButtonBox.StandardButton.Cancel).text() == _translated(TR_CANCEL)
    assert buttons.button(QDialogButtonBox.StandardButton.Yes).text() == _translated(TR_YES)
    assert buttons.button(QDialogButtonBox.StandardButton.No).text() == _translated(TR_NO)


def test_localize_dialog_buttons_ignores_buttons_not_present():
    """Only Close was added; localizing must not crash for the other mapped buttons."""
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)

    localize_dialog_buttons(buttons)  # should not raise

    assert buttons.button(QDialogButtonBox.StandardButton.Ok) is None


def test_localize_messagebox_buttons_sets_ok_yes_no_text():
    msg = QMessageBox()
    msg.setStandardButtons(
        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )

    localize_messagebox_buttons(msg)

    assert msg.button(QMessageBox.StandardButton.Ok).text() == _translated(TR_OK)
    assert msg.button(QMessageBox.StandardButton.Yes).text() == _translated(TR_YES)
    assert msg.button(QMessageBox.StandardButton.No).text() == _translated(TR_NO)
