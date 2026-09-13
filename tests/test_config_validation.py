# tests/test_config_validation.py
from __future__ import annotations

from expo_jbm329.app.settings.config_store import (
    DEFAULT_SETTINGS,
    _validate_settings_inplace,
    merge_defaults,
)


def test_settings_validation_bounds():
    cfg = merge_defaults(DEFAULT_SETTINGS, {})
    # gen_top_n has min_value=1, no max_value clamp currently in _validate_settings_inplace
    cfg["workbench"]["gen_top_n"] = 0
    cfg["excel"]["max_rows_per_sheet"] = 2_000_000

    _validate_settings_inplace(cfg)

    assert cfg["workbench"]["gen_top_n"] == 1
    assert cfg["excel"]["max_rows_per_sheet"] == 1_048_576


def test_settings_validation_chunk_sizes():
    cfg = merge_defaults(DEFAULT_SETTINGS, {})

    cfg["csv"]["read_chunk_size_rows"] = -100
    cfg["excel"]["chunk_size_rows"] = 0

    _validate_settings_inplace(cfg)

    assert cfg["csv"]["read_chunk_size_rows"] == 1
    assert cfg["excel"]["chunk_size_rows"] == 1


def test_settings_validation_file_format_behaviour():
    cfg = merge_defaults(DEFAULT_SETTINGS, {})
    cfg["file_format_behaviour"]["csv"] = "INVALID"

    _validate_settings_inplace(cfg)

    assert cfg["file_format_behaviour"]["csv"] == DEFAULT_SETTINGS["file_format_behaviour"]["csv"]
