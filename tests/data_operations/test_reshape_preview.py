"""Real full-data aggregation, conditional masks and bounded preview semantics."""

import pandas as pd
import pytest

from expo_jbm329.services.data_operations.reshape_condition_lint import parse_condition
from expo_jbm329.services.data_operations.reshape_conditions import condition_columns
from expo_jbm329.services.data_operations.reshape_preview import (
    ReshapeError,
    ReshapeFunction,
    ReshapeMetric,
    ReshapeProblem,
    ReshapeRequest,
    compute_reshape_preview,
    evaluate_condition,
)


def program(frame, text):
    parsed = parse_condition(text, condition_columns(list(frame.columns), list(frame.dtypes)))
    assert not parsed.diagnostics
    return parsed.instructions


def metric(frame, function, condition="", position=1, name=None):
    return ReshapeMetric(name or function, ReshapeFunction(function), position, program(frame, condition))


def test_all_functions_conditional_metrics_and_no_match_groups():
    source = pd.DataFrame({
        "clinic": ["B", "A", "B", "A", None],
        "value": pd.Series([10, 20, None, 40, 5], dtype="Int64"),
        "adult": pd.Series([False, True, True, True, None], dtype="boolean"),
    })
    original = source.copy(deep=True)
    metrics = tuple(metric(source, function, "[adult] = True") for function in ReshapeFunction)
    request = ReshapeRequest((0,), metrics)
    result = compute_reshape_preview(source, request)
    assert result.total_rows == 3
    assert result.request is request
    assert result.frame["clinic"].tolist()[:2] == ["B", "A"]
    assert pd.isna(result.frame["clinic"].iloc[2])
    assert result.frame["COUNT"].tolist() == [0, 2, 0]
    assert result.frame["COUNT DISTINCT"].tolist() == [0, 2, 0]
    for name, expected in [("SUM", 60), ("AVG", 30), ("MIN", 20), ("MAX", 40)]:
        assert result.frame[name].iloc[1] == expected
        assert pd.isna(result.frame[name].iloc[0])
        assert pd.isna(result.frame[name].iloc[2])
    pd.testing.assert_frame_equal(source, original)


def test_five_rows_are_full_data_aggregates_not_five_input_rows():
    source = pd.DataFrame({"group": list("gfedcba") * 10, "value": range(70)})
    result = compute_reshape_preview(source, ReshapeRequest((0,), (metric(source, "SUM"),)))
    assert result.total_rows == 7
    assert result.frame["group"].tolist() == list("gfedc")
    assert result.frame["SUM"].tolist() == [sum(range(offset, 70, 7)) for offset in range(5)]


def test_no_dimensions_empty_source_and_all_missing_values():
    source = pd.DataFrame({"value": pd.Series([], dtype="Int64")})
    metrics = tuple(metric(source, function, position=0) for function in ReshapeFunction)
    result = compute_reshape_preview(source, ReshapeRequest((), metrics))
    assert result.total_rows == 1
    assert result.frame["COUNT"].tolist() == [0]
    assert result.frame["COUNT DISTINCT"].tolist() == [0]
    assert pd.isna(result.frame["SUM"].iloc[0])
    empty_groups = compute_reshape_preview(source, ReshapeRequest((0,), metrics))
    assert empty_groups.total_rows == 0
    assert list(empty_groups.frame.columns) == ["value", *ReshapeFunction]
    assert empty_groups.frame.empty


def test_multiple_dimensions_categories_missing_values_and_duplicate_index():
    source = pd.DataFrame(
        {
            "category": pd.Categorical(["B", None, "A", "B", None], categories=["unused", "A", "B"]),
            "key": ["x", "x", None, "x", "x"],
            "value": [1, 2, 3, 4, 5],
        },
        index=[1, 1, 1, 0, 0],
    )
    result = compute_reshape_preview(source, ReshapeRequest((0, 1), (metric(source, "SUM", position=2),)))
    assert result.total_rows == 3
    assert result.frame["SUM"].tolist() == [5, 7, 3]
    assert result.frame["category"].dtype == source["category"].dtype
    assert pd.isna(result.frame["key"].iloc[2])


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ("[x] = 2", [False, True, False, False]),
        ("[x] != 2", [True, False, True, False]),
        ("[x] > 2", [False, False, True, False]),
        ("[x] >= 2", [False, True, True, False]),
        ("[x] < 2", [True, False, False, False]),
        ("[x] <= 2", [True, True, False, False]),
        ("[x] IN (1, 3)", [True, False, True, False]),
        ("[x] NOT IN (1, 3)", [False, True, False, False]),
        ("[x] IS NULL", [False, False, False, True]),
        ("[x] IS NOT NULL", [True, True, True, False]),
        ("[x] = 1 OR [x] = 2 AND [flag] = True", [True, False, False, False]),
        ("([x] = 1 OR [x] = 2) AND [flag] = True", [False, False, False, False]),
        ("[x] = 3 AND ([flag] = True OR [flag] IS NULL)", [False, False, True, False]),
    ],
)
def test_comparisons_membership_precedence_and_missing_semantics(condition, expected):
    frame = pd.DataFrame({
        "x": pd.Series([1, 2, 3, None], dtype="Int64"),
        "flag": pd.Series([False, False, True, None], dtype="boolean"),
    })
    frame.index = [0, 0, 0, 0]
    assert evaluate_condition(frame, program(frame, condition)).tolist() == expected


def test_quoted_text_and_escaped_column_names_are_not_reinterpreted():
    frame = pd.DataFrame({"a]b": ["O'Brien", "0018", "True", None]})
    assert evaluate_condition(frame, program(frame, "[a]]b] IN ('O''Brien', '0018')")).tolist() == [
        True,
        True,
        False,
        False,
    ]


def test_datetime_min_max_and_timezone_literal_conversion():
    source = pd.DataFrame({
        "group": ["a", "a", "b"],
        "date": pd.to_datetime(["2026-01-01", "2026-02-01", None], utc=True),
    })
    result = compute_reshape_preview(
        source,
        ReshapeRequest(
            (0,),
            (
                metric(source, "MIN", "[date] >= '2026-01-01'"),
                metric(source, "MAX", "[date] < '2026-03-01T00:00:00+00:00'"),
            ),
        ),
    )
    assert result.frame["MIN"].iloc[0] == pd.Timestamp("2026-01-01", tz="UTC")
    assert result.frame["MAX"].iloc[0] == pd.Timestamp("2026-02-01", tz="UTC")
    assert str(result.frame["MIN"].dtype) == str(source["date"].dtype)
    assert pd.isna(result.frame["MAX"].iloc[1])
    for text in ["'not a date'", "'NaT'"]:
        with pytest.raises(ReshapeError) as caught:
            evaluate_condition(source, program(source, f"[date] > {text}"))
        assert caught.value.problem == ReshapeProblem.VALUE


def test_aware_literal_against_naive_column_fails_explicitly():
    source = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"])})
    with pytest.raises(ReshapeError) as caught:
        evaluate_condition(source, program(source, "[date] > '2026-01-01T00:00:00Z'"))
    assert caught.value.problem == ReshapeProblem.VALUE


def test_uncomparable_objects_and_unhashable_dimensions_fail_explicitly():
    source = pd.DataFrame({"key": [[1], [2]], "value": [1, 2]})
    with pytest.raises(ReshapeError) as caught:
        compute_reshape_preview(source, ReshapeRequest((0,), (metric(source, "SUM"),)))
    assert caught.value.problem == ReshapeProblem.DATA
    with pytest.raises(ReshapeError):
        evaluate_condition(source, program(source, "[key] > 'text'"))


def test_configuration_validation_names_positions_and_function_dtypes():
    source = pd.DataFrame({"key": ["a"], "value": [1]})
    requests = [
        ReshapeRequest((), ()),
        ReshapeRequest((0, 0), (metric(source, "SUM"),)),
        ReshapeRequest((5,), (metric(source, "SUM"),)),
        ReshapeRequest((0,), (metric(source, "SUM", name="key"),)),
        ReshapeRequest((), (metric(source, "SUM", position=0),)),
        ReshapeRequest((), (metric(source, "SUM", position=9),)),
        ReshapeRequest((), (metric(source, "SUM", name=" "),)),
    ]
    for request in requests:
        with pytest.raises(ReshapeError):
            compute_reshape_preview(source, request)


def test_progress_and_cooperative_cancellation_without_source_mutation():
    source = pd.DataFrame({"key": ["a"] * 50, "value": range(50)})
    request = ReshapeRequest((0,), (metric(source, "SUM"), metric(source, "COUNT")))
    progress = []
    result = compute_reshape_preview(source, request, progress_cb=progress.append)
    assert result.frame["SUM"].iloc[0] == 1225
    assert progress == [0, 10, 55, 100]
    progress.clear()
    assert (
        compute_reshape_preview(
            source, request, progress_cb=progress.append, cancel_cb=lambda: bool(progress and progress[-1] >= 55)
        )
        is None
    )


def test_deep_conditions_parse_and_evaluate_iteratively():
    source = pd.DataFrame({"value": [1, 2]})
    expression = "(" * 2000 + "[value] > 1" + ")" * 2000
    assert evaluate_condition(source, program(source, expression)).tolist() == [False, True]


@pytest.mark.parametrize("dtype", ["object", "category"])
def test_quoted_scalar_values_match_picker_serialization_without_source_coercion(dtype):
    source = pd.DataFrame({"key": pd.Series([1, 2, None], dtype=dtype)})
    original = source.copy(deep=True)
    assert evaluate_condition(source, program(source, "[key] IN ('1', '2')")).tolist() == [True, True, False]
    pd.testing.assert_frame_equal(source, original)


def test_ambiguous_mixed_object_values_fail_instead_of_matching_wrong_scalar():
    source = pd.DataFrame({"key": pd.Series([1, "1"], dtype=object)})
    with pytest.raises(ReshapeError) as caught:
        evaluate_condition(source, program(source, "[key] = '1'"))
    assert caught.value.problem == ReshapeProblem.DATA


def test_boolean_numeric_object_mix_does_not_silently_match_equal_python_values():
    source = pd.DataFrame({"key": pd.Series([1, True], dtype=object)})
    with pytest.raises(ReshapeError) as caught:
        evaluate_condition(source, program(source, "[key] = 'True'"))
    assert caught.value.problem == ReshapeProblem.DATA


def test_different_metric_filters_do_not_change_each_other_or_the_group_universe():
    source = pd.DataFrame({"clinic": ["A", "B", "A"], "value": [10, 20, 30]})
    result = compute_reshape_preview(
        source,
        ReshapeRequest(
            (0,),
            (
                metric(source, "COUNT", name="Total"),
                metric(source, "COUNT", "[value] > 25", name="Above"),
            ),
        ),
    )
    assert result.frame["clinic"].tolist() == ["A", "B"]
    assert result.frame["Total"].tolist() == [2, 1]
    assert result.frame["Above"].tolist() == [1, 0]


def test_all_missing_values_and_integer_precision_are_preserved():
    source = pd.DataFrame({"key": ["A", "B"], "value": pd.Series([None, 2**60 + 1], dtype="UInt64")})
    result = compute_reshape_preview(
        source,
        ReshapeRequest(
            (0,),
            (
                metric(source, "SUM"),
                metric(source, "COUNT"),
                metric(source, "COUNT DISTINCT"),
            ),
        ),
    )
    assert pd.isna(result.frame["SUM"].iloc[0])
    assert result.frame["SUM"].iloc[1] == 2**60 + 1
    assert str(result.frame["SUM"].dtype) == "UInt64"
    assert result.frame["COUNT"].tolist() == [0, 1]
    assert evaluate_condition(source, program(source, f"[value] = {2**60 + 1}")).tolist() == [False, True]


@pytest.mark.parametrize("literal", ["2026-03-29T02:30:00", "2026-10-25T02:30:00"])
def test_dst_nonexistent_and_ambiguous_literals_are_explicit_errors(literal):
    source = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=1, tz="Europe/Stockholm")})
    with pytest.raises(ReshapeError) as caught:
        evaluate_condition(source, program(source, f"[date] > '{literal}'"))
    assert caught.value.problem == ReshapeProblem.VALUE
