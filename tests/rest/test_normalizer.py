from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from expo_jbm329.services.rest.normalizer import (
    RestNormalizeCancelledError,
    RestNormalizeError,
    normalize_json_payloads_to_df,
    normalize_json_to_df,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def test_normalize_json_to_df_handles_list_and_dict_payloads():
    df1 = normalize_json_to_df([{"a": 1}, {"a": 2}])
    df2 = normalize_json_to_df({"a": 1})

    assert list(df1.columns) == ["a"]
    assert df2.iloc[0]["a"] == 1


def test_normalize_json_to_df_supports_response_path():
    payload = {"data": {"items": [{"a": 1}, {"a": 2}]}}
    df = normalize_json_to_df(payload, response_path="data.items")

    assert len(df) == 2


def test_normalize_json_to_df_rejects_unsupported_root():
    with pytest.raises(RestNormalizeError):
        normalize_json_to_df("bad")


def test_normalize_json_to_df_uses_friendly_labels_for_coded_dimensions():
    payload = {
        "class": "dataset",
        "id": ["Kon", "Tid"],
        "size": [2, 1],
        "value": [10, 20],
        "dimension": {
            "Kon": {
                "label": "kön",
                "category": {
                    "index": {"1": 0, "2": 1},
                    "label": {"1": "män", "2": "kvinnor"},
                },
            },
            "Tid": {
                "label": "månad",
                "category": {
                    "index": {"2026M01": 0},
                    "label": {"2026M01": "2026M01"},
                },
            },
        },
    }

    df = normalize_json_to_df(payload)

    assert df["kön"].tolist() == ["män", "kvinnor"]
    assert df["månad"].tolist() == ["2026M01", "2026M01"]
    assert "Kon_label" not in df.columns


@pytest.mark.parametrize(
    "payload",
    [
        [{"value": 2**53 + 1, "flag": True}, {"value": None, "flag": None}],
        {"value": [2**53 + 1, None], "flag": [True, None]},
        [{"nested": {"value": 2**53 + 1, "flag": True}}, {"nested": {}}],
    ],
)
def test_rest_nullable_values_preserve_raw_precision(payload: object) -> None:
    original = deepcopy(payload)
    result = normalize_json_to_df(payload)
    assert payload == original
    assert result.dtypes.astype(str).tolist() == ["Int64", "boolean"]
    assert result.iloc[0, 0] == 2**53 + 1
    assert result.iloc[:, 0].isna().tolist() == [False, True]
    assert result.iloc[:, 1].isna().tolist() == [False, True]


def test_rest_response_path_preserves_unsigned_values_and_inputs() -> None:
    payload = {"data": [[{"value": 2**64 - 1}, {"value": None}]]}
    result = normalize_json_to_df(payload, response_path="data.0")
    assert str(result["value"].dtype) == "UInt64"
    assert result["value"].iloc[0] == 2**64 - 1
    assert payload["data"][0][0]["value"] == 2**64 - 1


@pytest.mark.parametrize(
    "payload",
    [
        [{"value": 1.0}, {"value": None}],
        [{"value": 1}, {"value": "text"}, {"value": None}],
        [{"value": True}, {"value": 1}, {"value": None}],
        [{"value": "001"}, {}],
        [{"value": None}, {"value": None}],
        [{"nested": {"float": 1.0, "list": [1, None]}}, {"nested": None}],
        [{"n.x": "flat", "n": {"x": "nested", "deep": {"value": 1.0}}}],
        [{"n": {"x": "nested"}, "n.x": "flat"}],
        [{"": {"value": 1.0}, "n": {"": {"x": "text"}}}],
        [{"empty": {}}, {}],
        [None, 1, "text"],
        [[1, 2], [3]],
        [],
        {"value": 1, "flag": True},
        {"list": [1, None], "other": "text"},
    ],
)
def test_rest_flattening_retains_legacy_unrelated_inference(payload: object) -> None:
    expected = pd.json_normalize(payload)
    pd.testing.assert_frame_equal(normalize_json_to_df(payload), expected)


@pytest.mark.parametrize(
    "payload",
    [
        {"value": [1.0, None], "text": ["001", None]},
        {"value": [None, None]},
        {"value": []},
        {},
    ],
)
def test_rest_dict_of_lists_retains_legacy_unrelated_inference(payload: dict[str, object]) -> None:
    pd.testing.assert_frame_equal(normalize_json_to_df(payload), pd.DataFrame(payload))


def jsonstat(values: list[object]) -> dict[str, object]:
    return {
        "class": "dataset",
        "id": ["category"],
        "value": values,
        "dimension": {
            "category": {"label": "Category", "category": {"index": {str(i): i for i in range(len(values))}}}
        },
    }


@pytest.mark.parametrize(
    ("values", "dtype"),
    [
        ([2**53 + 1, None], "Int64"),
        ([2**64 - 1, None], "UInt64"),
        ([True, None], "boolean"),
        ([1, 2], "int64"),
        ([True, False], "bool"),
        ([1.0, None], "float64"),
        ([None, None], "object"),
    ],
)
def test_jsonstat_preserves_missing_only_types(values: list[object], dtype: str) -> None:
    result = normalize_json_to_df(jsonstat(values))
    assert str(result["Value"].dtype) == dtype
    assert result.columns.tolist() == ["category", "Value"]
    if values[0] is not None:
        assert result["Value"].iloc[0] == values[0]


@pytest.mark.parametrize(
    ("pages", "dtype", "first"),
    [
        ([[{"value": 2**53 + 1}], [{"value": None}]], "Int64", 2**53 + 1),
        ([[{"value": None}], [{"value": 2**53 + 1}]], "Int64", None),
        ([[{"value": 2**64 - 1}], [{"value": -1}]], "object", 2**64 - 1),
        ([[{"value": 2**64 - 1}], [{"value": -1}, {"value": None}]], "object", 2**64 - 1),
        ([[{"value": 2**64}], [{"value": None}]], "object", 2**64),
        ([[{"value": True}], [{"other": "text"}]], "boolean", True),
        ([[{"value": 1}], [{"value": 2}]], "int64", 1),
        ([[{"value": 1.0}], [{"value": None}]], "float64", 1.0),
        ([[{"value": 1.0}], [{"value": 2}]], "float64", 1.0),
        ([[], [{"value": 1}]], "int64", 1),
    ],
)
def test_paginated_rest_uses_final_raw_column_evidence(pages: list[object], dtype: str, first: object) -> None:
    result = normalize_json_payloads_to_df(pages)
    assert str(result["value"].dtype) == dtype
    if first is None:
        assert pd.isna(result["value"].iloc[0])
        assert result["value"].iloc[1] == 2**53 + 1
    else:
        assert result["value"].iloc[0] == first
    assert isinstance(result.index, pd.RangeIndex)


def test_jsonstat_pages_reconcile_missing_values() -> None:
    result = normalize_json_payloads_to_df([jsonstat([2**53 + 1]), jsonstat([None])])
    assert str(result["Value"].dtype) == "Int64"
    assert result["Value"].iloc[0] == 2**53 + 1


def test_dict_of_lists_pages_reconcile_missing_values() -> None:
    result = normalize_json_payloads_to_df([{"value": [2**53 + 1], "flag": [True]}, {"value": [None], "flag": [None]}])
    assert result.dtypes.astype(str).tolist() == ["Int64", "boolean"]
    assert result["value"].iloc[0] == 2**53 + 1


@pytest.mark.parametrize(
    "pages",
    [
        [[{"value": 1.0, "text": "first"}], [{"text": "second"}]],
        [[{"value": 1, "text": "first"}], [{"value": "mixed", "text": None}]],
        [[], [{"value": None}]],
        [[{"value": None}], [{"value": None}]],
    ],
)
def test_paginated_rest_unrelated_inference_matches_legacy(pages: list[object]) -> None:
    expected = pd.concat([pd.json_normalize(page) for page in pages], ignore_index=True)
    pd.testing.assert_frame_equal(normalize_json_payloads_to_df(pages), expected)


@pytest.mark.parametrize(
    "normalize",
    [
        lambda cancel: normalize_json_payloads_to_df([[{"nested": {"value": 1}}]], cancel_cb=cancel),
        lambda cancel: normalize_json_payloads_to_df([jsonstat([1, None])], cancel_cb=cancel),
    ],
)
def test_normalization_cancellation_is_checked_throughout(normalize: Callable[..., pd.DataFrame]) -> None:
    count = 0

    def count_checks() -> bool:
        nonlocal count
        count += 1
        return False

    normalize(count_checks)
    assert count > 3
    for boundary in range(count):
        checks = iter([False] * boundary)
        with pytest.raises(RestNormalizeCancelledError):
            normalize(lambda checks=checks: next(checks, True))
