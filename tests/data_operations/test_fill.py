import pandas as pd
import pytest

from expo_jbm329.services.data_operations.fill import (
    fillna,
    fillna_mean,
    fillna_median,
    fillna_mode,
    replace_empty_with_nan,
)

# =====================================================================
# fillna (generic)
# =====================================================================

def test_fillna_basic():
    df = pd.DataFrame({"a": [1, None, 2]})

    out = fillna(df, "a", 0)

    assert out is not df
    assert out["a"].tolist() == [1, 0, 2]


def test_fillna_invalid_column():
    df = pd.DataFrame({"a": [1]})

    with pytest.raises(KeyError):
        fillna(df, "b", 0)


# =====================================================================
# fillna_mean
# =====================================================================

def test_fillna_mean_numeric():
    df = pd.DataFrame({"a": [1.0, None, 3.0]})

    out = fillna_mean(df, "a")

    # mean of [1, 3] is 2
    assert out["a"].tolist() == [1.0, 2.0, 3.0]


# =====================================================================
# fillna_median
# =====================================================================

def test_fillna_median_numeric():
    df = pd.DataFrame({"a": [1.0, None, 3.0]})

    out = fillna_median(df, "a")

    # median of [1, 3] is 2
    assert out["a"].tolist() == [1.0, 2.0, 3.0]


# =====================================================================
# fillna_mode
# =====================================================================

def test_fillna_mode_basic():
    df = pd.DataFrame({"a": ["x", "y", "x", None]})

    out = fillna_mode(df, "a")

    assert out["a"].tolist() == ["x", "y", "x", "x"]


def test_fillna_mode_no_mode():
    df = pd.DataFrame({"a": [None, None]})

    out = fillna_mode(df, "a")

    # mode is empty -> value=None -> NA remains
    assert pd.isna(out["a"].iloc[0])
    assert pd.isna(out["a"].iloc[1])


# =====================================================================
# replace_empty_with_nan
# =====================================================================

def test_replace_empty_with_nan_basic():
    df = pd.DataFrame({"a": ["", "   ", "x", None]})

    out = replace_empty_with_nan(df, "a")

    assert pd.isna(out["a"].iloc[0])
    assert pd.isna(out["a"].iloc[1])
    assert out["a"].iloc[2] == "x"
    assert pd.isna(out["a"].iloc[3])


def test_replace_empty_with_nan_invalid_column():
    df = pd.DataFrame({"a": ["x"]})

    with pytest.raises(KeyError):
        replace_empty_with_nan(df, "b")
