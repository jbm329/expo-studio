from __future__ import annotations

from unittest.mock import MagicMock

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget

from expo_jbm329.workbench.controllers.toolbar_controller import ToolbarController


class DummyIcons:
    def __init__(self):
        self.calls = []

    def get(self, name):
        self.calls.append(name)
        return QIcon()


def test_build_toolbar_wires_callbacks_and_states():
    icons = DummyIcons()
    callbacks = {
        name: MagicMock()
        for name in [
            "new_file",
            "open_file",
            "save_file",
            "run_full",
            "run_selfull",
            "run_top10",
            "cancel_job",
            "export_csv",
            "export_excel",
            "export_data",
            "join_data",
            "concatenate_data",
            "reshape_data",
            "format_view",
            "clear_editor",
            "refresh_schema",
            "undo",
            "analyze_data",
        ]
    }

    ctrl = ToolbarController(icons, **callbacks)
    tb = ctrl.build(QWidget())

    assert tb is ctrl.toolbar
    assert "file_new" in icons.calls


def test_analysis_availability_follows_active_readiness_without_changing_export_state():
    callbacks = {
        name: MagicMock()
        for name in [
            "new_file",
            "open_file",
            "save_file",
            "run_full",
            "run_selfull",
            "run_top10",
            "cancel_job",
            "export_csv",
            "export_excel",
            "export_data",
            "join_data",
            "concatenate_data",
            "reshape_data",
            "format_view",
            "clear_editor",
            "refresh_schema",
            "undo",
            "analyze_data",
        ]
    }
    ctrl = ToolbarController(DummyIcons(), **callbacks)
    parent = QWidget()
    ctrl.build(parent)

    ctrl.apply_has_data_state(True)

    assert ctrl._action_export_csv.isEnabled()  # noqa: SLF001
    assert not ctrl._action_analyze.isEnabled()  # noqa: SLF001
    ctrl.apply_analysis_state(True)
    assert ctrl._action_analyze.isEnabled()  # noqa: SLF001
    ctrl.apply_has_data_state(False)
    assert not ctrl._action_export_csv.isEnabled()  # noqa: SLF001
    assert ctrl._action_analyze.isEnabled()  # noqa: SLF001
    ctrl.apply_analysis_state(False)
    assert not ctrl._action_analyze.isEnabled()  # noqa: SLF001


def test_reshape_order_readiness_callback_and_retranslation():
    callbacks = {
        name: MagicMock()
        for name in (
            "new_file",
            "open_file",
            "save_file",
            "run_full",
            "run_selfull",
            "run_top10",
            "cancel_job",
            "export_csv",
            "export_excel",
            "export_data",
            "join_data",
            "concatenate_data",
            "reshape_data",
            "format_view",
            "clear_editor",
            "refresh_schema",
            "undo",
            "analyze_data",
        )
    }
    icons = DummyIcons()
    ctrl = ToolbarController(icons, **callbacks)
    parent = QWidget()
    toolbar = ctrl.build(parent)
    action = ctrl._action_reshape
    assert toolbar.actions().index(action) == toolbar.actions().index(ctrl._action_concatenate_data) + 1
    assert not action.isEnabled()
    ctrl.apply_has_data_state(True)
    ctrl.apply_has_multiple_datasets_state(True)
    assert not action.isEnabled()
    ctrl.apply_reshape_state(True)
    ctrl.apply_has_multiple_datasets_state(False)
    assert action.isEnabled()
    assert not ctrl._action_concatenate_data.isEnabled()
    action.trigger()
    callbacks["reshape_data"].assert_called_once_with(False)
    ctrl.retranslate_ui()
    assert action.text() == "Reshape"
    ctrl.apply_icons()
    assert icons.calls.count("table") == 2
    ctrl.apply_reshape_state(False)
    assert not action.isEnabled()
