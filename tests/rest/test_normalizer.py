from __future__ import annotations

import pytest

from expo_jbm329.services.rest.normalizer import (
    RestNormalizeError,
    normalize_json_to_df,
)


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
