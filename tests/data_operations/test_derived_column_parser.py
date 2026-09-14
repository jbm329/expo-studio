"""Tests for derived column formula parser.

These tests cover the phase 1 numeric formula parser used by the
derived column feature.

Supported syntax:
- Column references: [Column Name]
- Numeric constants
- Operators: +, -, *, /
- Parentheses
"""

from __future__ import annotations

import pytest

from expo_jbm329.services.data_operations.derived_column.derived_column_parser import (
    DerivedColumnFormulaError,
    FormulaToken,
    FormulaTokenType,
    extract_referenced_columns,
    parse_formula_to_rpn,
    tokenize_formula,
    validate_formula,
    validate_tokens,
)

# =====================================================================
# Helpers
# =====================================================================


def _token_values(tokens: list[FormulaToken]) -> list[str]:
    """Return token values for easier assertions.

    Args:
        tokens: Formula tokens.

    Returns:
        Token values in order.
    """
    return [token.value for token in tokens]


def _token_types(tokens: list[FormulaToken]) -> list[FormulaTokenType]:
    """Return token types for easier assertions.

    Args:
        tokens: Formula tokens.

    Returns:
        Token types in order.
    """
    return [token.token_type for token in tokens]


# =====================================================================
# Tokenizer
# =====================================================================


def test_tokenize_simple_addition() -> None:
    tokens = tokenize_formula("[A] + [B]")

    assert _token_values(tokens) == ["A", "+", "B"]
    assert _token_types(tokens) == [
        FormulaTokenType.COLUMN,
        FormulaTokenType.OPERATOR,
        FormulaTokenType.COLUMN,
    ]


def test_tokenize_formula_with_numeric_constant() -> None:
    tokens = tokenize_formula("[A] * 100")

    assert _token_values(tokens) == ["A", "*", "100"]
    assert _token_types(tokens) == [
        FormulaTokenType.COLUMN,
        FormulaTokenType.OPERATOR,
        FormulaTokenType.NUMBER,
    ]


def test_tokenize_decimal_numbers() -> None:
    tokens = tokenize_formula("[A] + 10.5 + .25 + 10.")

    assert _token_values(tokens) == ["A", "+", "10.5", "+", ".25", "+", "10."]


def test_tokenize_parentheses() -> None:
    tokens = tokenize_formula("([A] + [B]) / 2")

    assert _token_values(tokens) == ["(", "A", "+", "B", ")", "/", "2"]
    assert _token_types(tokens) == [
        FormulaTokenType.LPAREN,
        FormulaTokenType.COLUMN,
        FormulaTokenType.OPERATOR,
        FormulaTokenType.COLUMN,
        FormulaTokenType.RPAREN,
        FormulaTokenType.OPERATOR,
        FormulaTokenType.NUMBER,
    ]


def test_tokenize_column_with_spaces_and_swedish_chars() -> None:
    tokens = tokenize_formula("[Antal vårdkontakter] / [Listade patienter] * 100")

    assert _token_values(tokens) == [
        "Antal vårdkontakter",
        "/",
        "Listade patienter",
        "*",
        "100",
    ]


def test_tokenize_negative_number_at_start() -> None:
    tokens = tokenize_formula("-10 + [A]")

    assert _token_values(tokens) == ["-10", "+", "A"]
    assert _token_types(tokens) == [
        FormulaTokenType.NUMBER,
        FormulaTokenType.OPERATOR,
        FormulaTokenType.COLUMN,
    ]


def test_tokenize_negative_number_after_operator() -> None:
    tokens = tokenize_formula("[A] * -2")

    assert _token_values(tokens) == ["A", "*", "-2"]
    assert _token_types(tokens) == [
        FormulaTokenType.COLUMN,
        FormulaTokenType.OPERATOR,
        FormulaTokenType.NUMBER,
    ]


def test_tokenize_positive_number_after_operator() -> None:
    tokens = tokenize_formula("[A] * +2")

    assert _token_values(tokens) == ["A", "*", "+2"]
    assert _token_types(tokens) == [
        FormulaTokenType.COLUMN,
        FormulaTokenType.OPERATOR,
        FormulaTokenType.NUMBER,
    ]


def test_tokenize_empty_formula_raises() -> None:
    with pytest.raises(DerivedColumnFormulaError, match="Formula is empty"):
        tokenize_formula("")


def test_tokenize_whitespace_formula_raises() -> None:
    with pytest.raises(DerivedColumnFormulaError, match="Formula is empty"):
        tokenize_formula("   ")


def test_tokenize_unclosed_column_reference_raises() -> None:
    with pytest.raises(DerivedColumnFormulaError, match="Unclosed column reference"):
        tokenize_formula("[A")


def test_tokenize_empty_column_reference_raises() -> None:
    with pytest.raises(DerivedColumnFormulaError, match="Empty column reference"):
        tokenize_formula("[] + [B]")


def test_tokenize_unsupported_character_raises() -> None:
    with pytest.raises(DerivedColumnFormulaError, match="Unsupported character"):
        tokenize_formula("[A] ^ [B]")


# =====================================================================
# Referenced columns
# =====================================================================


def test_extract_referenced_columns() -> None:
    cols = extract_referenced_columns("[A] / [B] * 100")

    assert cols == {"A", "B"}


def test_extract_referenced_columns_removes_duplicates() -> None:
    cols = extract_referenced_columns("[A] + [A] / [B]")

    assert cols == {"A", "B"}


# =====================================================================
# Token validation
# =====================================================================


def test_validate_tokens_accepts_valid_formula() -> None:
    tokens = tokenize_formula("[A] / [B] * 100")

    validate_tokens(tokens, {"A", "B"})


def test_validate_tokens_unknown_column_raises() -> None:
    tokens = tokenize_formula("[A] + [Missing]")

    with pytest.raises(DerivedColumnFormulaError, match="Unknown column 'Missing'"):
        validate_tokens(tokens, {"A"})


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("[A] +", "Formula cannot end with operator"),
        ("+ [A]", "Missing operand before operator"),
        ("[A] [B]", "Missing operator before position"),
        ("[A] + * [B]", "Missing operand before operator"),
        ("([A] + [B]", "Unmatched opening parenthesis"),
        ("[A] + [B])", "Unmatched closing parenthesis"),
        ("([A] + )", "Missing operand before"),
        ("[A] ( [B] )", "Missing operator before"),
    ],
)
def test_validate_tokens_invalid_syntax_raises(formula: str, expected: str) -> None:
    tokens = tokenize_formula(formula)

    with pytest.raises(DerivedColumnFormulaError, match=expected):
        validate_tokens(tokens, {"A", "B"})


# =====================================================================
# Structured validation result
# =====================================================================


def test_validate_formula_valid_result() -> None:
    result = validate_formula("[A] / [B] * 100", {"A", "B"})

    assert result.ok is True
    assert result.message == "Formula is valid."
    assert result.referenced_columns == ("A", "B")


def test_validate_formula_invalid_result() -> None:
    result = validate_formula("[A] / [Missing]", {"A"})

    assert result.ok is False
    assert "Unknown column 'Missing'" in result.message
    assert result.referenced_columns == ()


def test_validate_formula_empty_result() -> None:
    result = validate_formula("", {"A"})

    assert result.ok is False
    assert "Formula is empty" in result.message


# =====================================================================
# RPN parsing
# =====================================================================


def test_parse_formula_to_rpn_simple_addition() -> None:
    rpn = parse_formula_to_rpn("[A] + [B]", {"A", "B"})

    assert _token_values(rpn) == ["A", "B", "+"]


def test_parse_formula_to_rpn_operator_precedence() -> None:
    rpn = parse_formula_to_rpn("[A] + [B] * 100", {"A", "B"})

    assert _token_values(rpn) == ["A", "B", "100", "*", "+"]


def test_parse_formula_to_rpn_parentheses_override_precedence() -> None:
    rpn = parse_formula_to_rpn("([A] + [B]) * 100", {"A", "B"})

    assert _token_values(rpn) == ["A", "B", "+", "100", "*"]


def test_parse_formula_to_rpn_left_associative_division_and_multiplication() -> None:
    rpn = parse_formula_to_rpn("[A] / [B] * 100", {"A", "B"})

    assert _token_values(rpn) == ["A", "B", "/", "100", "*"]


def test_parse_formula_to_rpn_nested_parentheses() -> None:
    rpn = parse_formula_to_rpn("(([A] + [B]) / ([C] - 2)) * 100", {"A", "B", "C"})

    assert _token_values(rpn) == [
        "A",
        "B",
        "+",
        "C",
        "2",
        "-",
        "/",
        "100",
        "*",
    ]


def test_parse_formula_to_rpn_constant_only() -> None:
    rpn = parse_formula_to_rpn("10", {"A"})

    assert _token_values(rpn) == ["10"]
    assert _token_types(rpn) == [FormulaTokenType.NUMBER]


def test_parse_formula_to_rpn_negative_constant() -> None:
    rpn = parse_formula_to_rpn("-10 + [A]", {"A"})

    assert _token_values(rpn) == ["-10", "A", "+"]


def test_parse_formula_to_rpn_invalid_formula_raises() -> None:
    with pytest.raises(DerivedColumnFormulaError):
        parse_formula_to_rpn("[A] +", {"A"})


# =====================================================================
# Explicit unsupported phase 1 behavior
# =====================================================================


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
def test_unsupported_phase_1_syntax_raises(formula: str) -> None:
    with pytest.raises(DerivedColumnFormulaError):
        parse_formula_to_rpn(formula, {"A", "B"})

