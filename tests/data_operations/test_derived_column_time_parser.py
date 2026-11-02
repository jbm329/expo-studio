"""Time hierarchy grammar and schema validation without date evaluation."""

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.derived_column.derived_column_expression import (
    ExpressionOperation,
    ExpressionType,
    expression_columns,
    expression_referenced_columns,
    parse_expression_formula,
    validate_expression_formula,
)

FUNCTIONS = [
    ("TIME", ExpressionType.TEXT),
    ("WEEK", ExpressionType.TEXT),
    ("WEEK#", ExpressionType.NUMBER),
    ("MONTH", ExpressionType.TEXT),
    ("MONTHSHORT", ExpressionType.TEXT),
    ("MONTH#", ExpressionType.NUMBER),
    ("TERTIAL", ExpressionType.TEXT),
    ("TERTIAL#", ExpressionType.NUMBER),
    ("QUARTER", ExpressionType.TEXT),
    ("QUARTER#", ExpressionType.NUMBER),
    ("YEAR", ExpressionType.NUMBER),
    ("ISOYEAR", ExpressionType.NUMBER),
    ("YEARWEEK", ExpressionType.TEXT),
    ("YEARMONTH", ExpressionType.TEXT),
    ("YEARQUARTER", ExpressionType.TEXT),
    ("YEARTERTIAL", ExpressionType.TEXT),
]
COLUMNS = expression_columns(
    ["When", "a]b", "Age", "Text", "Flag", "Duration"],
    ["datetime64[ns]", "datetime64[ns, UTC]", "Int64", "string", "boolean", "timedelta64[ns]"],
)


@pytest.mark.parametrize(("function", "result_type"), FUNCTIONS)
@pytest.mark.parametrize("lowercase", [False, True])
def test_time_function_type_operation_references_and_raw_spans(function, result_type, lowercase):
    name = function.lower() if lowercase else function
    formula = f" \n {name} ( ([a]]b]) ) "
    parsed = parse_expression_formula(formula, COLUMNS)
    node = parsed.expression
    assert node.operation == ExpressionOperation(function)
    assert node.value_type == result_type
    assert node.operands[0].value_type == ExpressionType.DATETIME
    assert node.operands[0].column_position == 1
    assert formula[node.start : node.end] == formula.strip()
    assert parsed.referenced_columns == ("a]b",)
    assert expression_referenced_columns(formula) == {"a]b"}
    assert validate_expression_formula(formula, COLUMNS).ok


@pytest.mark.parametrize(("function", "result_type"), FUNCTIONS)
@pytest.mark.parametrize("empty", [False, True])
def test_empty_and_all_nat_validation_is_schema_based(function, result_type, empty):
    frame = pd.DataFrame({"When": pd.Series([] if empty else [pd.NaT], dtype="datetime64[us]")})
    columns = expression_columns(list(frame.columns), list(frame.dtypes))
    parsed = parse_expression_formula(f"{function}([When])", columns)
    assert parsed.expression.value_type == result_type


@pytest.mark.parametrize(("function", "_result_type"), FUNCTIONS)
@pytest.mark.parametrize("operand", ["[Age]", "[Text]", "[Flag]", "[Duration]", "NULL", "'2026-01-01'", "2026"])
def test_time_functions_reject_nondatetime_operands(function, _result_type, operand):
    result = validate_expression_formula(f"{function}({operand})", COLUMNS)
    assert not result.ok
    assert result.error.code == "datetime_operand_required"
    assert result.error.context["position"] == 0
    assert result.error.context["end"] == len(function)


@pytest.mark.parametrize(
    ("formula", "code"),
    [
        ("YEAR()", "expected_expression"),
        ("YEAR([When]; [When])", "expected_token"),
        ("YEAR([When], [When])", "expected_token"),
        ("YEAR([When] [When])", "expected_token"),
        ("YEAR([When]", "expected_token"),
        ("YEAR [When]", "expected_token"),
        ("YEAR([missing])", "unknown_column"),
        ("YEAR(MONTH([When]))", "datetime_operand_required"),
        ("YEAR#([When])", "unsupported_character"),
        ("MONTHSHORT#([When])", "unsupported_character"),
        ("WEEK##([When])", "unsupported_character"),
        ("MONTH #([When])", "unsupported_character"),
        ("#([When])", "unsupported_character"),
        ("DATE([When])", "expected_expression"),
        ("[When]", "invalid_result_type"),
        ("IF(TRUE; [When]; [When])", "unsupported_column_type"),
        ("IF(TRUE; [When]; NULL)", "unsupported_column_type"),
        ("YEAR(IF(TRUE; [When]; [When]))", "unsupported_column_type"),
        ("IF([When] = [When]; 1; 0)", "unsupported_column_type"),
        ("IF([When] = NULL; 1; 0)", "unsupported_column_type"),
        ("IF([When] IN(NULL); 1; 0)", "unsupported_column_type"),
        ("[When] + 1", "invalid_operand_type"),
    ],
)
def test_time_syntax_errors_and_no_accidental_datetime_grammar_expansion(formula, code):
    result = validate_expression_formula(formula, COLUMNS)
    assert not result.ok
    assert result.error.code == code
    assert 0 <= result.error.context["position"] <= result.error.context["end"] <= len(formula)


@pytest.mark.parametrize(
    "formula",
    [
        "IF([When] IS NULL; 'Missing'; MONTH([When]))",
        "IF([When] IS NOT NULL; YEAR([When]); NULL)",
        "IF(MONTH#([When]) <= 6; 'H1'; 'H2')",
        "IF(MONTH([When]) IN('January', 'February'); 1; 0)",
        "YEAR([When]) + MONTH#([When]) / 12",
        "IF(WEEK#([When]) BETWEEN 1 AND 10; YEARWEEK([When]); NULL)",
        "IF(YEARQUARTER([When]) = YEARQUARTER([a]]b]); 'Same'; 'Other')",
        "IF(YEARTERTIAL([When]) IS NULL; 'Missing'; YEARTERTIAL([When]))",
    ],
)
def test_time_results_compose_with_existing_formula_operators(formula):
    assert validate_expression_formula(formula, COLUMNS).ok


def test_ambiguous_datetime_names_and_depth_limit_remain_structured():
    duplicate = expression_columns(["When", "When"], ["datetime64[ns]"] * 2)
    assert validate_expression_formula("YEAR([When])", duplicate).error.code == "column_not_unique"
    nested = "YEAR(" * 1000 + "[When]" + ")" * 1000
    assert validate_expression_formula(nested, COLUMNS).error.code == "expression_nesting_limit"
