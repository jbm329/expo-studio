"""Typed defaults apply to absent columns, never existing source cells."""

from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.column_defaults import ColumnFill, FillValue
from expo_jbm329.services.data_operations.concat import ConcatRequest, concat_dataframes


@pytest.mark.parametrize("source_first", [False, True])
@pytest.mark.parametrize(
    "dtype,source_value,default",
    [
        ("int8", -128, 127),
        ("int16", -32768, 32767),
        ("int32", -(2**31), 2**31 - 1),
        ("int64", 2**62 + 1, -(2**63)),
        ("uint8", 255, 0),
        ("uint16", 65535, 0),
        ("uint32", 2**32 - 1, 0),
        ("uint64", 2**64 - 1, 2**64 - 2),
        ("bool", True, False),
        ("bool", False, True),
        ("float32", 1.5, 0.25),
        ("float64", 1.5, -2.25),
        ("Int64", 2**62 + 1, 0),
        ("UInt64", 2**64 - 1, 0),
        ("boolean", True, False),
        ("Float64", 1.5, 0.0),
        ("string", "value", ""),
        ("object", "value", "  unknown  "),
        ("int64[pyarrow]", 2**62 + 1, 0),
        ("bool[pyarrow]", True, False),
        ("float[pyarrow]", 1.5, 0.25),
    ],
)
def test_typed_defaults_preserve_values_dtype_and_inputs(
    source_first: bool,
    dtype: str,
    source_value: FillValue,
    default: FillValue,
) -> None:
    source = pd.DataFrame({"value": pd.Series([source_value], dtype=dtype)})
    source.index = pd.Index([7], name="source")
    other = pd.DataFrame({"other": ["a", "b"]}, index=[9, 9])
    left, right = (source, other) if source_first else (other, source)
    originals = (left.copy(deep=True), right.copy(deep=True))
    mapping = {"value": ColumnFill(default)}
    result = concat_dataframes(
        ConcatRequest(
            left,
            right,
            left_fill=mapping if source_first else {},
            right_fill={} if source_first else mapping,
        )
    )
    values = [source_value, default, default] if source_first else [default, default, source_value]
    pd.testing.assert_series_equal(result["value"], pd.Series(values, name="value", dtype=dtype))
    assert list(result.columns) == (["value", "other"] if source_first else ["other", "value"])
    pd.testing.assert_frame_equal(left, originals[0])
    pd.testing.assert_frame_equal(right, originals[1])


@pytest.mark.parametrize(
    "dtype,value",
    [
        ("Int64", 0),
        ("boolean", False),
        ("Float64", 0.0),
        ("string", ""),
        ("object", "unknown"),
    ],
)
@pytest.mark.parametrize("all_null", [False, True])
def test_genuine_source_nulls_are_not_filled(dtype: str, value: FillValue, all_null: bool) -> None:
    source = pd.DataFrame({"value": pd.Series([None, None if all_null else value], dtype=dtype)})
    result = concat_dataframes(
        ConcatRequest(
            source,
            pd.DataFrame({"other": [1]}),
            left_fill={"value": ColumnFill(value)},
        )
    )
    assert pd.isna(result.loc[0, "value"])
    if all_null:
        assert pd.isna(result.loc[1, "value"])
    else:
        assert result.loc[1, "value"] == value
    assert result.loc[2, "value"] == value
    assert result["value"].dtype == source["value"].dtype


@pytest.mark.parametrize("source_empty,other_empty", [(True, False), (False, True), (True, True)])
@pytest.mark.parametrize("dtype,value", [("int64", 2**62 + 1), ("bool", False), ("string", "")])
def test_empty_input_schema_controls_default_dtype(
    source_empty: bool,
    other_empty: bool,
    dtype: str,
    value: FillValue,
) -> None:
    source = pd.DataFrame({"value": pd.Series([value], dtype=dtype)})
    other = pd.DataFrame({"other": [1]})
    if source_empty:
        source = source.iloc[:0]
    if other_empty:
        other = other.iloc[:0]
    result = concat_dataframes(ConcatRequest(source, other, left_fill={"value": ColumnFill(value)}))
    pd.testing.assert_series_equal(
        result["value"],
        pd.Series([value] * (len(source) + len(other)), name="value", dtype=dtype),
    )


@pytest.mark.parametrize("categories", [["a", "b"], [True, False], [1, 2]])
@pytest.mark.parametrize("other_empty", [False, True])
def test_category_metadata_and_existing_nulls_are_preserved(categories: list[object], other_empty: bool) -> None:
    source = pd.DataFrame({"value": pd.Categorical([categories[0], None], categories=categories, ordered=True)})
    original = source.copy(deep=True)
    other = pd.DataFrame({"other": pd.Series([] if other_empty else [1], dtype="int64")})
    result = concat_dataframes(ConcatRequest(source, other, left_fill={"value": ColumnFill("unknown")}))
    expected_categories = categories if other_empty else [*categories, "unknown"]
    assert result["value"].cat.categories.tolist() == expected_categories
    assert result["value"].cat.ordered
    assert pd.isna(result.loc[1, "value"])
    if not other_empty:
        assert result.loc[2, "value"] == "unknown"
    pd.testing.assert_frame_equal(source, original)


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
@pytest.mark.parametrize("timezone", [None, "Europe/Stockholm"])
def test_datetime_defaults_preserve_resolution_timezone_and_nat(unit: str, timezone: str | None) -> None:
    dtype = f"datetime64[{unit}]" if timezone is None else f"datetime64[{unit}, {timezone}]"
    source = pd.DataFrame({"value": pd.Series(["2024-01-01", None], dtype=dtype)})
    original = source.copy(deep=True)
    text = "2024-01-02T01:00:00+01:00" if timezone else "2024-01-02"
    result = concat_dataframes(
        ConcatRequest(
            source,
            pd.DataFrame({"other": [1]}),
            left_fill={"value": ColumnFill(text)},
        )
    )
    expected = pd.Series(["2024-01-01", None, "2024-01-02T01:00:00" if timezone else text], dtype=dtype, name="value")
    pd.testing.assert_series_equal(result["value"], expected)
    pd.testing.assert_frame_equal(source, original)


def test_datetime_defaults_respect_coarse_resolution_bounds() -> None:
    source = pd.DataFrame({"value": pd.Series(["2500-01-01"], dtype="datetime64[s]")})
    result = concat_dataframes(
        ConcatRequest(
            source,
            pd.DataFrame({"other": [1]}),
            left_fill={"value": ColumnFill("2600-01-01")},
        )
    )
    assert result["value"].dtype == source["value"].dtype
    assert result.loc[1, "value"] == pd.Timestamp("2600-01-01")


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
        ("float64", float("inf")),
        ("float64", float("nan")),
        ("string", 0),
        ("category", True),
        ("object", 1),
        ("datetime64[ns]", "2024-01-01T00:00:00Z"),
        ("datetime64[ns]", "not a date"),
        ("datetime64[ns]", "2600-01-01"),
        ("datetime64[s]", "2024-01-01T00:00:00.001"),
        ("datetime64[ns, Europe/Stockholm]", "2024-03-31T02:30:00"),
        ("datetime64[ns, Europe/Stockholm]", "2024-10-27T02:30:00"),
        ("timedelta64[ns]", "1 day"),
        ("period[M]", "2024-01"),
        ("complex128", 0),
    ],
)
def test_invalid_defaults_fail_even_without_generated_rows(dtype: str, value: FillValue) -> None:
    source = pd.DataFrame({"value": pd.Series([], dtype=dtype)})
    with pytest.raises(ValueError, match="Invalid default value"):
        concat_dataframes(ConcatRequest(source, pd.DataFrame(), left_fill={"value": ColumnFill(value)}))


def test_non_text_object_content_is_rejected_without_mutation() -> None:
    source = pd.DataFrame({"value": ["text", 7, None]})
    original = source.copy(deep=True)
    with pytest.raises(ValueError, match="Invalid default value"):
        concat_dataframes(
            ConcatRequest(
                source,
                pd.DataFrame({"other": [1]}),
                left_fill={"value": ColumnFill("unknown")},
            )
        )
    pd.testing.assert_frame_equal(source, original)


@pytest.mark.parametrize("mapping_side", ["left", "right"])
@pytest.mark.parametrize("column", ["shared", "unknown", "other"])
def test_defaults_require_correct_source_ownership(mapping_side: str, column: str) -> None:
    mapping = {column: ColumnFill()}
    left = pd.DataFrame({"shared": [1], "owned": [2]})
    right = pd.DataFrame({"shared": [3], "other": [4]})
    if mapping_side == "right":
        left, right = right, left
    with pytest.raises(ValueError, match="owned only by its source dataset"):
        concat_dataframes(
            ConcatRequest(
                left,
                right,
                left_fill=mapping if mapping_side == "left" else {},
                right_fill=mapping if mapping_side == "right" else {},
            )
        )


def test_defaults_are_independent_and_applied_before_deduplication() -> None:
    left = pd.DataFrame({"a": [0, 0]})
    right = pd.DataFrame({"b": [0, 0]})
    config = ConcatRequest(left, right, left_fill={"a": ColumnFill(0)}, right_fill={"b": ColumnFill(0)})
    expected = pd.DataFrame({"a": [0] * 4, "b": [0] * 4})
    pd.testing.assert_frame_equal(concat_dataframes(config), expected)
    config.remove_duplicates = True
    pd.testing.assert_frame_equal(concat_dataframes(config), expected.iloc[:1])
    assert ConcatRequest(left, right).left_fill is not ConcatRequest(left, right).left_fill


@pytest.mark.parametrize("dtype", ["int64", "bool", "string", "period[M]", "timedelta64[ns]", "complex128"])
def test_explicit_null_matches_omitted_default(dtype: str) -> None:
    source = pd.DataFrame({"value": pd.Series([], dtype=dtype)})
    other = pd.DataFrame({"other": [1]})
    expected = concat_dataframes(ConcatRequest(source, other))
    actual = concat_dataframes(ConcatRequest(source, other, left_fill={"value": ColumnFill()}))
    pd.testing.assert_frame_equal(actual, expected)


def test_shared_columns_reject_defaults_even_for_identical_layouts() -> None:
    frame = pd.DataFrame({"shared": [1]})
    with pytest.raises(ValueError, match="owned only by its source dataset"):
        concat_dataframes(ConcatRequest(frame, frame, left_fill={"shared": ColumnFill(0)}))


def test_ambiguous_duplicate_columns_reject_default_mapping() -> None:
    frame = pd.DataFrame([[1, 2]], columns=["a", "a"])
    with pytest.raises(ValueError, match="requires unique column names"):
        concat_dataframes(ConcatRequest(frame, frame, left_fill={"a": ColumnFill(0)}))


@pytest.mark.parametrize("source_empty", [False, True])
def test_existing_category_default_preserves_unused_categories(source_empty: bool) -> None:
    source = pd.DataFrame({
        "value": pd.Categorical(
            [] if source_empty else ["a", None],
            categories=["a", "unused"],
            ordered=True,
        )
    })
    original = source.copy(deep=True)
    result = concat_dataframes(
        ConcatRequest(
            source,
            pd.DataFrame({"other": [1]}),
            left_fill={"value": ColumnFill("unused")},
        )
    )
    assert result["value"].cat.categories.tolist() == ["a", "unused"]
    assert result["value"].cat.ordered
    assert result.iloc[-1]["value"] == "unused"
    pd.testing.assert_frame_equal(source, original)


def test_datetime_offset_is_converted_to_source_timezone() -> None:
    source = pd.DataFrame({"value": pd.Series([None], dtype="datetime64[us, Europe/Stockholm]")})
    result = concat_dataframes(
        ConcatRequest(
            source,
            pd.DataFrame({"other": [1]}),
            left_fill={"value": ColumnFill("2024-07-01T10:00:00.123456Z")},
        )
    )
    assert pd.isna(result.loc[0, "value"])
    assert result.loc[1, "value"] == pd.Timestamp("2024-07-01T12:00:00.123456", tz="Europe/Stockholm")
    assert result["value"].dtype == source["value"].dtype


def test_null_and_non_null_defaults_on_opposite_sides() -> None:
    left = pd.DataFrame({"quantity": pd.Series([2**62 + 1], dtype="int64")})
    right = pd.DataFrame({"flag": [True]})
    result = concat_dataframes(
        ConcatRequest(
            left,
            right,
            left_fill={"quantity": ColumnFill()},
            right_fill={"flag": ColumnFill(False)},
        )
    )
    expected = pd.DataFrame({
        "quantity": pd.Series([2**62 + 1, None], dtype="Int64"),
        "flag": [False, True],
    })
    pd.testing.assert_frame_equal(result, expected)
