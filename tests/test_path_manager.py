from pathlib import Path

from expo_jbm329.utils.path_manager import (
    APP_NAME,
    ensure_all_dirs,
    get_bootstrap_root,
    get_cache_dir,
    get_config_dir,
    get_connections_config_path,
    get_default_documents_dir,
    get_documents_dir,
    get_i18n_root,
    get_log_config_path,
    get_log_dir,
    get_log_path,
    get_rest_connections_config_path,
    get_settings_path,
    get_theme_root,
)


def test_fixed_dirs_return_path_objects():
    assert isinstance(get_config_dir(), Path)
    assert isinstance(get_log_dir(), Path)
    assert isinstance(get_cache_dir(), Path)


def test_config_and_log_paths():
    config_dir = get_config_dir()
    log_dir = get_log_dir()

    assert get_connections_config_path() == config_dir / "connections.json"
    assert get_rest_connections_config_path() == config_dir / "rest_connections.json"
    assert get_log_config_path() == config_dir / "logconfig.json"
    assert get_settings_path() == config_dir / "settings.json"
    assert get_log_path() == log_dir / "application.log"


def test_get_default_documents_dir():
    path = get_default_documents_dir()
    assert path.name == APP_NAME


def test_get_documents_dir_custom():
    settings = {"documents_dir": "~/CustomExpo"}
    path = get_documents_dir(settings)
    assert "CustomExpo" in str(path)


def test_get_documents_dir_default():
    settings = {}
    path = get_documents_dir(settings)
    assert path.name == APP_NAME


def test_runtime_roots_are_paths():
    assert isinstance(get_theme_root(), Path)
    assert isinstance(get_i18n_root(), Path)
    assert isinstance(get_bootstrap_root(), Path)


def test_ensure_all_dirs(tmp_path):
    settings = {"documents_dir": str(tmp_path / "expo-docs")}

    paths = ensure_all_dirs(settings)

    assert paths["config_dir"].exists()
    assert paths["log_dir"].exists()
    assert paths["cache_dir"].exists()
    assert paths["documents_dir"].exists()
    assert paths["documents_dir"] == tmp_path / "expo-docs"
