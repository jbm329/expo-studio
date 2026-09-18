
from unittest.mock import MagicMock

from expo_jbm329.services.settings_service import SettingsService


def test_settings_service_initialization():
    initial = {"key": "value"}
    service = SettingsService(initial_settings=initial)
    assert service.get() == initial


def test_settings_service_subscribe():
    service = SettingsService(initial_settings={"a": 1})
    callback = MagicMock()
    
    service.subscribe(callback)
    service.set_and_notify({"a": 2})
    
    callback.assert_called_once_with({"a": 2})


def test_settings_service_immediate_subscribe():
    initial = {"a": 1}
    service = SettingsService(initial_settings=initial)
    callback = MagicMock()
    
    service.subscribe(callback, immediate=True)
    callback.assert_called_once_with(initial)


def test_settings_service_reload():
    loader = MagicMock(return_value={"loaded": True})
    service = SettingsService(loader=loader)
    
    res = service.reload()
    assert res == {"loaded": True}
    assert service.get() == {"loaded": True}


def test_settings_service_unsubscribe():
    service = SettingsService(initial_settings={"a": 1})
    callback = MagicMock()
    
    service.subscribe(callback)
    service.unsubscribe(callback)
    service.set_and_notify({"a": 2})
    
    callback.assert_not_called()


def test_settings_service_dispatcher():
    dispatcher = MagicMock()
    service = SettingsService(initial_settings={"a": 1}, dispatcher=dispatcher)
    callback = MagicMock()
    
    service.subscribe(callback)
    service.set_and_notify({"a": 2})
    
    # Dispatcher should be called with a function that calls the callback
    dispatcher.assert_called_once()
    # Execute the function passed to dispatcher
    dispatcher.call_args[0][0]()
    callback.assert_called_once_with({"a": 2})
