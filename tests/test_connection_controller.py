# tests/test_connection_controller.py
from __future__ import annotations
import pytest
from expo_jbm329.workbench.controllers.connection_controller import ConnectionController
from unittest.mock import MagicMock

@pytest.fixture
def cc_setup():
    # Mock all the functional protocols
    get_connection_names = MagicMock(return_value=["Conn1", "Conn2"])
    clear_schema_cache = MagicMock()
    close_db_connection = MagicMock()
    
    ctrl = ConnectionController(
        get_connection_names=get_connection_names,
        clear_schema_cache=clear_schema_cache,
        close_db_connection=close_db_connection
    )
    
    load_schema = MagicMock()
    ctrl.bind_schema_loader(load_schema)
            
    return ctrl, {
        "get_names": get_connection_names,
        "load": load_schema,
        "clear_cache": clear_schema_cache,
        "close": close_db_connection,
    }

def test_initial_state(cc_setup):
    ctrl, mocks = cc_setup
    assert ctrl.active_connection is None
    assert ctrl.get_connection_names() == ["Conn1", "Conn2"]

def test_connect_updates_active_connection(cc_setup):
    ctrl, mocks = cc_setup
    ctrl.connect("Conn1")
    assert ctrl.active_connection == "Conn1"
    mocks["load"].assert_called_once_with("Conn1", False)

def test_connect_triggers_on_active_connection_changed(cc_setup):
    ctrl, mocks = cc_setup
    cb = MagicMock()
    ctrl.on_active_connection_changed(cb)
    
    ctrl.connect("Conn1")
    cb.assert_called_once_with(None, "Conn1")

def test_disconnect_clears_active_connection(cc_setup):
    ctrl, mocks = cc_setup
    ctrl.connect("Conn1")
    
    ctrl.disconnect("Conn1")
    assert ctrl.active_connection is None
    mocks["clear_cache"].assert_called_once_with("Conn1")
    mocks["close"].assert_called_once_with("Conn1")

def test_disconnect_active_triggers_callback(cc_setup):
    ctrl, mocks = cc_setup
    ctrl.connect("Conn1")
    
    cb = MagicMock()
    ctrl.on_active_connection_changed(cb)
    
    ctrl.disconnect()
    assert ctrl.active_connection is None
    cb.assert_called_once_with("Conn1", None)

def test_connect_to_same_does_nothing(cc_setup):
    ctrl, mocks = cc_setup
    ctrl.connect("Conn1")
    mocks["load"].reset_mock()
    
    ctrl.connect("Conn1")
    mocks["load"].assert_not_called()
    assert ctrl.active_connection == "Conn1"

def test_connect_failure_resets_active_connection(cc_setup):
    ctrl, mocks = cc_setup
    
    # Mock loader that fails
    mocks["load"].side_effect = RuntimeError("Connection failed")
    
    # Try to connect
    with pytest.raises(RuntimeError, match="Connection failed"):
        ctrl.connect("Conn1")
    
    # Verify active connection is NOT "Conn1"
    assert ctrl.active_connection is None

def test_retry_after_failure(cc_setup):
    ctrl, mocks = cc_setup
    
    loader_calls = []
    def loader(name, force):
        loader_calls.append(name)
        if len(loader_calls) == 1:
            raise RuntimeError("First attempt failed")
        # Second attempt succeeds
    
    mocks["load"].side_effect = loader
    
    # First attempt fails
    with pytest.raises(RuntimeError, match="First attempt failed"):
        ctrl.connect("Conn1")
    
    assert ctrl.active_connection is None
    
    # Second attempt should proceed
    ctrl.connect("Conn1")
    
    assert ctrl.active_connection == "Conn1"
    assert len(loader_calls) == 2
