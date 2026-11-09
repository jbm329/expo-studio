"""Tests for dataframe join operations in data_operations.joins."""

from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.joins import (
    JoinFillValue,
    JoinHow,
    JoinRequest,
    UnmatchedFill,
    concat_columns,
    concat_rows,
    detect_join_keys,
    join_dataframes,
    validate_join_fill,
)


@pytest.mark.parametrize("how,side", [("left", "right"), ("right", "left"), ("outer", "left"), ("outer", "right")])
def test_unmatched_defaults_follow_source_side(how: JoinHow, side: str) -> None:
    """Overlapping columns receive defaults only when their source row is absent."""
    left = pd.DataFrame({"id": [1, 2], "value": [2**62 + 1, 2**62 + 3], "flag": [True, False]})
    right = pd.DataFrame({"id": [2, 3], "value": [2**62 + 5, 2**62 + 7], "flag": [False, True]})
    originals = (left.copy(deep=True), right.copy(deep=True))
    fills = {"value": UnmatchedFill(42), "flag": UnmatchedFill(False)}
    request = JoinRequest(
        left,
        right,
        ["id"],
        ["id"],
        how=how,
        left_fill=fills if side == "left" else {},
        right_fill=fills if side == "right" else {},
        suffixes=("_orders", "_customers"),
    )
    result = join_dataframes(request)
    suffix = "_orders" if side == "left" else "_customers"
    missing = result["join_status"] == ("right_only" if side == "left" else "left_only")
    assert result.loc[missing, f"value{suffix}"].tolist() == [42]
    assert result.loc[missing, f"flag{suffix}"].tolist() == [False]
    assert str(result[f"value{suffix}"].dtype) == "int64"
    assert str(result[f"flag{suffix}"].dtype) == "bool"
    source = left if side == "left" else right
    assert (
        result.loc[~missing, f"value{suffix}"].tolist()
        == source.loc[source["id"].isin(result.loc[~missing, "id"]), "value"].tolist()
    )
    pd.testing.assert_frame_equal(left, originals[0])
    pd.testing.assert_frame_equal(right, originals[1])


@pytest.mark.parametrize("dtype,value", [("Int64", 0), ("boolean", True), ("Float64", 0.0), ("string", "unknown")])
def test_defaults_preserve_nullable_source_nulls(dtype: str, value: JoinFillValue) -> None:
    """Matched source NULLs remain NULL, even when an unmatched default is configured."""
    left = pd.DataFrame({"id": [1, 2, 3]})
    right = pd.DataFrame({"id": [2, 3], "value": pd.Series([None, value], dtype=dtype)})
    result = join_dataframes(
        JoinRequest(left, right, ["id"], ["id"], how="left", right_fill={"value": UnmatchedFill(value)})
    )
    assert result.loc[0, "value"] == value
    assert pd.isna(result.loc[1, "value"])
    assert result["value"].dtype == right["value"].dtype


@pytest.mark.parametrize("dtype", ["int8", "uint64", "bool"])
def test_defaults_with_full_match_restore_original_numpy_dtype(dtype: str) -> None:
    """A configured default controls the dtype even without unmatched rows."""
    value = True if dtype == "bool" else 1
    right = pd.DataFrame({"id": [1], "value": pd.Series([value], dtype=dtype)})
    result = join_dataframes(
        JoinRequest(right[["id"]], right, ["id"], ["id"], how="left", right_fill={"value": UnmatchedFill(value)})
    )
    assert result["value"].dtype == right["value"].dtype


def test_null_default_and_empty_text_are_distinct() -> None:
    """Explicit NULL keeps missing values while empty text is a real default."""
    left = pd.DataFrame({"id": [1, 2]})
    right = pd.DataFrame({"id": [2], "null": ["x"], "empty": ["y"]})
    result = join_dataframes(
        JoinRequest(
            left,
            right,
            ["id"],
            ["id"],
            how="left",
            right_fill={"null": UnmatchedFill(), "empty": UnmatchedFill("")},
        )
    )
    assert pd.isna(result.loc[0, "null"])
    assert result.loc[0, "empty"] == ""


def test_category_default_extends_categories_without_mutating_input() -> None:
    """New text categories are appended, preserving ordering and genuine NULLs."""
    left = pd.DataFrame({"id": [1, 2, 3]})
    right = pd.DataFrame({
        "id": [2, 3],
        "value": pd.Series(pd.Categorical([None, "a"], categories=["a", "b"], ordered=True)),
    })
    original = right.copy(deep=True)
    result = join_dataframes(
        JoinRequest(left, right, ["id"], ["id"], how="left", right_fill={"value": UnmatchedFill("unknown")})
    )
    assert result["value"].cat.categories.tolist() == ["a", "b", "unknown"]
    assert result["value"].cat.ordered
    assert pd.isna(result.loc[1, "value"])
    pd.testing.assert_frame_equal(right, original)


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
@pytest.mark.parametrize("timezone", [None, "Europe/Stockholm"])
def test_datetime_defaults_preserve_resolution_timezone_and_source_nat(unit: str, timezone: str | None) -> None:
    """Date defaults are normalized without changing dtype or matched NaT."""
    left = pd.DataFrame({"id": [1, 2]})
    dtype = f"datetime64[{unit}]" if timezone is None else f"datetime64[{unit}, {timezone}]"
    right = pd.DataFrame({"id": [2], "value": pd.Series([pd.NaT], dtype=dtype)})
    result = join_dataframes(
        JoinRequest(left, right, ["id"], ["id"], how="left", right_fill={"value": UnmatchedFill("2020-01-01 12:00:00")})
    )
    assert result["value"].dtype == right["value"].dtype
    assert result.loc[0, "value"] == pd.Timestamp("2020-01-01 12:00:00", tz=timezone)
    assert pd.isna(result.loc[1, "value"])


@pytest.mark.parametrize(
    "dtype,value",
    [
        ("int8", 128),
        ("uint64", -1),
        ("int64", 1.5),
        ("int64", True),
        ("bool", 1),
        ("float32", 1e100),
        ("float32", 1e-100),
        ("float32[pyarrow]", 1e100),
        ("float64", float("nan")),
        ("float64", float("inf")),
        ("float64", 10**400),
        ("string", 0),
        ("datetime64[ns]", "invalid"),
        ("datetime64[ns]", "2500-01-01"),
        ("datetime64[s]", "2020-01-01 00:00:00.001"),
        ("datetime64[ns]", "2020-01-01T00:00:00Z"),
        ("timedelta64[ns]", "1 day"),
        ("period[M]", "2020-01"),
        ("object", "text"),
    ],
)
def test_invalid_defaults_are_rejected(dtype: str, value: JoinFillValue) -> None:
    """Reject incompatible values instead of widening dtypes or rounding."""
    series = pd.Series([1], dtype=dtype) if dtype in {"object", "category"} else pd.Series([], dtype=dtype)
    with pytest.raises(ValueError, match="Invalid unmatched-row default"):
        validate_join_fill(series, UnmatchedFill(value))


@pytest.mark.parametrize(
    "how,column,columns",
    [
        ("inner", "value", None),
        ("right", "value", None),
        ("left", "id", None),
        ("left", "missing", None),
        ("left", "value", []),
    ],
)
def test_defaults_require_eligible_included_non_key_columns(
    how: JoinHow,
    column: str,
    columns: list[str] | None,
) -> None:
    """Invalid side, key, missing or excluded column configurations fail explicitly."""
    frame = pd.DataFrame({"id": [1], "value": [2]})
    with pytest.raises(ValueError, match="not available"):
        join_dataframes(
            JoinRequest(
                frame, frame, ["id"], ["id"], how=how, right_columns=columns, right_fill={column: UnmatchedFill(0)}
            )
        )


@pytest.mark.parametrize("dtype", ["float32", "float64", "Float32", "Float64", "float32[pyarrow]", "float64[pyarrow]"])
def test_custom_float_preserves_dtype_and_matched_nan(dtype: str) -> None:
    """Native and extension floating columns retain their dtype and source missing values."""
    left = pd.DataFrame({"id": [1, 2]})
    right = pd.DataFrame({"id": [2], "value": pd.Series([None], dtype=dtype)})
    result = join_dataframes(
        JoinRequest(left, right, ["id"], ["id"], how="left", right_fill={"value": UnmatchedFill(0.125)})
    )
    assert result["value"].dtype == right["value"].dtype
    assert result.loc[0, "value"] == 0.125
    assert pd.isna(result.loc[1, "value"])


@pytest.mark.parametrize("dtype,value", [("uint64", 2**64 - 1), ("int64", -(2**63)), ("bool", True)])
def test_defaults_cover_integer_boundaries_and_true(dtype: str, value: JoinFillValue) -> None:
    """Fill scalars retain the entire source integer range."""
    left = pd.DataFrame({"id": [1]})
    right = pd.DataFrame({"id": pd.Series([], dtype="int64"), "value": pd.Series([], dtype=dtype)})
    result = join_dataframes(
        JoinRequest(left, right, ["id"], ["id"], how="left", right_fill={"value": UnmatchedFill(value)})
    )
    assert result["value"].dtype == right["value"].dtype
    assert result.loc[0, "value"] == value


@pytest.mark.parametrize("value", ["2020-03-29 02:30:00", "2020-10-25 02:30:00", "NaT"])
def test_datetime_defaults_reject_dst_gaps_and_ambiguity(value: str) -> None:
    """Invalid local wall times must not be silently shifted or resolved."""
    series = pd.Series([], dtype="datetime64[ns, Europe/Stockholm]")
    with pytest.raises(ValueError, match="Invalid unmatched-row default"):
        validate_join_fill(series, UnmatchedFill(value))


def test_datetime_default_converts_explicit_timezone() -> None:
    """An explicit offset represents an instant, not a naive local wall time."""
    series = pd.Series([], dtype="datetime64[ns, Europe/Stockholm]")
    value = validate_join_fill(series, UnmatchedFill("2020-01-01T12:00:00Z"))
    assert value == pd.Timestamp("2020-01-01T13:00:00", tz="Europe/Stockholm")


def test_datetime_default_uses_source_resolution_bounds() -> None:
    """Coarser datetime resolutions are not artificially restricted to nanosecond bounds."""
    series = pd.Series([], dtype="datetime64[s]")
    value = validate_join_fill(series, UnmatchedFill("2500-01-01"))
    assert isinstance(value, pd.Timestamp)
    assert value.unit == "s"
    assert value == pd.Timestamp("2500-01-01")


@pytest.mark.parametrize("dtype", ["period[M]", "timedelta64[ns]"])
def test_unsupported_custom_default_types_allow_null(dtype: str) -> None:
    """NULL remains supported for period and timedelta columns."""
    series = pd.Series([], dtype=dtype)
    assert validate_join_fill(series, UnmatchedFill()) is None


def test_outer_join_applies_both_sides_without_changing_metadata() -> None:
    """Independent defaults leave match status and existing source values intact."""
    left = pd.DataFrame({"id": [1, 2], "text": ["a", "b"]})
    right = pd.DataFrame({"other_id": [2, 3], "text": ["c", "d"]})
    result = join_dataframes(
        JoinRequest(
            left,
            right,
            ["id"],
            ["other_id"],
            how="outer",
            left_fill={"text": UnmatchedFill("no left")},
            right_fill={"text": UnmatchedFill("no right")},
        )
    )
    assert result["join_status"].tolist() == ["left_only", "both", "right_only"]
    assert result["text_left"].tolist() == ["a", "b", "no left"]
    assert result["text_right"].tolist() == ["no right", "c", "d"]
    assert pd.isna(result.loc[0, "other_id"])
    assert pd.isna(result.loc[2, "id"])


def test_null_default_request_matches_omitted_defaults() -> None:
    """Explicit NULL configuration remains backwards compatible."""
    left = pd.DataFrame({"id": [1, 2]})
    right = pd.DataFrame({"id": [2], "value": [3]})
    expected = join_dataframes(JoinRequest(left, right, ["id"], ["id"], how="left"))
    result = join_dataframes(
        JoinRequest(left, right, ["id"], ["id"], how="left", right_fill={"value": UnmatchedFill()})
    )
    pd.testing.assert_frame_equal(result, expected)


def test_numeric_category_accepts_explicit_text_default() -> None:
    """An explicit text category preserves existing numeric category values."""
    left = pd.DataFrame({"id": [1, 2]})
    right = pd.DataFrame({"id": [2], "value": pd.Series([10], dtype="category")})
    result = join_dataframes(
        JoinRequest(left, right, ["id"], ["id"], how="left", right_fill={"value": UnmatchedFill("unknown")})
    )
    assert result["value"].cat.categories.tolist() == [10, "unknown"]
    assert result["value"].tolist() == ["unknown", 10]


@pytest.mark.parametrize("empty", [False, True])
def test_category_default_without_unmatched_rows_keeps_categories(empty: bool) -> None:
    """A configured category default does not require or add an unused category."""
    right = pd.DataFrame({"id": [1], "value": pd.Series(["a"], dtype="category")})
    if empty:
        right = right.iloc[:0]
    result = join_dataframes(
        JoinRequest(right[["id"]], right, ["id"], ["id"], how="left", right_fill={"value": UnmatchedFill("new")})
    )
    assert result["value"].cat.categories.tolist() == ["a"]
    assert result["value"].tolist() == ([] if empty else ["a"])


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
