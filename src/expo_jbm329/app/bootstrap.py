"""Unified configuration bootstrap for Expo.

This module ensures that:
- settings.json exists, is valid, is deep-merged with defaults, and saved.
- logconfig.json exists, is valid, is deep-merged with defaults, and saved.
- All config formats are forward-compatible (adding new fields in code
  automatically adds defaults in existing user files).
- All caches inside config_store.py are synchronized.
"""

from __future__ import annotations

import os
import sys

from expo_jbm329.app.settings.config_store import (
    load_settings,
    read_log_config,
    save_settings,
    write_log_config,
)
from expo_jbm329.workbench.icon import icons_rc
from expo_jbm329.workbench.splash import splash_rc

_RESOURCE_MODULES = (icons_rc, splash_rc)


def restore_clean_environment() -> None:
    """Restore original system environment variables when running in a frozen Linux bundle.

    PyInstaller modifies LD_LIBRARY_PATH to point to its internal directory,
    and PyInstaller's PyQt6 runtime hook sets Qt plugin environment variables
    (e.g. QT_PLUGIN_PATH, QML2_IMPORT_PATH). These cause external helper tools
    (such as kde-open, xdg-open, web browsers) to fail due to dynamic linker or
    Qt plugin version conflicts with bundled libraries.
    """
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
        # Restore or unset dynamic linker path
        if "LD_LIBRARY_PATH_ORIG" in os.environ:
            os.environ["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH_ORIG"]
        elif "LD_LIBRARY_PATHORIG" in os.environ:
            os.environ["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATHORIG"]
        else:
            os.environ.pop("LD_LIBRARY_PATH", None)

        # Restore or unset Qt plugin and QML environment variables
        for var in (
            "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QML_IMPORT_PATH",
            "QML2_IMPORT_PATH",
        ):
            orig_var = f"{var}_ORIG"
            if orig_var in os.environ:
                os.environ[var] = os.environ[orig_var]
            else:
                os.environ.pop(var, None)


def run_bootstrap() -> None:
    """Run once at application startup.

    This function performs the following initialization steps:
    1. Restore clean system environment for child processes in frozen Linux bundles.
    2. Load, deep-merge, validate, and save settings.json.
    3. Load, deep-merge, validate, and save logconfig.json.
    4. Disable TQDM progress bars by setting an environment variable.

    Note:
        connections.json is intentionally not touched here because it is
        user-driven and should not automatically change its structure.
    """
    # Environment cleanup for external links / subprocesses
    restore_clean_environment()

    # Settings
    settings = load_settings()
    save_settings(settings)  # ensures new defaults propagate

    # Logging
    logcfg = read_log_config()
    write_log_config(logcfg)

    # TQDM
    os.environ["TQDM_DISABLE"] = "1"
