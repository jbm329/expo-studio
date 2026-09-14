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

from expo_jbm329.app.settings.config_store import (
    load_settings,
    read_log_config,
    save_settings,
    write_log_config,
)
from expo_jbm329.workbench.icon import icons_rc
from expo_jbm329.workbench.splash import splash_rc


def run_bootstrap() -> None:
    """Run once at application startup.

    This function performs the following initialization steps:
    1. Load, deep-merge, validate, and save settings.json.
    2. Load, deep-merge, validate, and save logconfig.json.
    3. Disable TQDM progress bars by setting an environment variable.

    Note:
        connections.json is intentionally not touched here because it is
        user-driven and should not automatically change its structure.
    """
    # Settings
    settings = load_settings()
    save_settings(settings)  # ensures new defaults propagate

    # Logging
    logcfg = read_log_config()
    write_log_config(logcfg)

    # TQDM
    os.environ["TQDM_DISABLE"] = "1"
