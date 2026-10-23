"""Syntax-only validation of Reshape conditions without inspecting cell values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, NoReturn

from expo_jbm329.services.data_operations.reshape_conditions import ConditionColumn, ConditionOperator

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
                    pending.extend(("and_tail", "atom"))
            elif production == "or_tail":
                if self.take("OR"):
                    pending.extend(("or_tail", "and_tail", "atom"))
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
        operator = self.operator()
        if operator.is_null_test:
            return
        if operator.is_membership and not self.take("("):
            self.fail(ConditionLintCode.LIST)
        self.value()
        if operator.is_membership:
            while self.take(","):
                self.value()
            if not self.take(")"):
                self.fail(ConditionLintCode.LIST)

    def operator(self) -> ConditionOperator:
        start = self.index
        for operator in sorted(ConditionOperator, key=lambda candidate: len(candidate.value.split()), reverse=True):
            self.index = start
            if all(self.take(part) for part in operator.value.split()):
                return operator
        self.index = start
        return self.fail(ConditionLintCode.OPERATOR)

    def value(self) -> None:
        if self.current.kind != "value":
            self.fail(ConditionLintCode.VALUE)
        self.index += 1


def lint_condition(text: str, columns: Sequence[ConditionColumn]) -> tuple[ConditionDiagnostic, ...]:
    """Check syntax and column references, treating every quoted value as opaque.

    Args:
        text: Complete manual condition, including any newlines.
        columns: Captured positional column names and ambiguity metadata.

    Returns:
        Source-ordered diagnostics; empty input has no errors.
    """
    if not text.strip():
        return ()
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
    return tuple(sorted(diagnostics, key=lambda diagnostic: diagnostic.start))
