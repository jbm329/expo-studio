from __future__ import annotations

import pandas as pd
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

