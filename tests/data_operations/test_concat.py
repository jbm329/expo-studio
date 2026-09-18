"""Tests for dataframe concatenation operations in data_operations.concat."""
from __future__ import annotations

import pandas as pd

from expo_jbm329.services.data_operations.concat import ConcatRequest, concat_dataframes


def test_concat_dataframes_basic():
    """Test basic concatenation (UNION ALL behavior)."""
    df1 = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})
    df2 = pd.DataFrame({"id": [3, 4], "name": ["Charlie", "David"]})
    
    req = ConcatRequest(left=df1, right=df2, remove_duplicates=False)
    result = concat_dataframes(req)
    
    assert len(result) == 4
    assert list(result["id"]) == [1, 2, 3, 4]
    assert list(result["name"]) == ["Alice", "Bob", "Charlie", "David"]


def test_concat_dataframes_with_duplicates():
    """Test concatenation with deduplication (UNION behavior)."""
    df1 = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})
    df2 = pd.DataFrame({"id": [2, 3], "name": ["Bob", "Charlie"]}) # Row 2 is duplicate
    
    # Without deduplication
    req_all = ConcatRequest(left=df1, right=df2, remove_duplicates=False)
    result_all = concat_dataframes(req_all)
    assert len(result_all) == 4
    
    # With deduplication
    req_union = ConcatRequest(left=df1, right=df2, remove_duplicates=True)
    result_union = concat_dataframes(req_union)
    assert len(result_union) == 3
    assert list(result_union["id"]) == [1, 2, 3]


def test_concat_dataframes_different_columns():
    """Test concatenation of dataframes with different columns."""
    df1 = pd.DataFrame({"id": [1], "name": ["Alice"]})
    df2 = pd.DataFrame({"id": [2], "age": [30]})
    
    req = ConcatRequest(left=df1, right=df2)
    result = concat_dataframes(req)
    
    assert len(result) == 2
    assert "name" in result.columns
    assert "age" in result.columns
    assert pd.isna(result.loc[1, "name"])
    assert pd.isna(result.loc[0, "age"])


def test_concat_dataframes_preserves_order():
    """Test that concatenation preserves row order."""
    df1 = pd.DataFrame({"a": [1, 2]})
    df2 = pd.DataFrame({"a": [3, 4]})
    
    req = ConcatRequest(left=df1, right=df2)
    result = concat_dataframes(req)
    
    assert list(result["a"]) == [1, 2, 3, 4]
