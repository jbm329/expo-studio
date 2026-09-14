from __future__ import annotations

from expo_jbm329.app.settings.config_store import DEFAULT_SETTINGS, _validate_settings_inplace, merge_defaults


def test_settings_validation_clamps_numeric_bounds():
    cfg = merge_defaults(DEFAULT_SETTINGS, {})
    cfg["workbench"]["gen_top_n"] = -1
    cfg["excel"]["max_rows_per_sheet"] = 2_000_000

    _validate_settings_inplace(cfg)

    assert cfg["workbench"]["gen_top_n"] == 0
    assert cfg["excel"]["max_rows_per_sheet"] == 1_048_576


def test_settings_validation_normalizes_chunk_sizes_and_schema_cache():
    cfg = merge_defaults(DEFAULT_SETTINGS, {})
    cfg["csv"]["read_chunk_size_rows"] = -100
    cfg["csv"]["write_chunk_size_rows"] = 0
    cfg["excel"]["chunk_size_rows"] = 0
    cfg["schema_cache"]["ttl_seconds"] = 0
    cfg["schema_cache"]["prefetch_limit"] = -1
    cfg["schema_cache"]["prefetch_batch_size"] = 0

    _validate_settings_inplace(cfg)

    assert cfg["csv"]["read_chunk_size_rows"] == 1
    assert cfg["csv"]["write_chunk_size_rows"] == 1
    assert cfg["excel"]["chunk_size_rows"] == 1
    assert cfg["schema_cache"]["ttl_seconds"] == 1
    assert cfg["schema_cache"]["prefetch_limit"] == 0
    assert cfg["schema_cache"]["prefetch_batch_size"] == 1


def test_settings_validation_normalizes_strings_and_booleans():
    cfg = merge_defaults(DEFAULT_SETTINGS, {})
    cfg["workbench"]["language"] = "  de  "
    cfg["workbench"]["theme"] = "invalid"
    cfg["csv"]["default_encoding"] = "  UTF-16  "
    cfg["csv"]["sniff_delimiter"] = "yes"
    cfg["csv"]["default_sep"] = " ; "
    cfg["documents_dir"] = "  "

    _validate_settings_inplace(cfg)

    assert cfg["workbench"]["language"] == DEFAULT_SETTINGS["workbench"]["language"]
    assert cfg["workbench"]["theme"] == DEFAULT_SETTINGS["workbench"]["theme"]
    assert cfg["csv"]["default_encoding"] == "utf-16"
    assert cfg["csv"]["sniff_delimiter"] is True
    assert cfg["csv"]["default_sep"] == ";"
    assert cfg["documents_dir"] is None


def test_settings_validation_ensures_missing_blocks():
    cfg = {}

    _validate_settings_inplace(cfg)

    assert cfg["workbench"]["gen_top_n"] == DEFAULT_SETTINGS["workbench"]["gen_top_n"]
    assert cfg["csv"]["default_sep"] == DEFAULT_SETTINGS["csv"]["default_sep"]
    assert cfg["excel"]["streaming"] is True
