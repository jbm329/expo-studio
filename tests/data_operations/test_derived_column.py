"""Tests for derived column service.

These tests cover the service layer for creating numeric derived columns
from simple formulas.

Supported phase 1 behavior:
- Numeric constants
- Numeric column references using [Column Name]
- Operators: +, -, *, /
- Parentheses
- Nullable Float64 output
"""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnError,
    DerivedColumnSpec,
    create_derived_column,
    get_numeric_columns,
    validate_derived_column_spec,
)

# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture
def numeric_df() -> pd.DataFrame:
    """Create a simple numeric DataFrame for derived column tests."""
    return pd.DataFrame(
        {
            "A": pd.Series([10, 20, 30], dtype="Int64"),
            "B": pd.Series([2, 4, 5], dtype="Int64"),
            "C": pd.Series([1.5, 2.5, 3.5], dtype="Float64"),
        }
    )


@pytest.fixture
def mixed_df() -> pd.DataFrame:
    """Create a mixed dtype DataFrame for dtype filtering tests."""
    return pd.DataFrame(
        {
            "int_col": pd.Series([1, 2, 3], dtype="Int64"),
            "float_col": pd.Series([1.1, 2.2, 3.3], dtype="Float64"),
            "bool_col": pd.Series([True, False, True], dtype="boolean"),
            "string_col": pd.Series(["a", "b", "c"], dtype="string"),
            "object_col": pd.Series(["1", "2", "3"], dtype="object"),
        }
    )


# =====================================================================
# Numeric column discovery
# =====================================================================


def test_get_numeric_columns_excludes_bool_and_text(mixed_df: pd.DataFrame) -> None:
    columns = get_numeric_columns(mixed_df)

    assert columns == ["int_col", "float_col"]


def test_get_numeric_columns_returns_empty_for_no_numeric_columns() -> None:
    df = pd.DataFrame(
        {
            "name": pd.Series(["a", "b"], dtype="string"),
            "flag": pd.Series([True, False], dtype="boolean"),
        }
    )

    assert get_numeric_columns(df) == []


# =====================================================================
# Spec validation
# =====================================================================


def test_validate_derived_column_spec_accepts_valid_formula(
    numeric_df: pd.DataFrame,
) -> None:
    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] / [B] * 100",
    )

    result = validate_derived_column_spec(numeric_df, spec)

    assert result.ok is True
    assert result.message == "Formula is valid."
    assert result.referenced_columns == ("A", "B")


def test_validate_derived_column_spec_rejects_empty_column_name(
    numeric_df: pd.DataFrame,
) -> None:
    spec = DerivedColumnSpec(
        column_name="",
        formula="[A] + [B]",
    )

    result = validate_derived_column_spec(numeric_df, spec)

    assert result.ok is False
    assert "Output column name is required" in result.message


def test_validate_derived_column_spec_rejects_existing_column_without_overwrite(
    numeric_df: pd.DataFrame,
) -> None:
    spec = DerivedColumnSpec(
        column_name="A",
        formula="[A] + [B]",
        overwrite_existing=False,
    )

    result = validate_derived_column_spec(numeric_df, spec)

    assert result.ok is False
    assert "already exists" in result.message


def test_validate_derived_column_spec_accepts_existing_column_with_overwrite(
    numeric_df: pd.DataFrame,
) -> None:
    spec = DerivedColumnSpec(
        column_name="A",
        formula="[A] + [B]",
        overwrite_existing=True,
    )

    result = validate_derived_column_spec(numeric_df, spec)

    assert result.ok is True


def test_validate_derived_column_spec_rejects_unknown_column(
    numeric_df: pd.DataFrame,
) -> None:
    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] + [Missing]",
    )

    result = validate_derived_column_spec(numeric_df, spec)

    assert result.ok is False
    assert "Unknown column 'Missing'" in result.message


def test_validate_derived_column_spec_rejects_non_numeric_column() -> None:
    df = pd.DataFrame(
        {
            "A": pd.Series([1, 2, 3], dtype="Int64"),
            "Text": pd.Series(["x", "y", "z"], dtype="string"),
        }
    )

    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] + [Text]",
    )

    result = validate_derived_column_spec(df, spec)

    assert result.ok is False
    assert "Unknown column 'Text'" in result.message


def test_validate_derived_column_spec_rejects_bool_column() -> None:
    df = pd.DataFrame(
        {
            "A": pd.Series([1, 2, 3], dtype="Int64"),
            "Flag": pd.Series([True, False, True], dtype="boolean"),
        }
    )

    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] + [Flag]",
    )

    result = validate_derived_column_spec(df, spec)

    assert result.ok is False
    assert "Unknown column 'Flag'" in result.message


def test_validate_derived_column_spec_rejects_brackets_in_output_name(
    numeric_df: pd.DataFrame,
) -> None:
    spec = DerivedColumnSpec(
        column_name="[Result]",
        formula="[A] + [B]",
    )

    result = validate_derived_column_spec(numeric_df, spec)

    assert result.ok is False
    assert "must not contain" in result.message


# =====================================================================
# Create derived column
# =====================================================================


def test_create_derived_column_addition(numeric_df: pd.DataFrame) -> None:
    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] + [B]",
    )

    result = create_derived_column(numeric_df, spec)

    expected = pd.Series([12.0, 24.0, 35.0], name="Result", dtype="Float64")

    assert "Result" in result.columns
    assert_series_equal(result["Result"], expected)


def test_create_derived_column_operator_precedence(numeric_df: pd.DataFrame) -> None:
    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] + [B] * 100",
    )

    result = create_derived_column(numeric_df, spec)

    expected = pd.Series([210.0, 420.0, 530.0], name="Result", dtype="Float64")
    assert_series_equal(result["Result"], expected)


def test_create_derived_column_parentheses_override_precedence(
    numeric_df: pd.DataFrame,
) -> None:
    spec = DerivedColumnSpec(
        column_name="Result",
        formula="([A] + [B]) * 100",
    )

    result = create_derived_column(numeric_df, spec)

    expected = pd.Series([1200.0, 2400.0, 3500.0], name="Result", dtype="Float64")
    assert_series_equal(result["Result"], expected)


def test_create_derived_column_division_and_multiplication(
    numeric_df: pd.DataFrame,
) -> None:
    spec = DerivedColumnSpec(
        column_name="Percent",
        formula="[A] / [B] * 100",
    )

    result = create_derived_column(numeric_df, spec)

    expected = pd.Series([500.0, 500.0, 600.0], name="Percent", dtype="Float64")
    assert_series_equal(result["Percent"], expected)


def test_create_derived_column_constant_only(numeric_df: pd.DataFrame) -> None:
    spec = DerivedColumnSpec(
        column_name="Constant",
        formula="10",
    )

    result = create_derived_column(numeric_df, spec)

    expected = pd.Series([10.0, 10.0, 10.0], name="Constant", dtype="Float64")
    assert_series_equal(result["Constant"], expected)


def test_create_derived_column_negative_constant(numeric_df: pd.DataFrame) -> None:
    spec = DerivedColumnSpec(
        column_name="Result",
        formula="-10 + [A]",
    )

    result = create_derived_column(numeric_df, spec)

    expected = pd.Series([0.0, 10.0, 20.0], name="Result", dtype="Float64")
    assert_series_equal(result["Result"], expected)


def test_create_derived_column_decimal_constant(numeric_df: pd.DataFrame) -> None:
    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] * 0.5",
    )

    result = create_derived_column(numeric_df, spec)

    expected = pd.Series([5.0, 10.0, 15.0], name="Result", dtype="Float64")
    assert_series_equal(result["Result"], expected)


def test_create_derived_column_appends_column_at_end(
    numeric_df: pd.DataFrame,
) -> None:
    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] + [B]",
    )

    result = create_derived_column(numeric_df, spec)

    assert list(result.columns) == ["A", "B", "C", "Result"]


def test_create_derived_column_does_not_mutate_original_df(
    numeric_df: pd.DataFrame,
) -> None:
    original = numeric_df.copy(deep=True)

    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] + [B]",
    )

    _ = create_derived_column(numeric_df, spec)

    assert_frame_equal(numeric_df, original)
    assert "Result" not in numeric_df.columns


def test_create_derived_column_existing_column_raises_without_overwrite(
    numeric_df: pd.DataFrame,
) -> None:
    spec = DerivedColumnSpec(
        column_name="A",
        formula="[A] + [B]",
        overwrite_existing=False,
    )

    with pytest.raises(DerivedColumnError, match="already exists"):
        create_derived_column(numeric_df, spec)


def test_create_derived_column_existing_column_overwrites_when_allowed(
    numeric_df: pd.DataFrame,
) -> None:
    spec = DerivedColumnSpec(
        column_name="A",
        formula="[A] + [B]",
        overwrite_existing=True,
    )

    result = create_derived_column(numeric_df, spec)

    expected = pd.Series([12.0, 24.0, 35.0], name="A", dtype="Float64")
    assert_series_equal(result["A"], expected)


def test_create_derived_column_unknown_column_raises(
    numeric_df: pd.DataFrame,
) -> None:
    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] + [Missing]",
    )

    with pytest.raises(DerivedColumnError, match="Unknown column 'Missing'"):
        create_derived_column(numeric_df, spec)


def test_create_derived_column_non_numeric_column_raises() -> None:
    df = pd.DataFrame(
        {
            "A": pd.Series([1, 2, 3], dtype="Int64"),
            "Text": pd.Series(["x", "y", "z"], dtype="string"),
        }
    )

    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] + [Text]",
    )

    with pytest.raises(DerivedColumnError, match="Unknown column 'Text'"):
        create_derived_column(df, spec)


def test_create_derived_column_bool_column_raises() -> None:
    df = pd.DataFrame(
        {
            "A": pd.Series([1, 2, 3], dtype="Int64"),
            "Flag": pd.Series([True, False, True], dtype="boolean"),
        }
    )

    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] + [Flag]",
    )

    with pytest.raises(DerivedColumnError, match="Unknown column 'Flag'"):
        create_derived_column(df, spec)


# =====================================================================
# Missing values and division by zero
# =====================================================================


def test_create_derived_column_missing_values_propagate() -> None:
    df = pd.DataFrame(
        {
            "A": pd.Series([10, pd.NA, 30], dtype="Int64"),
            "B": pd.Series([2, 4, pd.NA], dtype="Int64"),
        }
    )

    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] / [B]",
    )

    result = create_derived_column(df, spec)

    expected = pd.Series([5.0, pd.NA, pd.NA], name="Result", dtype="Float64")
    assert_series_equal(result["Result"], expected)


def test_create_derived_column_division_by_zero_becomes_na() -> None:
    df = pd.DataFrame(
        {
            "A": pd.Series([10, 20, 30], dtype="Int64"),
            "B": pd.Series([2, 0, 5], dtype="Int64"),
        }
    )

    spec = DerivedColumnSpec(
        column_name="Result",
        formula="[A] / [B]",
    )

    result = create_derived_column(df, spec)

    expected = pd.Series([5.0, pd.NA, 6.0], name="Result", dtype="Float64")
    assert_series_equal(result["Result"], expected)


