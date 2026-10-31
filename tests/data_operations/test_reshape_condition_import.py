"""Semantic round trips between manual conditions and builder trees."""

from itertools import product

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.reshape_condition_import import (
    ConditionBuilderDiagnostic,
    condition_group_from_text,
)
from expo_jbm329.services.data_operations.reshape_condition_lint import ConditionLintCode, parse_condition
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionGroup,
    ConditionMatch,
    ConditionOperator,
    ConditionProblem,
    ConditionRule,
    ConditionValue,
    condition_columns,
    format_condition,
)
from expo_jbm329.services.data_operations.reshape_preview import evaluate_condition

COLUMNS = condition_columns(
    ["a", "b", "c", "a]b", "number", "flag", "date", "dup", "dup"],
    ["object", "category", "string", "object", "float64", "boolean", "datetime64[ns]", "object", "object"],
)


def imported(text: str) -> ConditionGroup:
    result = condition_group_from_text(text, COLUMNS)
    assert result.diagnostic is None
    assert result.group is not None
    return result.group


@pytest.mark.parametrize("text", ["", " \n\t "])
def test_blank_input_has_no_group_or_error(text: str) -> None:
    result = condition_group_from_text(text, COLUMNS)
    assert result.group is None
    assert result.diagnostic is None


@pytest.mark.parametrize("operator", list(ConditionOperator))
def test_all_builder_operators_round_trip(operator: ConditionOperator) -> None:
    operands = () if operator.is_null_test else (ConditionValue("string", "O'Brien []()"),)
    group = ConditionGroup((ConditionRule(COLUMNS[3], operator, operands),))
    text = format_condition(group)
    assert imported(text) == group
    assert format_condition(imported(text)) == text


@pytest.mark.parametrize(
    "text",
    [
        "[a] = ''",
        "[a]]b] = 'O''Brien'",
        "[a] IN ('one', 'two', 'line\nbreak')",
        "[date] >= '2026-10-31T10:00:00'",
        "[number] IN (+01, 1.0, -.5, 1e3)",
        "[flag] in (true, FALSE)",
        "((([a] = 'x')))",
        "[a] = 'x' or [b] = 'y' and [c] = 'z'",
        "([a] = 'x' OR [b] = 'y') AND [c] = 'z'",
        "[a] = 'x' AND ([b] = 'y' OR [c] = 'z')",
    ],
)
def test_normalized_text_preserves_execution_instructions(text: str) -> None:
    group = imported(text)
    formatted = format_condition(group)
    assert parse_condition(formatted, COLUMNS) == parse_condition(text, COLUMNS)
    assert imported(formatted) == group


def test_mixed_connectors_preserve_and_precedence_and_operand_order() -> None:
    group = imported("[a] = 'x' OR [b] = 'y' AND [c] = 'z'")
    assert group.match == ConditionMatch.ANY
    assert isinstance(group.rules[0], ConditionRule)
    nested = group.rules[1]
    assert isinstance(nested, ConditionGroup)
    assert nested.match == ConditionMatch.ALL
    assert [rule.column.name for rule in nested.rules if isinstance(rule, ConditionRule)] == ["b", "c"]
    assert format_condition(group) == "([a] = 'x' OR ([b] = 'y' AND [c] = 'z'))"


@pytest.mark.parametrize("connector", ["AND", "OR"])
def test_same_connector_groups_are_flattened(connector: str) -> None:
    group = imported(f"([a] = 'x' {connector} [b] = 'y') {connector} ([c] = 'z')")
    assert len(group.rules) == 3
    assert all(isinstance(rule, ConditionRule) for rule in group.rules)


def test_numeric_spelling_and_boolean_identity_are_builder_compatible() -> None:
    group = imported("[number] IN (+01, 1.00, -.5, 1e3000) AND [flag] = true")
    numeric, boolean = group.rules
    assert isinstance(numeric, ConditionRule)
    assert numeric.operands == (
        ConditionValue("integer", "+01"),
        ConditionValue("decimal", "1.00"),
        ConditionValue("decimal", "-.5"),
        ConditionValue("decimal", "1e3000"),
    )
    assert isinstance(boolean, ConditionRule)
    assert boolean.operands == (ConditionValue("boolean", "True"),)
    assert format_condition(group) == "([number] IN (+01, 1.00, -.5, 1e3000) AND [flag] = True)"


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("[absent] = 'x'", ConditionLintCode.UNKNOWN_COLUMN),
        ("[dup] = 'x'", ConditionLintCode.AMBIGUOUS_COLUMN),
        ("[number] = '1'", ConditionLintCode.NUMBER_VALUE),
        ("[flag] = 'True'", ConditionLintCode.BOOLEAN_VALUE),
        ("[a] = 1", ConditionLintCode.VALUE),
        ("([a] = 'x'", ConditionLintCode.CLOSE),
        ("[a] = 'unfinished", ConditionLintCode.QUOTE),
        ("[a] LIKE 'x'", ConditionLintCode.OPERATOR),
        ("[a] = 'x' AND", ConditionLintCode.EXPRESSION),
    ],
)
def test_invalid_input_returns_first_shared_diagnostic(text: str, code: ConditionLintCode) -> None:
    result = condition_group_from_text(text, COLUMNS)
    assert result.group is None
    assert result.diagnostic == parse_condition(text, COLUMNS).diagnostics[0]
    assert result.diagnostic.code == code


@pytest.mark.parametrize(
    "text",
    ["[a] IN ('x', 'x')", "[number] IN (1, 1)", "[flag] IN (true, TRUE)"],
)
def test_duplicate_operands_return_explicit_builder_failure_without_changing_lint(text: str) -> None:
    assert not parse_condition(text, COLUMNS).diagnostics
    result = condition_group_from_text(text, COLUMNS)
    assert result.group is None
    assert result.diagnostic == ConditionBuilderDiagnostic(ConditionProblem.INVALID_RULE, 0, len(text))


def test_deep_parentheses_and_long_chains_are_imported_without_recursive_parsing() -> None:
    assert len(imported("(" * 2000 + "[a] = 'x'" + ")" * 2000).rules) == 1
    group = imported(" AND ".join(["[a] = 'x'"] * 2000))
    assert len(group.rules) == 2000
    assert format_condition(group).count("[a]") == 2000


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[a] = true OR [b] = true AND [c] = true", [False, False, False, True, True, True, True, True]),
        ("([a] = true OR [b] = true) AND [c] = true", [False, False, False, True, False, True, False, True]),
        ("[a] = true AND ([b] = true OR [c] = true)", [False, False, False, False, False, True, True, True]),
        ("[a] = true AND ([b] = true AND [c] = true)", [False, False, False, False, False, False, False, True]),
        ("([a] = true OR [b] = true) OR [c] = true", [False, True, True, True, True, True, True, True]),
    ],
)
def test_round_trip_preserves_real_row_masks_for_every_truth_combination(text: str, expected: list[bool]) -> None:
    source = pd.DataFrame(list(product([False, True], repeat=3)), columns=["a", "b", "c"], dtype="boolean")
    columns = condition_columns(list(source.columns), list(source.dtypes))
    result = condition_group_from_text(text, columns)
    assert result.diagnostic is None
    assert result.group is not None
    original = parse_condition(text, columns)
    normalized = parse_condition(format_condition(result.group), columns)
    before = evaluate_condition(source, original.instructions)
    after = evaluate_condition(source, normalized.instructions)
    assert before.tolist() == expected
    pd.testing.assert_series_equal(after, before)
