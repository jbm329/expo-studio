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


@pytest.mark.parametrize(
    ("series", "value"),
    [
        (pd.Series([1, 2, None], dtype="float64"), 1),
        (pd.Series([1, 2, None], dtype="Int64"), 1),
        (pd.Series([1, 2, None], dtype="UInt64"), 1),
        (pd.Series([1, 2, None], dtype="Float64"), 1),
        (pd.Series([True, False, None], dtype=object), True),
        (pd.Series([True, False, None], dtype="boolean"), True),
        (pd.Series(["a", "b", None], dtype=object), "a"),
        (pd.Series(["a", "b", None], dtype="string"), "a"),
        (pd.Series(["a", "b", None], dtype="category"), "a"),
        (pd.Series(pd.to_datetime(["2024-01-01", "2024-01-02", None])), pd.Timestamp("2024-01-01")),
    ],
)
def test_remove_matching_value_keeps_missing_rows(series: pd.Series, value: object) -> None:
    frame = pd.DataFrame({"value": series, "record": ["match", "different", "missing"]})
    frame.index = [4, 4, 1]
    original = frame.copy(deep=True)

    result = filter_not_equals(frame, "value", value)

    assert result is not frame
    pd.testing.assert_frame_equal(result, original.iloc[[1, 2]])
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("dtype", ["float64", "Int64", "boolean", "string"])
@pytest.mark.parametrize("missing_value", [None, float("nan"), pd.NA, pd.NaT])
def test_remove_missing_value_keeps_only_nonmissing_rows(dtype: str, missing_value: object) -> None:
    frame = pd.DataFrame({"value": pd.Series([1, None, 0], dtype=dtype)})
    original = frame.copy(deep=True)

    result = filter_not_equals(frame, "value", missing_value)

    pd.testing.assert_frame_equal(result, original.iloc[[0, 2]])
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("dtype", ["Int64", "UInt64"])
def test_remove_matching_large_integer_is_exact(dtype: str) -> None:
    frame = pd.DataFrame({"value": pd.Series([2**53 + 1, 2**53, None], dtype=dtype)})

    result = filter_not_equals(frame, "value", 2**53)

    pd.testing.assert_frame_equal(result, frame.iloc[[0, 2]])


@pytest.mark.parametrize("dtype", ["Int64", "boolean"])
@pytest.mark.parametrize("values", [[], [pd.NA, pd.NA]])
def test_remove_and_compare_empty_or_all_missing_columns(dtype: str, values: list[object]) -> None:
    frame = pd.DataFrame({"value": pd.Series(values, dtype=dtype)})
    original = frame.copy(deep=True)

    pd.testing.assert_frame_equal(filter_not_equals(frame, "value", 1), original)
    pd.testing.assert_frame_equal(filter_compare(frame, "value", "!=", 1), original)
    pd.testing.assert_frame_equal(frame, original)


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


@pytest.mark.parametrize("dtype", ["float64", "Int64", "UInt64", "Float64"])
@pytest.mark.parametrize(
    ("operator", "expected_rows"),
    [("==", [0]), ("!=", [1, 2]), (">", [1]), (">=", [0, 1]), ("<", []), ("<=", [0])],
)
def test_numeric_comparisons_apply_operator_missing_policy(dtype: str, operator: str, expected_rows: list[int]) -> None:
    frame = pd.DataFrame({"value": pd.Series([1, 2, None], dtype=dtype), "record": ["one", "two", "missing"]})
    frame.index = [5, 5, -1]
    original = frame.copy(deep=True)

    result = filter_compare(frame, "value", operator, 1)

    assert result is not frame
    pd.testing.assert_frame_equal(result, original.iloc[expected_rows])
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("dtype", ["Int64", "UInt64"])
@pytest.mark.parametrize("column", ["value", "a`b", "a b"])
def test_comparison_preserves_large_integer_precision_and_literal_column_names(dtype: str, column: str) -> None:
    frame = pd.DataFrame({column: pd.Series([2**53 + 1, 2**53, None], dtype=dtype)})

    result = filter_compare(frame, column, "!=", 2**53)

    pd.testing.assert_frame_equal(result, frame.iloc[[0, 2]])


@pytest.mark.parametrize(
    "series",
    [
        pd.Series([1, 2, None], dtype="float64"),
        pd.Series([1, 2, None], dtype="Int64"),
        pd.Series([1, 2, None], dtype="UInt64"),
        pd.Series([1, 2, None], dtype="Float64"),
        pd.Series([True, False, None], dtype="boolean"),
        pd.Series([True, False, True], dtype=bool),
        pd.Series([1, 2, 1], dtype="int64"),
    ],
)
def test_not_equals_comparison_matches_cell_removal(series: pd.Series) -> None:
    frame = pd.DataFrame({"value": series})
    original = frame.copy(deep=True)
    value = series.iloc[0]

    pd.testing.assert_frame_equal(filter_compare(frame, "value", "!=", value), filter_not_equals(frame, "value", value))
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("operator", ["=", "in", "not in", "invalid"])
def test_filter_compare_rejects_unsupported_operator(operator: str) -> None:
    with pytest.raises(ValueError, match="Unsupported comparison operator"):
        filter_compare(pd.DataFrame({"value": [1, 2]}), "value", operator, 1)


@pytest.mark.parametrize("dtype", ["int64", "Int64", "float64"])
def test_filter_compare_propagates_incompatible_value_error(dtype: str) -> None:
    frame = pd.DataFrame({"value": pd.Series([1, 2], dtype=dtype)})

    with pytest.raises(TypeError):
        filter_compare(frame, "value", ">", "invalid")


def test_filter_compare_propagates_invalid_datetime_error() -> None:
    frame = pd.DataFrame({"value": pd.to_datetime(["2024-01-01"])})

    with pytest.raises(ValueError):
        filter_compare(frame, "value", ">", "invalid")


@pytest.mark.parametrize("dtype", ["Int64", "float64"])
@pytest.mark.parametrize("value", [None, pd.NA, float("nan")])
def test_comparison_with_missing_operand_matches_no_rows(dtype: str, value: object) -> None:
    frame = pd.DataFrame({"value": pd.Series([1, None, 2], dtype=dtype)})

    result = filter_compare(frame, "value", "!=", value)

    pd.testing.assert_frame_equal(result, frame.iloc[[]])


# =====================================================================
# Comparison filters (datetime)
# =====================================================================


def test_filter_compare_datetime():
    df = pd.DataFrame({"d": pd.to_datetime(["2024-01-01", "2024-01-10", "2024-02-01"])})

    out = filter_compare(df, "d", ">", "2024-01-05")

    assert out["d"].dt.day.tolist() == [10, 1]


@pytest.mark.parametrize("timezone", [None, "UTC"])
@pytest.mark.parametrize(
    ("operator", "expected_rows"),
    [("==", [0]), ("!=", [1, 2]), (">", [1]), (">=", [0, 1]), ("<", []), ("<=", [0])],
)
def test_datetime_comparison_applies_operator_missing_policy(
    timezone: str | None, operator: str, expected_rows: list[int]
) -> None:
    series = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-02", None]))
    if timezone is not None:
        series = series.dt.tz_localize(timezone)
    frame = pd.DataFrame({"value": series})
    value = "2024-01-01" if timezone is None else "2024-01-01T00:00:00Z"
    original = frame.copy(deep=True)

    result = filter_compare(frame, "value", operator, value)

    pd.testing.assert_frame_equal(result, original.iloc[expected_rows])
    pd.testing.assert_frame_equal(frame, original)


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
    df = pd.DataFrame({"d": pd.to_datetime(["2024-01-01", "2024-01-10", "2024-02-01"])})

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
