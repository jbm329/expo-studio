from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from expo_jbm329.workbench.controllers.connection_controller import ConnectionController


@pytest.fixture
def controller():
    get_connection_names = MagicMock(return_value=["Conn1", "Conn2"])
    clear_schema_cache = MagicMock()
    close_db_connection = MagicMock()
    ctrl = ConnectionController(
        get_connection_names=get_connection_names,
        clear_schema_cache=clear_schema_cache,
        close_db_connection=close_db_connection,
    )
    load_schema = MagicMock()
    ctrl.bind_schema_loader(load_schema)
    return ctrl, {
        "get_names": get_connection_names,
        "load": load_schema,
        "clear_cache": clear_schema_cache,
        "close": close_db_connection,
    }


def test_initial_state(controller):
    ctrl, mocks = controller

    assert ctrl.active_connection is None
    assert ctrl.get_connection_names() == ["Conn1", "Conn2"]
    mocks["get_names"].assert_called_once_with()


def test_connect_updates_active_connection_and_callback(controller):
    ctrl, mocks = controller
    callback = MagicMock()
    ctrl.on_active_connection_changed(callback)

    ctrl.connect("Conn1")

    assert ctrl.active_connection == "Conn1"
    mocks["load"].assert_called_once_with("Conn1", False)
    callback.assert_called_once_with(None, "Conn1")


def test_connect_to_same_does_nothing(controller):
    ctrl, mocks = controller

    ctrl.connect("Conn1")
    mocks["load"].reset_mock()

    ctrl.connect("Conn1")

    mocks["load"].assert_not_called()
    assert ctrl.active_connection == "Conn1"


def test_disconnect_active_connection(controller):
    ctrl, mocks = controller
    callback = MagicMock()
    ctrl.on_active_connection_changed(callback)

    ctrl.connect("Conn1")
    ctrl.disconnect()

    assert ctrl.active_connection is None
    mocks["clear_cache"].assert_called_once_with("Conn1")
    mocks["close"].assert_called_once_with("Conn1")
    callback.assert_any_call("Conn1", None)


def test_disconnect_non_active_connection_does_not_clear_active_state(controller):
    ctrl, mocks = controller
    ctrl.connect("Conn1")
    callback = MagicMock()
    ctrl.on_active_connection_changed(callback)

    ctrl.disconnect("Conn2")

    assert ctrl.active_connection == "Conn1"
    mocks["clear_cache"].assert_called_once_with("Conn2")
    mocks["close"].assert_called_once_with("Conn2")
    callback.assert_not_called()


def test_connect_without_schema_loader_raises():
    ctrl = ConnectionController(
        get_connection_names=lambda: [],
        clear_schema_cache=lambda _: None,
        close_db_connection=lambda _: None,
    )

    with pytest.raises(RuntimeError, match="load_schema is missing"):
        ctrl.connect("Conn1")

