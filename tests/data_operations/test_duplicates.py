"""Contracts for shared pandas-backed duplicate-row removal."""

from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.duplicates import remove_duplicate_rows


def test_all_columns_participate_and_first_occurrence_order_is_preserved() -> None:
    frame = pd.DataFrame(
        {"number": [2, 1, 2, 2, 1], "text": ["b", "a", "b", "different", "a"]},
        index=pd.Index([9, 9, 3, 8, 4], name="source"),
    )
    original = frame.copy(deep=True)

    result = remove_duplicate_rows(frame)

    expected = pd.DataFrame({"number": [2, 1, 2], "text": ["b", "a", "different"]})
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(frame, original)
    assert result is not frame


@pytest.mark.parametrize(
    "dtype,value",
    [
        ("Int64", 2**62 + 1),
        ("UInt64", 2**64 - 1),
        ("boolean", False),
        ("Float64", 1.5),
        ("float64", 1.5),
        ("string", "value"),
        ("object", "value"),
        ("category", "value"),
        ("datetime64[s]", "2500-01-01"),
        ("datetime64[ns, Europe/Stockholm]", "2024-01-01"),
        ("timedelta64[ns]", pd.Timedelta(days=1)),
        ("period[M]", "2024-01"),
        ("int64[pyarrow]", 2**62 + 1),
    ],
)
def test_matching_missing_values_and_extension_metadata_are_preserved(dtype: str, value: object) -> None:
    frame = pd.DataFrame({
        "value": pd.Series([value, None, value, None], dtype=dtype),
        "other": pd.Series(["same"] * 4, dtype="string"),
    })
    if dtype == "category":
        frame["value"] = frame["value"].cat.set_categories(["unused", "value"], ordered=True)
    frame.index = pd.Index([4, 3, 2, 1], name="source")
    original = frame.copy(deep=True)

    result = remove_duplicate_rows(frame)

    pd.testing.assert_frame_equal(result, frame.iloc[:2].reset_index(drop=True))
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("with_rows", [False, True])
def test_already_unique_and_empty_typed_frames_preserve_schema(with_rows: bool) -> None:
    frame = pd.DataFrame({
        "number": pd.Series([2, 1] if with_rows else [], dtype="Int64"),
        "text": pd.Series(["b", "a"] if with_rows else [], dtype="string"),
    })
    frame.index = pd.Index([8, 4] if with_rows else [], dtype="int64", name="source")
    original = frame.copy(deep=True)

    result = remove_duplicate_rows(frame)

    expected = frame.reset_index(drop=True) if with_rows else original
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(frame, original)


def test_duplicate_column_names_use_all_column_positions() -> None:
    frame = pd.DataFrame([[1, 2], [1, 3], [1, 2]], columns=["value", "value"])

    result = remove_duplicate_rows(frame)

    pd.testing.assert_frame_equal(result, pd.DataFrame([[1, 2], [1, 3]], columns=["value", "value"]))


@pytest.mark.parametrize("nested", [[1], {"key": 1}])
def test_unsupported_multicolumn_nested_values_raise_without_modifying_input(nested: object) -> None:
    frame = pd.DataFrame({"nested": [nested, nested], "other": [1, 1]})
    original = frame.copy(deep=True)

    with pytest.raises(TypeError, match="unhashable type"):
        remove_duplicate_rows(frame)

    pd.testing.assert_frame_equal(frame, original)
