import pandas as pd
import numpy as np
import pytest
from PyQt6.QtCore import Qt, QModelIndex
from expo_jbm329.utils.models import MinimalModel, DataFrameModel

def test_minimal_model_init():
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    model = MinimalModel(df)
    assert model.rowCount() == 2
    assert model.columnCount() == 3 # leading index column '#'
    
    # Check header
    assert model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) == "#"
    assert model.headerData(1, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) == "A"

def test_minimal_model_data():
    df = pd.DataFrame({"A": [1, 2]})
    model = MinimalModel(df)
    
    # Check index column data
    idx_col = model.index(0, 0)
    assert model.data(idx_col, Qt.ItemDataRole.DisplayRole) == "1" # (row + 1)
    
    # Check content column data
    col_a = model.index(0, 1)
    assert model.data(col_a, Qt.ItemDataRole.DisplayRole) == "1"

def test_dataframe_model_init():
    df = pd.DataFrame({"A": [1, 2], "B": [3.5, 4.5]})
    model = DataFrameModel(df)
    assert model.rowCount() == 2
    assert model.columnCount() == 3

def test_dataframe_model_sorting():
    df = pd.DataFrame({"A": [2, 1, 3]})
    model = DataFrameModel(df)
    
    # Initial order
    assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "2"
    
    # Sort Ascending
    model.sort(1, Qt.SortOrder.AscendingOrder)
    assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "1"
    
    # Sort Descending
    model.sort(1, Qt.SortOrder.DescendingOrder)
    assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "3"

def test_dataframe_model_datetime_formatting():
    # Model uses fmt_datetime_auto for datetime columns
    df = pd.DataFrame({"D": [pd.Timestamp("2023-01-01"), pd.Timestamp("2023-01-01 12:00:00")]})
    model = DataFrameModel(df)
    
    # Date only (hour=0)
    assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "2023-01-01"
    
    # Full datetime
    assert model.data(model.index(1, 1), Qt.ItemDataRole.DisplayRole) == "2023-01-01 12:00:00"

def test_dataframe_model_none_handling():
    df = pd.DataFrame({"A": [1, None]})
    model = DataFrameModel(df)
    
    # None should be empty string
    assert model.data(model.index(1, 1), Qt.ItemDataRole.DisplayRole) == ""
