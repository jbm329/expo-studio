"""Exact inference, operand widening and overflow checks for derived arithmetic."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from expo_jbm329.services.data_operations.derived_column.derived_column_expression import (
    expression_columns,
    parse_expression_formula,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_numeric import (
    IntegerOperation,
    NumericKind,
    checked_integer_arithmetic,
    common_numeric_kind,
    numeric_kind_from_dtype,
    numeric_literal_kind,
    parse_numeric_literal,
    prepare_integer_operand,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_parser import DerivedColumnFormulaError
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
    create_derived_column,
)

SIGNED_MIN = -(2**63)
SIGNED_MAX = 2**63 - 1
UNSIGNED_MAX = 2**64 - 1


@pytest.mark.parametrize(
    ("text", "expected", "kind"),
    [
        ("0", 0, NumericKind.SIGNED),
        ("+1", 1, NumericKind.SIGNED),
        ("-1", -1, NumericKind.SIGNED),
        (str(2**53 + 1), 2**53 + 1, NumericKind.SIGNED),
        (str(SIGNED_MIN), SIGNED_MIN, NumericKind.SIGNED),
        (str(SIGNED_MAX), SIGNED_MAX, NumericKind.SIGNED),
        (str(UNSIGNED_MAX), UNSIGNED_MAX, NumericKind.UNSIGNED),
        (str(2**64), 2**64, NumericKind.UNSIGNED),
        ("1.0", 1.0, NumericKind.FLOAT),
        ("1e0", 1.0, NumericKind.FLOAT),
        ("1E+2", 100.0, NumericKind.FLOAT),
        ("-.5", -0.5, NumericKind.FLOAT),
    ],
)
def test_exact_literal_parsing(text: str, expected: float, kind: NumericKind) -> None:
    value = parse_numeric_literal(text)
    assert value == expected
    assert type(value) is type(expected)
    assert numeric_literal_kind(value) == kind


@pytest.mark.parametrize("text", ["", "not a number", "1e999", "nan", "inf", "-inf"])
def test_invalid_literals_raise_structured_error(text: str) -> None:
    with pytest.raises(DerivedColumnFormulaError) as caught:
        parse_numeric_literal(text)
    assert caught.value.code == "invalid_number_literal"
    assert caught.value.context["token"] == text


@pytest.mark.parametrize(
    ("dtype", "expected"),
    [
        ("int8", NumericKind.SIGNED),
        ("Int16", NumericKind.SIGNED),
        ("int32", NumericKind.SIGNED),
        ("Int64", NumericKind.SIGNED),
        ("uint8", NumericKind.SIGNED),
        ("UInt16", NumericKind.SIGNED),
        ("uint32", NumericKind.SIGNED),
        ("UInt64", NumericKind.UNSIGNED),
        ("int64[pyarrow]", NumericKind.SIGNED),
        ("uint64[pyarrow]", NumericKind.UNSIGNED),
        ("Float32", NumericKind.FLOAT),
        ("float64[pyarrow]", NumericKind.FLOAT),
        ("boolean", None),
        ("bool[pyarrow]", None),
        ("object", None),
        ("string", None),
        ("datetime64[ns]", None),
        ("complex128", None),
        (pd.CategoricalDtype([1, 2]), NumericKind.SIGNED),
        (pd.CategoricalDtype(pd.Index([UNSIGNED_MAX], dtype="uint64")), NumericKind.UNSIGNED),
        (pd.CategoricalDtype([1.0, 2.5]), NumericKind.FLOAT),
        (pd.CategoricalDtype([True, False]), None),
        (pd.CategoricalDtype(), None),
    ],
)
def test_numeric_schema_classification(dtype: object, expected: NumericKind | None) -> None:
    assert numeric_kind_from_dtype(dtype) == expected
    assert expression_columns(["A"], [dtype])[0].numeric_kind == expected


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("[S]", NumericKind.SIGNED),
        ("[U]", NumericKind.UNSIGNED),
        ("[F]", NumericKind.FLOAT),
        ("[S]+[S]*2", NumericKind.SIGNED),
        ("[U]+1", NumericKind.UNSIGNED),
        ("+1*[U]", NumericKind.UNSIGNED),
        ("[U]+-1", NumericKind.SIGNED),
        ("[U]+[S]", NumericKind.SIGNED),
        ("[S]-[U]", NumericKind.SIGNED),
        ("-[U]", NumericKind.SIGNED),
        ("+[U]", NumericKind.UNSIGNED),
        ("[U]+1.0", NumericKind.FLOAT),
        ("[S]*1e0", NumericKind.FLOAT),
        ("[S]/[S]", NumericKind.FLOAT),
        (str(SIGNED_MIN), NumericKind.SIGNED),
        (str(UNSIGNED_MAX), NumericKind.UNSIGNED),
        (f"+{UNSIGNED_MAX}", NumericKind.UNSIGNED),
        ("IF(TRUE; [S]; NULL)", NumericKind.SIGNED),
        ("IF(FALSE; NULL; [U])", NumericKind.UNSIGNED),
        ("IF(TRUE; [U]; 0)", NumericKind.UNSIGNED),
        ("IF(TRUE; [U]; [S])", NumericKind.SIGNED),
        ("IF(TRUE; [S]; 0.0)", NumericKind.FLOAT),
        ("IF(FALSE; [F]; [S])", NumericKind.FLOAT),
        ("IF(TRUE; [S]; IF(FALSE; 0.0; NULL))", NumericKind.FLOAT),
        ("IF(TRUE; NULL; NULL)", None),
        ("NULL", None),
        ("NULL + [S]", NumericKind.SIGNED),
        ("NULL / [S]", NumericKind.FLOAT),
        ("NULL + NULL", None),
        ("'text'", None),
        ("IF(TRUE; 'text'; NULL)", None),
        ("YEAR([D])", NumericKind.SIGNED),
        ("ISOYEAR([D])", NumericKind.SIGNED),
        ("WEEK#([D])", NumericKind.SIGNED),
        ("MONTH#([D])", NumericKind.SIGNED),
        ("QUARTER#([D])", NumericKind.SIGNED),
        ("TERTIAL#([D])", NumericKind.SIGNED),
        ("YEAR([D])+[S]", NumericKind.SIGNED),
        ("YEAR([D])/2", NumericKind.FLOAT),
        ("MONTH([D])", None),
    ],
)
@pytest.mark.parametrize("empty", [False, True])
def test_expression_inference_uses_schema_not_values(formula: str, expected: NumericKind | None, empty: bool) -> None:
    source = pd.DataFrame({
        name: pd.Series([] if empty else [None, None], dtype=dtype)
        for name, dtype in (("S", "Int64"), ("U", "UInt64"), ("F", "Float64"), ("D", "datetime64[ns]"))
    })
    expression = parse_expression_formula(
        formula, expression_columns(list(source.columns), list(source.dtypes))
    ).expression
    assert expression.numeric_kind == expected
    assert formula[expression.start : expression.end] == formula


def test_null_and_literal_promotion_is_explicit() -> None:
    assert common_numeric_kind(None, None) is None
    assert common_numeric_kind(None, NumericKind.UNSIGNED) == NumericKind.UNSIGNED
    assert common_numeric_kind(NumericKind.UNSIGNED, None) == NumericKind.UNSIGNED
    assert common_numeric_kind(NumericKind.UNSIGNED, NumericKind.SIGNED) == NumericKind.SIGNED
    assert common_numeric_kind(NumericKind.UNSIGNED, NumericKind.SIGNED, right_literal=0) == NumericKind.UNSIGNED
    assert common_numeric_kind(NumericKind.SIGNED, NumericKind.UNSIGNED, left_literal=0) == NumericKind.UNSIGNED
    assert common_numeric_kind(NumericKind.SIGNED, NumericKind.UNSIGNED, left_literal=-1) == NumericKind.SIGNED


@pytest.mark.parametrize("dtype", ["Int8", "Int16", "Int32", "Int64", "int64[pyarrow]"])
def test_signed_operand_widening_preserves_index_nulls_and_source(dtype: str) -> None:
    values = pd.Series([120, None, -100], dtype=dtype, index=[8, 8, 2], name="A")
    original = values.copy(deep=True)
    result = prepare_integer_operand(values, NumericKind.SIGNED)
    assert_series_equal(result, pd.Series([120, None, -100], dtype="Int64", index=values.index, name="A"))
    assert_series_equal(values, original)


@pytest.mark.parametrize("kind", [NumericKind.SIGNED, NumericKind.UNSIGNED])
@pytest.mark.parametrize("empty", [False, True])
def test_null_operand_adopts_integer_kind(kind: NumericKind, empty: bool) -> None:
    values = pd.Series([] if empty else [None, None], dtype="Float64")
    assert_series_equal(prepare_integer_operand(values, kind), pd.Series(pd.NA, index=values.index, dtype=kind.value))


@pytest.mark.parametrize("kind", [NumericKind.SIGNED, NumericKind.UNSIGNED])
def test_correct_nullable_operands_are_reused_without_scanning_or_copying(kind: NumericKind) -> None:
    values = pd.Series([1, None], dtype=kind.value)
    assert prepare_integer_operand(values, kind) is values


@pytest.mark.parametrize(
    ("dtype", "values", "kind"),
    [
        ("UInt64", [2**63, None], NumericKind.SIGNED),
        ("uint64[pyarrow]", [UNSIGNED_MAX, None], NumericKind.SIGNED),
        ("Int64", [-1, None], NumericKind.UNSIGNED),
        ("boolean", [True, None], NumericKind.SIGNED),
        ("Float64", [1.0, None], NumericKind.SIGNED),
        ("object", [1, None], NumericKind.SIGNED),
    ],
)
def test_operand_conversion_does_not_wrap_or_coerce(
    dtype: str, values: list[int | float | None], kind: NumericKind
) -> None:
    with pytest.raises(DerivedColumnFormulaError) as caught:
        prepare_integer_operand(pd.Series(values, dtype=dtype), kind)
    assert caught.value.code == (
        "integer_out_of_range" if pd.api.types.is_integer_dtype(dtype) else "integer_operand_required"
    )


@pytest.mark.parametrize("operation", ["+", "-", "*"])
@pytest.mark.parametrize("kind", [NumericKind.SIGNED, NumericKind.UNSIGNED])
def test_arithmetic_boundary_grid_matches_python_integers(operation: Literal["+", "-", "*"], kind: NumericKind) -> None:
    lower, upper = (0, UNSIGNED_MAX) if kind == NumericKind.UNSIGNED else (SIGNED_MIN, SIGNED_MAX)
    edges = [0, 1, 2, upper // 2, upper - 1, upper]
    if kind == NumericKind.SIGNED:
        edges += [-1, -2, lower, lower + 1, lower // 2, 3037000499, 3037000500, -3037000500]
    for left in edges:
        for right in edges:
            expected = left + right if operation == "+" else left - right if operation == "-" else left * right
            a = pd.Series([left, None], dtype=kind.value, index=[7, 7])
            b = pd.Series([right, right], dtype=kind.value, index=a.index)
            if lower <= expected <= upper:
                scalar = checked_integer_arithmetic(operation, left, right, kind=kind)
                result = checked_integer_arithmetic(operation, a, b, kind=kind)
                assert isinstance(scalar, int)
                assert scalar == expected
                assert isinstance(result, pd.Series)
                assert_series_equal(result, pd.Series([expected, None], dtype=kind.value, index=a.index))
            else:
                for operands in ((left, right), (a, b)):
                    with pytest.raises(DerivedColumnFormulaError) as caught:
                        checked_integer_arithmetic(operation, *operands, kind=kind)
                    assert caught.value.code == "integer_overflow"
                    assert caught.value.context == {"operator": operation, "dtype": kind.value}


@pytest.mark.parametrize("operation", ["+", "-", "*"])
@pytest.mark.parametrize("kind", [NumericKind.SIGNED, NumericKind.UNSIGNED])
def test_vector_arithmetic_matches_seeded_exact_reference(operation: Literal["+", "-", "*"], kind: NumericKind) -> None:
    rng = np.random.default_rng(42)
    low = 0 if kind == NumericKind.UNSIGNED else -1_000_000
    left = [int(value) for value in rng.integers(low, 1_000_000, size=200)]
    right = [int(value) for value in rng.integers(low, 1_000_000, size=200)]
    expected = [
        a + b if operation == "+" else a - b if operation == "-" else a * b for a, b in zip(left, right, strict=True)
    ]
    if kind == NumericKind.UNSIGNED and operation == "-":
        left, right = (
            [max(a, b) for a, b in zip(left, right, strict=True)],
            [min(a, b) for a, b in zip(left, right, strict=True)],
        )
        expected = [a - b for a, b in zip(left, right, strict=True)]
    a = pd.Series([None if index % 7 == 0 else value for index, value in enumerate(left)], dtype=kind.value)
    b = pd.Series([None if index % 11 == 0 else value for index, value in enumerate(right)], dtype=kind.value)
    expected_values = [None if index % 7 == 0 or index % 11 == 0 else value for index, value in enumerate(expected)]
    result = checked_integer_arithmetic(operation, a, b, kind=kind)
    assert isinstance(result, pd.Series)
    assert_series_equal(result, pd.Series(expected_values, dtype=kind.value))


@pytest.mark.parametrize("operation", ["+", "-", "*"])
@pytest.mark.parametrize("kind", [NumericKind.SIGNED, NumericKind.UNSIGNED])
def test_full_width_vectors_match_python_bounds(operation: Literal["+", "-", "*"], kind: NumericKind) -> None:
    rng = np.random.default_rng(349)
    bits = rng.bit_generator.random_raw(600)
    array = bits if kind == NumericKind.UNSIGNED else bits.view(np.int64)
    left = [int(value) for value in array[:300]]
    right = [int(value) for value in array[300:]]
    # Include full-width products that fit as well as products that overflow.
    right[::3] = [1] * len(right[::3])
    lower, upper = (0, UNSIGNED_MAX) if kind == NumericKind.UNSIGNED else (SIGNED_MIN, SIGNED_MAX)
    fitting: list[tuple[int, int, int]] = []
    overflowing: list[tuple[int, int, int]] = []
    for a, b in zip(left, right, strict=True):
        value = a + b if operation == "+" else a - b if operation == "-" else a * b
        (fitting if lower <= value <= upper else overflowing).append((a, b, value))
    assert fitting and overflowing
    for cases, should_overflow in ((fitting, False), (overflowing, True)):
        a = pd.Series([case[0] for case in cases], dtype=kind.value)
        b = pd.Series([case[1] for case in cases], dtype=kind.value)
        if should_overflow:
            with pytest.raises(DerivedColumnFormulaError) as caught:
                checked_integer_arithmetic(operation, a, b, kind=kind)
            assert caught.value.code == "integer_overflow"
        else:
            result = checked_integer_arithmetic(operation, a, b, kind=kind)
            assert isinstance(result, pd.Series)
            assert_series_equal(result, pd.Series([case[2] for case in cases], dtype=kind.value))


@pytest.mark.parametrize(
    ("operation", "left", "right", "kind", "expected"),
    [
        ("+", 120, 10, NumericKind.SIGNED, 130),
        ("+", 255, 1, NumericKind.SIGNED, 256),
        ("+", 2**53 + 1, 2, NumericKind.SIGNED, 2**53 + 3),
        ("*", SIGNED_MIN, 1, NumericKind.SIGNED, SIGNED_MIN),
        ("*", SIGNED_MIN, 0, NumericKind.SIGNED, 0),
        ("*", UNSIGNED_MAX, 1, NumericKind.UNSIGNED, UNSIGNED_MAX),
        ("negative", SIGNED_MIN + 1, None, NumericKind.SIGNED, SIGNED_MAX),
        ("positive", SIGNED_MIN, None, NumericKind.SIGNED, SIGNED_MIN),
    ],
)
def test_scalar_and_series_arithmetic(
    operation: IntegerOperation, left: int, right: int | None, kind: NumericKind, expected: int
) -> None:
    source_dtype = "Int8" if left == 120 else "UInt8" if left == 255 else kind.value
    a = pd.Series([left, None], dtype=source_dtype)
    a.index = pd.MultiIndex.from_tuples([("a", 1), ("a", 1)])
    original = a.copy(deep=True)
    result = checked_integer_arithmetic(operation, a, right, kind=kind)
    assert isinstance(result, pd.Series)
    assert_series_equal(result, pd.Series([expected, None], dtype=kind.value, index=a.index))
    if right is not None:
        reverse = checked_integer_arithmetic(operation, left, pd.Series([right], dtype=kind.value), kind=kind)
        assert isinstance(reverse, pd.Series)
        assert_series_equal(reverse, pd.Series([expected], dtype=kind.value))
    assert_series_equal(a, original)


def test_scalar_signed_minimum_literal_is_exact() -> None:
    result = checked_integer_arithmetic("negative", 2**63, kind=NumericKind.SIGNED)
    assert isinstance(result, int)
    assert result == SIGNED_MIN


@pytest.mark.parametrize(
    ("operation", "left", "right", "kind", "code"),
    [
        ("+", 2**63, 0, NumericKind.SIGNED, "integer_out_of_range"),
        ("+", -1, 0, NumericKind.UNSIGNED, "integer_out_of_range"),
        ("*", 1, 2**64, NumericKind.UNSIGNED, "integer_out_of_range"),
        ("negative", SIGNED_MIN, None, NumericKind.SIGNED, "integer_overflow"),
        ("negative", 1, None, NumericKind.UNSIGNED, "integer_overflow"),
    ],
)
def test_invalid_scalar_operations_fail_explicitly(
    operation: IntegerOperation, left: int, right: int | None, kind: NumericKind, code: str
) -> None:
    with pytest.raises(DerivedColumnFormulaError) as caught:
        checked_integer_arithmetic(operation, left, right, kind=kind)
    assert caught.value.code == code


@pytest.mark.parametrize("kind", [NumericKind.SIGNED, NumericKind.UNSIGNED])
@pytest.mark.parametrize("operation", ["+", "-", "*", "positive", "negative"])
def test_empty_integer_results_keep_dtype(kind: NumericKind, operation: IntegerOperation) -> None:
    left = pd.Series([], dtype=kind.value)
    right = None if operation in {"positive", "negative"} else left
    result = checked_integer_arithmetic(operation, left, right, kind=kind)
    assert isinstance(result, pd.Series)
    assert_series_equal(result, left)


def test_empty_selection_does_not_evaluate_scalar_range() -> None:
    empty = pd.Series([], dtype="Int64")
    result = checked_integer_arithmetic("+", empty, 2**64, kind=NumericKind.SIGNED)
    assert isinstance(result, pd.Series)
    assert_series_equal(result, empty)


def test_unsigned_negation_uses_checked_signed_conversion() -> None:
    values = pd.Series([1, SIGNED_MAX, None], dtype="UInt64")
    result = checked_integer_arithmetic("negative", values, kind=NumericKind.SIGNED)
    assert isinstance(result, pd.Series)
    assert_series_equal(result, pd.Series([-1, -SIGNED_MAX, None], dtype="Int64"))
    with pytest.raises(DerivedColumnFormulaError) as caught:
        checked_integer_arithmetic("negative", pd.Series([2**63], dtype="UInt64"), kind=NumericKind.SIGNED)
    assert caught.value.code == "integer_out_of_range"


def test_missing_rows_cannot_trigger_overflow() -> None:
    left = pd.Series([SIGNED_MIN, None], dtype="Int64")
    right = pd.Series([None, -1], dtype="Int64")
    result = checked_integer_arithmetic("*", left, right, kind=NumericKind.SIGNED)
    assert isinstance(result, pd.Series)
    assert_series_equal(result, pd.Series([None, None], dtype="Int64"))


@pytest.mark.parametrize(
    ("left", "right", "kind", "expected"),
    [
        ([3037000499, -3037000499], [3037000499, 3037000499], NumericKind.SIGNED, [3037000499**2, -(3037000499**2)]),
        ([SIGNED_MIN, SIGNED_MAX], [1, 1], NumericKind.SIGNED, [SIGNED_MIN, SIGNED_MAX]),
        ([UNSIGNED_MAX, 0], [1, 1], NumericKind.UNSIGNED, [UNSIGNED_MAX, 0]),
        ([2**32 - 1, 0], [2**32 - 1, 0], NumericKind.UNSIGNED, [(2**32 - 1) ** 2, 0]),
        # Cross-row extrema can exceed the range even when each actual product fits.
        ([SIGNED_MIN, 1], [1, -1], NumericKind.SIGNED, [SIGNED_MIN, -1]),
        ([-(2**62), 2], [2, -(2**62)], NumericKind.SIGNED, [SIGNED_MIN, SIGNED_MIN]),
        ([UNSIGNED_MAX, 1], [1, UNSIGNED_MAX], NumericKind.UNSIGNED, [UNSIGNED_MAX, UNSIGNED_MAX]),
    ],
)
def test_multiplication_bounds_and_inconclusive_extrema_preserve_exact_results(
    left: list[int], right: list[int], kind: NumericKind, expected: list[int]
) -> None:
    a = pd.Series([*left, None], dtype=kind.value, index=[8, 8, 2])
    b = pd.Series([*right, 2], dtype=kind.value, index=a.index)
    original_a, original_b = a.copy(deep=True), b.copy(deep=True)
    result = checked_integer_arithmetic("*", a, b, kind=kind)
    assert isinstance(result, pd.Series)
    assert_series_equal(result, pd.Series([*expected, None], dtype=kind.value, index=a.index))
    assert_series_equal(a, original_a)
    assert_series_equal(b, original_b)


@pytest.mark.parametrize(
    ("left", "right", "kind"),
    [
        (3037000500, 3037000500, NumericKind.SIGNED),
        (SIGNED_MIN, -1, NumericKind.SIGNED),
        (-(2**62) - 1, 2, NumericKind.SIGNED),
        (2**32, 2**32, NumericKind.UNSIGNED),
        (UNSIGNED_MAX, 2, NumericKind.UNSIGNED),
    ],
)
@pytest.mark.parametrize("masked", [False, True])
def test_multiplication_outlier_is_checked_without_sampling(
    left: int, right: int, kind: NumericKind, masked: bool
) -> None:
    a = pd.Series([2] * 256 + [left], dtype=kind.value)
    b = pd.Series([3] * 256 + [None if masked else right], dtype=kind.value)
    if masked:
        result = checked_integer_arithmetic("*", a, b, kind=kind)
        assert isinstance(result, pd.Series)
        assert_series_equal(result, pd.Series([6] * 256 + [None], dtype=kind.value))
    else:
        with pytest.raises(DerivedColumnFormulaError) as caught:
            checked_integer_arithmetic("*", a, b, kind=kind)
        assert caught.value.code == "integer_overflow"


@pytest.mark.parametrize("kind", [NumericKind.SIGNED, NumericKind.UNSIGNED])
def test_individual_full_width_products_match_exact_python_bounds(kind: NumericKind) -> None:
    bits = np.random.default_rng(1284).bit_generator.random_raw(256)
    values = bits if kind == NumericKind.UNSIGNED else bits.view(np.int64)
    right_values = values[128:].copy()
    right_values[::3] = 1
    small = np.arange(len(right_values[1::3]), dtype=np.int64) % 17
    right_values[1::3] = small if kind == NumericKind.UNSIGNED else small - 8
    lower, upper = (0, UNSIGNED_MAX) if kind == NumericKind.UNSIGNED else (SIGNED_MIN, SIGNED_MAX)
    fitting = overflowing = 0
    for left, right in zip(values[:128], right_values, strict=True):
        expected = int(left) * int(right)
        a = pd.Series([0, int(left)], dtype=kind.value)
        b = pd.Series([0, int(right)], dtype=kind.value)
        with np.errstate(divide="raise", over="raise", invalid="raise"):
            if lower <= expected <= upper:
                fitting += 1
                result = checked_integer_arithmetic("*", a, b, kind=kind)
                assert isinstance(result, pd.Series)
                assert_series_equal(result, pd.Series([0, expected], dtype=kind.value))
            else:
                overflowing += 1
                with pytest.raises(DerivedColumnFormulaError) as caught:
                    checked_integer_arithmetic("*", a, b, kind=kind)
                assert caught.value.code == "integer_overflow"
    assert fitting > 0 and overflowing > 0


def test_signed_division_edge_cases_in_inconclusive_multiplication_bounds() -> None:
    a = pd.Series([SIGNED_MIN, SIGNED_MIN, -1, 0, SIGNED_MAX], dtype="Int64")
    b = pd.Series([0, 1, SIGNED_MAX, -1, -1], dtype="Int64")
    with np.errstate(divide="raise", over="raise", invalid="raise"):
        result = checked_integer_arithmetic("*", a, b, kind=NumericKind.SIGNED)
    assert isinstance(result, pd.Series)
    assert_series_equal(result, pd.Series([0, SIGNED_MIN, -SIGNED_MAX, 0, -SIGNED_MAX], dtype="Int64"))


@pytest.mark.parametrize("left,right", [(True, 1), (1, False)])
def test_boolean_scalars_are_not_integer_operands(left: int, right: int) -> None:
    with pytest.raises(DerivedColumnFormulaError) as caught:
        checked_integer_arithmetic("+", left, right, kind=NumericKind.SIGNED)
    assert caught.value.code == "integer_operand_required"


@pytest.mark.parametrize(
    ("left", "right", "kind", "expected"),
    [
        ("UInt64", "Int64", NumericKind.SIGNED, 3),
        ("UInt64", "UInt64", NumericKind.UNSIGNED, 3),
        ("uint64[pyarrow]", "Int64", NumericKind.SIGNED, 3),
    ],
)
def test_mixed_integer_storage_is_checked_before_arithmetic(
    left: str, right: str, kind: NumericKind, expected: int
) -> None:
    a = pd.Series([1, None], dtype=left)
    b = pd.Series([2, None], dtype=right)
    result = checked_integer_arithmetic("+", a, b, kind=kind)
    assert isinstance(result, pd.Series)
    assert_series_equal(result, pd.Series([expected, None], dtype=kind.value))
    with pytest.raises(DerivedColumnFormulaError) as caught:
        checked_integer_arithmetic(
            "+", pd.Series([UNSIGNED_MAX], dtype="UInt64"), pd.Series([0], dtype="Int64"), kind=NumericKind.SIGNED
        )
    assert caught.value.code == "integer_out_of_range"


def test_invalid_arity_kind_and_indexes_fail_explicitly() -> None:
    with pytest.raises(ValueError, match="integer numeric kind"):
        checked_integer_arithmetic("+", 1, 2, kind=NumericKind.FLOAT)
    with pytest.raises(ValueError, match="number of operands"):
        checked_integer_arithmetic("+", 1, kind=NumericKind.SIGNED)
    with pytest.raises(ValueError, match="number of operands"):
        checked_integer_arithmetic("negative", 1, 2, kind=NumericKind.SIGNED)
    with pytest.raises(ValueError, match="identical positional indexes"):
        checked_integer_arithmetic("+", pd.Series([1], index=[0]), pd.Series([2], index=[1]), kind=NumericKind.SIGNED)


@pytest.mark.parametrize("formula", ["IF(TRUE; [A]; 0)", "YEAR([When])"])
def test_if_merge_and_date_parts_preserve_integer_output(formula: str) -> None:
    source = pd.DataFrame({
        "A": pd.Series([1, None], dtype="Int64"),
        "B": pd.Series([2, 3], dtype="Int64"),
        "When": pd.to_datetime(pd.Series(["2026-01-01", None], dtype="string")),
    })
    result = create_derived_column(source, DerivedColumnSpec("Result", formula))
    assert str(result["Result"].dtype) == "Int64"
