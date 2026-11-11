# pyright: reportPrivateUsage=false

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import QStyleOptionViewItem, QTableView, QTabWidget, QWidget
from pytest import MonkeyPatch

from expo_jbm329.utils.models import DataFrameModel
from expo_jbm329.workbench.controllers.result_tabs.result_tab_column_presentation_delegate import (
    ResultTabColumnPresentationDelegate,
)
from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager


def test_delegate_leaves_unknown_column_unchanged() -> None:
    model = QStandardItemModel(1, 1)
    index = model.index(0, 0)
    delegate = ResultTabColumnPresentationDelegate(
        semantics_by_column_index={},
        numeric_column_kinds={},
    )
    option = QStyleOptionViewItem()

    model.setData(index, "x", Qt.ItemDataRole.EditRole)
    delegate.initStyleOption(option, index)
    assert option.text == "x"


@pytest.mark.parametrize(
    ("dtype", "value", "expected"),
    [
        ("int8", 123, "123"),
        ("uint8", 255, "255"),
        ("int16", 2025, "2,025"),
        ("uint16", 1234, "1,234"),
        ("int32", -1234, "-1,234"),
        ("uint32", 1234, "1,234"),
        ("int64", 9007199254740993, "9,007,199,254,740,993"),
        ("uint64", 2**64 - 1, "18,446,744,073,709,551,615"),
        ("Int8", 123, "123"),
        ("UInt8", 255, "255"),
        ("Int16", 2025, "2,025"),
        ("UInt16", 1234, "1,234"),
        ("Int32", -1234, "-1,234"),
        ("UInt32", 1234, "1,234"),
        ("Int64", -(2**63), "-9,223,372,036,854,775,808"),
        ("UInt64", 2**64 - 1, "18,446,744,073,709,551,615"),
    ],
)
def test_delegate_formats_integer_dtypes_exactly(
    monkeypatch: MonkeyPatch, dtype: str, value: int, expected: str
) -> None:
    monkeypatch.setattr(QLocale, "system", lambda: QLocale("en_US"))
    values = [value, pd.NA] if dtype[0].isupper() else [value]
    df = pd.DataFrame({"value": pd.Series(values, dtype=dtype)})
    original = df.copy(deep=True)
    model = DataFrameModel(df)
    delegate = ResultTabColumnPresentationDelegate(semantics_by_column_index={}, numeric_column_kinds={0: "integer"})
    option = QStyleOptionViewItem()
    index = model.index(0, 0)

    delegate.initStyleOption(option, index)

    assert option.text == expected
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == str(value)
    assert model.data(index, Qt.ItemDataRole.ToolTipRole) == str(value)
    assert model.data(index, Qt.ItemDataRole.EditRole) == value
    if len(values) == 2:
        delegate.initStyleOption(option, model.index(1, 0))
        assert option.text == ""
    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize("dtype", ["float32", "float64", "Float32", "Float64"])
@pytest.mark.parametrize(
    ("locale_name", "expected"),
    [
        ("en_US", ["1,234.00", "-1,234.50", "0.00", "inf", "-inf", ""]),
        ("sv_SE", ["1\u00a0234,00", "\u22121\u00a0234,50", "0,00", "inf", "\u2212inf", ""]),
        ("de_DE", ["1.234,00", "-1.234,50", "0,00", "inf", "-inf", ""]),
    ],
)
def test_delegate_formats_float_dtypes_with_fixed_decimals(
    monkeypatch: MonkeyPatch, dtype: str, locale_name: str, expected: list[str]
) -> None:
    monkeypatch.setattr(QLocale, "system", lambda: QLocale(locale_name))
    df = pd.DataFrame({"value": pd.Series([1234.0, -1234.5, 0.0, np.inf, -np.inf, np.nan], dtype=dtype)})
    original = df.copy(deep=True)
    model = DataFrameModel(df)
    delegate = ResultTabColumnPresentationDelegate(semantics_by_column_index={}, numeric_column_kinds={0: "float"})
    option = QStyleOptionViewItem()

    for row, text in enumerate(expected):
        delegate.initStyleOption(option, model.index(row, 0))
        assert option.text == text
    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "1234.0"
    pd.testing.assert_frame_equal(df, original)


def test_manager_uses_positional_dtypes_without_profiling_numeric_or_text_columns(monkeypatch: MonkeyPatch) -> None:
    parent = QWidget()
    manager = ResultTabManager(
        parent_widget=parent,
        tabs=QTabWidget(parent),
        busy_overlay=MagicMock(),
        async_ops=MagicMock(),
        col_profile_cache=MagicMock(),
        set_status=MagicMock(),
        dialogs=MagicMock(),
    )
    infer = MagicMock(side_effect=AssertionError("Formatting must not profile these columns"))
    monkeypatch.setattr(ResultTabManager, "get_series_semantics", infer)
    df = pd.DataFrame({
        "integer": pd.Series([2025, pd.NA], dtype="Int64"),
        "float": pd.Series([2025.0, pd.NA], dtype="Float64"),
        "bool": pd.Series([True, pd.NA], dtype="boolean"),
        "text": pd.Series(["1234", pd.NA], dtype="string"),
        "category": pd.Series([1234, None], dtype="category"),
        "object": pd.Series([1234, "text"], dtype=object),
        "decimal": pd.Series([Decimal("1234.5"), None], dtype=object),
    })
    model = DataFrameModel(df)
    view = QTableView(parent)
    view.setModel(model)

    manager._apply_presentation_delegate(view, df)

    delegate = view.itemDelegate()
    assert isinstance(delegate, ResultTabColumnPresentationDelegate)
    assert delegate._numeric_column_kinds == {0: "integer", 1: "float"}
    assert delegate._semantics_by_column_index == {}
    infer.assert_not_called()
    option = QStyleOptionViewItem()
    for column in range(2, df.shape[1]):
        for row in range(df.shape[0]):
            index = model.index(row, column)
            delegate.initStyleOption(option, index)
            assert option.text == model.data(index, Qt.ItemDataRole.DisplayRole)

    # Dtype metadata must not be keyed by potentially duplicated column labels.
    numeric = df.iloc[:, :2].copy()
    numeric.columns = ["value", "value"]
    manager._apply_presentation_delegate(view, numeric)
    delegate = view.itemDelegate()
    assert isinstance(delegate, ResultTabColumnPresentationDelegate)
    assert delegate._numeric_column_kinds == {0: "integer", 1: "float"}
