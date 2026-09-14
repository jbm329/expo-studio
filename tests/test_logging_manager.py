# tests/test_logging_manager.py
from __future__ import annotations

import logging
from unittest.mock import patch

from expo_jbm329.app.settings.config_store import DEFAULT_LOG_CONFIG, write_log_config
from expo_jbm329.app.logging.logging_manager import LoggingManager


def test_logging_manager_basic_setup(tmp_path):
    cfg = DEFAULT_LOG_CONFIG.copy()
    write_log_config(cfg)

    manager = LoggingManager()

    # Mock file handler to avoid file I/O
    with patch("expo_jbm329.app.logging.logging_manager.RotatingFileHandler") as mock_file:
        mock_file.return_value.level = logging.INFO
        manager.setup()

    root = logging.getLogger()
    # At least file handler if configured
    assert len(root.handlers) >= 1
