"""Typed condition builder values and text generation, without evaluation."""

from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Sequence


class ConditionOperator(StrEnum):
    """Stable tokens in Reshape's condition syntax."""

    EQUAL = "="
    NOT_EQUAL = "!="
    IN = "IN"
    NOT_IN = "NOT IN"
    GREATER = ">"
    GREATER_EQUAL = ">="
    LESS = "<"
    LESS_EQUAL = "<="
    IS_NULL = "IS NULL"
    IS_NOT_NULL = "IS NOT NULL"

    @property
    def is_null_test(self) -> bool:
        """Return whether this operator requires no values."""
        return self in {self.IS_NULL, self.IS_NOT_NULL}

    @property
    def is_membership(self) -> bool:
        """Return whether multiple selected values are permitted."""
        return self in {self.IN, self.NOT_IN}


class ConditionMatch(StrEnum):
    """Single connector used for every rule in a group."""

    ALL = "AND"
    ANY = "OR"


class ConditionProblem(StrEnum):
    """Explicit failures independent of translated UI wording."""

    UNSUPPORTED_VALUE = "unsupported_value"
    AMBIGUOUS_VALUE = "ambiguous_value"
    INVALID_RULE = "invalid_rule"


class ConditionError(ValueError):
    """Condition input cannot be represented without ambiguity."""

    def __init__(self, problem: ConditionProblem) -> None:
        """Store a stable failure code for UI translation."""
        self.problem = problem
        super().__init__(problem.value)


@dataclass(frozen=True, slots=True)
class ConditionValue:
    """Canonical nonlocalized value text plus its scalar type identity."""

    kind: str
    text: str


class ConditionLiteralType(StrEnum):
    """Unquoted literal syntax permitted by a column's storage dtype."""

    QUOTED = "quoted"
    NUMBER = "number"
    BOOLEAN = "boolean"


NUMBER_LITERAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


@dataclass(frozen=True, slots=True)
class ConditionColumn:
    """Source position and syntax name, with ambiguous names disabled."""

    position: int
    name: str
    available: bool
    literal_type: ConditionLiteralType = ConditionLiteralType.QUOTED


@dataclass(frozen=True, slots=True)
class ConditionRule:
    """One builder rule tied to an unambiguous source column."""

    column: ConditionColumn
    operator: ConditionOperator
    operands: tuple[ConditionValue, ...] = ()


@dataclass(frozen=True, slots=True)
class ConditionGroup:
    """Applied builder state, independent of widgets and manual text."""

    rules: tuple[ConditionRule | ConditionGroup, ...]
    match: ConditionMatch = ConditionMatch.ALL


def condition_columns(labels: Sequence[object], dtypes: Sequence[object] | None = None) -> tuple[ConditionColumn, ...]:
    """Capture names and optional storage dtypes, disabling ambiguous names."""
    from collections import Counter

    names = tuple(str(label) for label in labels)
    if dtypes is not None and len(dtypes) != len(names):
        message = "Source dtype metadata must match the number of source columns."
        raise ValueError(message)
    counts = Counter(names)
    columns: list[ConditionColumn] = []
    for index, name in enumerate(names):
        literal_type = ConditionLiteralType.QUOTED
        if dtypes is not None:
            dtype = str(dtypes[index])
            if pd.api.types.is_bool_dtype(dtype):
                literal_type = ConditionLiteralType.BOOLEAN
            elif pd.api.types.is_integer_dtype(dtype) or pd.api.types.is_float_dtype(dtype):
                literal_type = ConditionLiteralType.NUMBER
        columns.append(ConditionColumn(index, name, counts[name] == 1, literal_type))
    return tuple(columns)


def condition_value(value: object) -> ConditionValue | None:
    """Serialize a supported scalar without locale changes or data conversion.

    Args:
        value: Original source cell value.

    Returns:
        Canonical scalar identity, or None for a missing scalar.

    Raises:
        ConditionError: If a nonmissing value is not a supported scalar.
    """
    if not pd.api.types.is_scalar(value):
        raise ConditionError(ConditionProblem.UNSUPPORTED_VALUE)
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.datetime64):
        if pd.isna(value):
            return None
        value = pd.Timestamp(value)
    elif isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, str):
        return ConditionValue("string", value)
    if isinstance(value, bool):
        return ConditionValue("boolean", str(value))
    if isinstance(value, int):
        return ConditionValue("integer", str(value))
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise ConditionError(ConditionProblem.UNSUPPORTED_VALUE)
        return ConditionValue("float", repr(value))
    if isinstance(value, Decimal):
        if value.is_nan():
            return None
        if not value.is_finite():
            raise ConditionError(ConditionProblem.UNSUPPORTED_VALUE)
        return ConditionValue("decimal", str(value))
    if isinstance(value, dt.datetime):
        return ConditionValue("datetime", value.isoformat())
    if isinstance(value, dt.date):
        return ConditionValue("date", value.isoformat())
    raise ConditionError(ConditionProblem.UNSUPPORTED_VALUE)


def format_condition(group: ConditionGroup) -> str:
    """Validate complete builder rules and emit escaped Reshape syntax.

    Args:
        group: Typed applied rules, never manually entered syntax.

    Returns:
        A deterministic expression, parenthesized when multiple rules exist.

    Raises:
        ConditionError: If rules are incomplete or value tokens are ambiguous.
    """
    if not group.rules:
        raise ConditionError(ConditionProblem.INVALID_RULE)
    expressions: list[str] = []
    for rule in group.rules:
        if isinstance(rule, ConditionGroup):
            expressions.append(format_condition(rule))
            continue
        if not rule.column.available or rule.column.position < 0:
            raise ConditionError(ConditionProblem.INVALID_RULE)
        operator = rule.operator
        if operator.is_null_test:
            if rule.operands:
                raise ConditionError(ConditionProblem.INVALID_RULE)
        elif not rule.operands or (not operator.is_membership and len(rule.operands) != 1):
            raise ConditionError(ConditionProblem.INVALID_RULE)
        if len(set(rule.operands)) != len(rule.operands):
            raise ConditionError(ConditionProblem.INVALID_RULE)
        if len({value.text for value in rule.operands}) != len(rule.operands):
            raise ConditionError(ConditionProblem.AMBIGUOUS_VALUE)
        name = "[" + rule.column.name.replace("]", "]]") + "]"
        expression = f"{name} {operator.value}"
        literals = []
        for value in rule.operands:
            numeric = (
                rule.column.literal_type == ConditionLiteralType.NUMBER
                and value.kind in {"integer", "float", "decimal"}
                and NUMBER_LITERAL.fullmatch(value.text) is not None
            )
            boolean = (
                rule.column.literal_type == ConditionLiteralType.BOOLEAN
                and value.kind == "boolean"
                and value.text in {"True", "False"}
            )
            literals.append(value.text if numeric or boolean else "'" + value.text.replace("'", "''") + "'")
        if operator.is_membership:
            expression += " (" + ", ".join(literals) + ")"
        elif not operator.is_null_test:
            expression += " " + literals[0]
        expressions.append(expression)
    text = f" {group.match.value} ".join(expressions)
    return f"({text})" if len(expressions) > 1 else text
