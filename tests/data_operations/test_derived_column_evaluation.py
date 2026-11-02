"""Conditional creation, three-valued logic, and positional preview parity."""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from expo_jbm329.services.data_operations.derived_column.derived_column_evaluation import evaluate_expression
from expo_jbm329.services.data_operations.derived_column.derived_column_expression import (
    expression_columns,
    parse_expression_formula,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_parser import DerivedColumnFormulaError
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnError,
    DerivedColumnSpec,
    create_derived_column,
    preview_derived_column,
    validate_derived_column_spec,
)


def create(source, formula, **kwargs):
    return create_derived_column(source, DerivedColumnSpec("Result", formula, **kwargs))["Result"]


def test_requested_age_groups_with_inclusive_boundaries_gaps_and_missing():
    source = pd.DataFrame({"Age": pd.Series([-1, 0, 20, 20.5, 21, 40, 41, None], dtype="Float64")})
    formula = "IF([Age] BETWEEN 0 AND 20; 'Youth'; IF([Age] BETWEEN 21 AND 40; 'Midlife'; 'Oldies'))"
    assert_series_equal(
        create(source, formula),
        pd.Series(
            ["Oldies", "Youth", "Youth", "Oldies", "Midlife", "Midlife", "Oldies", "Oldies"],
            dtype="string",
            name="Result",
        ),
    )


@pytest.mark.parametrize("dtype", ["string", "object", "category"])
def test_requested_vehicle_groups_on_text_only_source(dtype):
    source = pd.DataFrame({"Vehicle": pd.Series(["BMW", "Volvo", "Ford", None, ""], dtype=dtype)})
    original = source.copy(deep=True)
    formula = "IF([Vehicle] IN('BMW', 'Volvo'); 'Cars'; 'Other')"
    assert validate_derived_column_spec(source, DerivedColumnSpec("Result", formula)).ok
    assert_series_equal(
        create(source, formula),
        pd.Series(["Cars", "Cars", "Other", "Other", "Other"], dtype="string", name="Result"),
    )
    assert_frame_equal(source, original)


@pytest.mark.parametrize("dtype", ["string", "object", "category"])
@pytest.mark.parametrize("values", [["a", None, "", "O'Brien"], [None, None], []])
def test_text_null_replacement_preserves_nonmissing_values_and_source(dtype, values):
    source = pd.DataFrame({"Column1": pd.Series(values, dtype=dtype)})
    if dtype == "category":
        source["Column1"] = source["Column1"].cat.set_categories(["a", "", "O'Brien"])
    source.index = pd.Index([7] * len(source), name="row")
    original = source.copy(deep=True)
    result = create(source, "IF([Column1] IS NULL; 'Empty'; [Column1])")
    assert_series_equal(
        result,
        pd.Series(
            ["Empty" if value is None else value for value in values], index=source.index, dtype="string", name="Result"
        ),
    )
    assert_frame_equal(source, original)


@pytest.mark.parametrize("dtype", ["Int64", "Float64", "float64", "category"])
@pytest.mark.parametrize("values", [[18, None, 0, -2], [None, None], []])
def test_numeric_null_replacement_is_nullable_float_with_original_index(dtype, values):
    source = pd.DataFrame({"Age": pd.Series(values, dtype=dtype)})
    source.index = pd.Index([8] * len(source), name="row")
    # An untyped empty/all-null category has no numeric schema.
    if dtype == "category":
        source["Age"] = source["Age"].cat.set_categories([18, 0, -2])
    assert_series_equal(
        create(source, "IF([Age] IS NULL; 0; [Age])"),
        pd.Series(
            [0 if value is None else value for value in values], index=source.index, dtype="Float64", name="Result"
        ),
    )


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ("[Age] = 2", [0, 1, 0, 0]),
        ("[Age] != 2", [1, 0, 1, 0]),
        ("[Age] < 2", [1, 0, 0, 0]),
        ("[Age] <= 2", [1, 1, 0, 0]),
        ("[Age] > 2", [0, 0, 1, 0]),
        ("[Age] >= 2", [0, 1, 1, 0]),
        ("[Age] BETWEEN 1 AND 2", [1, 1, 0, 0]),
        ("[Age] NOT BETWEEN 1 AND 2", [0, 0, 1, 0]),
        ("[Age] IN(1,3)", [1, 0, 1, 0]),
        ("[Age] NOT IN(1,3)", [0, 1, 0, 0]),
        ("[Age] IS NULL", [0, 0, 0, 1]),
        ("[Age] IS NOT NULL", [1, 1, 1, 0]),
        ("NOT [Age] = 2", [1, 0, 1, 0]),
        ("NOT ([Age] != 2)", [0, 1, 0, 0]),
        ("[Age] + 1 > [Limit]", [0, 1, 0, 0]),
        ("[Age] BETWEEN [Limit]-1 AND [Limit]+1", [1, 1, 0, 0]),
    ],
)
def test_each_numeric_predicate_and_column_arithmetic(condition, expected):
    source = pd.DataFrame({"Age": pd.Series([1, 2, 3, None], dtype="Int64"), "Limit": [2, 2, 5, 1]})
    source.index = [2, 1, 1, 0]
    assert_series_equal(
        create(source, f"IF({condition}; 1; 0)"),
        pd.Series(expected, index=source.index, dtype="Float64", name="Result"),
    )


@pytest.mark.parametrize("left", [True, False, None])
@pytest.mark.parametrize("right", [True, False, None])
@pytest.mark.parametrize("operator", ["AND", "OR"])
def test_complete_nullable_boolean_truth_tables(left, right, operator):
    source = pd.DataFrame({
        "Left": pd.Series([left], dtype="boolean"),
        "Right": pd.Series([right], dtype="boolean"),
    })
    expected = source.Left & source.Right if operator == "AND" else source.Left | source.Right
    # NOT distinguishes preserved unknown from a premature false conversion.
    for negate in (False, True):
        condition = f"[Left] {operator} [Right]"
        wanted = ~expected if negate else expected
        if negate:
            condition = f"NOT ({condition})"
        result = create(source, f"IF({condition}; 1; 0)")
        assert result.iloc[0] == int(wanted.fillna(False).iloc[0])


@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        ("[Vehicle] = [Other]", [1, 0, 0, 0]),
        ("[Vehicle] != 'BMW'", [0, 1, 1, 0]),
        ("[Vehicle] NOT IN('BMW', 'Volvo')", [0, 0, 1, 0]),
        ("NOT [Vehicle] IN('BMW', NULL)", [0, 0, 0, 0]),
        ("[Vehicle] IN('BMW', NULL)", [1, 0, 0, 0]),
    ],
)
def test_text_comparisons_and_missing_membership_candidates(predicate, expected):
    source = pd.DataFrame({
        "Vehicle": pd.Series(["BMW", "Volvo", "Ford", None], dtype="string"),
        "Other": pd.Series(["BMW", None, "Saab", None], dtype="string"),
    })
    assert_series_equal(create(source, f"IF({predicate}; 1; 0)"), pd.Series(expected, dtype="Float64", name="Result"))


@pytest.mark.parametrize(
    ("formula", "expected", "dtype"),
    [
        ("IF([Age] > 1; [Age]*2; [Age]+1)", [2, 4, None], "Float64"),
        ("IF([Age] > 1; NULL; [Age])", [1, None, None], "Float64"),
        ("IF([Age] > 1; 'yes'; NULL)", [None, "yes", None], "string"),
        ("IF([Age] > 1; NULL; NULL)", [None, None, None], "Float64"),
        ("IF([Age] > 1; IF([Age] < 3; 'two'; 'large'); 'other')", ["other", "two", "other"], "string"),
        ("IF([Age] > 1; 1/0; 2)", [2, None, 2], "Float64"),
        ("IF([Age] > 1; -[Age]; +[Age])", [1, -2, None], "Float64"),
        ("IF([Age] > 1; 2; 3)+1", [4, 3, 4], "Float64"),
    ],
)
def test_nested_results_nulls_arithmetic_and_division(formula, expected, dtype):
    source = pd.DataFrame({"Age": pd.Series([1, 2, None], dtype="Int64")})
    assert_series_equal(create(source, formula), pd.Series(expected, dtype=dtype, name="Result"))


def test_if_only_evaluates_selected_rows_in_each_branch():
    source = pd.DataFrame({
        "Flag": pd.Series([True, False], dtype="boolean"),
        "Text": pd.Series(["valid", 123], dtype=object),
    })
    result = create(source, "IF([Flag]; [Text]; 'other')")
    assert result.tolist() == ["valid", "other"]
    with pytest.raises(DerivedColumnFormulaError, match="non_text_column"):
        create(source, "IF([Flag]; 'other'; [Text])")


@pytest.mark.parametrize("values", [[1, "1"], [True, "True"], [["nested"], "text"]])
def test_nontext_objects_fail_instead_of_silent_stringification(values):
    source = pd.DataFrame({"Text": pd.Series(values, dtype=object)})
    with pytest.raises(DerivedColumnFormulaError, match="non_text_column"):
        create(source, "IF([Text] IS NULL; 'Empty'; [Text])")


@pytest.mark.parametrize("dtype", ["Int64", "Float64"])
@pytest.mark.parametrize("values", [[], [None, None], [1, 2]])
def test_mixed_branches_are_rejected_by_both_validation_and_creation(dtype, values):
    source = pd.DataFrame({"Age": pd.Series(values, dtype=dtype)})
    spec = DerivedColumnSpec("Result", "IF([Age] IS NULL; 'Empty'; [Age])")
    validation = validate_derived_column_spec(source, spec)
    assert validation.error.code == "incompatible_branch_types"
    with pytest.raises(DerivedColumnFormulaError, match="incompatible_branch_types"):
        create_derived_column(source, spec)


def test_explicit_numeric_output_is_preserved_and_text_conversion_rejected():
    source = pd.DataFrame({"Age": pd.Series([1, None], dtype="Int64")})
    assert str(create(source, "IF([Age] IS NULL; 0; [Age])", output_dtype="Float64").dtype) == "Float64"
    spec = DerivedColumnSpec("Result", "IF([Age] IS NULL; 'Empty'; 'Present')", output_dtype="Float64")
    assert validate_derived_column_spec(source, spec).error.code == "result_conversion_failed"
    with pytest.raises(DerivedColumnError, match="result_conversion_failed"):
        create_derived_column(source, spec)


@pytest.mark.parametrize("replace", [True, False])
def test_infinity_policy_applies_to_conditional_numeric_output(replace):
    source = pd.DataFrame({"Age": pd.Series([1, None], dtype="Float64")})
    result = create(source, "IF([Age] IS NULL; 0; [Age]/0)", replace_inf_with_na=replace)
    assert pd.isna(result.iloc[0]) if replace else result.iloc[0] == float("inf")
    assert result.iloc[1] == 0


@pytest.mark.parametrize(
    ("formula", "columns"),
    [
        ("IF([Age] IS NULL; 0; [Age])", ["Age", "Result"]),
        ("IF([Text] IS NULL; 'Empty'; [Text])", ["Text", "Result"]),
        ("IF([Age] > 1; IF([Age] < 3; [Text]; 'large'); NULL)", ["Age", "Text", "Result"]),
    ],
)
def test_preview_matches_full_creation_with_duplicate_and_nondefault_indexes(formula, columns):
    source = pd.DataFrame({
        "Age": pd.Series([1, None, 2, 4], dtype="Int64"),
        "Text": pd.Series(["a", None, "c", ""], dtype="string"),
    })
    source.index = pd.Index([8, 3, 3, 0], name="rows")
    original = source.copy(deep=True)
    spec = DerivedColumnSpec("Result", formula)
    full = create_derived_column(source, spec)
    preview = preview_derived_column(source, spec, rows=3)
    assert preview.ok
    assert_frame_equal(preview.data, full.loc[:, columns].head(3))
    assert_frame_equal(source, original)


def test_empty_preview_has_schema_derived_dtype():
    source = pd.DataFrame({"Text": pd.Series([], dtype="string")})
    preview = preview_derived_column(source, DerivedColumnSpec("Result", "IF([Text] IS NULL; 'Empty'; [Text])"))
    assert preview.ok
    assert preview.data.empty
    assert isinstance(preview.data["Result"].dtype, pd.StringDtype)


def test_overwrite_uses_original_source_and_does_not_mutate_input():
    source = pd.DataFrame({"Text": pd.Series(["x", None], dtype="string")}, index=[0, 1])
    original = source.copy(deep=True)
    spec = DerivedColumnSpec("Text", "IF([Text] IS NULL; 'Empty'; [Text])", overwrite_existing=True)
    result = create_derived_column(source, spec)
    assert result.Text.tolist() == ["x", "Empty"]
    assert_frame_equal(source, original)
    with pytest.raises(DerivedColumnError, match="output_column_exists"):
        create_derived_column(source, DerivedColumnSpec("Text", spec.formula))


def test_preview_reports_failure_code_and_logs_instead_of_success_shaped_result(caplog):
    source = pd.DataFrame({"Age": [1]})
    result = preview_derived_column(source, DerivedColumnSpec("Result", "IF(TRUE; 'x'; [Age])"))
    assert not result.ok
    assert result.data is None
    assert result.message == "incompatible_branch_types"
    assert "incompatible_branch_types" in caplog.text


def test_flat_expression_evaluation_does_not_recurse():
    source = pd.DataFrame({"Age": pd.Series([1, None], dtype="Int64")})
    formula = "IF([Age] IS NULL; 0; " + "+".join(["[Age]"] * 2000) + ")"
    result = create(source, formula)
    assert result.tolist() == [2000, 0]


@pytest.mark.parametrize("categorical", [False, True])
def test_large_integer_comparisons_are_not_rounded_to_float(categorical):
    source = pd.DataFrame({"Age": pd.Series([2**60, 2**60 + 1, None], dtype="UInt64")})
    if categorical:
        source["Age"] = source["Age"].astype("category")
    assert create(source, f"IF([Age] = {2**60 + 1}; 1; 0)").tolist() == [0, 1, 0]


def test_datetime_null_tests_do_not_require_text_conversion():
    source = pd.DataFrame({"When": pd.to_datetime(["2026-01-01", None])})
    assert create(source, "IF([When] IS NULL; 'Empty'; 'Present')").tolist() == ["Present", "Empty"]


def test_direct_evaluation_returns_original_multiindex():
    source = pd.DataFrame({"Age": pd.Series([1, None, 2], dtype="Int64")})
    source.index = pd.MultiIndex.from_tuples([("a", 1), ("a", 1), ("b", 0)], names=["group", "row"])
    parsed = parse_expression_formula(
        "IF([Age] IS NULL; 0; [Age])", expression_columns(list(source.columns), list(source.dtypes))
    )
    assert_series_equal(
        evaluate_expression(source, parsed.expression),
        pd.Series([1, 0, 2], dtype="Float64", index=source.index),
    )


@pytest.mark.parametrize("operator", ["=", "!=", "<", "<=", ">", ">="])
@pytest.mark.parametrize("reverse", [False, True])
def test_text_compared_to_null_is_unknown_even_under_not(operator, reverse):
    source = pd.DataFrame({"Text": pd.Series(["a", None], dtype="string")})
    condition = f"NULL {operator} [Text]" if reverse else f"[Text] {operator} NULL"
    assert create(source, f"IF(NOT ({condition}); 1; 0)").tolist() == [0, 0]


def test_between_with_null_bound_preserves_false_and_unknown():
    source = pd.DataFrame({"Text": pd.Series(["a", "z", None], dtype="string")})
    # Unknown AND false is false; negation therefore selects the row above 'm'.
    assert create(source, "IF(NOT ([Text] BETWEEN NULL AND 'm'); 1; 0)").tolist() == [0, 1, 0]


def test_sibling_nested_conditionals_keep_selection_stacks_independent():
    source = pd.DataFrame({
        "Age": pd.Series([1, 2, None, 4], dtype="Int64"),
        "Flag": pd.Series([True, False, None, True], dtype="boolean"),
    })
    formula = "IF([Age] < 3; IF([Flag]; [Age]; [Age]+1); IF([Age] IS NULL; 0; [Age]*2)) + IF([Flag]; 10; 20)"
    assert create(source, formula).tolist() == [11, 23, 20, 18]


def test_escaped_column_names_and_strings_are_evaluated_not_reparsed():
    source = pd.DataFrame({"a]b": pd.Series(["O'Brien", None, "[];()"], dtype="string")})
    assert create(source, "IF([a]]b] = 'O''Brien'; 'It''s a match'; [a]]b])").tolist() == [
        "It's a match",
        pd.NA,
        "[];()",
    ]


@pytest.mark.parametrize("formula", ["[Age]+1", "IF([Age] IS NULL; 0; [Age])"])
def test_ambiguous_source_columns_are_rejected_before_evaluation(formula):
    source = pd.DataFrame([[1, 2]], columns=["Age", "Age"])
    spec = DerivedColumnSpec("Result", formula)
    assert validate_derived_column_spec(source, spec).error.code == "column_not_unique"
    with pytest.raises(DerivedColumnFormulaError, match="column_not_unique"):
        create_derived_column(source, spec)


@pytest.mark.parametrize("formula", ["IF(TRUE; 'ok'; [Missing])", "IF(TRUE; 'ok'; 1)"])
def test_creation_checks_unselected_branch_schema_before_lazy_evaluation(formula):
    source = pd.DataFrame({"Age": [1]})
    spec = DerivedColumnSpec("Result", formula)
    validation = validate_derived_column_spec(source, spec)
    assert not validation.ok
    with pytest.raises(DerivedColumnFormulaError) as caught:
        create_derived_column(source, spec)
    assert caught.value.code == validation.error.code
