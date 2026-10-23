import pandas as pd
import pytest

from expo_jbm329.services.data_operations.dtypes import (
    SemanticDType,
    classify_series_dtype,
    get_numeric_column_positions,
    get_numeric_columns,
    is_categorical_series,
    is_numeric_series,
    is_text_like_dtype,
)


def test_classify_series_dtype_integer():
    series = pd.Series([1, 2, 3], dtype="Int64")

    assert classify_series_dtype(series) == SemanticDType.INT


def test_classify_series_dtype_float():
    series = pd.Series([1.0, 2.5, None])

    assert classify_series_dtype(series) == SemanticDType.FLOAT


def test_classify_series_dtype_bool():
    series = pd.Series([True, False, None], dtype="boolean")

    assert classify_series_dtype(series) == SemanticDType.BOOL


def test_classify_series_dtype_datetime():
    series = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-02"]))

    assert classify_series_dtype(series) == SemanticDType.DATETIME


def test_classify_series_dtype_string():
    series = pd.Series(["a", "b", None], dtype="string")

    assert classify_series_dtype(series) == SemanticDType.STRING


def test_classify_series_dtype_category():
    series = pd.Series(pd.Categorical(["a", "b"]))

    assert classify_series_dtype(series) == SemanticDType.CATEGORY


def test_classify_series_dtype_other():
    series = pd.Series([[1], [2]])

    assert classify_series_dtype(series) == SemanticDType.OTHER


def test_is_text_like_string_dtype():
    series = pd.Series(["a", "b"], dtype="string")

    assert is_text_like_dtype(series) is True


def test_is_text_like_object_dtype():
    series = pd.Series(["a", "b"], dtype=object)

    assert is_text_like_dtype(series) is True


def test_is_text_like_categorical_string():
    series = pd.Series(pd.Categorical(["a", "b"], categories=["a", "b"]))

    assert is_text_like_dtype(series) is True


def test_is_text_like_numeric_false():
    series = pd.Series([1, 2, 3])

    assert is_text_like_dtype(series) is False


def test_is_categorical_series_true():
    series = pd.Series(pd.Categorical(["a", "b"]))

    assert is_categorical_series(series) is True


def test_is_categorical_series_false():
    series = pd.Series(["a", "b"])

    assert is_categorical_series(series) is False


def test_is_numeric_series_int_and_float_true():
    int_series = pd.Series([1, 2, 3], dtype="Int64")
    float_series = pd.Series([1.0, 2.5, None])

    assert is_numeric_series(int_series) is True
    assert is_numeric_series(float_series) is True


def test_is_numeric_series_bool_only_when_included():
    series = pd.Series([True, False, None], dtype="boolean")

    assert is_numeric_series(series) is False
    assert is_numeric_series(series, include_bool=True) is True


def test_get_numeric_columns_excludes_booleans_by_default():
    df = pd.DataFrame({
        "txt": ["a", "b"],
        "num": [1, 2],
        "flt": [1.0, 2.0],
        "flag": [True, False],
        "cat": pd.Categorical(["x", "y"]),
    })

    assert get_numeric_columns(df) == ["num", "flt"]


def test_get_numeric_columns_can_include_booleans():
    df = pd.DataFrame({
        "txt": ["a", "b"],
        "num": [1, 2],
        "flt": [1.0, 2.0],
        "flag": [True, False],
        "cat": pd.Categorical(["x", "y"]),
    })

    assert get_numeric_columns(df, include_bool=True) == ["num", "flt", "flag"]


@pytest.mark.parametrize(
    ("dtype", "eligible"),
    [
        ("int32", True),
        ("int64", True),
        ("uint64", True),
        ("float32", True),
        ("float64", True),
        ("Int64", True),
        ("UInt64", True),
        ("Float64", True),
        ("int64[pyarrow]", True),
        ("uint64[pyarrow]", True),
        ("float[pyarrow]", True),
        ("double[pyarrow]", True),
        ("bool", False),
        ("boolean", False),
        ("bool[pyarrow]", False),
        ("complex128", False),
        ("datetime64[ns]", False),
        ("timedelta64[ns]", False),
        ("object", False),
        ("string", False),
        ("string[pyarrow]", False),
        ("category", False),
    ],
)
def test_numeric_positions_use_dtype_even_without_rows(dtype, eligible):
    dataframe = pd.DataFrame({"empty": pd.Series([], dtype=dtype)})
    original = dataframe.copy(deep=True)
    assert get_numeric_column_positions(dataframe) == ((0,) if eligible else ())
    pd.testing.assert_frame_equal(dataframe, original)


def test_numeric_positions_preserve_order_labels_and_exclude_numeric_looking_values():
    series = [
        pd.Series(["1", "2"], dtype=object),
        pd.Series([None, None], dtype="Int64"),
        pd.Series(["1", "2"], dtype="string"),
        pd.Series([None, None], dtype="Float64"),
        pd.Series(pd.Categorical([1, 2])),
        pd.Series([1, 2], dtype="uint64"),
        pd.Series([float("nan"), float("nan")]),
    ]
    dataframe = pd.concat(series, axis=1)
    dataframe.columns = [1, "1", "duplicate", "duplicate", ("tuple", 0), None, "null_float"]
    original = dataframe.copy(deep=True)
    assert get_numeric_column_positions(dataframe) == (1, 3, 5, 6)
    pd.testing.assert_frame_equal(dataframe, original)
    assert get_numeric_column_positions(pd.DataFrame()) == ()


def test_numeric_positions_do_not_access_values_or_semantic_inference(monkeypatch):
    from expo_jbm329.services.data_operations import dtypes

    dataframe = pd.DataFrame({
        "numeric": pd.Series([1, 2], dtype="Int64"),
        "text": pd.Series(["1", "2"], dtype=object),
    })

    def reject_value_access(*args, **kwargs):
        message = "Numeric position discovery must use dtype metadata only."
        raise AssertionError(message)

    monkeypatch.setattr(pd.DataFrame, "__getitem__", reject_value_access)
    monkeypatch.setattr(pd.DataFrame, "iloc", property(reject_value_access))
    monkeypatch.setattr(pd.DataFrame, "values", property(reject_value_access))
    monkeypatch.setattr(dtypes, "classify_series_dtype", reject_value_access)
    assert get_numeric_column_positions(dataframe) == (0,)
