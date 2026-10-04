from __future__ import annotations

import pytest
from platformdirs import PlatformDirs
from PyQt6.QtWidgets import QApplication

from expo_jbm329.app.settings import config_store
from expo_jbm329.utils import path_manager


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Ensure a QApplication exists for all tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# Ensure we import the correct package root
@pytest.fixture(autouse=True)
def _isolate_user_dirs(monkeypatch, tmp_path):
    """Forces the app to use a temporary config directory
    instead of the user's real config folder.
    This ensures tests run fully isolated and do not
    touch real settings.json/logconfig.json.
    """

    fake_home = tmp_path / "HOME"
    fake_home.mkdir(parents=True, exist_ok=True)
    fake_localappdata = tmp_path / "LOCALAPPDATA"
    fake_localappdata.mkdir(parents=True, exist_ok=True)
    fake_appdata = tmp_path / "APPDATA"
    fake_appdata.mkdir(parents=True, exist_ok=True)
    fake_xdg_config = tmp_path / "XDG_CONFIG"
    fake_xdg_config.mkdir(parents=True, exist_ok=True)
    fake_xdg_data = tmp_path / "XDG_DATA"
    fake_xdg_data.mkdir(parents=True, exist_ok=True)
    fake_xdg_cache = tmp_path / "XDG_CACHE"
    fake_xdg_cache.mkdir(parents=True, exist_ok=True)

    # Patch platformdirs so Expo sees this directory as the real one
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows fallback
    monkeypatch.setenv("LOCALAPPDATA", str(fake_localappdata))
    monkeypatch.setenv("APPDATA", str(fake_appdata))
    monkeypatch.setenv("WIN_PD_OVERRIDE_LOCAL_APPDATA", str(fake_localappdata))
    monkeypatch.setenv("WIN_PD_OVERRIDE_APPDATA", str(fake_appdata))
    monkeypatch.setenv("WIN_PD_OVERRIDE_COMMON_APPDATA", str(fake_appdata))
    monkeypatch.setenv("WIN_PD_OVERRIDE_PERSONAL", str(fake_home / "Documents"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_xdg_config))
    monkeypatch.setenv("XDG_DATA_HOME", str(fake_xdg_data))
    monkeypatch.setenv("XDG_CACHE_HOME", str(fake_xdg_cache))

    old_dirs = path_manager.dirs
    path_manager.dirs = PlatformDirs(appname=path_manager.APP_NAME, appauthor=False, roaming=False)
    config_store._settings_cache = None

    try:
        yield
    finally:
        path_manager.dirs = old_dirs
        config_store._settings_cache = None
