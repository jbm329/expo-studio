"""Parser utilities for derived column formulas.

This module provides a small, safe formula parser for numeric derived columns.

Supported syntax in phase 1:
    - Column references: [Column Name]
    - Numeric constants: 10, 10.5, -3, -3.14
    - Operators: +, -, *, /
    - Parentheses: (, )

Examples:
    [A] + [B]
    [A] / [B] * 100
    ([A] + [B]) / 2
    -10 + [A]

The parser intentionally does not evaluate arbitrary Python code. It tokenizes
the formula, validates references, and converts the expression to Reverse Polish
Notation (RPN) using the shunting-yard algorithm.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Final

# =====================================================================
# Exceptions
# =====================================================================


class DerivedColumnFormulaError(ValueError):
    """Structured error for derived column formulas."""
    def __init__(
        self,
        code: str,
        *,
        context: dict[str, object] | None = None,
        message: str | None = None,
    ) -> None:
        """Initialize DerivedColumnFormulaError.

        Args:
            code: Error code for the exception.
            context: Optional context information for the error.
            message: Optional custom error message. If not provided, defaults to the error code.
        """
        self.code = code
        self.context = context or {}
        self.message = message or code

        super().__init__(self.message)

    def __repr__(self) -> str:
        """Return a string representation of the error."""
        return f"{self.__class__.__name__}(code={self.code!r}, context={self.context!r})"


# =====================================================================
# Models
# =====================================================================


class FormulaTokenType(Enum):
    """Supported token types in derived column formulas."""

    COLUMN = "column"
    NUMBER = "number"
    OPERATOR = "operator"
    LPAREN = "lparen"
    RPAREN = "rparen"


@dataclass(frozen=True, slots=True)
class FormulaToken:
    """A single token in a derived column formula.

    Attributes:
        token_type: The type of token.
        value: The raw or normalized token value.
        position: Character position in the original formula.
    """

    token_type: FormulaTokenType
    value: str
    position: int


@dataclass(frozen=True, slots=True)
class FormulaValidationResult:
    """Validation result for a derived column formula.

    Attributes:
        ok: Whether the formula is valid.
        error: Structured validation error (code + context).
        referenced_columns: Columns referenced by the formula.
    """

    ok: bool
    error: DerivedColumnFormulaError | None = None
    referenced_columns: tuple[str, ...] = ()


# =====================================================================
# Constants
# =====================================================================


_OPERATOR_PRECEDENCE: Final[dict[str, int]] = {
    "+": 1,
    "-": 1,
    "*": 2,
    "/": 2,
}

_SUPPORTED_OPERATORS: Final[set[str]] = set(_OPERATOR_PRECEDENCE)


_NUMBER_RE: Final[re.Pattern[str]] = re.compile(
    r"\d+(?:\.\d*)?|\.\d+"
)


# =====================================================================
# Public API
# =====================================================================

def tokenize_formula(formula: str) -> list[FormulaToken]:
    """Tokenize a derived column formula.

    Args:
        formula: User-facing formula string.

    Returns:
        A list of FormulaToken instances.

    Raises:
        DerivedColumnFormulaError: If tokenization fails.
    """
    text = (formula or "").strip()
    if not text:
        msg = "formula_empty"
        raise DerivedColumnFormulaError(msg)

    tokens: list[FormulaToken] = []
    i = 0
    expecting_operand = True

    while i < len(text):
        char = text[i]

        # --------------------------------------------------------------
        # Whitespace
        # --------------------------------------------------------------
        if char.isspace():
            i += 1
            continue

        # --------------------------------------------------------------
        # Column reference: [Column Name]
        # --------------------------------------------------------------
        if char == "[":
            end = text.find("]", i + 1)
            if end == -1:
                msg = "unclosed_column_reference"
                raise DerivedColumnFormulaError(
                    msg,
                    context={
                        "position": i
                    }
                )

            column_name = text[i + 1:end].strip()
            if not column_name:
                msg = "empty_column_reference"
                raise DerivedColumnFormulaError(
                    msg,
                    context={
                        "position": i
                    }
                )

            tokens.append(
                FormulaToken(
                    token_type=FormulaTokenType.COLUMN,
                    value=column_name,
                    position=i,
                )
            )
            i = end + 1
            expecting_operand = False
            continue

        # --------------------------------------------------------------
        # Parentheses
        # --------------------------------------------------------------
        if char == "(":
            tokens.append(
                FormulaToken(
                    token_type=FormulaTokenType.LPAREN,
                    value=char,
                    position=i,
                )
            )
            i += 1
            expecting_operand = True
            continue

        if char == ")":
            tokens.append(
                FormulaToken(
                    token_type=FormulaTokenType.RPAREN,
                    value=char,
                    position=i,
                )
            )
            i += 1
            expecting_operand = False
            continue

        # --------------------------------------------------------------
        # Signed number, e.g. -10 or +10.
        #
        # Unary signs are only allowed when an operand is expected and
        # the sign is directly followed by a numeric literal.
        # --------------------------------------------------------------
        if char in {"+", "-"} and expecting_operand:
            if i + 1 < len(text):
                match = _NUMBER_RE.match(text, i + 1)
                if match:
                    number = char + match.group(0)
                    tokens.append(
                        FormulaToken(
                            token_type=FormulaTokenType.NUMBER,
                            value=number,
                            position=i,
                        )
                    )
                    i = match.end()
                    expecting_operand = False
                    continue

            # If not followed by a number, treat as operator and let the
            # syntax validator raise a clearer message later.
            tokens.append(
                FormulaToken(
                    token_type=FormulaTokenType.OPERATOR,
                    value=char,
                    position=i,
                )
            )
            i += 1
            expecting_operand = True
            continue

        # --------------------------------------------------------------
        # Number
        # --------------------------------------------------------------
        match = _NUMBER_RE.match(text, i)
        if match:
            tokens.append(
                FormulaToken(
                    token_type=FormulaTokenType.NUMBER,
                    value=match.group(0),
                    position=i,
                )
            )
            i = match.end()
            expecting_operand = False
            continue

        # --------------------------------------------------------------
        # Operator
        # --------------------------------------------------------------
        if char in _SUPPORTED_OPERATORS:
            tokens.append(
                FormulaToken(
                    token_type=FormulaTokenType.OPERATOR,
                    value=char,
                    position=i,
                )
            )
            i += 1
            expecting_operand = True
            continue

        msg = "unsupported_character"
        raise DerivedColumnFormulaError(
            msg,
            context={
                "char": char,
                "position": i,
            },
        )

    return tokens


def parse_formula_to_rpn(formula: str, available_columns: set[str]) -> list[FormulaToken]:
    """Parse a formula into Reverse Polish Notation.

    Args:
        formula: User-facing formula string.
        available_columns: Set of valid column names.

    Returns:
        A list of FormulaToken instances in RPN order.

    Raises:
        DerivedColumnFormulaError: If the formula is invalid.
    """
    tokens = tokenize_formula(formula)
    validate_tokens(tokens, available_columns)

    output: list[FormulaToken] = []
    operators: list[FormulaToken] = []

    for token in tokens:
        if token.token_type in {FormulaTokenType.NUMBER, FormulaTokenType.COLUMN}:
            output.append(token)
            continue

        if token.token_type == FormulaTokenType.OPERATOR:
            while (
                operators
                and operators[-1].token_type == FormulaTokenType.OPERATOR
                and _operator_precedence(operators[-1]) >= _operator_precedence(token)
            ):
                output.append(operators.pop())

            operators.append(token)
            continue

        if token.token_type == FormulaTokenType.LPAREN:
            operators.append(token)
            continue

        if token.token_type == FormulaTokenType.RPAREN:
            found_lparen = False

            while operators:
                top = operators.pop()
                if top.token_type == FormulaTokenType.LPAREN:
                    found_lparen = True
                    break

                output.append(top)

            if not found_lparen:
                msg = "unmatched_closing_parenthesis"
                raise DerivedColumnFormulaError(
                    msg,
                    context={
                        "position": token.position,
                    }
                )

    while operators:
        top = operators.pop()

        if top.token_type == FormulaTokenType.LPAREN:
            msg = "unmatched_opening_parenthesis"
            raise DerivedColumnFormulaError(
                msg,
                context={
                    "position": top.position,
                }
            )

        output.append(top)

    return output


def validate_formula(
    formula: str,
    available_columns: set[str],
) -> FormulaValidationResult:
    """Validate a formula and return a structured validation result.

    This function is intended for GUI validation, including real-time validation
    while the user edits the formula.

    Args:
        formula: User-facing formula string.
        available_columns: Set of valid column names.

    Returns:
        FormulaValidationResult with validation status and referenced columns.
    """
    try:
        tokens = tokenize_formula(formula)
        validate_tokens(tokens, available_columns)
        parse_formula_to_rpn(formula, available_columns)

        return FormulaValidationResult(
            ok=True,
        )

    except DerivedColumnFormulaError as exc:
        return FormulaValidationResult(
            ok=False,
            error=exc,
        )


def extract_referenced_columns(formula: str) -> set[str]:
    """Extract column references from a formula.

    Args:
        formula: User-facing formula string.

    Returns:
        Set of referenced column names.

    Raises:
        DerivedColumnFormulaError: If tokenization fails.
    """
    tokens = tokenize_formula(formula)
    return extract_referenced_columns_from_tokens(tokens)


def extract_referenced_columns_from_tokens(tokens: list[FormulaToken]) -> set[str]:
    """Extract referenced columns from already tokenized formula.

    Args:
        tokens: Formula tokens.

    Returns:
        Set of referenced column names.
    """
    return {
        token.value
        for token in tokens
        if token.token_type == FormulaTokenType.COLUMN
    }


def validate_tokens(tokens: list[FormulaToken], available_columns: set[str]) -> None:
    """Validate token sequence and column references.

    Args:
        tokens: Formula tokens.
        available_columns: Set of valid column names.

    Raises:
        DerivedColumnFormulaError: If the token sequence is invalid.
    """
    if not tokens:
        msg = "formula_empty"
        raise DerivedColumnFormulaError(msg)

    _validate_column_references(tokens, available_columns)
    _validate_syntax(tokens)


# =====================================================================
# Internal helpers
# =====================================================================


def _operator_precedence(token: FormulaToken) -> int:
    """Return precedence for an operator token.

    Args:
        token: Operator token.

    Returns:
        Integer precedence value.

    Raises:
        DerivedColumnFormulaError: If the operator is unsupported.
    """
    try:
        return _OPERATOR_PRECEDENCE[token.value]
    except KeyError as exc:
        msg = "unsupported_operator"
        raise DerivedColumnFormulaError(
            msg,
            context={
                "token": token.value,
                "position": token.position,
            }
        ) from exc


def _validate_column_references(
    tokens: list[FormulaToken],
    available_columns: set[str],
) -> None:
    """Validate that all referenced columns exist.

    Args:
        tokens: Formula tokens.
        available_columns: Set of valid column names.

    Raises:
        DerivedColumnFormulaError: If a column reference is unknown.
    """
    for token in tokens:
        if token.token_type != FormulaTokenType.COLUMN:
            continue

        if token.value not in available_columns:
            msg = "unknown_column"
            raise DerivedColumnFormulaError(
                msg,
                context={
                    "column": token.value,
                    "position": token.position,
                },
            )


def _validate_syntax(tokens: list[FormulaToken]) -> None:
    """Validate expression syntax.

    Args:
        tokens: Formula tokens.

    Raises:
        DerivedColumnFormulaError: If syntax is invalid.
    """
    expecting_operand = True
    paren_balance = 0
    saw_operand = False

    previous: FormulaToken | None = None

    for token in tokens:
        token_type = token.token_type

        if token_type in {FormulaTokenType.NUMBER, FormulaTokenType.COLUMN}:
            if not expecting_operand:
                msg = "missing_operator_before_operand"
                raise DerivedColumnFormulaError(
                    msg,
                    context={"position": token.position},
                )

            expecting_operand = False
            saw_operand = True
            previous = token
            continue

        if token_type == FormulaTokenType.LPAREN:
            if not expecting_operand:
                msg = "missing_operand_before_opening_parenthesis"
                raise DerivedColumnFormulaError(
                    msg,
                    context={
                        "position": token.position,
                    }
                )

            paren_balance += 1
            expecting_operand = True
            previous = token
            continue

        if token_type == FormulaTokenType.RPAREN:
            if expecting_operand:
                msg = "missing_operand_before_closing_parenthesis"
                raise DerivedColumnFormulaError(
                    msg,
                    context={"position": token.position},
                )

            paren_balance -= 1
            if paren_balance < 0:
                msg = "unmatched_closing_parenthesis"
                raise DerivedColumnFormulaError(
                    msg,
                    context={"position": token.position},
                )

            expecting_operand = False
            previous = token
            continue

        if token_type == FormulaTokenType.OPERATOR:
            if expecting_operand:
                msg = "missing_operand_before_operator"
                raise DerivedColumnFormulaError(
                    msg,
                    context={
                        "operator": token.value,
                        "position": token.position,
                    }
                )

            expecting_operand = True
            previous = token
            continue

        msg = "unsupported_token"
        raise DerivedColumnFormulaError(
            msg,
            context={
                "token": token.value,
                "position": token.position,
            },
        )

    if paren_balance > 0:
        msg = "unmatched_opening_parenthesis"
        raise DerivedColumnFormulaError(msg)

    if expecting_operand:
        if previous and previous.token_type == FormulaTokenType.OPERATOR:
            msg = "formula_ends_with_operator"
            raise DerivedColumnFormulaError(
                msg,
                context={"operator": previous.value}
            )

        msg = "formula_incomplete"
        raise DerivedColumnFormulaError(msg)

    if not saw_operand:
        msg = "formula_missing_value"
        raise DerivedColumnFormulaError(msg)
