import pandas as pd
import pytest

from expo_jbm329.services.data_operations.convert import (
    to_boolean,
    to_category,
    to_datetime,
    to_float,
    to_integer,
    to_string,
)

# =====================================================================
# to_string
# =====================================================================

def test_to_string_preserves_na():
    df = pd.DataFrame({"a": [1, None, "x"]})

    out = to_string(df, "a")

    assert out["a"].dtype.name == "string"
    assert pd.isna(out["a"].iloc[1])


# =====================================================================
# to_integer
# =====================================================================

def test_to_integer_basic():
    df = pd.DataFrame({"a": ["1", "2", None]})

    out = to_integer(df, "a")

    assert out["a"].dtype.name == "Int64"
    assert out["a"].tolist() == [1, 2, pd.NA]


def test_to_integer_invalid_coerce():
    df = pd.DataFrame({"a": ["1", "x"]})

    out = to_integer(df, "a", errors="coerce")

    assert out["a"].tolist() == [1, pd.NA]


def test_to_integer_invalid_raise():
    df = pd.DataFrame({"a": ["1", "x"]})

    with pytest.raises(TypeError):
        to_integer(df, "a", errors="raise")


# =====================================================================
# to_float
# =====================================================================

def test_to_float_basic():
    df = pd.DataFrame({"a": ["1.5", "2"]})

    out = to_float(df, "a")

    assert out["a"].dtype == "float64"
    assert out["a"].tolist() == [1.5, 2.0]


# =====================================================================
# to_boolean
# =====================================================================

def test_to_boolean_default_values():
    df = pd.DataFrame({"a": ["yes", "no", "ja", "nej", None]})

    out = to_boolean(df, "a")

    assert out["a"].dtype.name == "boolean"
    assert out["a"].tolist() == [True, False, True, False, pd.NA]


def test_to_boolean_custom_values():
    df = pd.DataFrame({"a": ["Y", "N", "x"]})

    out = to_boolean(
        df,
        "a",
        true_values=["Y"],
        false_values=["N"],
    )

    assert out["a"].tolist() == [True, False, pd.NA]


def test_to_boolean_raise_on_unknown():
    df = pd.DataFrame({"a": ["yes", "maybe"]})

    with pytest.raises(ValueError):
        to_boolean(df, "a", errors="raise")


# =====================================================================
# to_datetime
# =====================================================================

def test_to_datetime_basic():
    df = pd.DataFrame({"d": ["2024-01-01", "2024-01-02"]})

    out = to_datetime(df, "d")

    assert pd.api.types.is_datetime64_any_dtype(out["d"])


def test_to_datetime_with_format():
    df = pd.DataFrame({"d": ["01-02-2024"]})

    out = to_datetime(df, "d", fmt="%d-%m-%Y")

    assert out["d"].iloc[0].year == 2024
    assert out["d"].iloc[0].month == 2


def test_to_datetime_date_only():
    df = pd.DataFrame({"d": ["2024-01-01 12:34:56"]})

    out = to_datetime(df, "d", date_only=True)

    assert str(out["d"].iloc[0]) == "2024-01-01 00:00:00"


def test_to_datetime_coerce_invalid():
    df = pd.DataFrame({"d": ["not-a-date"]})

    out = to_datetime(df, "d", errors="coerce")

    assert pd.isna(out["d"].iloc[0])


# =====================================================================
# to_category
# =====================================================================

def test_to_category_alpha_order():
    df = pd.DataFrame({"a": ["b", "a", "c", "a"]})

    out = to_category(df, "a", order="alpha")

    assert list(out["a"].dtype.categories) == ["a", "b", "c"]


def test_to_category_freq_order():
    df = pd.DataFrame({"a": ["b", "a", "a", "c", "a"]})

    out = to_category(df, "a", order="freq")

    assert list(out["a"].dtype.categories) == ["a", "b", "c"]


def test_to_category_preserve_order():
    df = pd.DataFrame({"a": ["b", "a", "c", "a"]})

    out = to_category(df, "a", order="preserve")

    assert list(out["a"].dtype.categories) == ["b", "a", "c"]
