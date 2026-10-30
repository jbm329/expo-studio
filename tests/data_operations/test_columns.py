from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.columns import (
    join_columns,
    move_column,
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


@pytest.mark.parametrize(
    ("source_index", "destination_index", "expected_columns"),
    [
        (1, 2, ["a", "c", "b", "d"]),
        (2, 1, ["a", "c", "b", "d"]),
        (2, 0, ["c", "a", "b", "d"]),
        (1, 3, ["a", "c", "d", "b"]),
        (0, 3, ["b", "c", "d", "a"]),
        (3, 0, ["d", "a", "b", "c"]),
        (1, 1, ["a", "b", "c", "d"]),
    ],
)
def test_move_column_preserves_data_and_metadata(
    source_index: int, destination_index: int, expected_columns: list[str]
) -> None:
    df = pd.DataFrame(
        {
            "a": pd.array([1, None, 3], dtype="Int64"),
            "b": pd.array(["x", None, "z"], dtype="string"),
            "c": pd.Categorical(["low", "high", None], categories=["low", "high"], ordered=True),
            "d": pd.to_datetime(["2026-01-01", None, "2026-01-03"], utc=True),
        },
        index=pd.Index([30, 10, 20], name="row"),
    )
    df.columns.name = "fields"
    df.attrs = {"dataset": "source", "details": {"units": ["count"]}}
    original = df.copy(deep=True)

    out = move_column(df, source_index, destination_index)

    assert out is not df
    pd.testing.assert_frame_equal(out, original.loc[:, expected_columns])
    pd.testing.assert_frame_equal(df, original)
    assert out.attrs == original.attrs
    assert df.attrs == original.attrs

    out.iloc[0, out.columns.get_loc("a")] = 99
    out.attrs["details"]["units"].append("changed")
    pd.testing.assert_frame_equal(df, original)
    assert df.attrs == original.attrs


def test_move_column_single_column_returns_independent_copy() -> None:
    df = pd.DataFrame({"a": [1, 2]})

    out = move_column(df, 0, 0)

    assert out is not df
    pd.testing.assert_frame_equal(out, df)
    out.iloc[0, 0] = 99
    assert df.iloc[0, 0] == 1


def test_move_column_zero_rows_preserves_dtypes() -> None:
    df = pd.DataFrame({"a": pd.Series(dtype="Int64"), "b": pd.Series(dtype="string"), "c": pd.Series(dtype="boolean")})
    original = df.copy(deep=True)

    out = move_column(df, 0, 2)

    pd.testing.assert_frame_equal(out, original.loc[:, ["b", "c", "a"]])
    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize("column_labels", [["same", "other", "same"], [10, 20, 30], ["same", 10, "same"]])
def test_move_column_uses_positions_not_labels(column_labels: list[str | int]) -> None:
    df = pd.DataFrame([[1, 2, 3], [4, 5, 6]], columns=column_labels)
    original = df.copy(deep=True)
    expected = pd.DataFrame(
        [[2, 3, 1], [5, 6, 4]],
        columns=[column_labels[1], column_labels[2], column_labels[0]],
    )

    out = move_column(df, 0, 2)

    pd.testing.assert_frame_equal(out, expected)
    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize(
    ("source_index", "destination_index", "message"),
    [
        (-1, 0, "Invalid source column index: -1"),
        (2, 0, "Invalid source column index: 2"),
        (0, -1, "Invalid destination column index: -1"),
        (0, 2, "Invalid destination column index: 2"),
    ],
)
def test_move_column_rejects_invalid_indices(source_index: int, destination_index: int, message: str) -> None:
    df = pd.DataFrame({"a": [1], "b": [2]})
    original = df.copy(deep=True)

    with pytest.raises(IndexError, match=message):
        move_column(df, source_index, destination_index)

    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize("row_count", [0, 2])
def test_move_column_rejects_frame_without_columns(row_count: int) -> None:
    df = pd.DataFrame(index=pd.RangeIndex(row_count))
    original = df.copy(deep=True)

    with pytest.raises(IndexError, match="Invalid source column index: 0"):
        move_column(df, 0, 0)

    pd.testing.assert_frame_equal(df, original)


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
