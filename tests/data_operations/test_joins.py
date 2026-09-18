"""Tests for dataframe join operations in data_operations.joins."""
from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.joins import (
    JoinRequest,
    concat_columns,
    concat_rows,
    detect_join_keys,
    join_dataframes,
)


@pytest.fixture
def left_df() -> pd.DataFrame:
    """Fixture for left dataframe."""
    return pd.DataFrame({
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Charlie"],
        "age": [25, 30, 35]
    })


@pytest.fixture
def right_df() -> pd.DataFrame:
    """Fixture for right dataframe."""
    return pd.DataFrame({
        "user_id": [2, 3, 4],
        "city": ["New York", "London", "Paris"],
        "age": [30, 35, 40]
    })


def test_join_dataframes_inner(left_df, right_df):
    """Test inner join."""
    cfg = JoinRequest(
        left=left_df,
        right=right_df,
        left_on=["id"],
        right_on=["user_id"],
        how="inner"
    )
    result = join_dataframes(cfg)
    
    assert len(result) == 2
    assert list(result["id"]) == [2, 3]
    assert "city" in result.columns
    # Check suffixes for conflicting 'age' column
    assert "age_left" in result.columns
    assert "age_right" in result.columns


def test_join_dataframes_left(left_df, right_df):
    """Test left join."""
    cfg = JoinRequest(
        left=left_df,
        right=right_df,
        left_on=["id"],
        right_on=["user_id"],
        how="left"
    )
    result = join_dataframes(cfg)
    
    assert len(result) == 3
    assert list(result["id"]) == [1, 2, 3]
    assert pd.isna(result.loc[result["id"] == 1, "city"]).all()


def test_join_dataframes_mismatched_keys(left_df, right_df):
    """Test error when key lengths mismatch."""
    cfg = JoinRequest(
        left=left_df,
        right=right_df,
        left_on=["id", "name"],
        right_on=["user_id"],
        how="inner"
    )
    with pytest.raises(ValueError, match="left_on and right_on must have same length"):
        join_dataframes(cfg)


def test_detect_join_keys():
    """Test join key detection logic."""
    df1 = pd.DataFrame({
        "id": [1, 2],
        "name": ["a", "b"],
        "score": [1.1, 2.2],
        "cat": pd.Series(["x", "y"], dtype="category"),
        "only1": [1, 1]
    })
    df2 = pd.DataFrame({
        "id": [1, 3],          # numeric match
        "name": [1, 2],        # name matches but dtype doesn't (str vs int)
        "score": [3.3, 4.4],   # numeric match
        "cat": pd.Series(["x", "z"], dtype="category"), # categorical match
        "only2": [2, 2]
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
