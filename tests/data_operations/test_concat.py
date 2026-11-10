"""Tests for dataframe concatenation operations in data_operations.concat."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.data_operations.concat import ConcatRequest, concat_dataframes


def test_concat_dataframes_basic():
    """Test basic concatenation (UNION ALL behavior)."""
    df1 = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})
    df2 = pd.DataFrame({"id": [3, 4], "name": ["Charlie", "David"]})

    req = ConcatRequest(left=df1, right=df2, remove_duplicates=False)
    result = concat_dataframes(req)

    assert len(result) == 4
    assert list(result["id"]) == [1, 2, 3, 4]
    assert list(result["name"]) == ["Alice", "Bob", "Charlie", "David"]


def test_concat_dataframes_with_duplicates():
    """Test concatenation with deduplication (UNION behavior)."""
    df1 = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})
    df2 = pd.DataFrame({"id": [2, 3], "name": ["Bob", "Charlie"]})  # Row 2 is duplicate

    # Without deduplication
    req_all = ConcatRequest(left=df1, right=df2, remove_duplicates=False)
    result_all = concat_dataframes(req_all)
    assert len(result_all) == 4

    # With deduplication
    req_union = ConcatRequest(left=df1, right=df2, remove_duplicates=True)
    result_union = concat_dataframes(req_union)
    assert len(result_union) == 3
    assert list(result_union["id"]) == [1, 2, 3]


def test_concat_dataframes_different_columns():
    """Test concatenation of dataframes with different columns."""
    df1 = pd.DataFrame({"id": [1], "name": ["Alice"]})
    df2 = pd.DataFrame({"id": [2], "age": [30]})

    req = ConcatRequest(left=df1, right=df2)
    result = concat_dataframes(req)

    assert len(result) == 2
    assert "name" in result.columns
    assert "age" in result.columns
    assert pd.isna(result.loc[1, "name"])
    assert pd.isna(result.loc[0, "age"])


def test_concat_dataframes_preserves_order():
    """Test that concatenation preserves row order."""
    df1 = pd.DataFrame({"a": [1, 2]})
    df2 = pd.DataFrame({"a": [3, 4]})

    req = ConcatRequest(left=df1, right=df2)
    result = concat_dataframes(req)

    assert list(result["a"]) == [1, 2, 3, 4]


@pytest.mark.parametrize(
    "dtype,expected_dtype",
    [
        ("int8", "Int8"),
        ("int16", "Int16"),
        ("int32", "Int32"),
        ("int64", "Int64"),
        ("uint8", "UInt8"),
        ("uint16", "UInt16"),
        ("uint32", "UInt32"),
        ("uint64", "UInt64"),
        ("bool", "boolean"),
    ],
)
@pytest.mark.parametrize("source_first", [False, True])
@pytest.mark.parametrize("source_empty,other_empty", [(False, False), (True, False), (False, True), (True, True)])
def test_one_sided_numpy_columns_preserve_precision_and_nullable_schema(
    dtype: str,
    expected_dtype: str,
    source_first: bool,
    source_empty: bool,
    other_empty: bool,
) -> None:
    values = [True, False] if dtype == "bool" else [int(np.iinfo(dtype).min), int(np.iinfo(dtype).max)]
    source = pd.DataFrame({"value": pd.Series(values, dtype=dtype)})
    source.index = pd.Index([7, 7], name="original")
    other = pd.DataFrame({"other": ["a", "b"]}, index=pd.Index([9, 9], name="other_index"))
    if source_empty:
        source = source.iloc[:0]
    if other_empty:
        other = other.iloc[:0]
    left, right = (source, other) if source_first else (other, source)
    originals = (left.copy(deep=True), right.copy(deep=True))

    result = concat_dataframes(ConcatRequest(left, right))

    expected_values = source["value"].tolist()
    absent_values = [pd.NA] * len(other)
    expected = pd.Series(
        expected_values + absent_values if source_first else absent_values + expected_values,
        name="value",
        dtype=expected_dtype,
    )
    pd.testing.assert_series_equal(result["value"], expected)
    assert list(result.columns) == (["value", "other"] if source_first else ["other", "value"])
    pd.testing.assert_index_equal(result.index, pd.RangeIndex(len(left) + len(right)))
    pd.testing.assert_frame_equal(left, originals[0])
    pd.testing.assert_frame_equal(right, originals[1])


@pytest.mark.parametrize("source_first", [False, True])
@pytest.mark.parametrize(
    "dtype,values",
    [
        ("Int64", [2**62 + 1, None]),
        ("UInt64", [2**64 - 1, None]),
        ("boolean", [False, None]),
        ("Float64", [1.5, None]),
        ("string", ["text", None]),
        ("category", ["a", None]),
        ("datetime64[s]", ["2500-01-01", None]),
        ("datetime64[ns, Europe/Stockholm]", ["2024-01-01", None]),
        ("timedelta64[ns]", [pd.Timedelta(days=1), None]),
        ("period[M]", ["2024-01", None]),
        ("int64[pyarrow]", [2**62 + 1, None]),
        ("bool[pyarrow]", [True, None]),
    ],
)
@pytest.mark.parametrize("all_null", [False, True])
def test_one_sided_extension_columns_and_source_nulls_are_preserved(
    source_first: bool,
    dtype: str,
    values: list[object],
    all_null: bool,
) -> None:
    series = pd.Series([None, None] if all_null else values, name="value", dtype=dtype)
    source = series.to_frame()
    if dtype == "category":
        source["value"] = source["value"].cat.set_categories(["a", "b"], ordered=True)
    other = pd.DataFrame({"other": [1]})
    left, right = (source, other) if source_first else (other, source)
    original = source.copy(deep=True)
    result = concat_dataframes(ConcatRequest(left, right))
    expected = pd.concat(
        [source["value"], pd.Series([None], name="value", dtype=source["value"].dtype)]
        if source_first
        else [pd.Series([None], name="value", dtype=source["value"].dtype), source["value"]],
        ignore_index=True,
    )
    pd.testing.assert_series_equal(result["value"], expected)
    pd.testing.assert_frame_equal(source, original)


@pytest.mark.parametrize("remove_duplicates", [False, True])
def test_nullable_columns_on_both_sides_keep_column_order_and_deduplication(remove_duplicates: bool) -> None:
    left = pd.DataFrame({
        "id": [1, 1],
        "left_value": pd.Series([2**62 + 1, 2**62 + 1], dtype="int64"),
        "left_flag": [False, False],
    })
    right = pd.DataFrame({
        "right_flag": [True, True],
        "id": [2, 2],
        "right_value": pd.Series([2**64 - 1, 2**64 - 1], dtype="uint64"),
    })
    original_left, original_right = left.copy(deep=True), right.copy(deep=True)
    result = concat_dataframes(ConcatRequest(left, right, remove_duplicates=remove_duplicates))
    expected = pd.DataFrame({
        "id": [1, 1, 2, 2],
        "left_value": pd.Series([2**62 + 1, 2**62 + 1, None, None], dtype="Int64"),
        "left_flag": pd.Series([False, False, None, None], dtype="boolean"),
        "right_flag": pd.Series([None, None, True, True], dtype="boolean"),
        "right_value": pd.Series([None, None, 2**64 - 1, 2**64 - 1], dtype="UInt64"),
    })
    if remove_duplicates:
        expected = expected.iloc[[0, 2]].reset_index(drop=True)
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(left, original_left)
    pd.testing.assert_frame_equal(right, original_right)


@pytest.mark.parametrize("different_layout", [False, True])
@pytest.mark.parametrize(
    "left_dtype,right_dtype,left_value,right_value",
    [
        ("int64", "int64", 2**62 + 1, 2**62 + 3),
        ("int32", "int64", 1, 2**62 + 1),
        ("int64", "float64", 2**62 + 1, 1.5),
        ("int64", "uint64", -1, 2**64 - 1),
        ("bool", "int64", True, 2),
    ],
)
def test_shared_columns_keep_existing_pandas_reconciliation(
    different_layout: bool,
    left_dtype: str,
    right_dtype: str,
    left_value: int | bool,
    right_value: float,
) -> None:
    left = pd.DataFrame({"shared": pd.Series([left_value], dtype=left_dtype)})
    right = pd.DataFrame({"shared": pd.Series([right_value], dtype=right_dtype)})
    if different_layout:
        right["other"] = ["text"]
    expected = pd.concat([left, right], ignore_index=True, sort=False)
    pd.testing.assert_frame_equal(concat_dataframes(ConcatRequest(left, right)), expected)


def test_identical_duplicate_column_layout_keeps_existing_behavior() -> None:
    left = pd.DataFrame([[1, 2]], columns=["a", "a"])
    right = pd.DataFrame([[3, 4]], columns=["a", "a"])
    expected = pd.concat([left, right], ignore_index=True, sort=False)
    pd.testing.assert_frame_equal(concat_dataframes(ConcatRequest(left, right)), expected)


@pytest.mark.parametrize("duplicate_first", [False, True])
def test_different_duplicate_column_layout_is_explicitly_rejected(duplicate_first: bool) -> None:
    duplicate = pd.DataFrame([[1, 2]], columns=["a", "a"])
    other = pd.DataFrame({"b": [3]})
    left, right = (duplicate, other) if duplicate_first else (other, duplicate)
    with pytest.raises(ValueError, match="requires unique column names"):
        concat_dataframes(ConcatRequest(left, right))
