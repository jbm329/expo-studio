import pandas as pd
import pytest

from expo_jbm329.services.data_operations.filter import (
    filter_between,
    filter_compare,
    filter_contains,
    filter_custom,
    filter_equals,
    filter_isna,
    filter_not_equals,
    filter_notna,
)

# =====================================================================
# Equality filters
# =====================================================================

def test_filter_equals_basic():
    df = pd.DataFrame({"a": [1, 2, 1]})

    out = filter_equals(df, "a", 1)

    assert out is not df
    assert out["a"].tolist() == [1, 1]


def test_filter_not_equals_basic():
    df = pd.DataFrame({"a": [1, 2, 1]})

    out = filter_not_equals(df, "a", 1)

    assert out["a"].tolist() == [2]


def test_filter_not_equals_nan():
    df = pd.DataFrame({"a": [1, None, 2]})

    out = filter_not_equals(df, "a", pd.NA)

    assert out["a"].tolist() == [1, 2]


# =====================================================================
# String filters
# =====================================================================

def test_filter_contains_case_sensitive():
    df = pd.DataFrame({"a": ["Foo", "bar", "foobar"]})

    out = filter_contains(df, "a", "foo", case=True)

    assert out["a"].tolist() == ["foobar"]


def test_filter_contains_case_insensitive():
    df = pd.DataFrame({"a": ["Foo", "bar", "foobar"]})

    out = filter_contains(df, "a", "foo", case=False)

    assert out["a"].tolist() == ["Foo", "foobar"]


# =====================================================================
# NA filters
# =====================================================================

def test_filter_isna():
    df = pd.DataFrame({"a": [1, None, 2]})

    out = filter_isna(df, "a")

    assert len(out) == 1
    assert pd.isna(out["a"].iloc[0])


def test_filter_notna():
    df = pd.DataFrame({"a": [1, None, 2]})

    out = filter_notna(df, "a")

    assert out["a"].tolist() == [1, 2]


# =====================================================================
# Comparison filters (numeric)
# =====================================================================

def test_filter_compare_numeric_gt():
    df = pd.DataFrame({"a": [1, 2, 3]})

    out = filter_compare(df, "a", ">", 1)

    assert out["a"].tolist() == [2, 3]


def test_filter_compare_numeric_le():
    df = pd.DataFrame({"a": [1, 2, 3]})

    out = filter_compare(df, "a", "<=", 2)

    assert out["a"].tolist() == [1, 2]


def test_filter_compare_invalid_dtype():
    df = pd.DataFrame({"a": ["x", "y"]})

    with pytest.raises(TypeError):
        filter_compare(df, "a", ">", 1)


# =====================================================================
# Comparison filters (datetime)
# =====================================================================

def test_filter_compare_datetime():
    df = pd.DataFrame(
        {"d": pd.to_datetime(["2024-01-01", "2024-01-10", "2024-02-01"])}
    )

    out = filter_compare(df, "d", ">", "2024-01-05")

    assert out["d"].dt.day.tolist() == [10, 1]


# =====================================================================
# Between filters
# =====================================================================

def test_filter_between_numeric_inclusive():
    df = pd.DataFrame({"a": [1, 2, 3, 4]})

    out = filter_between(df, "a", 2, 3, inclusive="both")

    assert out["a"].tolist() == [2, 3]


def test_filter_between_numeric_exclusive():
    df = pd.DataFrame({"a": [1, 2, 3, 4]})

    out = filter_between(df, "a", 2, 4, inclusive="neither")

    assert out["a"].tolist() == [3]


def test_filter_between_datetime():
    df = pd.DataFrame(
        {"d": pd.to_datetime(["2024-01-01", "2024-01-10", "2024-02-01"])}
    )

    out = filter_between(
        df,
        "d",
        "2024-01-05",
        "2024-01-31",
        inclusive="both",
    )

    assert out["d"].dt.day.tolist() == [10]


def test_filter_between_invalid_dtype():
    df = pd.DataFrame({"a": ["x", "y"]})

    with pytest.raises(TypeError):
        filter_between(df, "a", 1, 2)


# =====================================================================
# Custom predicate
# =====================================================================

def test_filter_custom_basic():
    df = pd.DataFrame({"a": [1, 2, 3]})

    out = filter_custom(df, lambda d: d["a"] > 1)

    assert out["a"].tolist() == [2, 3]


def test_filter_custom_invalid_return():
    df = pd.DataFrame({"a": [1, 2]})

    with pytest.raises(ValueError):
        filter_custom(df, lambda d: True)

