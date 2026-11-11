from __future__ import annotations

import pandas as pd
import pytest
from PyQt6.QtCore import Qt

from expo_jbm329.utils.models import DataFrameModel, JoinPreviewModel


def test_dataframe_model_init():
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    model = DataFrameModel(df)

    assert model.rowCount() == 2
    assert model.columnCount() == 2
    assert model.headerData(0, Qt.Orientation.Horizontal) == "A"
    assert model.headerData(1, Qt.Orientation.Horizontal) == "B"
    assert model.headerData(0, Qt.Orientation.Vertical) == "1"


def test_dataframe_model_data_and_none_handling():
    df = pd.DataFrame({"A": [1, None]})
    model = DataFrameModel(df)

    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "1.0"
    assert model.data(model.index(1, 0), Qt.ItemDataRole.DisplayRole) == ""


def test_dataframe_model_datetime_formatting():
    df = pd.DataFrame({"D": [pd.Timestamp("2023-01-01"), pd.Timestamp("2023-01-01 12:00:00")]})
    model = DataFrameModel(df)

    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
    assert model.data(model.index(1, 0), Qt.ItemDataRole.DisplayRole)


def test_dataframe_model_sorting():
    df = pd.DataFrame({"A": [2, 1, 3]})
    model = DataFrameModel(df)

    model.sort(0, Qt.SortOrder.AscendingOrder)
    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "1"

    model.sort(0, Qt.SortOrder.DescendingOrder)
    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "3"


def test_join_preview_model_inherits_dataframe_model():
    df = pd.DataFrame({"A": [1], "B": [2]})
    model = JoinPreviewModel(df)

    assert model.rowCount() == 1
    assert model.columnCount() == 2


@pytest.mark.parametrize("dtype", ["Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64"])
@pytest.mark.parametrize("ascending", [True, False])
def test_nullable_integer_sort_preserves_exact_values_and_missing_placement(dtype: str, ascending: bool) -> None:
    bits = int(dtype.removeprefix("UInt").removeprefix("Int"))
    maximum = 2**bits - 1 if dtype.startswith("U") else 2 ** (bits - 1) - 1
    minimum = 0 if dtype.startswith("U") else -(2 ** (bits - 1))
    frame = pd.DataFrame({
        "value": pd.Series([maximum, maximum - 1, pd.NA, minimum, pd.NA], dtype=dtype),
        "record": ["maximum", "near_maximum", "missing_first", "minimum", "missing_second"],
    })
    frame.index = [10, 10, -1, 4, 4]
    original = frame.copy(deep=True)
    model = DataFrameModel(frame)
    expected = ["minimum", "near_maximum", "maximum"] if ascending else ["maximum", "near_maximum", "minimum"]
    order = Qt.SortOrder.AscendingOrder if ascending else Qt.SortOrder.DescendingOrder

    model.sort(0, order)

    assert [model.data(model.index(row, 1)) for row in range(5)] == [
        *expected,
        "missing_first",
        "missing_second",
    ]
    expected_values = [minimum, maximum - 1, maximum] if ascending else [maximum, maximum - 1, minimum]
    assert [model.data(model.index(row, 0), Qt.ItemDataRole.EditRole) for row in range(3)] == expected_values
    assert [model.data(model.index(row, 0)) for row in (3, 4)] == ["", ""]
    assert model.data(model.index(3, 0), Qt.ItemDataRole.EditRole) is pd.NA
    pd.testing.assert_frame_equal(model.data_frame(), original)


@pytest.mark.parametrize("ascending", [True, False])
def test_nullable_boolean_sort_keeps_missing_last_and_equal_rows_stable(ascending: bool) -> None:
    frame = pd.DataFrame({
        "value": pd.Series([True, pd.NA, False, True, pd.NA, False], dtype="boolean"),
        "record": ["true_first", "missing_first", "false_first", "true_second", "missing_second", "false_second"],
    })
    original = frame.copy(deep=True)
    model = DataFrameModel(frame)
    false_rows = ["false_first", "false_second"]
    true_rows = ["true_first", "true_second"]

    for order in (
        Qt.SortOrder.DescendingOrder if ascending else Qt.SortOrder.AscendingOrder,
        Qt.SortOrder.AscendingOrder if ascending else Qt.SortOrder.DescendingOrder,
    ):
        model.sort(0, order)

    expected = [*false_rows, *true_rows] if ascending else [*true_rows, *false_rows]
    assert [model.data(model.index(row, 1)) for row in range(6)] == [
        *expected,
        "missing_first",
        "missing_second",
    ]
    assert [model.data(model.index(row, 0)) for row in (4, 5)] == ["", ""]
    pd.testing.assert_frame_equal(model.data_frame(), original)


@pytest.mark.parametrize("dtype", ["Int64", "UInt64", "boolean"])
@pytest.mark.parametrize("values", [[], [pd.NA], [pd.NA, pd.NA]])
def test_nullable_sort_handles_empty_and_all_missing_columns(dtype: str, values: list[object]) -> None:
    frame = pd.DataFrame({"value": pd.Series(values, dtype=dtype)})
    original = frame.copy(deep=True)
    model = DataFrameModel(frame)

    for order in (Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder):
        model.sort(0, order)
        assert model.rowCount() == len(values)
        assert [model.data(model.index(row, 0)) for row in range(len(values))] == [""] * len(values)
    pd.testing.assert_frame_equal(model.data_frame(), original)


@pytest.mark.parametrize(
    ("dtype", "values"),
    [
        ("Int64", [2**63 - 1, 2**63 - 2]),
        ("UInt64", [2**64 - 1, 2**64 - 2]),
        ("boolean", [True, False]),
    ],
)
def test_complete_nullable_columns_sort_without_changing_storage(dtype: str, values: list[object]) -> None:
    frame = pd.DataFrame({"value": pd.Series(values, dtype=dtype), "record": ["larger", "smaller"]})
    original = frame.copy(deep=True)
    model = DataFrameModel(frame)
    notifications: list[str] = []
    model.layoutAboutToBeChanged.connect(lambda: notifications.append("before"))
    model.layoutChanged.connect(lambda: notifications.append("after"))

    model.sort(0, Qt.SortOrder.AscendingOrder)

    assert [model.data(model.index(row, 1)) for row in range(2)] == ["smaller", "larger"]
    assert notifications == ["before", "after"]
    pd.testing.assert_frame_equal(model.data_frame(), original)


@pytest.mark.parametrize(
    ("series", "ascending_records", "descending_records"),
    [
        (pd.Series([2, 1, 3], dtype="int64"), ["second", "first", "third"], ["third", "first", "second"]),
        (pd.Series([True, False, True], dtype=bool), ["second", "first", "third"], ["third", "first", "second"]),
        (pd.Series([2.0, float("nan"), 1.0]), ["third", "first", "second"], ["second", "first", "third"]),
        (pd.Series(["b", None, "a"], dtype=object), ["second", "third", "first"], ["first", "third", "second"]),
        (
            pd.Series(pd.to_datetime(["2020-01-02", None, "2020-01-01"])),
            ["third", "first", "second"],
            ["second", "first", "third"],
        ),
    ],
)
def test_nonnullable_sort_behavior_is_unchanged(
    series: pd.Series, ascending_records: list[str], descending_records: list[str]
) -> None:
    frame = pd.DataFrame({"value": series, "record": ["first", "second", "third"]})
    original = frame.copy(deep=True)
    model = DataFrameModel(frame)

    model.sort(0, Qt.SortOrder.AscendingOrder)
    assert [model.data(model.index(row, 1)) for row in range(3)] == ascending_records
    model.sort(0, Qt.SortOrder.DescendingOrder)
    assert [model.data(model.index(row, 1)) for row in range(3)] == descending_records
    pd.testing.assert_frame_equal(model.data_frame(), original)
