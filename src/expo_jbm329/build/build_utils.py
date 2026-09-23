"""Build helpers.

Utilities for building the project.
"""

from __future__ import annotations

import pathlib
import shutil
import stat
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

BASE = pathlib.Path(__file__).parents[3]


def project_root() -> pathlib.Path:
    """Return the project root directory."""
    return BASE


def src_root() -> pathlib.Path:
    """Return the source root directory."""
    return BASE / "src"


def dist_dir() -> pathlib.Path:
    """Return the distribution output directory."""
    return BASE / "dist"


def release_dir() -> pathlib.Path:
    """Return the release output directory."""
    return BASE / "release"


def staging_dir() -> pathlib.Path:
    """Return the release staging directory."""
    return release_dir() / "staging"


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


def _chmod_writable(path: pathlib.Path) -> None:
    """Ensure a filesystem path is writable."""
    try:
        path.chmod(stat.S_IWRITE)
    except OSError:
        return


def _onerror(func: Callable[[str], object], path: str, _exc_info: object) -> None:
    """Retry a failed filesystem operation after making the path writable."""
    _chmod_writable(pathlib.Path(path))
    func(path)


def remove_directory_tree(path: pathlib.Path, retries: int = 6, backoff: float = 0.2) -> bool:
    """Remove a directory tree with retries and backoff.

    Args:
        path: Directory to remove.
        retries: Number of retry attempts.
        backoff: Initial backoff delay multiplier in seconds.

    Returns:
        True if the directory was removed successfully, otherwise False.
    """
    if not path.exists():
        return True

    for attempt in range(retries):
        try:
            shutil.rmtree(path, onexc=_onerror)
        except OSError:
            time.sleep(backoff * (attempt + 1))
        else:
            return True

    return False


def prepare_clean_directory(path: pathlib.Path) -> None:
    """Create an empty directory, removing any existing directory tree first.

    Args:
        path: Directory to create empty.

    Raises:
        OSError: If an existing directory tree cannot be removed.
    """
    if path.exists() and not remove_directory_tree(path):
        message = f"Could not remove directory: {path}"
        raise OSError(message)

    path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """Test function."""
    print(f"PLATFORM: {detect_platform()}")
    print(f"PROJECT_ROOT: {project_root()}")
    print(f"SRC_ROOT: {src_root()}")
    print(f"DIST_DIR: {dist_dir()}")
    print(f"RELEASE_DIR: {release_dir()}")
    print(f"STAGING_DIR: {staging_dir()}")
    print(f"LOCALES_DIR: {locales_dir()}")
    print(f"INSTALLER_DIR: {installer_dir()}")


if __name__ == "__main__":
    main()
