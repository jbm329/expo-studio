"""Column selection precedes absent-column handling without removing rows."""

from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.column_defaults import ColumnFill, FillValue
from expo_jbm329.services.data_operations.concat import ConcatRequest, concat_dataframes


def test_selection_preserves_source_order_and_union_not_selection_order() -> None:
    left = pd.DataFrame({"first": [1], "shared": [2], "drop": [3], "last": [4]})
    right = pd.DataFrame({"right_first": [5], "shared": [6], "right_last": [7], "drop": [8]})
    result = concat_dataframes(
        ConcatRequest(
            left,
            right,
            left_columns=["last", "shared", "first"],
            right_columns=["right_last", "shared", "right_first"],
        )
    )
    expected = concat_dataframes(
        ConcatRequest(left[["first", "shared", "last"]], right[["right_first", "shared", "right_last"]])
    )
    pd.testing.assert_frame_equal(result, expected)
    assert result.columns.tolist() == ["first", "shared", "last", "right_first", "right_last"]


def test_selection_recomputes_absence_independently_on_both_sides() -> None:
    left = pd.DataFrame({"id": [1], "number": [2**62 + 1], "flag": [False], "drop": [10]})
    right = pd.DataFrame({"id": [2], "number": [3], "flag": [True], "drop": [20]})
    result = concat_dataframes(
        ConcatRequest(
            left,
            right,
            left_columns=["number", "id"],
            right_columns=["flag", "id"],
            left_fill={"number": ColumnFill(0)},
            right_fill={"flag": ColumnFill(False)},
        )
    )
    pd.testing.assert_frame_equal(result, pd.DataFrame({"id": [1, 2], "number": [2**62 + 1, 0], "flag": [False, True]}))


@pytest.mark.parametrize("source_first", [False, True])
@pytest.mark.parametrize("custom_default", [False, True])
@pytest.mark.parametrize(
    "dtype,nullable_dtype,value,default",
    [
        ("int8", "Int8", -128, 127),
        ("int64", "Int64", 2**62 + 1, -(2**63)),
        ("uint64", "UInt64", 2**64 - 1, 0),
        ("bool", "boolean", True, False),
        ("float64", "float64", 1.5, 0.0),
        ("Int64", "Int64", 2**62 + 1, 0),
        ("boolean", "boolean", True, False),
        ("string", "string", "original", ""),
        ("object", "object", "original", "unknown"),
        ("category", "category", "original", "original"),
        ("datetime64[s]", "datetime64[s]", "2500-01-01", pd.Timestamp("2400-01-01")),
        (
            "datetime64[ns, Europe/Stockholm]",
            "datetime64[ns, Europe/Stockholm]",
            "2024-01-01",
            pd.Timestamp("2024-07-01", tz="Europe/Stockholm"),
        ),
    ],
)
def test_selecting_shared_column_only_on_one_side_discards_other_values(
    source_first: bool,
    custom_default: bool,
    dtype: str,
    nullable_dtype: str,
    value: FillValue,
    default: FillValue,
) -> None:
    source = pd.DataFrame({"value": pd.Series([value], dtype=dtype)})
    source.index = pd.Index([7], name="source")
    other = pd.DataFrame({"value": ["discard", "these"], "drop": [1, 2]}, index=[9, 9])
    left, right = (source, other) if source_first else (other, source)
    originals = (left.copy(deep=True), right.copy(deep=True))
    fill = {"value": ColumnFill(default)} if custom_default else {}
    result = concat_dataframes(
        ConcatRequest(
            left,
            right,
            left_columns=None if source_first else [],
            right_columns=[] if source_first else None,
            left_fill=fill if source_first else {},
            right_fill={} if source_first else fill,
        )
    )
    expected_dtype = source["value"].dtype if custom_default or nullable_dtype == dtype else nullable_dtype
    absent = pd.Series([default if custom_default else float("nan")] * len(other), dtype=expected_dtype, name="value")
    expected = pd.concat(
        [source["value"].astype(expected_dtype), absent]
        if source_first
        else [absent, source["value"].astype(expected_dtype)],
        ignore_index=True,
    )
    pd.testing.assert_series_equal(result["value"], expected)
    assert result.columns.tolist() == ["value"]
    pd.testing.assert_index_equal(result.index, pd.RangeIndex(3))
    pd.testing.assert_frame_equal(left, originals[0])
    pd.testing.assert_frame_equal(right, originals[1])


@pytest.mark.parametrize("source_first", [False, True])
@pytest.mark.parametrize("source_empty,other_empty", [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize("custom_default", [False, True])
def test_selection_retains_empty_schema_rows_and_nullable_source_nulls(
    source_first: bool, source_empty: bool, other_empty: bool, custom_default: bool
) -> None:
    source = pd.DataFrame({"value": pd.Series([None, 2**62 + 1], dtype="Int64"), "drop": [1, 2]})
    other = pd.DataFrame({"value": [3, 4], "drop": [5, 6]})
    if source_empty:
        source = source.iloc[:0]
    if other_empty:
        other = other.iloc[:0]
    left, right = (source, other) if source_first else (other, source)
    fill = {"value": ColumnFill(0)} if custom_default else {}
    result = concat_dataframes(
        ConcatRequest(
            left,
            right,
            left_columns=["value"] if source_first else [],
            right_columns=[] if source_first else ["value"],
            left_fill=fill if source_first else {},
            right_fill={} if source_first else fill,
        )
    )
    absent = [0 if custom_default else None] * len(other)
    expected_values = source["value"].tolist() + absent if source_first else absent + source["value"].tolist()
    pd.testing.assert_frame_equal(result, pd.DataFrame({"value": pd.Series(expected_values, dtype="Int64")}))


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize(
    "selection,message",
    [
        (["unknown"], "Unknown columns"),
        (["value", "value"], "must not contain duplicate names"),
    ],
)
def test_invalid_selections_fail_explicitly(side: str, selection: list[str], message: str) -> None:
    frame = pd.DataFrame({"value": [1]})
    request = ConcatRequest(frame, frame)
    if side == "left":
        request.left_columns = selection
    else:
        request.right_columns = selection
    with pytest.raises(ValueError, match=message):
        concat_dataframes(request)


@pytest.mark.parametrize("left_columns,right_columns", [([], []), (None, []), ([], None), (None, None)])
def test_no_output_columns_are_rejected(left_columns: list[str] | None, right_columns: list[str] | None) -> None:
    frame = pd.DataFrame(index=[1, 1])
    with pytest.raises(ValueError, match="at least one selected output column"):
        concat_dataframes(ConcatRequest(frame, frame, left_columns=left_columns, right_columns=right_columns))


def test_excluding_all_existing_columns_is_rejected() -> None:
    frame = pd.DataFrame({"value": [1, 2]})
    with pytest.raises(ValueError, match="at least one selected output column"):
        concat_dataframes(ConcatRequest(frame, frame, left_columns=[], right_columns=[]))


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("selected", [False, True])
def test_defaults_require_selected_one_sided_ownership(side: str, selected: bool) -> None:
    frame = pd.DataFrame({"value": [1], "keep": [2]})
    request = ConcatRequest(frame, frame)
    if side == "left":
        request.left_columns = ["value", "keep"] if selected else ["keep"]
        request.left_fill = {"value": ColumnFill(0)}
    else:
        request.right_columns = ["value", "keep"] if selected else ["keep"]
        request.right_fill = {"value": ColumnFill(0)}
    with pytest.raises(ValueError, match="owned only by its source dataset"):
        concat_dataframes(request)


def test_projected_out_object_values_are_not_validated_as_source_content() -> None:
    left = pd.DataFrame({"value": ["text"]})
    right = pd.DataFrame({"value": [object()]})
    result = concat_dataframes(ConcatRequest(left, right, right_columns=[], left_fill={"value": ColumnFill("absent")}))
    assert result["value"].tolist() == ["text", "absent"]


@pytest.mark.parametrize("side", ["left", "right"])
def test_explicit_selection_requires_unambiguous_source_schema(side: str) -> None:
    frame = pd.DataFrame([[1, 2]], columns=["value", "value"])
    request = ConcatRequest(frame, frame)
    if side == "left":
        request.left_columns = ["value"]
    else:
        request.right_columns = ["value"]
    with pytest.raises(ValueError, match="selection requires unique column names"):
        concat_dataframes(request)


@pytest.mark.parametrize("remove_duplicates", [False, True])
def test_deduplication_uses_selected_and_filled_values(remove_duplicates: bool) -> None:
    left = pd.DataFrame({"value": [0, 0], "drop": [1, 2]})
    right = pd.DataFrame({"value": [3, 4], "drop": [5, 6]})
    result = concat_dataframes(
        ConcatRequest(
            left,
            right,
            remove_duplicates=remove_duplicates,
            left_columns=["value"],
            right_columns=[],
            left_fill={"value": ColumnFill(0)},
        )
    )
    pd.testing.assert_frame_equal(result, pd.DataFrame({"value": [0] if remove_duplicates else [0, 0, 0, 0]}))


@pytest.mark.parametrize("right_dtype,right_value", [("int64", 2**62 + 3), ("float64", 1.5), ("uint64", 2**64 - 1)])
def test_selected_shared_columns_retain_pandas_reconciliation(right_dtype: str, right_value: float) -> None:
    left = pd.DataFrame({"value": pd.Series([2**62 + 1], dtype="int64"), "drop": [1]})
    right = pd.DataFrame({"value": pd.Series([right_value], dtype=right_dtype), "drop": [2]})
    result = concat_dataframes(ConcatRequest(left, right, left_columns=["value"], right_columns=["value"]))
    expected = pd.concat([left[["value"]], right[["value"]]], ignore_index=True, sort=False)
    pd.testing.assert_frame_equal(result, expected)
