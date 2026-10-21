from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from platformdirs import PlatformDirs
from PyQt6.QtCore import QTranslator
from PyQt6.QtWidgets import QApplication

from expo_jbm329.app.settings import config_store
from expo_jbm329.utils import path_manager

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Ensure a QApplication exists for all tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(params=["en", "sv"])
def widget_language(request: pytest.FixtureRequest, qt_app: QApplication) -> Iterator[str]:
    """Install a compiled catalog for widget formatting tests."""
    language = str(request.param)
    translator = QTranslator()
    catalog = Path(__file__).parents[1] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language}.qm"
    assert translator.load(str(catalog))
    qt_app.installTranslator(translator)
    try:
        yield language
    finally:
        qt_app.removeTranslator(translator)


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
