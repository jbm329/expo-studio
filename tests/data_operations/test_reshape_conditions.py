"""Condition syntax and distinct-page behavior without GUI dependencies."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.data_operations.reshape_condition_values import (
    ValuePageRequest,
    ValueRequestCancelledError,
    distinct_value_page,
)
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionColumn,
    ConditionError,
    ConditionGroup,
    ConditionMatch,
    ConditionOperator,
    ConditionProblem,
    ConditionRule,
    ConditionValue,
    condition_columns,
    condition_value,
    format_condition,
)


@pytest.mark.parametrize("operator", list(ConditionOperator))
def test_operator_syntax(operator: ConditionOperator) -> None:
    values = () if operator.is_null_test else (ConditionValue("string", "O'Brien"),)
    group = ConditionGroup((ConditionRule(ConditionColumn(0, "a]b", True), operator, values),))
    suffix = "" if operator.is_null_test else " ('O''Brien')" if operator.is_membership else " 'O''Brien'"
    assert format_condition(group) == f"[a]]b] {operator.value}{suffix}"


@pytest.mark.parametrize("match", list(ConditionMatch))
def test_group_connector(match: ConditionMatch) -> None:
    first = ConditionRule(ConditionColumn(0, "", True), ConditionOperator.EQUAL, (ConditionValue("string", ""),))
    second = ConditionRule(ConditionColumn(1, "Age", True), ConditionOperator.IS_NULL)
    assert format_condition(ConditionGroup((first, second), match)) == f"([] = '' {match.value} [Age] IS NULL)"


def test_serialized_column_collisions_disable_every_ambiguous_position() -> None:
    assert condition_columns([1, "1", "ok", "ok", "unique"]) == (
        ConditionColumn(0, "1", False),
        ConditionColumn(1, "1", False),
        ConditionColumn(2, "ok", False),
        ConditionColumn(3, "ok", False),
        ConditionColumn(4, "unique", True),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ConditionValue("string", "")),
        (np.int64(1), ConditionValue("integer", "1")),
        (np.float64(1.25), ConditionValue("float", "1.25")),
        (np.bool_(True), ConditionValue("boolean", "True")),
        (Decimal("1.20"), ConditionValue("decimal", "1.20")),
        (dt.date(2025, 1, 2), ConditionValue("date", "2025-01-02")),
        (
            pd.Timestamp("2025-01-02T03:04:05.123456789+01:00"),
            ConditionValue("datetime", "2025-01-02T03:04:05.123456789+01:00"),
        ),
        (np.datetime64("2025-01-02"), ConditionValue("datetime", "2025-01-02T00:00:00")),
    ],
)
def test_scalar_tokens(raw: object, expected: ConditionValue) -> None:
    assert condition_value(raw) == expected


@pytest.mark.parametrize("raw", [None, pd.NA, pd.NaT, float("nan"), np.datetime64("NaT"), Decimal("NaN")])
def test_missing_values(raw: object) -> None:
    assert condition_value(raw) is None


@pytest.mark.parametrize("raw", [[1], {"a": 1}, (1,), b"text", 1j, float("inf"), Decimal("Infinity"), dt.timedelta(1)])
def test_unsupported_values_are_explicit(raw: object) -> None:
    with pytest.raises(ConditionError) as exc:
        condition_value(raw)
    assert exc.value.problem == ConditionProblem.UNSUPPORTED_VALUE


@pytest.mark.parametrize(
    ("operator", "values"),
    [
        (ConditionOperator.IN, ()),
        (ConditionOperator.EQUAL, ()),
        (ConditionOperator.IS_NULL, (ConditionValue("string", "x"),)),
        (ConditionOperator.EQUAL, (ConditionValue("string", "x"), ConditionValue("string", "y"))),
        (ConditionOperator.IN, (ConditionValue("string", "x"), ConditionValue("string", "x"))),
    ],
)
def test_invalid_rule_arity(operator: ConditionOperator, values: tuple[ConditionValue, ...]) -> None:
    with pytest.raises(ConditionError):
        format_condition(ConditionGroup((ConditionRule(ConditionColumn(0, "a", True), operator, values),)))


def test_empty_and_unavailable_rules_and_ambiguous_values() -> None:
    with pytest.raises(ConditionError):
        format_condition(ConditionGroup(()))
    with pytest.raises(ConditionError):
        format_condition(ConditionGroup((ConditionRule(ConditionColumn(0, "a", False), ConditionOperator.IS_NULL),)))
    rule = ConditionRule(
        ConditionColumn(0, "a", True),
        ConditionOperator.IN,
        (ConditionValue("integer", "1"), ConditionValue("string", "1")),
    )
    with pytest.raises(ConditionError) as exc:
        format_condition(ConditionGroup((rule,)))
    assert exc.value.problem == ConditionProblem.AMBIGUOUS_VALUE


@pytest.mark.parametrize("size", [0, 1, 99, 100, 101, 200, 201])
def test_page_boundaries_and_no_mutation(size: int) -> None:
    source = pd.DataFrame({"a": range(size)})
    original = source.copy(deep=True)
    for page in range(3):
        result = distinct_value_page(source, ValuePageRequest(0, page=page))
        expected = tuple(ConditionValue("integer", str(i)) for i in range(page * 100, min(size, (page + 1) * 100)))
        assert result.entries == expected
        assert result.has_next == (size > (page + 1) * 100)
    pd.testing.assert_frame_equal(source, original)


def test_search_across_chunks_is_literal_case_insensitive_and_preserves_order() -> None:
    source = pd.DataFrame({"a": ["repeat"] * 2050 + ["a[B", "A[b", "tail", "a[B"]})
    result = distinct_value_page(source, ValuePageRequest(0, "[b"))
    assert result.entries == (ConditionValue("string", "a[B"), ConditionValue("string", "A[b"))
    assert not result.has_next


def test_null_empty_and_duplicate_values() -> None:
    source = pd.DataFrame({"a": [None, "", pd.NA, "", "x", float("nan"), "x"]})
    assert distinct_value_page(source, ValuePageRequest(0)).entries == (
        ConditionValue("string", ""),
        ConditionValue("string", "x"),
    )


@pytest.mark.parametrize("values", [[1, "1"], ["x", []]])
def test_unrepresentable_column_fails(values: list[object]) -> None:
    with pytest.raises(ConditionError):
        distinct_value_page(pd.DataFrame({"a": values}), ValuePageRequest(0))


@pytest.mark.parametrize("page_request", [ValuePageRequest(-1), ValuePageRequest(1), ValuePageRequest(0, page=-1)])
def test_invalid_request(page_request: ValuePageRequest) -> None:
    with pytest.raises(ValueError):
        distinct_value_page(pd.DataFrame({"a": [1]}), page_request)


def test_cancellation_between_chunks_and_after_empty_scan() -> None:
    calls = 0

    def cancelled() -> bool:
        nonlocal calls
        calls += 1
        return calls > 1

    with pytest.raises(ValueRequestCancelledError):
        distinct_value_page(pd.DataFrame({"a": ["same"] * 5000}), ValuePageRequest(0), cancel_cb=cancelled)
    assert calls == 2
    with pytest.raises(ValueRequestCancelledError):
        distinct_value_page(pd.DataFrame({"a": []}), ValuePageRequest(0), cancel_cb=lambda: True)
