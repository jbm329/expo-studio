"""Contracts for shared column defaults and join compatibility entry points."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.data_operations.column_defaults import (
    ColumnFill,
    FillColumn,
    FillValue,
    describe_fill_column,
    parse_fill,
    prepare_nullable_columns,
    validate_fill,
    validate_fill_column,
)
from expo_jbm329.services.data_operations.joins import (
    JoinFillColumn,
    UnmatchedFill,
    describe_join_fill_column,
    parse_join_fill,
    validate_join_fill,
    validate_join_fill_column,
)


def test_join_metadata_and_value_types_are_shared() -> None:
    assert UnmatchedFill is ColumnFill
    assert JoinFillColumn is FillColumn
    assert describe_join_fill_column is describe_fill_column


@pytest.mark.parametrize(
    "dtype,text,decimal,value",
    [
        ("int64", " 4611686018427387905 ", ".", 2**62 + 1),
        ("uint64", str(2**64 - 1), ".", 2**64 - 1),
        ("float32", "1,25", ",", 1.25),
        ("Float64", "1e-3", ".", 0.001),
        ("string", "  text  ", ".", "  text  "),
        ("object", "", ".", ""),
        ("category", "unknown", ".", "unknown"),
        ("datetime64[ns, UTC]", "2024-01-01T01:00:00+01:00", ".", pd.Timestamp("2024-01-01", tz="UTC")),
    ],
)
def test_shared_parser_and_join_wrapper_agree(
    dtype: str,
    text: str,
    decimal: str,
    value: FillValue,
) -> None:
    metadata = describe_fill_column(pd.Series([], name="value", dtype=dtype))
    expected = ColumnFill(value)
    assert parse_fill(metadata, text, decimal_point=decimal) == expected
    assert parse_join_fill(metadata, text, decimal_point=decimal) == expected


@pytest.mark.parametrize(
    "dtype,text,decimal",
    [
        ("int8", "128", "."),
        ("uint64", "-1", "."),
        ("int64", "1e3", "."),
        ("float32", "1e100", "."),
        ("float64", "1e-999", "."),
        ("float64", "NaN", "."),
        ("float64", "1.000", ","),
        ("float64", "1,000", "."),
        ("datetime64[s]", "2024-01-01T00:00:00.001", "."),
        ("datetime64[ns]", "2024-01-01T00:00:00Z", "."),
        ("datetime64[ns, Europe/Stockholm]", "2024-03-31T02:30:00", "."),
        ("datetime64[ns, Europe/Stockholm]", "2024-10-27T02:30:00", "."),
        ("period[M]", "2024-01", "."),
    ],
)
def test_invalid_input_preserves_join_error_wording(dtype: str, text: str, decimal: str) -> None:
    metadata = describe_fill_column(pd.Series([], name="value", dtype=dtype))
    with pytest.raises(ValueError, match="Invalid default value for column"):
        parse_fill(metadata, text, decimal_point=decimal)
    with pytest.raises(ValueError) as caught:
        parse_join_fill(metadata, text, decimal_point=decimal)
    assert str(caught.value) == f"Invalid unmatched-row default for column 'value' ({dtype})."


@pytest.mark.parametrize("dtype,value", [("boolean", False), ("Int64", 0), ("string", "")])
def test_metadata_validation_is_scalar_only(dtype: str, value: FillValue, monkeypatch: pytest.MonkeyPatch) -> None:
    series = pd.Series([pd.NA, value], name="value", dtype=dtype)
    original = series.copy(deep=True)
    monkeypatch.setattr(pd.Series, "dropna", lambda *args, **kwargs: pytest.fail("Must not scan values"))
    metadata = describe_fill_column(series)
    assert validate_fill_column(metadata, ColumnFill(value)) == ColumnFill(value)
    assert validate_join_fill_column(metadata, ColumnFill(value)) == ColumnFill(value)
    assert validate_fill(series, ColumnFill(value)) == value
    pd.testing.assert_series_equal(series, original)


def test_object_content_validation_remains_worker_responsibility() -> None:
    series = pd.Series(["text", 7, None], name="value", dtype="object")
    original = series.copy(deep=True)
    metadata = describe_fill_column(series)
    assert metadata.kind == "text"
    assert validate_fill_column(metadata, ColumnFill("unknown")) == ColumnFill("unknown")
    assert validate_fill(series, ColumnFill()) is None
    with pytest.raises(ValueError, match="Invalid default value"):
        validate_fill(series, ColumnFill("unknown"))
    with pytest.raises(ValueError, match="Invalid unmatched-row default"):
        validate_join_fill(series, ColumnFill("unknown"))
    pd.testing.assert_series_equal(series, original)


@pytest.mark.parametrize("value", [1, True])
def test_metadata_validation_preserves_join_error_wording(value: int | bool) -> None:
    metadata = FillColumn("value", "string", "text")
    with pytest.raises(ValueError, match="Invalid default value"):
        validate_fill_column(metadata, ColumnFill(value))
    with pytest.raises(ValueError) as caught:
        validate_join_fill_column(metadata, ColumnFill(value))
    assert str(caught.value) == "Invalid unmatched-row default for column 'value' (string)."


@pytest.mark.parametrize(
    "dtype,nullable_dtype",
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
@pytest.mark.parametrize("empty", [False, True])
def test_nullable_preparation_preserves_width_values_index_and_source(
    dtype: str,
    nullable_dtype: str,
    empty: bool,
) -> None:
    values = [True, False] if dtype == "bool" else [int(np.iinfo(dtype).min), int(np.iinfo(dtype).max)]
    frame = pd.DataFrame({
        "value": pd.Series(values, dtype=dtype),
        "unchanged": pd.Series([1, 2], dtype="int64"),
        "text": pd.Series(["a", None], dtype="string"),
    })
    frame.index = pd.Index([9, 9], name="source")
    if empty:
        frame = frame.iloc[:0]
    original = frame.copy(deep=True)
    result = prepare_nullable_columns(frame, {"value"})
    assert result is not frame
    assert str(result["value"].dtype) == nullable_dtype
    assert result["value"].tolist() == frame["value"].tolist()
    pd.testing.assert_index_equal(result.index, frame.index)
    pd.testing.assert_series_equal(result["unchanged"], frame["unchanged"])
    pd.testing.assert_series_equal(result["text"], frame["text"])
    pd.testing.assert_frame_equal(frame, original)


def test_nullable_preparation_all_or_no_columns() -> None:
    frame = pd.DataFrame({"n": [2**62 + 1], "flag": [True]})
    all_columns = prepare_nullable_columns(frame)
    assert str(all_columns["n"].dtype) == "Int64"
    assert str(all_columns["flag"].dtype) == "boolean"
    assert all_columns["n"].tolist() == [2**62 + 1]
    no_columns = prepare_nullable_columns(frame, [])
    assert no_columns is not frame
    pd.testing.assert_frame_equal(no_columns, frame)


@pytest.mark.parametrize(
    "dtype",
    [
        "Int8",
        "UInt64",
        "boolean",
        "Float64",
        "string",
        "category",
        "int64[pyarrow]",
        "bool[pyarrow]",
        "datetime64[ns, UTC]",
        "timedelta64[ns]",
        "period[M]",
        "Sparse[float64, nan]",
    ],
)
def test_nullable_preparation_preserves_existing_extension_and_temporal_dtypes(dtype: str) -> None:
    frame = pd.DataFrame({"value": pd.Series([None, None], dtype=dtype)})
    original = frame.copy(deep=True)
    pd.testing.assert_frame_equal(prepare_nullable_columns(frame), original)
    pd.testing.assert_frame_equal(frame, original)
