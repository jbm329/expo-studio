from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from expo_jbm329.services.data_operations.derived_column.derived_column_parser import (
    DerivedColumnFormulaError,
    FormulaTokenType,
    extract_referenced_columns,
    parse_formula_to_rpn,
    tokenize_formula,
    validate_formula,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnError,
    DerivedColumnSpec,
    create_derived_column,
    evaluate_rpn,
    preview_derived_column,
    validate_derived_column_spec,
)
from expo_jbm329.services.data_operations.dtypes import get_numeric_columns


@pytest.fixture
def numeric_df() -> pd.DataFrame:
    return pd.DataFrame({
        "A": pd.Series([10, 20, 30], dtype="Int64"),
        "B": pd.Series([2, 4, 5], dtype="Int64"),
        "C": pd.Series([1.5, 2.5, 3.5], dtype="Float64"),
    })


@pytest.fixture
def mixed_df() -> pd.DataFrame:
    return pd.DataFrame({
        "int_col": pd.Series([1, 2, 3], dtype="Int64"),
        "float_col": pd.Series([1.1, 2.2, 3.3], dtype="Float64"),
        "bool_col": pd.Series([True, False, True], dtype="boolean"),
        "string_col": pd.Series(["a", "b", "c"], dtype="string"),
    })


def test_get_numeric_columns_excludes_bool_and_text(mixed_df: pd.DataFrame):
    assert get_numeric_columns(mixed_df) == ["int_col", "float_col"]


def test_tokenize_formula_parses_columns_numbers_and_operators():
    tokens = tokenize_formula("([A] + 10.5) / -2")

    assert [token.token_type for token in tokens] == [
        FormulaTokenType.LPAREN,
        FormulaTokenType.COLUMN,
        FormulaTokenType.OPERATOR,
        FormulaTokenType.NUMBER,
        FormulaTokenType.RPAREN,
        FormulaTokenType.OPERATOR,
        FormulaTokenType.NUMBER,
    ]
    assert tokens[1].value == "A"
    assert tokens[3].value == "10.5"
    assert tokens[6].value == "-2"


def test_validate_formula_accepts_valid_formula():
    result = validate_formula("[A] / [B] * 100", {"A", "B"})

    assert result.ok is True
    assert result.error is None
    assert result.referenced_columns == ()


def test_validate_formula_rejects_unknown_column():
    result = validate_formula("[A] + [Missing]", {"A"})

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "unknown_column"


def test_parse_formula_to_rpn_orders_by_precedence():
    rpn = parse_formula_to_rpn("[A] + [B] * 100", {"A", "B"})

    assert [token.value for token in rpn] == ["A", "B", "100", "*", "+"]


def test_extract_referenced_columns():
    assert extract_referenced_columns("([A] + [B]) / [C]") == {"A", "B", "C"}


def test_validate_derived_column_spec_accepts_valid_formula(numeric_df: pd.DataFrame):
    spec = DerivedColumnSpec(column_name="Result", formula="[A] / [B] * 100")

    result = validate_derived_column_spec(numeric_df, spec)

    assert result.ok is True
    assert result.error is None


def test_validate_derived_column_spec_rejects_empty_column_name(numeric_df: pd.DataFrame):
    spec = DerivedColumnSpec(column_name="", formula="[A] + [B]")

    result = validate_derived_column_spec(numeric_df, spec)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "missing_output_column_name"


def test_validate_derived_column_spec_rejects_existing_column_without_overwrite(
    numeric_df: pd.DataFrame,
):
    spec = DerivedColumnSpec(column_name="A", formula="[A] + [B]", overwrite_existing=False)

    result = validate_derived_column_spec(numeric_df, spec)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "output_column_exists"


def test_validate_derived_column_spec_rejects_unknown_column(numeric_df: pd.DataFrame):
    spec = DerivedColumnSpec(column_name="Result", formula="[A] + [Missing]")

    result = validate_derived_column_spec(numeric_df, spec)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "unknown_column"


def test_create_derived_column_addition(numeric_df: pd.DataFrame):
    spec = DerivedColumnSpec(column_name="Result", formula="[A] + [B]")

    result = create_derived_column(numeric_df, spec)

    assert list(result.columns) == ["A", "B", "C", "Result"]
    assert_series_equal(result["Result"], pd.Series([12.0, 24.0, 35.0], name="Result", dtype="Float64"))


def test_create_derived_column_overwrites_when_allowed(numeric_df: pd.DataFrame):
    spec = DerivedColumnSpec(column_name="A", formula="[A] + [B]", overwrite_existing=True)

    result = create_derived_column(numeric_df, spec)

    assert_series_equal(result["A"], pd.Series([12.0, 24.0, 35.0], name="A", dtype="Float64"))


def test_create_derived_column_rejects_existing_column_without_overwrite(numeric_df: pd.DataFrame):
    spec = DerivedColumnSpec(column_name="A", formula="[A] + [B]")

    with pytest.raises(DerivedColumnError, match="output_column_exists"):
        create_derived_column(numeric_df, spec)


def test_create_derived_column_rejects_unknown_column(numeric_df: pd.DataFrame):
    spec = DerivedColumnSpec(column_name="Result", formula="[A] + [Missing]")

    with pytest.raises(DerivedColumnFormulaError, match="unknown_column"):
        create_derived_column(numeric_df, spec)


def test_create_derived_column_rejects_non_numeric_column():
    df = pd.DataFrame({"A": pd.Series([1, 2, 3], dtype="Int64"), "Text": pd.Series(["x", "y", "z"], dtype="string")})
    spec = DerivedColumnSpec(column_name="Result", formula="[A] + [Text]")

    with pytest.raises(DerivedColumnFormulaError, match="unknown_column"):
        create_derived_column(df, spec)


def test_create_derived_column_missing_values_propagate():
    df = pd.DataFrame({"A": pd.Series([10, pd.NA, 30], dtype="Int64"), "B": pd.Series([2, 4, pd.NA], dtype="Int64")})
    spec = DerivedColumnSpec(column_name="Result", formula="[A] / [B]")

    result = create_derived_column(df, spec)

    assert_series_equal(result["Result"], pd.Series([5.0, pd.NA, pd.NA], name="Result", dtype="Float64"))


def test_create_derived_column_division_by_zero_becomes_na():
    df = pd.DataFrame({"A": pd.Series([10, 20, 30], dtype="Int64"), "B": pd.Series([2, 0, 5], dtype="Int64")})
    spec = DerivedColumnSpec(column_name="Result", formula="[A] / [B]")

    result = create_derived_column(df, spec)

    assert_series_equal(result["Result"], pd.Series([5.0, pd.NA, 6.0], name="Result", dtype="Float64"))


def test_preview_derived_column_returns_compact_preview(numeric_df: pd.DataFrame):
    spec = DerivedColumnSpec(column_name="Result", formula="[A] + [B]")

    preview = preview_derived_column(numeric_df, spec, rows=2)

    assert preview.ok is True
    assert preview.data is not None
    assert list(preview.data.columns) == ["Result"]
    assert len(preview.data) == 2


def test_preview_derived_column_returns_failure_for_invalid_formula(numeric_df: pd.DataFrame):
    spec = DerivedColumnSpec(column_name="Result", formula="[A] + [Missing]")

    preview = preview_derived_column(numeric_df, spec)

    assert preview.ok is False
    assert preview.data is None


def test_evaluate_rpn_works_with_series(numeric_df: pd.DataFrame):
    rpn = parse_formula_to_rpn("[A] + [B]", {"A", "B"})

    result = evaluate_rpn(numeric_df, rpn)

    assert_series_equal(result, pd.Series([12, 24, 35], dtype="Int64"), check_dtype=False)
