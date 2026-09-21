# tests/test_config_merge.py
from __future__ import annotations

from expo_jbm329.app.settings.config_store import merge_defaults


def test_merge_defaults_flat():
    defaults = {"a": 1, "b": 2}
    user = {"b": 999}

    merged = merge_defaults(defaults, user)

    assert merged == {"a": 1, "b": 999}


def test_merge_defaults_nested():
    defaults = {
        "a": 1,
        "nested": {"x": 5, "y": 10},
    }
    user = {
        "nested": {"y": 99},  # override
    }

    merged = merge_defaults(defaults, user)

    assert merged["a"] == 1
    assert merged["nested"]["x"] == 5
    assert merged["nested"]["y"] == 99


def test_merge_defaults_user_extra_keys():
    defaults = {"a": 1}
    user = {"a": 2, "b": "extra"}

    merged = merge_defaults(defaults, user)

    assert merged["a"] == 2
    assert merged["b"] == "extra"
