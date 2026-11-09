"""Tests for dataframe join operations in data_operations.joins."""

from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.joins import (
    JoinHow,
    JoinRequest,
    concat_columns,
    concat_rows,
    detect_join_keys,
    join_dataframes,
)


@pytest.mark.parametrize("how", ["inner", "left", "right", "outer"])
def test_join_preserves_integer_boolean_values_and_sources(how: JoinHow) -> None:
    """Prepare only the nullable side and preserve merge semantics and inputs."""
    left = pd.DataFrame({"id": [1, 2], "value": [2**62 + 1, 2**62 + 3], "flag": [True, False]})
    right = pd.DataFrame({"other_id": [2, 3], "value": [2**62 + 5, 2**62 + 7], "flag": [False, True]})
    original_left = left.copy(deep=True)
    original_right = right.copy(deep=True)
    result = join_dataframes(JoinRequest(left, right, ["id"], ["other_id"], how=how))

    for side, frame, key, missing_status, nullable in [
        ("left", left, "id", "right_only", how in {"right", "outer"}),
        ("right", right, "other_id", "left_only", how in {"left", "outer"}),
    ]:
        assert str(result[key].dtype) == ("Int64" if nullable else "int64")
        assert str(result[f"value_{side}"].dtype) == ("Int64" if nullable else "int64")
        assert str(result[f"flag_{side}"].dtype) == ("boolean" if nullable else "bool")
        present = result["join_status"] != missing_status
        for _, row in result.loc[present].iterrows():
            source = frame.loc[frame[key] == row[key]].iloc[0]
            assert row[f"value_{side}"] == source["value"]
            assert row[f"flag_{side}"] == source["flag"]
        assert result.loc[~present, [key, f"value_{side}", f"flag_{side}"]].isna().all().all()

    expected = left.merge(
        right, left_on="id", right_on="other_id", how=how, suffixes=("_left", "_right"), indicator="join_status"
    )
    assert list(result.columns) == list(expected.columns)
    pd.testing.assert_series_equal(result["join_status"], expected["join_status"])
    pd.testing.assert_frame_equal(left, original_left)
    pd.testing.assert_frame_equal(right, original_right)


@pytest.mark.parametrize("how", ["left", "right", "outer"])
def test_join_full_match_keeps_configured_nullable_dtype(how: JoinHow) -> None:
    """Output dtypes do not depend on whether rows happen to match."""
    left = pd.DataFrame({"id": [1, 2], "value": [3, 4]})
    right = pd.DataFrame({"id": [1, 2], "value": [5, 6]})
    result = join_dataframes(JoinRequest(left, right, ["id"], ["id"], how=how))
    assert str(result["value_left"].dtype) == ("Int64" if how in {"right", "outer"} else "int64")
    assert str(result["value_right"].dtype) == ("Int64" if how in {"left", "outer"} else "int64")
    assert not result.isna().any().any()


@pytest.mark.parametrize("dtype", ["int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"])
def test_join_preserves_integer_width_and_signedness(dtype: str) -> None:
    """Nullable conversion must not narrow unsigned or smaller integers."""
    value = 2**64 - 1 if dtype == "uint64" else 10
    left = pd.DataFrame({"id": [1, 2]})
    right = pd.DataFrame({"id": [2], "value": pd.Series([value], dtype=dtype)})
    result = join_dataframes(JoinRequest(left, right, ["id"], ["id"], how="left"))
    expected_dtype = dtype.replace("uint", "UInt").replace("int", "Int")
    assert str(result["value"].dtype) == expected_dtype
    assert result.loc[1, "value"] == value
    assert pd.isna(result.loc[0, "value"])


@pytest.mark.parametrize("how", ["inner", "left", "right", "outer"])
def test_join_preserves_existing_nullable_dtypes_and_nulls(how: JoinHow) -> None:
    """Existing extension dtypes and matched source NULLs remain intact."""
    left = pd.DataFrame({"id": [1, 2, 3]})
    right = pd.DataFrame({
        "id": [2, 3],
        "value": pd.Series([pd.NA, 5], dtype="Int32"),
        "flag": pd.Series([pd.NA, True], dtype="boolean"),
    })
    result = join_dataframes(JoinRequest(left, right, ["id"], ["id"], how=how))
    assert str(result["value"].dtype) == "Int32"
    assert str(result["flag"].dtype) == "boolean"
    assert result.loc[result["id"] == 2, ["value", "flag"]].isna().all().all()


def test_join_prepares_selected_columns_and_keys_without_changing_suffixes() -> None:
    """Selection controls preparation, not output shape or suffix naming."""
    left = pd.DataFrame({"id": [1, 2], "value": [3, 4]})
    right = pd.DataFrame({"other_id": [2], "value": [5], "unused": [6], "flag": [True]})
    result = join_dataframes(
        JoinRequest(
            left, right, ["id"], ["other_id"], how="left", right_columns=["value", "flag"], suffixes=("_A", "_B")
        )
    )
    assert list(result.columns) == ["id", "value_A", "other_id", "value_B", "unused", "flag", "join_status"]
    assert str(result["value_B"].dtype) == "Int64"
    assert str(result["other_id"].dtype) == "Int64"
    assert str(result["flag"].dtype) == "boolean"
    assert str(result["unused"].dtype) == "float64"


@pytest.mark.parametrize("how", ["left", "right", "outer"])
def test_join_preserves_large_shared_multikey_values(how: JoinHow) -> None:
    """Shared join keys retain precision while pandas coalesces unmatched keys."""
    large = 2**62 + 1
    left = pd.DataFrame({"id": [large, large + 2], "part": [1, 2], "value": [3, 4]})
    right = pd.DataFrame({"id": [large + 2, large + 4], "part": [2, 3], "value": [5, 6]})
    result = join_dataframes(JoinRequest(left, right, ["id", "part"], ["id", "part"], how=how))
    expected_keys = {
        "left": [large, large + 2],
        "right": [large + 2, large + 4],
        "outer": [large, large + 2, large + 4],
    }
    assert sorted(result["id"].tolist()) == expected_keys[how]
    assert not result[["id", "part"]].isna().any().any()


@pytest.mark.parametrize("how", ["left", "right", "outer"])
def test_join_empty_nullable_side_keeps_types(how: JoinHow) -> None:
    """Empty inputs retain their declared integer and boolean schema."""
    populated = pd.DataFrame({"id": [1], "value": [5], "flag": [True]})
    empty = populated.iloc[:0]
    left, right = (empty, populated) if how == "right" else (populated, empty)
    result = join_dataframes(JoinRequest(left, right, ["id"], ["id"], how=how))
    side = "left" if how == "right" else "right"
    assert len(result) == 1
    assert str(result[f"value_{side}"].dtype) == "Int64"
    assert str(result[f"flag_{side}"].dtype) == "boolean"
    assert result[[f"value_{side}", f"flag_{side}"]].isna().all().all()


def test_join_leaves_other_column_types_unchanged() -> None:
    """Only numpy integers and booleans require nullable preparation."""
    left = pd.DataFrame({"id": [1, 2, 3]})
    right = pd.DataFrame({
        "id": [2, 3],
        "float": pd.Series([1.5, 2.5], dtype="float32"),
        "nullable_float": pd.Series([pd.NA, 2.5], dtype="Float64"),
        "text": pd.Series(["a", pd.NA], dtype="string"),
        "object": pd.Series(["b", None], dtype="object"),
        "category": pd.Series(["a", "b"], dtype="category"),
        "datetime": pd.to_datetime(["2020-01-01", "2020-01-02"], utc=True),
        "duration": pd.to_timedelta([1, 2], unit="D"),
        "arrow_integer": pd.Series([pd.NA, 2**62 + 1], dtype="int64[pyarrow]"),
    })
    result = join_dataframes(JoinRequest(left, right, ["id"], ["id"], how="left"))
    expected = left.merge(right, on="id", how="left", indicator="join_status")
    pd.testing.assert_frame_equal(result, expected)


def test_join_many_to_many_preserves_exact_values_and_row_count() -> None:
    """Nullable preparation does not alter duplicate-key matching."""
    left = pd.DataFrame({"id": [1, 1, 2]})
    right = pd.DataFrame({"id": [1, 1, 3], "value": [2**62 + 1, 2**62 + 3, 2**62 + 5]})
    result = join_dataframes(JoinRequest(left, right, ["id"], ["id"], how="outer"))
    assert len(result) == 6
    assert result.loc[result["join_status"] == "both", "value"].tolist() == [
        2**62 + 1,
        2**62 + 3,
        2**62 + 1,
        2**62 + 3,
    ]


@pytest.fixture
def left_df() -> pd.DataFrame:
    """Fixture for left dataframe."""
    return pd.DataFrame({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"], "age": [25, 30, 35]})


@pytest.fixture
def right_df() -> pd.DataFrame:
    """Fixture for right dataframe."""
    return pd.DataFrame({"user_id": [2, 3, 4], "city": ["New York", "London", "Paris"], "age": [30, 35, 40]})


def test_join_dataframes_inner(left_df, right_df):
    """Test inner join."""
    cfg = JoinRequest(left=left_df, right=right_df, left_on=["id"], right_on=["user_id"], how="inner")
    result = join_dataframes(cfg)

    assert len(result) == 2
    assert list(result["id"]) == [2, 3]
    assert "city" in result.columns
    # Check suffixes for conflicting 'age' column
    assert "age_left" in result.columns
    assert "age_right" in result.columns


def test_join_dataframes_left(left_df, right_df):
    """Test left join."""
    cfg = JoinRequest(left=left_df, right=right_df, left_on=["id"], right_on=["user_id"], how="left")
    result = join_dataframes(cfg)

    assert len(result) == 3
    assert list(result["id"]) == [1, 2, 3]
    assert pd.isna(result.loc[result["id"] == 1, "city"]).all()


def test_join_dataframes_mismatched_keys(left_df, right_df):
    """Test error when key lengths mismatch."""
    cfg = JoinRequest(left=left_df, right=right_df, left_on=["id", "name"], right_on=["user_id"], how="inner")
    with pytest.raises(ValueError, match="left_on and right_on must have same length"):
        join_dataframes(cfg)


def test_detect_join_keys():
    """Test join key detection logic."""
    df1 = pd.DataFrame({
        "id": [1, 2],
        "name": ["a", "b"],
        "score": [1.1, 2.2],
        "cat": pd.Series(["x", "y"], dtype="category"),
        "only1": [1, 1],
    })
    df2 = pd.DataFrame({
        "id": [1, 3],  # numeric match
        "name": [1, 2],  # name matches but dtype doesn't (str vs int)
        "score": [3.3, 4.4],  # numeric match
        "cat": pd.Series(["x", "z"], dtype="category"),  # categorical match
        "only2": [2, 2],
    })

    # In df1 'name' is object/string, in df2 'name' is int64 (by default).
    # detect_join_keys should catch: id, score, cat
    keys = detect_join_keys(df1, df2)

    assert "id" in keys
    assert "score" in keys
    assert "cat" in keys
    assert "name" not in keys
    assert "only1" not in keys
    assert "only2" not in keys


def test_concat_rows():
    """Test row-wise concatenation."""
    df1 = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    df2 = pd.DataFrame({"a": [5, 6], "b": [7, 8]})

    result = concat_rows(df1, df2)

    assert len(result) == 4
    assert list(result["a"]) == [1, 2, 5, 6]
    # Check index is reset
    assert list(result.index) == [0, 1, 2, 3]


def test_concat_rows_empty_error():
    """Test error when no dataframes provided to concat_rows."""
    with pytest.raises(ValueError, match="No dataframes were provided"):
        concat_rows()


def test_concat_columns():
    """Test column-wise concatenation."""
    df1 = pd.DataFrame({"a": [1, 2]}, index=[0, 1])
    df2 = pd.DataFrame({"b": [3, 4]}, index=[0, 1])

    result = concat_columns(df1, df2)

    assert result.shape == (2, 2)
    assert "a" in result.columns
    assert "b" in result.columns


def test_concat_columns_empty_error():
    """Test error when no dataframes provided to concat_columns."""
    with pytest.raises(ValueError, match="No dataframes were provided"):
        concat_columns()
