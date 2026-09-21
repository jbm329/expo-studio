from __future__ import annotations

import json
import os

from expo_jbm329.app.bootstrap import run_bootstrap
from expo_jbm329.app.settings.config_store import DEFAULT_SETTINGS
from expo_jbm329.utils.path_manager import get_log_config_path, get_settings_path


def test_bootstrap_creates_files(tmp_path, monkeypatch):
    # Patch the path functions directly to ensure isolation
    monkeypatch.setattr("expo_jbm329.utils.path_manager.get_settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr("expo_jbm329.utils.path_manager.get_log_config_path", lambda: tmp_path / "logconfig.json")

    p_settings = get_settings_path()
    p_log = get_log_config_path()

    run_bootstrap()

    assert p_settings.exists()
    assert p_log.exists()
    assert p_log.name == "logconfig.json"


def test_bootstrap_merges_missing_keys(tmp_path, monkeypatch):
    monkeypatch.setattr("expo_jbm329.utils.path_manager.get_settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr("expo_jbm329.utils.path_manager.get_log_config_path", lambda: tmp_path / "logconfig.json")

    # Clear cache to ensure we read from disk
    from expo_jbm329.app.settings import config_store

    config_store._settings_cache = None

    p = get_settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Use a key that is NOT validated/coerced back to default if it already exists correctly
    p.write_text(json.dumps({"workbench": {"theme": "dark"}}), encoding="utf-8")

    run_bootstrap()

    merged = json.loads(p.read_text("utf-8"))
    # Check top level keys from DEFAULT_SETTINGS
    for key in DEFAULT_SETTINGS:
        assert key in merged
    # Check that our theme was preserved
    assert merged["workbench"]["theme"] == "dark"


def test_bootstrap_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("expo_jbm329.utils.path_manager.get_settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr("expo_jbm329.utils.path_manager.get_log_config_path", lambda: tmp_path / "logconfig.json")

    # Clear cache
    from expo_jbm329.app.settings import config_store

    config_store._settings_cache = None

    run_bootstrap()
    p = get_settings_path()
    first = json.loads(p.read_text("utf-8"))

    # Clear cache again to force re-read
    config_store._settings_cache = None
    run_bootstrap()
    second = json.loads(p.read_text("utf-8"))

    assert first == second


def test_bootstrap_disables_tqdm():
    if "TQDM_DISABLE" in os.environ:
        del os.environ["TQDM_DISABLE"]

    run_bootstrap()

    assert os.environ.get("TQDM_DISABLE") == "1"
