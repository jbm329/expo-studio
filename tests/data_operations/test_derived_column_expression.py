"""Typed conditional grammar, schema validation and positioned failures."""

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.derived_column.derived_column_expression import (
    ExpressionOperation as Op,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_expression import (
    ExpressionType as Type,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_expression import (
    expression_columns,
    expression_referenced_columns,
    parse_expression_formula,
    validate_expression_formula,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_parser import DerivedColumnFormulaError

COLUMNS = expression_columns(
    ["Age", "Limit", "Vehicle", "Column1", "Other", "Flag", "When", "a]b", "IF", " spaced "],
    ["Int64", "Float64", "string", "object", "string", "boolean", "datetime64[ns]", "string", "Int64", "string"],
)


@pytest.mark.parametrize(
    ("formula", "expected_type", "references"),
    [
        (
            "IF([Age] BETWEEN 0 AND 20; 'Youth'; IF([Age] BETWEEN 21 AND 40; 'Midlife'; 'Oldies'))",
            Type.TEXT,
            ("Age",),
        ),
        ("IF([Vehicle] IN('BMW', 'Volvo'); 'Cars'; 'Other')", Type.TEXT, ("Vehicle",)),
        ("IF([Vehicle] IN ('BMW', 'Volvo'); 'Cars'; 'Other')", Type.TEXT, ("Vehicle",)),
        ("IF([Column1] IS NULL; 'Empty'; [Column1])", Type.TEXT, ("Column1",)),
        ("IF([Age] IS NULL; 0; [Age])", Type.NUMBER, ("Age",)),
        ("IF([Age] + 1 > [Limit]; [Age] / 2; [Limit] * -2)", Type.NUMBER, ("Age", "Limit")),
        ("IF([Vehicle] = [Other]; [Vehicle]; [Other])", Type.TEXT, ("Other", "Vehicle")),
        ("IF([Flag]; 1; 0)", Type.NUMBER, ("Flag",)),
        ("IF(TRUE; 'yes'; NULL)", Type.TEXT, ()),
        ("IF(NULL; NULL; 2)", Type.NUMBER, ()),
        ("IF(FALSE; NULL; NULL)", Type.NULL, ()),
        ("if([Vehicle] is not  null; [Vehicle]; 'Unknown')", Type.TEXT, ("Vehicle",)),
        ("IF([When] IS NULL; 'Missing date'; 'Present')", Type.TEXT, ("When",)),
        ("IF([IF] > 0; [ spaced ]; 'Not an IF keyword')", Type.TEXT, (" spaced ", "IF")),
        ("IF([Age] = 1; IF([Flag]; 1; NULL); 2)", Type.NUMBER, ("Age", "Flag")),
        ("[Age] + [Limit] * 100", Type.NUMBER, ("Age", "Limit")),
        ("[Age]+[Limit]*100", Type.NUMBER, ("Age", "Limit")),
        ("[Age]-1", Type.NUMBER, ("Age",)),
        ("2+-3*[Age]", Type.NUMBER, ("Age",)),
        ("2--[Age]", Type.NUMBER, ("Age",)),
        ("([Age] + [Limit]) / 2", Type.NUMBER, ("Age", "Limit")),
        ("10", Type.NUMBER, ()),
        ("'text'", Type.TEXT, ()),
        ("NULL", Type.NULL, ()),
        ("-[Age] + +[Limit]", Type.NUMBER, ("Age", "Limit")),
        ("'IF([Unknown]; 1; 2)'", Type.TEXT, ()),
    ],
)
def test_valid_formulas_infer_types_and_references(formula, expected_type, references):
    parsed = parse_expression_formula(formula, COLUMNS)
    assert parsed.expression.value_type == expected_type
    assert parsed.referenced_columns == references
    validation = validate_expression_formula(formula, COLUMNS)
    assert validation.ok
    assert validation.error is None
    assert validation.referenced_columns == references
    assert expression_referenced_columns(formula) == set(references)


@pytest.mark.parametrize(
    "predicate",
    [
        "[Age] = 1",
        "[Age] != 1",
        "[Age] < [Limit]",
        "[Age] <= 0",
        "[Age] > -1",
        "[Age] >= +2",
        "[Age] BETWEEN -2 AND 2",
        "[Age] NOT BETWEEN 1 AND 3",
        "[Age] IN(1, -2, +3, .5, 1e2, NULL)",
        "[Age] NOT IN(1, 2)",
        "[Age] IS NULL",
        "[Age] IS NOT NULL",
        "[Vehicle] = 'BMW'",
        "[Vehicle] != 'BMW'",
        "[Vehicle] NOT IN('BMW', 'Volvo')",
        "[Column1] IS NULL",
        "[Column1] IS NOT NULL",
        "[Flag] IN(TRUE, false, NULL)",
        "NOT [Age] > 1",
        "NOT NOT ([Age] > 1 AND [Vehicle] = 'BMW')",
        "[Age] + 1 BETWEEN [Limit] - 2 AND [Limit] + 3",
        "([Age] + 1) * 2 >= ([Limit] / 3)",
        "[Age] BETWEEN 1 AND 2 AND [Age] != 0",
        "[Age] BETWEEN NULL AND 2 OR [Vehicle] IS NULL",
        "'a' = 'a'",
        "1 = 1",
        "NULL = NULL",
    ],
)
def test_predicate_operators(predicate):
    expression = parse_expression_formula(f"IF({predicate}; 1; 0)", COLUMNS).expression
    assert expression.operands[0].value_type == Type.BOOLEAN


def test_arithmetic_precedence_and_associativity():
    expression = parse_expression_formula("[Age] + [Limit] * 2 / 3 - 1", COLUMNS).expression
    assert expression.operation == Op.SUBTRACT
    addition = expression.operands[0]
    assert addition.operation == Op.ADD
    division = addition.operands[1]
    assert division.operation == Op.DIVIDE
    assert division.operands[0].operation == Op.MULTIPLY
    grouped = parse_expression_formula("([Age] + [Limit]) * 2", COLUMNS).expression
    assert grouped.operation == Op.MULTIPLY
    assert grouped.operands[0].operation == Op.ADD
    subtraction = parse_expression_formula("[Age]-1-2", COLUMNS).expression
    assert subtraction.operation == Op.SUBTRACT
    assert subtraction.operands[0].operation == Op.SUBTRACT


def test_boolean_precedence_not_comparison_and_between_separator():
    condition = parse_expression_formula(
        "IF(NOT [Age] BETWEEN 1 AND 20 AND [Flag] OR [Vehicle] = 'BMW'; 1; 0)", COLUMNS
    ).expression.operands[0]
    assert condition.operation == Op.OR
    conjunction = condition.operands[0]
    assert conjunction.operation == Op.AND
    assert conjunction.operands[0].operation == Op.NOT
    assert conjunction.operands[0].operands[0].operation == Op.BETWEEN
    assert conjunction.operands[1].operation == Op.COLUMN
    grouped = parse_expression_formula("IF(NOT ([Flag] OR [Age] > 2); 1; 0)", COLUMNS).expression.operands[0]
    assert grouped.operation == Op.NOT
    assert grouped.operands[0].operation == Op.OR


def test_if_can_participate_in_arithmetic_and_conditions():
    expression = parse_expression_formula("IF([Flag]; 1; 2) * [Age]", COLUMNS).expression
    assert expression.operation == Op.MULTIPLY
    assert expression.operands[0].operation == Op.IF
    condition = parse_expression_formula("IF(IF([Flag]; [Age]; [Limit]) > 2; 1; 0)", COLUMNS).expression.operands[0]
    assert condition.operation == Op.GREATER
    assert condition.operands[0].operation == Op.IF


def test_escaped_literals_separators_keywords_and_exact_spans():
    formula = "  IF([a]]b] IN('O''Brien', ';,) AND [Ghost]', ''); 'It''s a car'; [a]]b]) "
    expression = parse_expression_formula(formula, COLUMNS).expression
    condition, then, otherwise = expression.operands
    assert condition.operands[0].value == "a]b"
    assert [value.value for value in condition.operands[1:]] == ["O'Brien", ";,) AND [Ghost]", ""]
    assert then.value == "It's a car"
    assert otherwise.column_position == 7
    assert formula[then.start : then.end] == "'It''s a car'"
    assert formula[expression.start : expression.end] == formula.strip()
    assert expression_referenced_columns(formula) == {"a]b"}


@pytest.mark.parametrize("number", ["0", "10.", ".5", "2.5e-3", "1E+12", "-2", "+2", "-.5"])
def test_numeric_literal_spelling_and_signs(number):
    expression = parse_expression_formula(f"IF([Age] IN({number}); {number}; 0)", COLUMNS).expression
    assert expression.operands[0].operands[1].value == number
    assert expression.value_type == Type.NUMBER


@pytest.mark.parametrize(
    ("formula", "code"),
    [
        ("", "formula_empty"),
        (" \n ", "formula_empty"),
        ("IF()", "expected_expression"),
        ("IF([Flag]; 1)", "expected_token"),
        ("IF([Flag]; 1; 2; 3)", "expected_token"),
        ("IF([Flag], 1, 2)", "expected_token"),
        ("IF([Flag];; 2)", "expected_expression"),
        ("IF([Flag]; 1;)", "expected_expression"),
        ("IF [Flag]; 1; 2", "expected_token"),
        ("IF([Flag]; 1; 2", "expected_token"),
        ("IF([Age] IN(); 1; 0)", "expected_literal"),
        ("IF([Age] IN(1,); 1; 0)", "expected_literal"),
        ("IF([Age] IN(1; 2); 1; 0)", "expected_token"),
        ("IF([Age] IN(1 2); 1; 0)", "expected_token"),
        ("IF([Age] IN([Limit]); 1; 0)", "expected_literal"),
        ("IF([Age] IN(-[Limit]); 1; 0)", "expected_literal"),
        ("IF([Age] BETWEEN 1 OR 2; 1; 0)", "expected_token"),
        ("IF([Age] BETWEEN 1 AND; 1; 0)", "expected_expression"),
        ("IF([Age] NOT = 2; 1; 0)", "expected_token"),
        ("IF([Age] IS NOT; 1; 0)", "expected_token"),
        ("IF([Vehicle] = 'BMW; 1; 0)", "unclosed_string_literal"),
        ("IF([Vehicle = 'BMW'; 1; 0)", "unclosed_column_reference"),
        ("IF({Age] > 2; 1; 0)", "unsupported_character"),
        ("[] + 1", "empty_column_reference"),
        ("[Age] ^ 2", "unsupported_character"),
        ("[Age] ** 2", "expected_expression"),
        ("[Age] == 2", "unsupported_operator"),
        ("[Age] <> 2", "unsupported_operator"),
        ("[Age] +", "expected_expression"),
        ("[Age] [Limit]", "unexpected_token"),
        ("([Age] + 2", "expected_token"),
        ("[Age])", "unexpected_token"),
        ("1e999", "invalid_number_literal"),
        ("1e", "unexpected_token"),
        ("1.2.3", "unexpected_token"),
        ('"text"', "unsupported_character"),
        ("__import__('os')", "unsupported_character"),
        ("sum([Age])", "expected_expression"),
        ("IF([Missing] > 0; 1; 0)", "unknown_column"),
        ("IF([Flag]; [Age]; [Missing])", "unknown_column"),
        ("IF([Age]; 1; 0)", "invalid_operand_type"),
        ("IF('yes'; 1; 0)", "invalid_operand_type"),
        ("IF([Age] AND [Flag]; 1; 0)", "invalid_operand_type"),
        ("IF(NOT [Vehicle]; 1; 0)", "invalid_operand_type"),
        ("IF([Age] = '1'; 1; 0)", "incompatible_operand_types"),
        ("IF([Age] = [Vehicle]; 1; 0)", "incompatible_operand_types"),
        ("IF([Age] IN(1, '2'); 1; 0)", "incompatible_operand_types"),
        ("IF([Age] BETWEEN 1 AND '2'; 1; 0)", "incompatible_operand_types"),
        ("IF([Flag]; 'Empty'; [Age])", "incompatible_branch_types"),
        ("IF([Flag]; 1; IF([Flag]; 'text'; NULL))", "incompatible_branch_types"),
        ("[Vehicle] + 1", "invalid_operand_type"),
        ("-[Vehicle]", "invalid_operand_type"),
        ("IF([Flag]; TRUE; FALSE)", "invalid_result_type"),
        ("[Flag]", "invalid_result_type"),
        ("[Age] > 1", "invalid_result_type"),
        ("IF([When] = '2026-01-01'; 1; 0)", "unsupported_column_type"),
    ],
)
def test_invalid_formulas_report_same_structured_failure_in_validation_and_parse(formula, code):
    validation = validate_expression_formula(formula, COLUMNS)
    assert not validation.ok
    assert validation.error is not None
    assert validation.error.code == code
    with pytest.raises(DerivedColumnFormulaError) as caught:
        parse_expression_formula(formula, COLUMNS)
    assert caught.value.code == code
    assert caught.value.context == validation.error.context
    assert 0 <= caught.value.context["position"] <= caught.value.context["end"] <= len(formula)


def test_errors_retain_original_whitespace_positions_and_column_identity():
    formula = " \n IF([Flag]; 0; [Absent])"
    result = validate_expression_formula(formula, COLUMNS)
    assert result.error is not None
    context = result.error.context
    assert context["column"] == "Absent"
    assert formula[context["position"] : context["end"]] == "[Absent]"
    formula = "  IF([Flag]; 'unterminated"
    result = validate_expression_formula(formula, COLUMNS)
    assert result.error.context["position"] == formula.index("'")
    assert result.error.context["end"] == len(formula)


@pytest.mark.parametrize("dtype", ["Int64", "Float64", "string", "object"])
@pytest.mark.parametrize("empty", [False, True])
def test_passthrough_type_validation_uses_schema_even_when_empty_or_all_missing(dtype, empty):
    frame = pd.DataFrame({"value": pd.Series([] if empty else [None, None], dtype=dtype)})
    columns = expression_columns(list(frame.columns), list(frame.dtypes))
    numeric = dtype in {"Int64", "Float64"}
    text = validate_expression_formula("IF([value] IS NULL; 'Empty'; [value])", columns)
    number = validate_expression_formula("IF([value] IS NULL; 0; [value])", columns)
    assert text.ok is not numeric
    assert number.ok is numeric
    invalid = text if numeric else number
    assert invalid.error.code == "incompatible_branch_types"


@pytest.mark.parametrize(
    ("dtype", "value_type"),
    [
        ("Int64", Type.NUMBER),
        ("UInt64", Type.NUMBER),
        ("float64", Type.NUMBER),
        ("Float64", Type.NUMBER),
        ("bool", Type.BOOLEAN),
        ("boolean", Type.BOOLEAN),
        ("string", Type.TEXT),
        ("object", Type.TEXT),
        ("datetime64[ns]", Type.DATETIME),
        ("datetime64[s]", Type.DATETIME),
        ("datetime64[ms]", Type.DATETIME),
        ("datetime64[us]", Type.DATETIME),
        (pd.DatetimeTZDtype(tz="Europe/Stockholm"), Type.DATETIME),
        ("datetime64[ns, UTC]", Type.DATETIME),
        ("timedelta64[ns]", Type.UNSUPPORTED),
        ("complex128", Type.UNSUPPORTED),
        (pd.CategoricalDtype(["BMW", "Volvo"]), Type.TEXT),
        (pd.CategoricalDtype([1, 2]), Type.NUMBER),
        (pd.CategoricalDtype([True, False]), Type.BOOLEAN),
        (pd.CategoricalDtype(), Type.TEXT),
        (pd.CategoricalDtype(pd.to_datetime(["2026-01-01"])), Type.UNSUPPORTED),
    ],
)
def test_schema_classification(dtype, value_type):
    assert expression_columns(["value"], [dtype])[0].value_type == value_type


def test_ambiguous_names_and_nonstring_labels_are_unavailable():
    columns = expression_columns(["dup", "dup", 1, "1", "unique"], ["Int64"] * 5)
    assert [column.available for column in columns] == [False, False, False, False, True]
    for name in ("dup", "1"):
        result = validate_expression_formula(f"[{name}] + 1", columns)
        assert result.error.code == "column_not_unique"
    assert not expression_columns([1], ["Int64"])[0].available
    with pytest.raises(ValueError, match="dtype metadata"):
        expression_columns(["value"], [])


def test_parsed_expression_is_frozen():
    expression = parse_expression_formula("[Age]", COLUMNS).expression
    with pytest.raises(FrozenInstanceError):
        expression.value = "other"


@pytest.mark.parametrize(
    "formula",
    [
        "(" * 1000 + "1" + ")" * 1000,
        "NOT " * 1000 + "[Flag]",
        "-" * 1000 + "1",
        "IF([Flag]; 1; " * 1000 + "0" + ")" * 1000,
    ],
)
def test_excessive_nesting_is_a_structured_failure_not_recursion_error(formula):
    result = validate_expression_formula(formula, COLUMNS)
    assert result.error.code == "expression_nesting_limit"
    assert result.error.context["limit"] > 0


def test_long_flat_expression_and_regular_nesting_parse_successfully():
    expression = parse_expression_formula(" + ".join(["[Age]"] * 2000), COLUMNS).expression
    assert expression.operation == Op.ADD
    assert parse_expression_formula("(" * 20 + "[Age]" + ")" * 20, COLUMNS).expression.value_type == Type.NUMBER


def test_reference_extraction_decodes_without_treating_quoted_text_as_columns():
    formula = "IF([a]]b] = '[Ghost]'; [Age]; IF([Age] > [Limit]; NULL; [Age]))"
    assert expression_referenced_columns(formula) == {"a]b", "Age", "Limit"}
    with pytest.raises(DerivedColumnFormulaError, match="formula_empty"):
        expression_referenced_columns(" \n ")


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("IF([Age] NOT BETWEEN 0 AND 20; 1; 0)", Op.NOT_BETWEEN),
        ("IF([Vehicle] NOT IN('BMW'); 1; 0)", Op.NOT_IN),
        ("IF([Age] IS NOT NULL; 1; 0)", Op.IS_NOT_NULL),
        ("IF([Age] BETWEEN 0 AND 20; 1; 0)", Op.BETWEEN),
        ("IF([Vehicle] IN('BMW'); 1; 0)", Op.IN),
        ("IF([Age] IS NULL; 1; 0)", Op.IS_NULL),
    ],
)
def test_compound_operators_retain_evaluation_identity(formula, expected):
    assert parse_expression_formula(formula, COLUMNS).expression.operands[0].operation == expected


def test_unknown_columns_fail_even_in_a_constant_unselected_branch():
    result = validate_expression_formula("IF(TRUE; 'selected'; [Absent])", COLUMNS)
    assert result.error.code == "unknown_column"
    result = validate_expression_formula("IF(TRUE; 'selected'; [Age])", COLUMNS)
    assert result.error.code == "incompatible_branch_types"


def test_exact_whitespace_and_keyword_column_names_are_distinct():
    parsed = parse_expression_formula("IF([IF] > 1; [ spaced ]; NULL)", COLUMNS)
    assert parsed.expression.operands[1].value == " spaced "
    assert parsed.referenced_columns == (" spaced ", "IF")
    assert validate_expression_formula("[spaced]", COLUMNS).error.code == "unknown_column"


def test_parenthesized_operand_spans_include_their_closing_delimiters():
    formula = " ([Age] + (2 * 3)) "
    expression = parse_expression_formula(formula, COLUMNS).expression
    assert formula[expression.start : expression.end] == formula.strip()
    right = expression.operands[1]
    assert formula[right.start : right.end] == "(2 * 3)"
    formula = "IF(([Age] > 1 OR [Flag]); ([Age] + 1); (0))"
    expression = parse_expression_formula(formula, COLUMNS).expression
    assert [formula[operand.start : operand.end] for operand in expression.operands] == [
        "([Age] > 1 OR [Flag])",
        "([Age] + 1)",
        "(0)",
    ]
