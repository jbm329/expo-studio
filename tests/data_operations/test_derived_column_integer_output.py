"""Service-level integer preservation through both existing formula grammars."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from expo_jbm329.services.data_operations.derived_column.derived_column_evaluation import evaluate_expression
from expo_jbm329.services.data_operations.derived_column.derived_column_expression import (
    expression_columns,
    parse_expression_formula,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_parser import (
    DerivedColumnFormulaError,
    parse_formula_to_rpn,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
    create_derived_column,
    evaluate_rpn,
    preview_derived_column,
    validate_derived_column_spec,
)


def formula_for_path(formula: str, typed: bool) -> str:
    """Force the typed grammar with a unary plus on a grouped expression."""
    return f"+({formula})" if typed else formula


INTEGER_DTYPES = [
    "int8",
    "int16",
    "int32",
    "int64",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
    "Int8",
    "Int16",
    "Int32",
    "Int64",
    "UInt8",
    "UInt16",
    "UInt32",
    "UInt64",
    "int64[pyarrow]",
    "uint64[pyarrow]",
]


@pytest.mark.parametrize("dtype", INTEGER_DTYPES)
@pytest.mark.parametrize("typed", [False, True])
@pytest.mark.parametrize(
    "formula,expected", [("[A]+[B]", [130, 102]), ("[A]-[B]", [110, 98]), ("[A]*[B]", [1200, 200])]
)
def test_integer_arithmetic_widens_before_evaluation(
    dtype: str, typed: bool, formula: str, expected: list[int]
) -> None:
    source = pd.DataFrame({"A": pd.Series([120, 100], dtype=dtype), "B": pd.Series([10, 2], dtype=dtype)})
    original = source.copy(deep=True)
    spec = DerivedColumnSpec("Result", formula_for_path(formula, typed))
    assert validate_derived_column_spec(source, spec).ok
    result = create_derived_column(source, spec)
    output_dtype = "UInt64" if dtype.lower().replace("[pyarrow]", "") == "uint64" else "Int64"
    assert_series_equal(result.Result, pd.Series(expected, dtype=output_dtype, name="Result"))
    assert_frame_equal(source, original)


@pytest.mark.parametrize("dtype", ["int64", "uint64"])
@pytest.mark.parametrize("typed", [False, True])
@pytest.mark.parametrize("formula", ["[A]", "[A]+[B]", "[A]*[B]"])
def test_shared_numpy_operand_storage_does_not_alias_created_output(dtype: str, typed: bool, formula: str) -> None:
    source = pd.DataFrame({
        "A": pd.Series([2, 3], dtype=dtype),
        "B": pd.Series([4, 5], dtype=dtype),
    })
    original = source.copy(deep=True)
    result = create_derived_column(source, DerivedColumnSpec("Result", formula_for_path(formula, typed)))
    assert not np.shares_memory(result.Result.to_numpy(), source.A.to_numpy())
    result.loc[0, "Result"] = 99
    result.loc[1, "Result"] = pd.NA
    assert_frame_equal(source, original)


@pytest.mark.parametrize("dtype", INTEGER_DTYPES + ["category"])
@pytest.mark.parametrize("empty", [False, True])
def test_integer_if_null_replacement_preserves_exact_values_schema_and_preview(dtype: str, empty: bool) -> None:
    storage = "Int64" if dtype == "category" else dtype
    wide = dtype.lower().replace("[pyarrow]", "") in {"int64", "uint64"} or dtype == "category"
    value = 2**53 + 1 if wide else 120
    values = pd.Series([value, value + 1], dtype=storage)
    if dtype == "category":
        values = values.astype("category")
    source = pd.DataFrame({"A": values})
    source.index = pd.MultiIndex.from_tuples([("a", 1), ("a", 1)], names=["group", "row"])
    if empty:
        source = source.iloc[:0]
    original = source.copy(deep=True)
    spec = DerivedColumnSpec("Result", "IF([A] IS NULL; 0; IF(TRUE; [A]; NULL))")
    result = create_derived_column(source, spec).Result
    expected_dtype = "UInt64" if dtype.lower().replace("[pyarrow]", "") == "uint64" else "Int64"
    assert_series_equal(
        result,
        pd.Series([] if empty else [value, value + 1], dtype=expected_dtype, index=source.index, name="Result"),
    )
    preview = preview_derived_column(source, spec, rows=1)
    assert preview.ok and preview.data is not None
    assert_series_equal(preview.data.Result, result.head(1))
    assert_frame_equal(source, original)


@pytest.mark.parametrize(
    ("formula", "expected", "dtype"),
    [
        ("IF([Flag]; [A]; NULL)", [2**53 + 1, None, None], "Int64"),
        ("IF([Flag]; NULL; [A])", [None, 2**53 + 3, None], "Int64"),
        ("IF([A] IS NULL; 0; [A])", [2**53 + 1, 2**53 + 3, 0], "Int64"),
        ("IF([Flag]; [U]; 0)", [2**64 - 1, 0, 0], "UInt64"),
        ("IF([Flag]; [U]; NULL)", [2**64 - 1, None, None], "UInt64"),
        ("IF([Flag]; IF(TRUE; [A]; NULL); 1)+1", [2**53 + 2, 2, 2], "Int64"),
        ("IF(TRUE; [A]; 0.0)", [float(2**53 + 1), float(2**53 + 3), None], "Float64"),
        ("IF(TRUE; [A]; 1e0)", [float(2**53 + 1), float(2**53 + 3), None], "Float64"),
        ("IF(TRUE; [A]; [F])", [float(2**53 + 1), float(2**53 + 3), None], "Float64"),
        ("IF([Flag]; NULL; NULL)", [None, None, None], "Float64"),
    ],
)
@pytest.mark.parametrize("empty", [False, True])
def test_if_merge_uses_full_schema_not_selected_values(
    formula: str, expected: list[int | float | None], dtype: str, empty: bool
) -> None:
    source = pd.DataFrame({
        "A": pd.Series([2**53 + 1, 2**53 + 3, None], dtype="Int64"),
        "U": pd.Series([2**64 - 1, 1, None], dtype="UInt64"),
        "F": pd.Series([None, None, None], dtype="Float64"),
        "Flag": pd.Series([True, False, None], dtype="boolean"),
    })
    source.index = pd.Index([8, 8, 1], name="row")
    if empty:
        source = source.iloc[:0]
    spec = DerivedColumnSpec("Result", formula)
    result = create_derived_column(source, spec).Result
    assert_series_equal(result, pd.Series([] if empty else expected, index=source.index, dtype=dtype, name="Result"))
    preview = preview_derived_column(source, spec, rows=1)
    assert preview.ok and preview.data is not None
    assert_series_equal(preview.data.Result, result.head(1))


@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("output_dtype", ["auto", "Float64"])
def test_if_checks_only_selected_unsigned_rows_before_signed_merge(
    active: bool, output_dtype: Literal["auto", "Float64"]
) -> None:
    source = pd.DataFrame({
        "U": pd.Series([2**63, 2, None], dtype="UInt64"),
        "S": pd.Series([-1, -2, -3], dtype="Int64"),
        "Flag": pd.Series([active, True, True], dtype="boolean"),
    })
    formula = "IF([Flag]; [U]; [S])"
    spec = DerivedColumnSpec("Result", formula, output_dtype=output_dtype)
    if active:
        with pytest.raises(DerivedColumnFormulaError) as caught:
            create_derived_column(source, spec)
        assert caught.value.code == "integer_out_of_range"
        assert caught.value.context["position"] == 0
        assert caught.value.context["end"] == len(formula)
    else:
        result = create_derived_column(source, spec).Result
        assert_series_equal(
            result, pd.Series([-1, 2, None], dtype="Int64" if output_dtype == "auto" else "Float64", name="Result")
        )


@pytest.mark.parametrize("branch", ["[Max]+1", "[Max]*2", str(2**64), f"{-(2**63) - 1}", "YEAR([When])+[Max]"])
@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("output_dtype", ["auto", "Float64"])
def test_if_preserves_lazy_integer_errors_and_date_arithmetic(
    branch: str, active: bool, output_dtype: Literal["auto", "Float64"]
) -> None:
    source = pd.DataFrame({
        "Max": pd.Series([2**63 - 1], dtype="Int64"),
        "When": pd.to_datetime(["2026-01-01"]),
    })
    formula = f"IF({'TRUE' if active else 'FALSE'}; {branch}; 0)"
    if active:
        with pytest.raises(DerivedColumnFormulaError) as caught:
            create_derived_column(source, DerivedColumnSpec("Result", formula, output_dtype=output_dtype))
        assert caught.value.code in {"integer_overflow", "integer_out_of_range"}
        start, end = caught.value.context["position"], caught.value.context["end"]
        assert isinstance(start, int) and isinstance(end, int)
        assert formula[start:end] == branch
    else:
        result = create_derived_column(source, DerivedColumnSpec("Result", formula, output_dtype=output_dtype)).Result
        assert result.iloc[0] == 0
        if output_dtype == "Float64":
            assert str(result.dtype) == "Float64"
        else:
            assert pd.api.types.is_integer_dtype(result.dtype)


@pytest.mark.parametrize("dtype", ["Int64", "UInt64", "int64[pyarrow]", "uint64[pyarrow]"])
@pytest.mark.parametrize("formula", ["IF(TRUE; [A]; NULL)", "IF(FALSE; NULL; [A])"])
def test_all_missing_if_branch_retains_integer_schema(dtype: str, formula: str) -> None:
    source = pd.DataFrame({"A": pd.Series([None, None], dtype=dtype)})
    result = create_derived_column(source, DerivedColumnSpec("Result", formula)).Result
    expected_dtype = "UInt64" if dtype.lower().startswith("u") else "Int64"
    assert_series_equal(result, pd.Series([None, None], dtype=expected_dtype, name="Result"))


@pytest.mark.parametrize("dtype", ["Int64", "UInt64"])
def test_if_keeps_large_categorical_values_exact_with_missing_codes(dtype: str) -> None:
    value = 2**64 - 1 if dtype == "UInt64" else 2**53 + 1
    source = pd.DataFrame({"A": pd.Series([value, None], dtype=dtype).astype("category")})
    result = create_derived_column(source, DerivedColumnSpec("Result", "IF(TRUE; [A]; NULL)")).Result
    assert_series_equal(result, pd.Series([value, None], dtype=dtype, name="Result"))


@pytest.mark.parametrize("function", ["YEAR", "ISOYEAR", "WEEK#", "MONTH#", "QUARTER#", "TERTIAL#"])
@pytest.mark.parametrize("output_dtype", ["auto", "Float64"])
def test_numeric_date_parts_keep_nulls_inside_if_and_arithmetic(
    function: str, output_dtype: Literal["auto", "Float64"]
) -> None:
    source = pd.DataFrame({"When": pd.to_datetime(pd.Series(["2026-01-01", None], dtype="string"))})
    formula = f"IF([When] IS NULL; NULL; {function}([When]))+1"
    expected = 2027 if function in {"YEAR", "ISOYEAR"} else 2
    result = create_derived_column(source, DerivedColumnSpec("Result", formula, output_dtype=output_dtype)).Result
    assert_series_equal(
        result, pd.Series([expected, None], dtype="Int64" if output_dtype == "auto" else "Float64", name="Result")
    )


@pytest.mark.parametrize("dtype", ["Int64", "UInt64", "int64[pyarrow]", "uint64[pyarrow]", "category"])
@pytest.mark.parametrize("typed", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_exact_large_values_missing_and_empty_outputs(dtype: str, typed: bool, empty: bool) -> None:
    values = pd.Series([2**53 + 1, None, 2**53 + 3], dtype="Int64" if dtype == "category" else dtype)
    if dtype == "category":
        values = values.astype("category")
    source = pd.DataFrame({"A": values})
    source.index = pd.MultiIndex.from_tuples([("a", 1), ("a", 1), ("b", 2)], names=["group", "row"])
    if empty:
        source = source.iloc[:0]
    original = source.copy(deep=True)
    spec = DerivedColumnSpec("Result", formula_for_path("[A]+1", typed))
    result = create_derived_column(source, spec, insertion_index=0)
    output_dtype = "UInt64" if dtype.startswith(("U", "u")) else "Int64"
    expected = pd.Series(
        [] if empty else [2**53 + 2, None, 2**53 + 4], index=source.index, dtype=output_dtype, name="Result"
    )
    assert_series_equal(result.Result, expected)
    preview = preview_derived_column(source, spec, rows=2)
    assert preview.ok and preview.data is not None
    assert_series_equal(preview.data.Result, result.Result.head(2))
    assert_frame_equal(source, original)


@pytest.mark.parametrize("typed", [False, True])
@pytest.mark.parametrize("values", [[], [None, None]])
@pytest.mark.parametrize("dtype", ["Int64", "UInt64", "int64[pyarrow]"])
def test_all_missing_integer_schema_stays_integer(typed: bool, values: list[None], dtype: str) -> None:
    source = pd.DataFrame({"A": pd.Series(values, dtype=dtype)})
    result = create_derived_column(source, DerivedColumnSpec("Result", formula_for_path("[A]*2", typed)))
    assert_series_equal(
        result.Result,
        pd.Series(pd.NA, index=source.index, dtype="UInt64" if dtype == "UInt64" else "Int64", name="Result"),
    )


@pytest.mark.parametrize("typed", [False, True])
@pytest.mark.parametrize(
    ("formula", "expected", "dtype"),
    [
        ("[A]", [3, None], "Int64"),
        ("[A]+1", [4, None], "Int64"),
        ("([A]+2)*3-1", [14, None], "Int64"),
        ("1+2", [3, 3], "Int64"),
        (str(2**63 - 1), [2**63 - 1, 2**63 - 1], "Int64"),
        (str(-(2**63)), [-(2**63), -(2**63)], "Int64"),
        (str(2**64 - 1), [2**64 - 1, 2**64 - 1], "UInt64"),
        ("[U]+1", [2**64 - 1, None], "UInt64"),
        ("0+[U]", [2**64 - 2, None], "UInt64"),
        ("[A]+1.0", [4.0, None], "Float64"),
        ("[A]+[F]", [4.0, None], "Float64"),
        ("[A]/1", [3.0, None], "Float64"),
        ("2/1", [2.0, 2.0], "Float64"),
        ("1.0", [1.0, 1.0], "Float64"),
    ],
)
def test_literal_and_operator_result_contract(
    typed: bool, formula: str, expected: list[int | float | None], dtype: str
) -> None:
    source = pd.DataFrame({
        "A": pd.Series([3, None], dtype="Int16"),
        "F": pd.Series([1.0, None], dtype="Float64"),
        "U": pd.Series([2**64 - 2, None], dtype="UInt64"),
    })
    result = create_derived_column(source, DerivedColumnSpec("Result", formula_for_path(formula, typed)))
    assert_series_equal(result.Result, pd.Series(expected, dtype=dtype, name="Result"))


@pytest.mark.parametrize("typed", [False, True])
@pytest.mark.parametrize(
    ("formula", "code"),
    [
        ("[Max]+1", "integer_overflow"),
        ("([Max]+1)-1", "integer_overflow"),
        ("[Min]-1", "integer_overflow"),
        ("[Min]*-1", "integer_overflow"),
        ("[Max]*2", "integer_overflow"),
        ("[U]+2", "integer_overflow"),
        ("0-[U]", "integer_overflow"),
        ("[U]*2", "integer_overflow"),
        ("[U]+[Max]", "integer_out_of_range"),
        ("[Max]-[U]", "integer_out_of_range"),
        (str(2**64), "integer_out_of_range"),
        (str(-(2**63) - 1), "integer_out_of_range"),
        (f"{2**63 - 1}+1", "integer_overflow"),
    ],
)
@pytest.mark.parametrize("output_dtype", ["auto", "Float64"])
def test_checked_errors_have_source_spans_and_do_not_mutate_input(
    typed: bool, formula: str, code: str, output_dtype: Literal["auto", "Float64"]
) -> None:
    source = pd.DataFrame({
        "Max": pd.Series([2**63 - 1], dtype="Int64"),
        "Min": pd.Series([-(2**63)], dtype="Int64"),
        "U": pd.Series([2**64 - 2], dtype="UInt64"),
    })
    original = source.copy(deep=True)
    actual_formula = formula_for_path(formula, typed)
    spec = DerivedColumnSpec("Result", actual_formula, output_dtype=output_dtype)
    assert validate_derived_column_spec(source, spec).ok
    with pytest.raises(DerivedColumnFormulaError) as caught:
        create_derived_column(source, spec)
    error = caught.value
    assert error.code == code
    position, end = error.context["position"], error.context["end"]
    assert isinstance(position, int) and isinstance(end, int)
    assert 0 <= position < end <= len(actual_formula)
    preview = preview_derived_column(source, spec)
    assert not preview.ok and preview.data is None and preview.message == code
    assert_frame_equal(source, original)


@pytest.mark.parametrize(
    ("formula", "expected", "dtype"),
    [
        ("-[A]", [-3, None], "Int64"),
        ("+[A]", [3, None], "Int64"),
        ("-[U]", [-3, None], "Int64"),
        ("+[U]", [3, None], "UInt64"),
        ("[A]+1e0", [4.0, None], "Float64"),
        ("IF(TRUE; 2; 3)+[A]", [5, None], "Int64"),
        ("YEAR([D])+[A]", [2029, None], "Int64"),
        ("NULL+[A]", [None, None], "Int64"),
    ],
)
def test_typed_unary_null_and_numeric_result_kinds(
    formula: str, expected: list[int | float | None], dtype: str
) -> None:
    source = pd.DataFrame({
        "A": pd.Series([3, None], dtype="Int64"),
        "U": pd.Series([3, None], dtype="UInt64"),
        "D": pd.Series([pd.Timestamp("2026-01-01"), pd.NaT], dtype="datetime64[ns]"),
    })
    result = create_derived_column(source, DerivedColumnSpec("Result", formula))
    assert_series_equal(result.Result, pd.Series(expected, dtype=dtype, name="Result"))


@pytest.mark.parametrize(
    "formula",
    [
        "IF(FALSE; [Max]+1; 0)",
        f"IF(FALSE; {2**64}; 0)",
        f"IF(FALSE; -{2**63 + 1}; 0)",
        "IF(FALSE; [U]+[Max]; 0)",
    ],
)
def test_inactive_branches_do_not_raise_numeric_errors(formula: str) -> None:
    source = pd.DataFrame({
        "Max": pd.Series([2**63 - 1, None], dtype="Int64"),
        "U": pd.Series([2**64 - 1, None], dtype="UInt64"),
    })
    result = create_derived_column(source, DerivedColumnSpec("Result", formula))
    dtype = "UInt64" if formula == f"IF(FALSE; {2**64}; 0)" else "Int64"
    assert_series_equal(result.Result, pd.Series([0, 0], dtype=dtype, name="Result"))


@pytest.mark.parametrize("typed", [False, True])
def test_explicit_float_output_is_only_a_final_conversion(typed: bool) -> None:
    source = pd.DataFrame({"A": pd.Series([2**53 + 1, None], dtype="Int64")})
    result = create_derived_column(
        source, DerivedColumnSpec("Result", formula_for_path("([A]-1)+1", typed), output_dtype="Float64")
    )
    assert str(result.Result.dtype) == "Float64"
    assert result.Result.iloc[0] == float(2**53 + 1)
    assert pd.isna(result.Result.iloc[1])


def test_direct_evaluators_preserve_exact_integer_results() -> None:
    source = pd.DataFrame({"A": pd.Series([2**53 + 1, None], dtype="Int64")})
    source.index = [4, 4]
    formula = "[A]+2"
    typed = evaluate_expression(
        source,
        parse_expression_formula(formula, expression_columns(list(source.columns), list(source.dtypes))).expression,
    )
    rpn = evaluate_rpn(source, parse_formula_to_rpn(formula, {"A"}))
    assert isinstance(rpn, pd.Series)
    assert_series_equal(typed, pd.Series([2**53 + 3, None], index=source.index, dtype="Int64"))
    assert_series_equal(rpn, typed)
