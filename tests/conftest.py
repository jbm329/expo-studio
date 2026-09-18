from __future__ import annotations

# import json
# import os
# import shutil
# from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication


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
    """
    Forces the app to use a temporary config directory
    instead of the user's real config folder.
    This ensures tests run fully isolated and do not
    touch real settings.json/logconfig.json.
    """

    fake_home = tmp_path / "HOME"
    fake_home.mkdir()

    # Patch platformdirs so Expo sees this directory as the real one
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows fallback

    yield  # Run test

    # Clean after test — pytest tmp_path handles cleanup