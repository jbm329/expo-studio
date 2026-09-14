from __future__ import annotations

import pytest

from expo_jbm329.services.data_operations.derived_column.derived_column_parser import (
    DerivedColumnFormulaError,
    FormulaToken,
    FormulaTokenType,
    extract_referenced_columns,
    extract_referenced_columns_from_tokens,
    parse_formula_to_rpn,
    tokenize_formula,
    validate_formula,
    validate_tokens,
)


def _token_values(tokens: list[FormulaToken]) -> list[str]:
    return [token.value for token in tokens]


def _token_types(tokens: list[FormulaToken]) -> list[FormulaTokenType]:
    return [token.token_type for token in tokens]


def test_tokenize_simple_addition():
    tokens = tokenize_formula("[A] + [B]")

    assert _token_values(tokens) == ["A", "+", "B"]
    assert _token_types(tokens) == [
        FormulaTokenType.COLUMN,
        FormulaTokenType.OPERATOR,
        FormulaTokenType.COLUMN,
    ]


def test_tokenize_numeric_literals():
    tokens = tokenize_formula("[A] + 10.5 + .25 + 10.")

    assert _token_values(tokens) == ["A", "+", "10.5", "+", ".25", "+", "10."]


def test_tokenize_parentheses():
    tokens = tokenize_formula("([A] + [B]) / 2")

    assert _token_types(tokens) == [
        FormulaTokenType.LPAREN,
        FormulaTokenType.COLUMN,
        FormulaTokenType.OPERATOR,
        FormulaTokenType.COLUMN,
        FormulaTokenType.RPAREN,
        FormulaTokenType.OPERATOR,
        FormulaTokenType.NUMBER,
    ]


def test_tokenize_negative_number_at_start():
    tokens = tokenize_formula("-10 + [A]")

    assert _token_values(tokens) == ["-10", "+", "A"]


def test_tokenize_negative_number_after_operator():
    tokens = tokenize_formula("[A] * -2")

    assert _token_values(tokens) == ["A", "*", "-2"]


def test_tokenize_empty_formula_raises():
    with pytest.raises(DerivedColumnFormulaError, match="formula_empty"):
        tokenize_formula("")


def test_tokenize_unclosed_column_reference_raises():
    with pytest.raises(DerivedColumnFormulaError, match="unclosed_column_reference"):
        tokenize_formula("[A")


def test_tokenize_empty_column_reference_raises():
    with pytest.raises(DerivedColumnFormulaError, match="empty_column_reference"):
        tokenize_formula("[] + [B]")


def test_tokenize_unsupported_character_raises():
    with pytest.raises(DerivedColumnFormulaError, match="unsupported_character"):
        tokenize_formula("[A] ^ [B]")


def test_extract_referenced_columns():
    assert extract_referenced_columns("[A] / [B] * 100") == {"A", "B"}


def test_extract_referenced_columns_from_tokens_deduplicates():
    tokens = tokenize_formula("[A] + [A] / [B]")

    assert extract_referenced_columns_from_tokens(tokens) == {"A", "B"}


def test_validate_tokens_accepts_valid_formula():
    validate_tokens(tokenize_formula("[A] / [B] * 100"), {"A", "B"})


def test_validate_tokens_unknown_column_raises():
    with pytest.raises(DerivedColumnFormulaError, match="unknown_column"):
        validate_tokens(tokenize_formula("[A] + [Missing]"), {"A"})


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("[A] +", "formula_ends_with_operator"),
        ("+ [A]", "missing_operand_before_operator"),
        ("[A] [B]", "missing_operator_before_operand"),
        ("[A] + * [B]", "missing_operand_before_operator"),
        ("([A] + [B]", "unmatched_opening_parenthesis"),
        ("[A] + [B])", "unmatched_closing_parenthesis"),
        ("([A] + )", "missing_operand_before_closing_parenthesis"),
        ("[A] ( [B] )", "missing_operand_before_opening_parenthesis"),
    ],
)
def test_validate_tokens_invalid_syntax_raises(formula: str, expected: str):
    with pytest.raises(DerivedColumnFormulaError, match=expected):
        validate_tokens(tokenize_formula(formula), {"A", "B"})


def test_validate_formula_valid_result():
    result = validate_formula("[A] / [B] * 100", {"A", "B"})

    assert result.ok is True
    assert result.error is None
    assert result.referenced_columns == ()


def test_validate_formula_invalid_result():
    result = validate_formula("[A] / [Missing]", {"A"})

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "unknown_column"
    assert result.referenced_columns == ()


def test_parse_formula_to_rpn_simple_addition():
    rpn = parse_formula_to_rpn("[A] + [B]", {"A", "B"})

    assert _token_values(rpn) == ["A", "B", "+"]


def test_parse_formula_to_rpn_operator_precedence():
    rpn = parse_formula_to_rpn("[A] + [B] * 100", {"A", "B"})

    assert _token_values(rpn) == ["A", "B", "100", "*", "+"]


def test_parse_formula_to_rpn_parentheses_override_precedence():
    rpn = parse_formula_to_rpn("([A] + [B]) * 100", {"A", "B"})

    assert _token_values(rpn) == ["A", "B", "+", "100", "*"]


def test_parse_formula_to_rpn_invalid_formula_raises():
    with pytest.raises(DerivedColumnFormulaError):
        parse_formula_to_rpn("[A] +", {"A"})


@pytest.mark.parametrize(
    "formula",
    [
        "round([A])",
        "sqrt([A])",
        "[A] ** 2",
        "[A] > [B]",
        "[A] and [B]",
        '"text"',
    ],
)
def test_unsupported_phase_1_syntax_raises(formula: str):
    with pytest.raises(DerivedColumnFormulaError):
        parse_formula_to_rpn(formula, {"A", "B"})
