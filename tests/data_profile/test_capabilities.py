from __future__ import annotations

from types import SimpleNamespace

from expo_jbm329.services.data_profile.capabilities import infer_series_capabilities


def test_infer_series_capabilities_for_numeric_and_datetime():
    numeric = SimpleNamespace(
        semantic_dtype="float",
        has_time_component=False,
        can_be_int=True,
        can_be_float=True,
        can_be_datetime=False,
        is_year_like=False,
        can_be_bool=False,
        cardinality_ratio=None,
    )
    caps = infer_series_capabilities(numeric, "object")

    assert caps.can_fill_numeric is True
    assert caps.can_filter_numeric is True
    assert caps.can_convert_to_int is True
    assert caps.can_convert_to_float is True
    assert caps.can_convert_to_string is True


def test_infer_series_capabilities_for_category_and_datetime():
    sem = SimpleNamespace(
        semantic_dtype="category",
        has_time_component=True,
        can_be_int=False,
        can_be_float=False,
        can_be_datetime=True,
        is_year_like=False,
        can_be_bool=False,
        cardinality_ratio=0.2,
    )
    caps = infer_series_capabilities(sem, "string")

    assert caps.can_clean_text is True
    assert caps.can_regex_text is True
    assert caps.can_convert_to_category is True
    assert caps.can_edit_categories is True
