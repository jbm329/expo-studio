from __future__ import annotations

from unittest.mock import MagicMock

from PyQt6.QtWidgets import QMenuBar

from expo_jbm329.workbench.controllers.menu_controller import MenuController


def test_menu_actions_wire_callbacks():
    menubar = QMenuBar()
    callbacks = {
        name: MagicMock()
        for name in [
            "new_file",
            "open_file",
            "save_file",
            "save_file_as",
            "quit_app",
            "export_csv",
            "export_excel",
            "export_data",
            "export_profile",
            "clear_editor",
            "open_settings_dialog",
            "open_log_settings_dialog",
            "open_connection_dialog",
            "open_rest_connection_dialog",
            "show_about_dialog",
        ]
    }

    ctrl = MenuController(menubar=menubar, **callbacks)
    ctrl._act_new.trigger()
    ctrl._act_open.trigger()
    ctrl._act_save.trigger()
    ctrl._act_save_as.trigger()
    ctrl._act_quit.trigger()
    ctrl._act_clear.trigger()
    ctrl.act_data_profiling.trigger()

    assert callbacks["new_file"].called
    assert callbacks["open_file"].called
    assert callbacks["save_file"].called
    assert callbacks["save_file_as"].called
    assert callbacks["quit_app"].called
    assert callbacks["clear_editor"].called
    assert callbacks["export_profile"].called


def test_has_data_state_and_retranslate():
    menubar = QMenuBar()
    ctrl = MenuController(
        menubar=menubar,
        new_file=lambda: None,
        open_file=lambda: None,
        save_file=lambda: None,
        save_file_as=lambda: None,
        quit_app=lambda: None,
        export_csv=lambda: None,
        export_excel=lambda: None,
        export_data=lambda: None,
        export_profile=lambda: None,
        clear_editor=lambda: None,
        open_settings_dialog=lambda: None,
        open_log_settings_dialog=lambda: None,
        open_connection_dialog=lambda: None,
        open_rest_connection_dialog=lambda: None,
        show_about_dialog=lambda: None,
    )

    ctrl.apply_has_data_state(True)
    assert ctrl._act_export_csv.isEnabled()
    ctrl.apply_has_data_state(False)
    assert not ctrl._act_export_csv.isEnabled()
    ctrl.retranslate_ui()
    assert ctrl._menu_file.title()
