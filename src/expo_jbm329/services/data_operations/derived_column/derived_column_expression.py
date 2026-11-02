"""Typed, nonexecuting parser for arithmetic and conditional derived columns.

IF(condition; then; else) supports nested IF and text/numeric column branches.
Predicates include =, !=, <, <=, >, >=, BETWEEN/NOT BETWEEN, IN/NOT IN, and
IS NULL/IS NOT NULL. Literal membership lists use commas. Precedence is
arithmetic, predicates (including BETWEEN's internal AND), NOT, AND, then OR.
Column metadata determines result compatibility, never sampled cell values;
NULL is compatible with either text or numeric results, but mixing them fails.
Validation and future evaluation consume the same parsed, typed expression.
Legacy arithmetic RPN entry points remain in derived_column_parser.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, NoReturn

import pandas as pd

from expo_jbm329.services.data_operations.derived_column.derived_column_parser import (
    DerivedColumnFormulaError,
    FormulaValidationResult,
)
from expo_jbm329.services.data_operations.expression_primitives import (
    UnclosedLiteralError,
    decode_delimited_literal,
)
from expo_jbm329.services.data_operations.reshape_conditions import NUMBER_LITERAL

if TYPE_CHECKING:
    from collections.abc import Sequence


class ExpressionType(StrEnum):
    """Schema-based value types, independent of pandas result storage."""

    NUMBER = "number"
    TEXT = "text"
    BOOLEAN = "boolean"
    NULL = "null"
    UNSUPPORTED = "unsupported"


class ExpressionOperation(StrEnum):
    """Safe operations understood by the derived column evaluator."""

    LITERAL = "literal"
    COLUMN = "column"
    IF = "IF"
    POSITIVE = "positive"
    NEGATIVE = "negative"
    ADD = "+"
    SUBTRACT = "-"
    MULTIPLY = "*"
    DIVIDE = "/"
    EQUAL = "="
    NOT_EQUAL = "!="
    GREATER = ">"
    GREATER_EQUAL = ">="
    LESS = "<"
    LESS_EQUAL = "<="
    BETWEEN = "BETWEEN"
    NOT_BETWEEN = "NOT BETWEEN"
    IN = "IN"
    NOT_IN = "NOT IN"
    IS_NULL = "IS NULL"
    IS_NOT_NULL = "IS NOT NULL"
    NOT = "NOT"
    AND = "AND"
    OR = "OR"


@dataclass(frozen=True, slots=True)
class ExpressionColumn:
    """A source column's position, exact name, type, and name availability."""

    position: int
    name: str
    value_type: ExpressionType
    available: bool = True


@dataclass(frozen=True, slots=True)
class FormulaExpression:
    """Immutable typed expression with a Python-character source span.

    Literal values retain decoded text or numeric spelling. NULL has an empty
    value; column nodes retain their resolved positional source identity.
    """

    operation: ExpressionOperation
    value_type: ExpressionType
    start: int
    end: int
    operands: tuple[FormulaExpression, ...] = ()
    value: str = ""
    column_position: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedFormula:
    """Complete validated expression and its sorted source references."""

    expression: FormulaExpression
    referenced_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str
    start: int
    end: int


_MAX_PARSE_DEPTH = 64
_PRECEDENCE = {
    "OR": 1,
    "AND": 2,
    "=": 3,
    "!=": 3,
    ">": 3,
    ">=": 3,
    "<": 3,
    "<=": 3,
    "BETWEEN": 3,
    "IN": 3,
    "IS": 3,
    "NOT": 3,
    "+": 4,
    "-": 4,
    "*": 5,
    "/": 5,
}


def expression_columns(labels: Sequence[object], dtypes: Sequence[object]) -> tuple[ExpressionColumn, ...]:
    """Capture column types without inspecting or coercing source cells.

    Args:
        labels: Source column labels in positional order.
        dtypes: Corresponding pandas storage dtypes.

    Returns:
        Positional metadata, with duplicate syntax names marked unavailable.
        Object columns are text candidates; evaluation must reject nontext
        objects rather than stringifying them. Categories use their value dtype.

    Raises:
        ValueError: If metadata lengths differ.
    """
    if len(labels) != len(dtypes):
        message = "Source dtype metadata must match the number of source columns."
        raise ValueError(message)
    names = tuple(str(label) for label in labels)
    counts = Counter(names)
    columns: list[ExpressionColumn] = []
    for position, (label, dtype) in enumerate(zip(labels, dtypes, strict=True)):
        dtype_name = (
            str(getattr(dtype.categories, "dtype", "object")) if isinstance(dtype, pd.CategoricalDtype) else str(dtype)
        )
        if pd.api.types.is_bool_dtype(dtype_name):
            value_type = ExpressionType.BOOLEAN
        elif pd.api.types.is_integer_dtype(dtype_name) or pd.api.types.is_float_dtype(dtype_name):
            value_type = ExpressionType.NUMBER
        elif pd.api.types.is_object_dtype(dtype_name) or pd.api.types.is_string_dtype(dtype_name):
            value_type = ExpressionType.TEXT
        else:
            value_type = ExpressionType.UNSUPPORTED
        name = names[position]
        columns.append(ExpressionColumn(position, name, value_type, counts[name] == 1 and isinstance(label, str)))
    return tuple(columns)


def _fail(code: str, token: _Token, **context: object) -> NoReturn:
    raise DerivedColumnFormulaError(
        code,
        context={"position": token.start, "end": token.end, "token": token.value, **context},
    )


def _tokenize(formula: str) -> list[_Token]:
    tokens: list[_Token] = []
    position = 0
    while position < len(formula):
        start = position
        character = formula[position]
        if character.isspace():
            position += 1
            continue
        if character in {"[", "'"}:
            try:
                value, position = decode_delimited_literal(formula, position)
            except UnclosedLiteralError as error:
                code = "unclosed_column_reference" if character == "[" else "unclosed_string_literal"
                _fail(code, _Token("invalid", "", error.start, error.end))
            kind = "column" if character == "[" else "string"
            if kind == "column" and not value:
                _fail("empty_column_reference", _Token(kind, value, start, position))
        elif character in ".0123456789" and (number := NUMBER_LITERAL.match(formula, position)) is not None:
            value = number[0]
            position = number.end()
            kind = "number"
            if not math.isfinite(float(value)):
                _fail("invalid_number_literal", _Token(kind, value, start, position))
        elif character.isalpha():
            position += 1
            while position < len(formula) and (formula[position].isalnum() or formula[position] == "_"):
                position += 1
            value = formula[start:position].upper()
            kind = "word"
        elif character in "=!<>":
            position += 1
            while position < len(formula) and formula[position] in "=!<>":
                position += 1
            value = formula[start:position]
            kind = "symbol"
            if value not in {"=", "!=", "<", "<=", ">", ">="}:
                _fail("unsupported_operator", _Token(kind, value, start, position))
        elif character in "+-*/();,":
            position += 1
            kind = "symbol"
            value = character
        else:
            _fail("unsupported_character", _Token("invalid", character, start, start + 1), char=character)
        tokens.append(_Token(kind, value, start, position))
    tokens.append(_Token("eof", "", len(formula), len(formula)))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token], columns: Sequence[ExpressionColumn]) -> None:
        self.tokens = tokens
        self.position = 0
        self.depth = 0
        self.columns: dict[str, list[ExpressionColumn]] = {}
        for column in columns:
            self.columns.setdefault(column.name, []).append(column)

    @property
    def current(self) -> _Token:
        return self.tokens[self.position]

    def take(self, value: str) -> bool:
        if self.current.kind in {"word", "symbol"} and self.current.value == value:
            self.position += 1
            return True
        return False

    def require(self, value: str) -> None:
        if not self.take(value):
            _fail("expected_token", self.current, expected=value)

    def expression(self, minimum: int = 1) -> FormulaExpression:
        self.depth += 1
        if self.depth > _MAX_PARSE_DEPTH:
            _fail("expression_nesting_limit", self.current, limit=_MAX_PARSE_DEPTH)
        try:
            left = self.primary()
            while self.current.kind in {"word", "symbol"}:
                precedence = _PRECEDENCE.get(self.current.value, 0)
                if precedence < minimum:
                    break
                left = self.infix(left, precedence)
            return left
        finally:
            self.depth -= 1

    def primary(self) -> FormulaExpression:
        token = self.current
        self.position += 1
        if token.kind in {"number", "string"} or (token.kind == "word" and token.value in {"NULL", "TRUE", "FALSE"}):
            value_type = {
                "number": ExpressionType.NUMBER,
                "string": ExpressionType.TEXT,
                "NULL": ExpressionType.NULL,
                "TRUE": ExpressionType.BOOLEAN,
                "FALSE": ExpressionType.BOOLEAN,
            }[token.value if token.kind == "word" else token.kind]
            return FormulaExpression(ExpressionOperation.LITERAL, value_type, token.start, token.end, value=token.value)
        if token.kind == "column":
            matches = self.columns.get(token.value, [])
            if not matches:
                _fail("unknown_column", token, column=token.value)
            if len(matches) != 1 or not matches[0].available:
                _fail("column_not_unique", token, column=token.value)
            column = matches[0]
            return FormulaExpression(
                ExpressionOperation.COLUMN,
                column.value_type,
                token.start,
                token.end,
                value=column.name,
                column_position=column.position,
            )
        if token.kind == "symbol" and token.value == "(":
            result = self.expression()
            end = self.current.end
            self.require(")")
            return replace(result, start=token.start, end=end)
        if token.kind == "word" and token.value == "IF":
            return self.conditional(token)
        if token.kind in {"word", "symbol"} and token.value in {"+", "-", "NOT"}:
            operand = self.expression(3 if token.value == "NOT" else 6)
            operation = {
                "+": ExpressionOperation.POSITIVE,
                "-": ExpressionOperation.NEGATIVE,
                "NOT": ExpressionOperation.NOT,
            }[token.value]
            value_type = ExpressionType.BOOLEAN if token.value == "NOT" else ExpressionType.NUMBER
            self.check_type(operand, value_type, token)
            return FormulaExpression(operation, value_type, token.start, operand.end, (operand,))
        _fail("expected_expression", token)

    def conditional(self, token: _Token) -> FormulaExpression:
        self.require("(")
        condition = self.expression()
        self.check_type(condition, ExpressionType.BOOLEAN, token)
        self.require(";")
        then = self.expression()
        self.require(";")
        otherwise = self.expression()
        end = self.current.end
        self.require(")")
        value_type = self.compatible_type((then, otherwise), token, code="incompatible_branch_types")
        if value_type not in {ExpressionType.TEXT, ExpressionType.NUMBER, ExpressionType.NULL}:
            _fail("invalid_result_type", token, dtype=value_type.value)
        return FormulaExpression(ExpressionOperation.IF, value_type, token.start, end, (condition, then, otherwise))

    @staticmethod
    def check_type(expression: FormulaExpression, expected: ExpressionType, token: _Token) -> None:
        if expression.value_type not in {expected, ExpressionType.NULL}:
            _fail("invalid_operand_type", token, expected=expected.value, actual=expression.value_type.value)

    @staticmethod
    def compatible_type(
        operands: tuple[FormulaExpression, ...],
        token: _Token,
        *,
        code: str = "incompatible_operand_types",
    ) -> ExpressionType:
        types = {operand.value_type for operand in operands} - {ExpressionType.NULL}
        if ExpressionType.UNSUPPORTED in types:
            _fail("unsupported_column_type", token)
        if len(types) > 1:
            _fail(code, token)
        return next(iter(types), ExpressionType.NULL)

    def infix(self, left: FormulaExpression, precedence: int) -> FormulaExpression:
        token = self.current
        self.position += 1
        operator = token.value
        if operator == "IS":
            negate = self.take("NOT")
            end = self.current.end
            self.require("NULL")
            operation = ExpressionOperation.IS_NOT_NULL if negate else ExpressionOperation.IS_NULL
            return FormulaExpression(operation, ExpressionType.BOOLEAN, left.start, end, (left,))
        if operator == "NOT":
            if self.take("IN"):
                operator = "NOT IN"
            elif self.take("BETWEEN"):
                operator = "NOT BETWEEN"
            else:
                _fail("expected_token", self.current, expected="IN or BETWEEN")
        if operator in {"IN", "NOT IN"}:
            self.require("(")
            values = [self.membership_literal()]
            while self.take(","):
                values.append(self.membership_literal())
            end = self.current.end
            self.require(")")
            operands = (left, *values)
        elif operator in {"BETWEEN", "NOT BETWEEN"}:
            lower = self.expression(precedence + 1)
            self.require("AND")
            upper = self.expression(precedence + 1)
            operands = (left, lower, upper)
            end = upper.end
        else:
            right = self.expression(precedence + 1)
            operands = (left, right)
            end = right.end
        if operator in {"+", "-", "*", "/"}:
            for operand in operands:
                self.check_type(operand, ExpressionType.NUMBER, token)
            value_type = ExpressionType.NUMBER
        elif operator in {"AND", "OR"}:
            for operand in operands:
                self.check_type(operand, ExpressionType.BOOLEAN, token)
            value_type = ExpressionType.BOOLEAN
        else:
            self.compatible_type(operands, token)
            value_type = ExpressionType.BOOLEAN
        return FormulaExpression(ExpressionOperation(operator), value_type, left.start, end, operands)

    def membership_literal(self) -> FormulaExpression:
        token = self.current
        sign = ""
        if token.kind == "symbol" and token.value in {"+", "-"}:
            sign = token.value
            self.position += 1
            if self.current.kind != "number":
                _fail("expected_literal", self.current)
        elif token.kind not in {"number", "string"} and not (
            token.kind == "word" and token.value in {"NULL", "TRUE", "FALSE"}
        ):
            _fail("expected_literal", token)
        literal = self.primary()
        if not sign:
            return literal
        return FormulaExpression(
            ExpressionOperation.LITERAL,
            ExpressionType.NUMBER,
            token.start,
            literal.end,
            value=sign + literal.value,
        )


def parse_expression_formula(formula: str, columns: Sequence[ExpressionColumn]) -> ParsedFormula:
    """Parse and type-check a complete derived column expression.

    Args:
        formula: User expression; no Python or SQL execution is performed.
        columns: Captured source-column schema in positional order.

    Returns:
        Immutable expression suitable for validation and subsequent evaluation.

    Raises:
        DerivedColumnFormulaError: For invalid syntax, incompatible types,
            unavailable columns, or nesting beyond the parser's safe limit.
    """
    tokens = _tokenize(formula)
    if tokens[0].kind == "eof":
        _fail("formula_empty", tokens[0])
    parser = _Parser(tokens, columns)
    expression = parser.expression()
    if parser.current.kind != "eof":
        _fail("unexpected_token", parser.current)
    if expression.value_type not in {ExpressionType.NUMBER, ExpressionType.TEXT, ExpressionType.NULL}:
        _fail("invalid_result_type", tokens[0], dtype=expression.value_type.value)
    return ParsedFormula(expression, tuple(sorted({token.value for token in tokens if token.kind == "column"})))


def validate_expression_formula(formula: str, columns: Sequence[ExpressionColumn]) -> FormulaValidationResult:
    """Return structured validation using the evaluation parser's exact path."""
    try:
        parsed = parse_expression_formula(formula, columns)
    except DerivedColumnFormulaError as error:
        return FormulaValidationResult(ok=False, error=error)
    return FormulaValidationResult(ok=True, referenced_columns=parsed.referenced_columns)


def expression_referenced_columns(formula: str) -> set[str]:
    """Extract decoded references without requiring a source schema."""
    tokens = _tokenize(formula)
    if tokens[0].kind == "eof":
        _fail("formula_empty", tokens[0])
    return {token.value for token in tokens if token.kind == "column"}
