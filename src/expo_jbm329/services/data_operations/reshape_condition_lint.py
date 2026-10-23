"""Syntax-only validation of Reshape conditions without inspecting cell values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, NoReturn

from expo_jbm329.services.data_operations.reshape_conditions import (
    NUMBER_LITERAL,
    ConditionColumn,
    ConditionLiteralType,
    ConditionMatch,
    ConditionOperator,
    ConditionRule,
    ConditionValue,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class ConditionLintCode(StrEnum):
    """Stable diagnostic identities for presentation-layer translation."""

    COLUMN = "column"
    UNKNOWN_COLUMN = "unknown_column"
    AMBIGUOUS_COLUMN = "ambiguous_column"
    BRACKET = "bracket"
    QUOTE = "quote"
    OPERATOR = "operator"
    VALUE = "value"
    NUMBER_VALUE = "number_value"
    BOOLEAN_VALUE = "boolean_value"
    LIST = "list"
    CLOSE = "close"
    UNMATCHED_CLOSE = "unmatched_close"
    EXPRESSION = "expression"
    CONNECTOR = "connector"
    GROUP_CONNECTOR = "group_connector"


@dataclass(frozen=True, slots=True)
class ConditionDiagnostic:
    """One source span in Python character offsets, not Qt UTF-16 positions."""

    code: ConditionLintCode
    start: int
    end: int
    name: str = ""


@dataclass(frozen=True, slots=True)
class ParsedCondition:
    """Shared parse result; postfix instructions avoid recursive evaluation."""

    instructions: tuple[ConditionRule | ConditionMatch, ...]
    diagnostics: tuple[ConditionDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    text: str
    start: int
    end: int


def _tokens(text: str) -> tuple[list[_Token], ConditionDiagnostic | None]:
    result: list[_Token] = []
    position = 0
    while position < len(text):
        start = position
        character = text[position]
        if character.isspace():
            position += 1
            continue
        if character in {"[", "'"}:
            closing = "]" if character == "[" else "'"
            position += 1
            decoded: list[str] = []
            while position < len(text):
                if text[position] != closing:
                    decoded.append(text[position])
                    position += 1
                elif position + 1 < len(text) and text[position + 1] == closing:
                    decoded.append(closing)
                    position += 2
                else:
                    position += 1
                    result.append(_Token("column" if character == "[" else "value", "".join(decoded), start, position))
                    break
            else:
                code = ConditionLintCode.BRACKET if character == "[" else ConditionLintCode.QUOTE
                return result, ConditionDiagnostic(code, start, len(text))
        elif character in "+-.0123456789" and (number := NUMBER_LITERAL.match(text, position)) is not None:
            position = number.end()
            result.append(_Token("number", number[0], start, position))
        elif character.isalpha():
            position += 1
            while position < len(text) and (text[position].isalnum() or text[position] == "_"):
                position += 1
            result.append(_Token("word", text[start:position].upper(), start, position))
        elif character in "=!<>":
            position += 1
            while position < len(text) and text[position] in "=!<>":
                position += 1
            result.append(_Token("operator", text[start:position], start, position))
        else:
            position += 1
            result.append(_Token(character, character, start, position))
    return result, None


class _SyntaxError(Exception):
    """Stop structural parsing at the first nonrecoverable grammar error."""


class _Parser:
    def __init__(self, tokens: list[_Token], length: int, columns: Sequence[ConditionColumn]) -> None:
        self.tokens = [*tokens, _Token("eof", "", length, length)]
        self.index = 0
        self.columns: dict[str, list[ConditionColumn]] = {}
        for column in columns:
            self.columns.setdefault(column.name, []).append(column)
        self.diagnostics: list[ConditionDiagnostic] = []
        self.instructions: list[ConditionRule | ConditionMatch] = []

    @property
    def current(self) -> _Token:
        return self.tokens[self.index]

    def fail(self, code: ConditionLintCode) -> NoReturn:
        token = self.current
        self.diagnostics.append(ConditionDiagnostic(code, token.start, token.end))
        raise _SyntaxError

    def take(self, text: str) -> bool:
        if self.current.text == text and self.current.kind not in {"value", "column", "eof"}:
            self.index += 1
            return True
        return False

    def expression(self) -> None:
        # An explicit grammar stack also handles deeply nested manual input.
        pending = ["or_tail", "and_tail", "atom"]
        while pending:
            production = pending.pop()
            if production == "atom":
                if self.take("("):
                    pending.extend(("close", "or_tail", "and_tail", "atom"))
                else:
                    self.predicate()
            elif production == "and_tail":
                if self.take("AND"):
                    pending.extend(("and_tail", "emit_and", "atom"))
            elif production == "or_tail":
                if self.take("OR"):
                    pending.extend(("or_tail", "emit_or", "and_tail", "atom"))
            elif production == "emit_and":
                self.instructions.append(ConditionMatch.ALL)
            elif production == "emit_or":
                self.instructions.append(ConditionMatch.ANY)
            elif not self.take(")"):
                self.fail(ConditionLintCode.CLOSE if self.current.kind == "eof" else ConditionLintCode.GROUP_CONNECTOR)

    def predicate(self) -> None:
        token = self.current
        if token.kind != "column":
            self.fail(ConditionLintCode.EXPRESSION if token.kind in {"eof", ")"} else ConditionLintCode.COLUMN)
        matches = self.columns.get(token.text, [])
        if not matches:
            self.diagnostics.append(
                ConditionDiagnostic(ConditionLintCode.UNKNOWN_COLUMN, token.start, token.end, token.text)
            )
        elif len(matches) != 1 or not matches[0].available:
            self.diagnostics.append(
                ConditionDiagnostic(ConditionLintCode.AMBIGUOUS_COLUMN, token.start, token.end, token.text)
            )
        self.index += 1
        literal_type = (
            matches[0].literal_type if len(matches) == 1 and matches[0].available else ConditionLiteralType.QUOTED
        )
        operator = self.operator()
        column = matches[0] if matches else ConditionColumn(-1, token.text, False)
        if operator.is_null_test:
            self.instructions.append(ConditionRule(column, operator))
            return
        if operator.is_membership and not self.take("("):
            self.fail(ConditionLintCode.LIST)
        operands = [self.value(literal_type)]
        if operator.is_membership:
            while self.take(","):
                operands.append(self.value(literal_type))
            if not self.take(")"):
                self.fail(ConditionLintCode.LIST)
        self.instructions.append(ConditionRule(column, operator, tuple(operands)))

    def operator(self) -> ConditionOperator:
        start = self.index
        for operator in sorted(ConditionOperator, key=lambda candidate: len(candidate.value.split()), reverse=True):
            self.index = start
            if all(self.take(part) for part in operator.value.split()):
                return operator
        self.index = start
        return self.fail(ConditionLintCode.OPERATOR)

    def value(self, literal_type: ConditionLiteralType) -> ConditionValue:
        token = self.current
        kind = "string"
        if literal_type == ConditionLiteralType.NUMBER:
            if token.kind != "number":
                self.fail(ConditionLintCode.NUMBER_VALUE)
            kind = "number"
        elif literal_type == ConditionLiteralType.BOOLEAN:
            if token.kind != "word" or token.text not in {"TRUE", "FALSE"}:
                self.fail(ConditionLintCode.BOOLEAN_VALUE)
            kind = "boolean"
        elif token.kind != "value":
            self.fail(ConditionLintCode.VALUE)
        self.index += 1
        return ConditionValue(kind, token.text)


def parse_condition(text: str, columns: Sequence[ConditionColumn]) -> ParsedCondition:
    """Parse syntax and column references without evaluating literal contents.

    Args:
        text: Complete manual condition, including any newlines.
        columns: Captured positional column names and ambiguity metadata.

    Returns:
        Postfix instructions on success or positioned diagnostics on failure.
    """
    if not text.strip():
        return ParsedCondition((), ())
    tokens, lexical_error = _tokens(text)
    parser = _Parser(tokens, len(text), columns)
    try:
        parser.expression()
        if parser.current.kind != "eof":
            parser.fail(
                ConditionLintCode.UNMATCHED_CLOSE if parser.current.kind == ")" else ConditionLintCode.CONNECTOR
            )
    except _SyntaxError:
        pass
    diagnostics = parser.diagnostics
    if lexical_error is not None:
        # The truncated token stream cannot provide useful EOF syntax feedback.
        diagnostics = [diagnostic for diagnostic in diagnostics if diagnostic.start < lexical_error.start]
        diagnostics.append(lexical_error)
    errors = tuple(sorted(diagnostics, key=lambda diagnostic: diagnostic.start))
    return ParsedCondition(() if errors else tuple(parser.instructions), errors)


def lint_condition(text: str, columns: Sequence[ConditionColumn]) -> tuple[ConditionDiagnostic, ...]:
    """Return diagnostics from the same parser used for execution."""
    return parse_condition(text, columns).diagnostics
