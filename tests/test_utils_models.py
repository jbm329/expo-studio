from __future__ import annotations

import pandas as pd

from expo_jbm329.utils.models import DataFrameModel, JoinPreviewModel
from PyQt6.QtCore import Qt


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
