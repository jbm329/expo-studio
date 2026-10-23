"""Dtype-aware literal syntax without inspecting or converting source values."""

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.reshape_condition_lint import lint_condition
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionGroup,
    ConditionLiteralType,
    ConditionOperator,
    ConditionRule,
    condition_columns,
    condition_value,
    format_condition,
)


@pytest.mark.parametrize(
    ("dtype", "expected"),
    [
        ("int64", ConditionLiteralType.NUMBER),
        ("Int64", ConditionLiteralType.NUMBER),
        ("UInt32", ConditionLiteralType.NUMBER),
        ("float64", ConditionLiteralType.NUMBER),
        ("Float64", ConditionLiteralType.NUMBER),
        ("bool", ConditionLiteralType.BOOLEAN),
        ("boolean", ConditionLiteralType.BOOLEAN),
        ("object", ConditionLiteralType.QUOTED),
        ("category", ConditionLiteralType.QUOTED),
        ("string", ConditionLiteralType.QUOTED),
        ("datetime64[ns]", ConditionLiteralType.QUOTED),
        ("datetime64[ns, UTC]", ConditionLiteralType.QUOTED),
        ("complex128", ConditionLiteralType.QUOTED),
    ],
)
def test_classification_uses_storage_dtype(dtype, expected):
    assert condition_columns(["a"], [dtype])[0].literal_type == expected


@pytest.mark.parametrize("dtype", ["int64", "Int64", "Float64"])
@pytest.mark.parametrize("literal", ["18", "-18", "+18", "2.5", ".5", "1.", "-2.5e-3", "1E+12", "'anything'"])
def test_numeric_literals(dtype, literal):
    columns = condition_columns(["a"], [dtype])
    assert not lint_condition(f"([a] >= {literal} OR [a] IN ({literal}, 'legacy'))", columns)


@pytest.mark.parametrize("literal", ["True", "FALSE", "true", "fAlSe", "'anything'"])
def test_boolean_literals(literal):
    columns = condition_columns(["a"], ["boolean"])
    assert not lint_condition(f"[a] IN ({literal}, True) AND [a] != false", columns)


@pytest.mark.parametrize(
    ("dtype", "literal"),
    [
        ("int64", "True"),
        ("bool", "1"),
        ("bool", "yes"),
        ("int64", "1e"),
        ("int64", "1.2.3"),
        ("int64", "--1"),
        ("int64", "1e+"),
        ("int64", "NaN"),
        ("int64", "inf"),
        ("int64", "18abc"),
        ("object", "18"),
        ("string", "True"),
        ("category", "1"),
        ("datetime64[ns]", "2026"),
        ("bool", "TrueFalse"),
    ],
)
def test_wrong_or_malformed_unquoted_literal_is_invalid(dtype, literal):
    assert lint_condition(f"[a] = {literal}", condition_columns(["a"], [dtype]))


@pytest.mark.parametrize(
    ("dtype", "value", "literal"),
    [
        ("Int64", 18, "18"),
        ("float64", -2.5, "-2.5"),
        ("boolean", True, "True"),
        ("object", 18, "'18'"),
        ("category", True, "'True'"),
        ("string", "0018", "'0018'"),
    ],
)
def test_builder_and_linter_share_dtype_rules(dtype, value, literal):
    columns = condition_columns(["a"], [dtype])
    operand = condition_value(value)
    expression = format_condition(ConditionGroup((ConditionRule(columns[0], ConditionOperator.IN, (operand,)),)))
    assert expression == f"[a] IN ({literal})"
    assert not lint_condition(expression, columns)


def test_real_dtype_objects_and_numeric_categories_remain_quoted():
    frame = pd.DataFrame({
        "number": pd.Series([1], dtype="Int64"),
        "flag": pd.Series([True], dtype="boolean"),
        "category": pd.Series([1], dtype="category"),
        "object": pd.Series([1], dtype=object),
    })
    columns = condition_columns(list(frame.columns), list(frame.dtypes))
    assert [column.literal_type for column in columns] == [
        ConditionLiteralType.NUMBER,
        ConditionLiteralType.BOOLEAN,
        ConditionLiteralType.QUOTED,
        ConditionLiteralType.QUOTED,
    ]
    assert not lint_condition("[number] = 1 AND [flag] = True AND [category] = '1'", columns)


def test_metadata_length_mismatch_fails_explicitly():
    with pytest.raises(ValueError, match="dtype metadata"):
        condition_columns(["a"], [])
