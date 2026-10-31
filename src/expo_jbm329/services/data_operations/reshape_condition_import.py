"""Import manual Reshape syntax into the visual builder's typed tree."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from expo_jbm329.services.data_operations.reshape_condition_lint import parse_condition
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionError,
    ConditionGroup,
    ConditionProblem,
    ConditionRule,
    ConditionValue,
    format_condition,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from expo_jbm329.services.data_operations.reshape_condition_lint import ConditionDiagnostic
    from expo_jbm329.services.data_operations.reshape_conditions import ConditionColumn


@dataclass(frozen=True, slots=True)
class ConditionBuilderDiagnostic:
    """Valid syntax that cannot be represented as a complete builder rule."""

    code: ConditionProblem
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ConditionImportResult:
    """Imported tree, empty input, or the first explicit import failure."""

    group: ConditionGroup | None = None
    diagnostic: ConditionDiagnostic | ConditionBuilderDiagnostic | None = None


def condition_group_from_text(text: str, columns: Sequence[ConditionColumn]) -> ConditionImportResult:
    """Rebuild a builder tree using the shared parser's precedence rules.

    Args:
        text: Manual condition with the same grammar as linting and execution.
        columns: Captured positional column names and literal-type metadata.

    Returns:
        A normalized builder group, an empty result for blank input, or the
        first diagnostic. Builder-only failures identify the whole expression.
        Numeric spelling is retained; quoted literals retain their decoded
        text without attempting to infer the original source scalar type.
    """
    parsed = parse_condition(text, columns)
    if parsed.diagnostics:
        return ConditionImportResult(diagnostic=parsed.diagnostics[0])
    if not parsed.instructions:
        return ConditionImportResult()
    stack: list[ConditionRule | ConditionGroup] = []
    for instruction in parsed.instructions:
        if isinstance(instruction, ConditionRule):
            operands = tuple(_builder_value(value) for value in instruction.operands)
            rule = replace(instruction, operands=operands)
            try:
                format_condition(ConditionGroup((rule,)))
            except ConditionError as error:
                return ConditionImportResult(diagnostic=ConditionBuilderDiagnostic(error.problem, 0, len(text)))
            stack.append(rule)
        else:
            right = stack.pop()
            left = stack.pop()
            children: list[ConditionRule | ConditionGroup] = []
            for child in (left, right):
                if isinstance(child, ConditionGroup) and child.match == instruction:
                    children.extend(child.rules)
                else:
                    children.append(child)
            stack.append(ConditionGroup(tuple(children), instruction))
    root = stack.pop()
    return ConditionImportResult(root if isinstance(root, ConditionGroup) else ConditionGroup((root,)))


def _builder_value(value: ConditionValue) -> ConditionValue:
    if value.kind == "number":
        kind = "decimal" if any(character in value.text for character in ".eE") else "integer"
        return ConditionValue(kind, value.text)
    if value.kind == "boolean":
        return ConditionValue("boolean", value.text.title())
    return value
