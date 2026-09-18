from __future__ import annotations

from unittest.mock import MagicMock

from PyQt6.QtWidgets import QWidget

from expo_jbm329.workbench.controllers.rest_panel_controller import RestPanelController


class DummySignal:
    def __init__(self):
        self.connected = []

    def connect(self, cb):
        self.connected.append(cb)


class DummyItem:
    def __init__(self, role=None, children=None):
        self._role = role
        self._children = children or []
        self.icons = []

    def data(self, column, role):
        return self._role

    def setIcon(self, column, icon):
        self.icons.append(icon)

    def childCount(self):
        return len(self._children)

    def child(self, idx):
        return self._children[idx]


class DummyTree:
    FOLDER_ROLE = 1

    def __init__(self):
        self.load_requested = DummySignal()
        self.edit_requested = DummySignal()
        self.copy_requested = DummySignal()
        self.root = DummyItem(children=[DummyItem(role=1), DummyItem(role=2)])
        self.reload_called = False

    def invisibleRootItem(self):
        return self.root

    def reload(self):
        self.reload_called = True


class DummyIconService:
    def __init__(self):
        self.icons_updated = DummySignal()

    def get(self, name):
        return name


def test_initialize_and_reload_wires_tree():
    rest_controller = MagicMock()
    tree = DummyTree()
    icon_service = DummyIconService()
    ctrl = RestPanelController(
        parent_widget=QWidget(),
        rest_tree=tree,
        rest_controller=rest_controller,
        open_rest_connection_dialog=MagicMock(),
        icon_service=icon_service,
    )

    ctrl.initialize()

    assert tree.reload_called
    assert tree.load_requested.connected
    assert tree.edit_requested.connected
    assert tree.copy_requested.connected


def test_copy_requested_opens_dialog():
    rest_controller = MagicMock(copy_preset=MagicMock(return_value="new"))
    open_dialog = MagicMock()
    tree = DummyTree()
    ctrl = RestPanelController(
        parent_widget=QWidget(),
        rest_tree=tree,
        rest_controller=rest_controller,
        open_rest_connection_dialog=open_dialog,
        icon_service=DummyIconService(),
    )

    ctrl._on_copy_requested("preset")

    rest_controller.copy_preset.assert_called_once_with("preset")
    open_dialog.assert_called_once_with("new")
