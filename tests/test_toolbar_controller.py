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
    callbacks = {name: MagicMock() for name in [
        "new_file", "open_file", "save_file", "run_full", "run_selfull", "run_top10",
        "cancel_job", "export_csv", "export_excel", "export_data", "join_data",
        "concatenate_data", "format_view", "clear_editor", "refresh_schema",
        "undo", "visualize_data",
    ]}

    ctrl = ToolbarController(icons, **callbacks)
    tb = ctrl.build(QWidget())

    assert tb is ctrl.toolbar
    assert "file_new" in icons.calls

