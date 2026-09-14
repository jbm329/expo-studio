from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.columns import (
    join_columns,
    rename_column,
    safe_drop_column,
    sort_dataframe,
    split_column,
)


def test_sort_dataframe_ascending():
    df = pd.DataFrame({"a": [3, 1, 2]})

    out = sort_dataframe(df, "a", ascending=True)

    assert out is not df
    assert out["a"].tolist() == [1, 2, 3]


def test_sort_dataframe_descending():
    df = pd.DataFrame({"a": [3, 1, 2]})

    out = sort_dataframe(df, "a", ascending=False)

    assert out["a"].tolist() == [3, 2, 1]


def test_sort_dataframe_invalid_column():
    df = pd.DataFrame({"a": [1]})

    with pytest.raises(KeyError):
        sort_dataframe(df, "missing")


def test_safe_drop_column_basic():
    df = pd.DataFrame({"a": [1], "b": [2]})

    out = safe_drop_column(df, 0)

    assert out is not df
    assert list(out.columns) == ["b"]


def test_safe_drop_column_invalid_index():
    df = pd.DataFrame({"a": [1]})

    with pytest.raises(IndexError):
        safe_drop_column(df, 1)


def test_rename_column_basic():
    df = pd.DataFrame({"a": [1], "b": [2]})

    out = rename_column(df, "a", "x")

    assert list(out.columns) == ["x", "b"]


def test_rename_column_existing_name():
    df = pd.DataFrame({"a": [1], "b": [2]})

    with pytest.raises(ValueError):
        rename_column(df, "a", "b")


def test_rename_column_missing_column():
    df = pd.DataFrame({"a": [1]})

    with pytest.raises(KeyError):
        rename_column(df, "missing", "x")


def test_split_column_first_keep_original():
    df = pd.DataFrame({"a": ["x-y"]})

    out = split_column(df, "a", "-", mode="first", keep_original=True)

    assert list(out.columns) == ["a", "a_1", "a_2"]
    assert out["a_1"].iloc[0] == "x"
    assert out["a_2"].iloc[0] == "y"
    assert str(out["a_1"].dtype) == "string"
    assert str(out["a_2"].dtype) == "string"


def test_split_column_last_replace_original():
    df = pd.DataFrame({"a": ["x-y-z"]})

    out = split_column(df, "a", "-", mode="last", keep_original=False)

    assert list(out.columns) == ["a_1", "a_2"]
    assert out["a_1"].iloc[0] == "x-y"
    assert out["a_2"].iloc[0] == "z"


def test_split_column_trims_whitespace_and_missing_parts():
    df = pd.DataFrame({"a": [" x - ", None]})

    out = split_column(df, "a", "-", keep_original=False)

    assert out["a_1"].iloc[0] == "x"
    assert out["a_2"].iloc[0] is pd.NA or pd.isna(out["a_2"].iloc[0])
    assert pd.isna(out["a_1"].iloc[1])
    assert pd.isna(out["a_2"].iloc[1])


def test_split_column_missing_column():
    df = pd.DataFrame({"a": ["x-y"]})

    with pytest.raises(KeyError):
        split_column(df, "missing", "-")


def test_split_column_empty_delimiter():
    df = pd.DataFrame({"a": ["x-y"]})

    with pytest.raises(ValueError):
        split_column(df, "a", "")


def test_join_columns_keep_original():
    df = pd.DataFrame({"a": ["x"], "b": ["y"]})

    out = join_columns(df, ["a", "b"], delimiter="-", keep_original=True)

    assert list(out.columns) == ["a", "b", "a_b"]
    assert out["a_b"].iloc[0] == "x-y"
    assert str(out["a_b"].dtype) == "string"


def test_join_columns_drop_original():
    df = pd.DataFrame({"a": ["x"], "b": ["y"]})

    out = join_columns(df, ["a", "b"], delimiter="-", keep_original=False)

    assert list(out.columns) == ["a_b"]
    assert out["a_b"].iloc[0] == "x-y"


def test_join_columns_custom_name():
    df = pd.DataFrame({"a": ["x"], "b": ["y"], "c": ["z"]})

    out = join_columns(df, ["a", "b"], delimiter="-", new_name="joined")

    assert list(out.columns) == ["a", "b", "joined", "c"]
    assert out["joined"].iloc[0] == "x-y"


def test_join_columns_trims_and_fills_missing():
    df = pd.DataFrame({"a": [" x "], "b": [None]})

    out = join_columns(df, ["a", "b"], delimiter="-", keep_original=False)

    assert out["a_b"].iloc[0] == "x-"


def test_join_columns_missing_column():
    df = pd.DataFrame({"a": ["x"]})

    with pytest.raises(KeyError):
        join_columns(df, ["a", "missing"])
