"""Path management for the Expo application.

This module handles the discovery and creation of standard application
directories (config, logs, cache) using platform-agnostic paths, as well
as user-configurable document subdirectories.
"""

from __future__ import annotations

import sys
from pathlib import Path

from platformdirs import PlatformDirs

APP_NAME = "Expo"


dirs = PlatformDirs(appname=APP_NAME, appauthor=False, roaming=False)


# --------- Fixed directories ----------


def get_config_dir() -> Path:
    """Return the user configuration directory.

    Returns:
        Path object for the configuration directory.
    """
    return dirs.user_config_path


def get_connections_config_path() -> Path:
    """Return the path to the database connections configuration file.

    Returns:
        Path object for connections.json.
    """
    return get_config_dir() / "connections.json"


def get_rest_connections_config_path() -> Path:
    """Return the path to the REST connections configuration file.

    Returns:
        Path object for rest_connections.json.
    """
    return get_config_dir() / "rest_connections.json"


def get_log_config_path() -> Path:
    """Return the path to the logging configuration file.

    Returns:
        Path object for logconfig.json.
    """
    return get_config_dir() / "logconfig.json"


def get_log_dir() -> Path:
    """Return the user log directory.

    Returns:
        Path object for the log directory.
    """
    return dirs.user_log_path


def get_log_path() -> Path:
    """Return the path to the main application log file.

    Returns:
        Path object for application.log.
    """
    return get_log_dir() / "application.log"


def get_cache_dir() -> Path:
    """Return the user cache directory.

    Returns:
        Path object for the cache directory.
    """
    return dirs.user_cache_path


# --------- Default documents dir ----------
def get_default_documents_dir() -> Path:
    """Return the default documents directory for the application.

    Returns:
        Path object for the default documents directory.
    """
    base = dirs.user_documents_path
    if not base or not Path(base).exists():
        base = Path.home() / "Documents"
    return base / APP_NAME


def get_settings_path() -> Path:
    """Return the path to the application settings file.

    Returns:
        Path object for settings.json.
    """
    return get_config_dir() / "settings.json"


# --------- Active documents dir ----------


def get_documents_dir(settings: dict) -> Path:
    """Return the active documents directory from settings or the default.

    Args:
        settings: Application settings dictionary.

    Returns:
        Path object for the documents directory.
    """
    custom = settings.get("documents_dir")
    if custom and isinstance(custom, str):
        return Path(custom).expanduser()
    return get_default_documents_dir()


def get_theme_root() -> Path:
    """Return the runtime theme root for both dev and PyInstaller environments.

    Returns:
        Path object for the theme root directory.
    """
    # PyInstaller runtime
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "theme"  # noqa: SLF001

    return Path(__file__).resolve().parents[1] / "workbench" / "theme"


def get_i18n_root() -> Path:
    """Return the runtime theme root for both dev and PyInstaller environments.

    Returns:
        Path object for the i18n root directory.
    """
    # PyInstaller runtime
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "i18n"  # noqa: SLF001

    return Path(__file__).resolve().parents[1] / "i18n"


def get_bootstrap_root() -> Path:
    """Return the runtime bootstrap root for both dev and PyInstaller environments.

    Returns:
        Path object for the i18n root directory.
    """
    # PyInstaller runtime
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "bootstrap"  # noqa: SLF001

    return Path(__file__).resolve().parents[1] / "bootstrap"


def ensure_all_dirs(settings: dict) -> dict[str, Path]:
    """Create the directory structure and necessary configuration files.

    Args:
        settings: Application settings dictionary.

    Returns:
        A mapping of directory/file names to their Path objects.
    """
    paths = {
        "config_dir": get_config_dir(),
        "settings_path": get_settings_path(),
        "connections_config_path": get_connections_config_path(),
        "log_dir": get_log_dir(),
        "log_config_path": get_log_config_path(),
        "cache_dir": get_cache_dir(),
        "documents_dir": get_documents_dir(settings),
    }

    # Skapa kataloger
    for key in ("config_dir", "log_dir", "cache_dir", "documents_dir"):
        paths[key].mkdir(parents=True, exist_ok=True)

    return paths
