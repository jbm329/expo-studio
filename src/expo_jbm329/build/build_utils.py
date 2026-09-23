"""Build helpers.

Utilities for building the project.
"""

from __future__ import annotations

import pathlib
import sys

BASE = pathlib.Path(__file__).parents[3]


def project_root() -> pathlib.Path:
    """Return the project root directory."""
    return BASE


def src_root() -> pathlib.Path:
    """Return the source root directory."""
    return BASE / "src"


def locales_dir() -> pathlib.Path:
    """Return the locales directory."""
    return BASE / "src" / "expo_jbm329" / "i18n" / "locales"


def installer_dir() -> pathlib.Path:
    """Return the installer directory where .iss and .appid is located."""
    return BASE / "tools" / "installer"


def icons_qrc() -> pathlib.Path:
    """Return the path to the icons.qrc file."""
    return BASE / "src" / "expo_jbm329" / "workbench" / "icon" / "icons.qrc"


def splash_qrc() -> pathlib.Path:
    """Return the path to the splash.qrc file."""
    return BASE / "src" / "expo_jbm329" / "workbench" / "splash" / "splash.qrc"


def detect_platform() -> str:
    """Return a normalized platform identifier for release artifacts."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform.startswith("darwin"):
        return "macos"
    return sys.platform.replace(" ", "_")


def main() -> None:
    """Test function."""
    print(f"PLATFORM: {detect_platform()}")
    print(f"PROJECT_ROOT: {project_root()}")
    print(f"SRC_ROOT: {src_root()}")
    print(f"LOCALES_DIR: {locales_dir()}")
    print(f"INSTALLER_DIR: {installer_dir()}")


if __name__ == "__main__":
    main()
