import pandas as pd

from expo_jbm329.services.data_operations.dtypes import (
    classify_series_dtype,
    is_boolean_dtype_column,
    is_categorical_dtype_column,
    is_categorical_series,
    is_datetime_dtype_column,
    is_float_dtype_column,
    is_integer_dtype_column,
    is_numeric_dtype_column,
    is_semantic_string_column,
    is_string_dtype_column,
    is_text_like_dtype,
)

# =====================================================================
# classify_series_dtype
# =====================================================================

def test_classify_series_dtype_integer():
    s = pd.Series([1, 2, 3], dtype="Int64")

    assert classify_series_dtype(s) == "int"


def test_classify_series_dtype_float():
    s = pd.Series([1.0, 2.5, None])

    assert classify_series_dtype(s) == "float"


def test_classify_series_dtype_bool():
    s = pd.Series([True, False, None], dtype="boolean")

    assert classify_series_dtype(s) == "bool"


def test_classify_series_dtype_datetime():
    s = pd.to_datetime(["2024-01-01", "2024-01-02"])

    assert classify_series_dtype(pd.Series(s)) == "datetime"


def test_classify_series_dtype_string():
    s = pd.Series(["a", "b", None], dtype="string")

    assert classify_series_dtype(s) == "string"


def test_classify_series_dtype_other():
    s = pd.Series([[1], [2]])

    assert classify_series_dtype(s) == "other"


# =====================================================================
# is_text_like_dtype
# =====================================================================

def test_is_text_like_string_dtype():
    s = pd.Series(["a", "b"], dtype="string")

    assert is_text_like_dtype(s) is True


def test_is_text_like_object_dtype():
    s = pd.Series(["a", "b"], dtype=object)

    assert is_text_like_dtype(s) is True


def test_is_text_like_categorical_string():
    s = pd.Series(
        pd.Categorical(["a", "b"], categories=["a", "b"])
    )

    assert is_text_like_dtype(s) is True


def test_is_text_like_numeric_false():
    s = pd.Series([1, 2, 3])

    assert is_text_like_dtype(s) is False


# =====================================================================
# is_categorical_series
# =====================================================================

def test_is_categorical_series_true():
    s = pd.Series(pd.Categorical(["a", "b"]))

    assert is_categorical_series(s) is True


def test_is_categorical_series_false():
    s = pd.Series(["a", "b"])

    assert is_categorical_series(s) is False


# =====================================================================
# UI-index based helpers
# =====================================================================

def _df_for_ui_tests():
    return pd.DataFrame(
        {
            "txt": ["a", "b"],
            "num": [1, 2],
            "flt": [1.0, 2.0],
            "flag": [True, False],
            "dt": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "cat": pd.Categorical(["x", "y"]),
        }
    )


def test_is_semantic_string_column():
    df = _df_for_ui_tests()

    is_str, col = is_semantic_string_column(df, 1)

    assert is_str is True
    assert col == "txt"


def test_is_numeric_dtype_column():
    df = _df_for_ui_tests()

    is_num, col = is_numeric_dtype_column(df, 2)

    assert is_num is True
    assert col == "num"


def test_is_integer_dtype_column():
    df = _df_for_ui_tests()

    is_int, col = is_integer_dtype_column(df, 2)

    assert is_int is True
    assert col == "num"


def test_is_float_dtype_column():
    df = _df_for_ui_tests()

    is_flt, col = is_float_dtype_column(df, 3)

    assert is_flt is True
    assert col == "flt"


def test_is_boolean_dtype_column():
    df = _df_for_ui_tests()

    is_bool, col = is_boolean_dtype_column(df, 4)

    assert is_bool is True
    assert col == "flag"


def test_is_string_dtype_column():
    df = _df_for_ui_tests()

    is_str, col = is_string_dtype_column(df, 1)

    assert is_str is True
    assert col == "txt"


def test_is_datetime_dtype_column():
    df = _df_for_ui_tests()

    is_dt, col = is_datetime_dtype_column(df, 5)

    assert is_dt is True
    assert col == "dt"


def test_is_categorical_dtype_column():
    df = _df_for_ui_tests()

    is_cat, col = is_categorical_dtype_column(df, 6)

    assert is_cat is True
    assert col == "cat"


def test_ui_helpers_index_zero_is_index_guard():
    df = _df_for_ui_tests()

    assert is_numeric_dtype_column(df, 0) == (False, None)
    assert is_semantic_string_column(df, 0) == (False, None)
