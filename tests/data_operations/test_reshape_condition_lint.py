"""Syntax-only manual condition diagnostics and builder compatibility."""

import pytest

from expo_jbm329.services.data_operations.reshape_condition_lint import ConditionLintCode, lint_condition
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionColumn,
    ConditionGroup,
    ConditionMatch,
    ConditionOperator,
    ConditionRule,
    ConditionValue,
    condition_columns,
    format_condition,
)

COLUMNS = condition_columns(["a", "b", "Year", "a]b", "", "emoji😀", "dup", "dup", 1, "1"])


@pytest.mark.parametrize(
    "text",
    [
        "",
        " \n\t",
        "[a] = 'anything'",
        "[a] != ''",
        "[a] < 'not a number'",
        "[a] >= '[]() AND OR'",
        "[a] in ('a', 'b')",
        "[a] not in ('x')",
        "[a] is null",
        "[a] Is Not Null",
        "[a] = 'O''Brien'",
        "[a]]b] = 'escaped'",
        "[] = ''",
        "[emoji😀] = '😀'",
        "([a] = '1' OR [b] = '2') AND [Year] = '2019'",
        "[a] = '1' or [b] = '2' and [Year] = '2019'",
        "\n(\n[a]\nNOT\tIN\n('one',\n 'two')\n)\n",
        "[a] = 'line\nbreak' AND [b] = 'not present in any dataset'",
        "((([a] <= 'x')))",
        "[a] = ''''",
        "[a] = 'a''b''c'",
    ],
)
def test_valid_conditions(text):
    assert lint_condition(text, COLUMNS) == ()


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("a = '1'", ConditionLintCode.COLUMN),
        ("[A] = '1'", ConditionLintCode.UNKNOWN_COLUMN),
        ("[absent] = 'x'", ConditionLintCode.UNKNOWN_COLUMN),
        ("[dup] = 'x'", ConditionLintCode.AMBIGUOUS_COLUMN),
        ("[1] = 'x'", ConditionLintCode.AMBIGUOUS_COLUMN),
        ("[a = 'x'", ConditionLintCode.BRACKET),
        ("[a] = 'x", ConditionLintCode.QUOTE),
        ("[a] == 'x'", ConditionLintCode.OPERATOR),
        ("[a] <> 'x'", ConditionLintCode.OPERATOR),
        ("[a] LIKE 'x'", ConditionLintCode.OPERATOR),
        ("[a] BETWEEN '1' AND '2'", ConditionLintCode.OPERATOR),
        ("[a] NOT = 'x'", ConditionLintCode.OPERATOR),
        ("[a] IS TRUE", ConditionLintCode.OPERATOR),
        ("[a] = 1", ConditionLintCode.VALUE),
        ('[a] = "x"', ConditionLintCode.VALUE),
        ("[a] =", ConditionLintCode.VALUE),
        ("[a] IN 'x'", ConditionLintCode.LIST),
        ("[a] IN ()", ConditionLintCode.VALUE),
        ("[a] IN ('x',)", ConditionLintCode.VALUE),
        ("[a] IN ('x' 'y')", ConditionLintCode.LIST),
        ("[a] IN ('x'", ConditionLintCode.LIST),
        ("[a] IN ('x', 1)", ConditionLintCode.VALUE),
        ("([a] = 'x'", ConditionLintCode.CLOSE),
        ("()", ConditionLintCode.EXPRESSION),
        ("[a] = 'x' OR", ConditionLintCode.EXPRESSION),
        ("NOT [a] = 'x'", ConditionLintCode.COLUMN),
        ("[a] = 'x' [b] = 'y'", ConditionLintCode.CONNECTOR),
        ("[a] IS NULL 'x'", ConditionLintCode.CONNECTOR),
        ("[a] = 'x');", ConditionLintCode.UNMATCHED_CLOSE),
        ("[a] = 'x' -- comment", ConditionLintCode.CONNECTOR),
        ("[a] = 'x' AND OR [b] = 'y'", ConditionLintCode.COLUMN),
        ("[a] = 'O'Brien'", ConditionLintCode.CONNECTOR),
    ],
)
def test_invalid_conditions(text, code):
    assert code in [diagnostic.code for diagnostic in lint_condition(text, COLUMNS)]


def test_multiple_unknown_columns_report_exact_source_spans():
    text = "[missing] = '😀' AND [other] IS NULL"
    diagnostics = lint_condition(text, COLUMNS)
    assert [diagnostic.name for diagnostic in diagnostics] == ["missing", "other"]
    assert [text[item.start : item.end] for item in diagnostics] == ["[missing]", "[other]"]


def test_unclosed_literal_suppresses_cascading_eof_error():
    diagnostics = lint_condition("[a] = 'unfinished", COLUMNS)
    assert len(diagnostics) == 1
    assert diagnostics[0].code == ConditionLintCode.QUOTE


@pytest.mark.parametrize("operator", list(ConditionOperator))
def test_builder_expressions_pass_same_linter(operator):
    column = ConditionColumn(0, "a]b😀", True)
    operands = () if operator.is_null_test else (ConditionValue("string", "O'Brien []()😀"),)
    rule = ConditionRule(column, operator, operands)
    nested = ConditionGroup((ConditionGroup((rule, rule), ConditionMatch.ANY), rule))
    assert lint_condition(format_condition(nested), (column,)) == ()


def test_eof_error_position_and_opaque_brackets_inside_values():
    text = "[a] = 'unknown 😀' AND "
    error = lint_condition(text, COLUMNS)[0]
    assert error.start == error.end == len(text)
    assert not lint_condition("[a] = '[nonexistent] >= () OR'", COLUMNS)


def test_deep_nesting_and_long_condition_chains_do_not_recurse():
    assert not lint_condition("(" * 2000 + "[a] = 'x'" + ")" * 2000, COLUMNS)
    assert not lint_condition(" AND ".join(["[a] = 'x'"] * 2000), COLUMNS)


def test_unmatched_final_parenthesis_has_specific_diagnostic_and_span():
    text = "([Ref_Vårdform_Nyckel] = 'AKUT' OR [Akutflagga] = 'True') AND [Ålder] >= '18')"
    columns = condition_columns(["Ref_Vårdform_Nyckel", "Akutflagga", "Ålder"])
    diagnostics = lint_condition(text, columns)
    assert len(diagnostics) == 1
    assert diagnostics[0].code == ConditionLintCode.UNMATCHED_CLOSE
    assert (diagnostics[0].start, diagnostics[0].end) == (len(text) - 1, len(text))
    assert not lint_condition(text[:-1], columns)
    assert not lint_condition("(" + text, columns)


def test_parentheses_in_names_and_values_do_not_affect_group_matching():
    columns = condition_columns(["a)"])
    assert not lint_condition("([a)] IN (')', '('))", columns)
    assert lint_condition("[a)] = '(')", columns)[0].code == ConditionLintCode.UNMATCHED_CLOSE
