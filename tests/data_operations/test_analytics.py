from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.analytics import (
    get_column_profile,
    null_stats,
    summarize,
)

# =====================================================================
# summarize
# =====================================================================


def test_summarize_basic_structure():
    df = pd.DataFrame({
        "a": [1, 2, 3],
        "b": ["x", "y", "z"],
    })

    out = summarize(df)

    assert out is not df
    assert "a" in out.index
    assert "b" in out.index
    assert "count" in out.columns


def test_summarize_empty_dataframe():
    df = pd.DataFrame()

    out = summarize(df)

    assert isinstance(out, pd.DataFrame)
    assert out.empty


# =====================================================================
# null_stats
# =====================================================================


def test_null_stats_basic():
    df = pd.DataFrame({
        "a": [1, None, 2],
        "b": [None, None, "x"],
    })

    out = null_stats(df)

    assert list(out.columns) == ["nulls", "pct_null"]

    assert out.loc["a", "nulls"] == 1
    assert out.loc["b", "nulls"] == 2

    assert out.loc["a", "pct_null"] == (1 / 3) * 100
    assert out.loc["b", "pct_null"] == (2 / 3) * 100


def test_null_stats_empty_dataframe():
    df = pd.DataFrame()

    out = null_stats(df)

    assert isinstance(out, pd.DataFrame)
    assert list(out.columns) == ["nulls", "pct_null"]
    assert out.empty


# =====================================================================
# get_column_profile
# =====================================================================


@patch("expo_jbm329.services.data_operations.analytics.profile_series")
def test_get_column_profile_calls_profile_series(mock_profile_series):
    df = pd.DataFrame({"a": [1, 2, 3]})

    mock_profile = MagicMock(name="ColumnProfile")
    mock_profile_series.return_value = mock_profile

    out = get_column_profile(df, "a")

    # profile_series should be called once with the Series and name
    mock_profile_series.assert_called_once()
    args, kwargs = mock_profile_series.call_args

    assert args[0].equals(df["a"])
    assert kwargs["name"] == "a"

    assert out is mock_profile


def test_get_column_profile_invalid_column():
    df = pd.DataFrame({"a": [1, 2]})

    with pytest.raises(KeyError):
        get_column_profile(df, "missing")
