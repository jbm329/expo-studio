"""Shared literal decoding and explicit nullable comparison policies."""

from decimal import Decimal

import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from expo_jbm329.services.data_operations.expression_primitives import (
    UnclosedLiteralError,
    compare_values,
    decode_delimited_literal,
    membership_mask,
)


@pytest.mark.parametrize(
    ("text", "start", "decoded", "end"),
    [
        ("[Age] > 1", 0, "Age", 5),
        (" [a]]b] ", 1, "a]b", 7),
        ("'O''Brien';", 0, "O'Brien", 10),
        ("''", 0, "", 2),
        ("[]", 0, "", 2),
        ("''''", 0, "'", 4),
        ("'[Age]; IN('", 0, "[Age]; IN(", 12),
        ("'line\nbreak'", 0, "line\nbreak", 12),
    ],
)
def test_decode_delimited_literal(text, start, decoded, end):
    assert decode_delimited_literal(text, start) == (decoded, end)


@pytest.mark.parametrize("text", ["[Age", "'unfinished", "'escaped''", "[escaped]]"])
def test_unclosed_literal_retains_source_span(text):
    with pytest.raises(UnclosedLiteralError) as caught:
        decode_delimited_literal("  " + text, 2)
    assert (caught.value.start, caught.value.end) == (2, len(text) + 2)


@pytest.mark.parametrize(("text", "start"), [("", 0), ("abc", 0), ("'x'", -1), ("'x'", 3)])
def test_decoder_rejects_invalid_start(text, start):
    with pytest.raises(ValueError, match="opening bracket"):
        decode_delimited_literal(text, start)


@pytest.mark.parametrize("dtype", ["Int64", "Float64", "float64", "object"])
@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        ("=", [False, True]),
        ("!=", [True, False]),
        (">", [False, False]),
        (">=", [False, True]),
        ("<", [True, False]),
        ("<=", [True, True]),
    ],
)
@pytest.mark.parametrize("preserve_unknown", [False, True])
def test_comparison_policy_and_index(dtype, operator, expected, preserve_unknown):
    source = pd.Series([1, 2, None], dtype=dtype, index=["b", "a", "a"], name="source")
    original = source.copy(deep=True)
    result = compare_values(source, 2, operator, preserve_unknown=preserve_unknown)
    assert_series_equal(
        result,
        pd.Series(
            [*expected, pd.NA if preserve_unknown else False],
            index=source.index,
            name=source.name,
            dtype="boolean" if preserve_unknown else bool,
        ),
    )
    assert_series_equal(source, original)


def test_series_operands_propagate_missing_on_either_side_without_reordering():
    left = pd.Series([1, 2, None, 4], index=[2, 1, 1, 0], dtype="Int64")
    right = pd.Series([1, None, 3, 5], index=left.index, dtype="Int64")
    result = compare_values(left, right, "=", preserve_unknown=True)
    assert_series_equal(result, pd.Series([True, pd.NA, pd.NA, False], index=left.index, dtype="boolean"))


@pytest.mark.parametrize("right", [None, pd.NA, float("nan"), pd.NaT])
@pytest.mark.parametrize("preserve_unknown", [False, True])
@pytest.mark.parametrize("operator", ["=", "!=", ">", ">=", "<", "<="])
def test_missing_scalar_comparison(right, preserve_unknown, operator):
    source = pd.Series([1, None], dtype="Float64")
    result = compare_values(source, right, operator, preserve_unknown=preserve_unknown)
    expected = pd.Series([pd.NA, pd.NA], dtype="boolean") if preserve_unknown else pd.Series([False, False])
    assert_series_equal(result, expected)


@pytest.mark.parametrize(
    ("source", "right", "operator", "expected"),
    [
        (pd.Series(["BMW", "Volvo", None], dtype="string"), "BMW", "=", [True, False, pd.NA]),
        (pd.Series([True, False, None], dtype="boolean"), True, "!=", [False, True, pd.NA]),
        (pd.Series([Decimal("1.2"), None], dtype=object), Decimal("1.2"), "=", [True, pd.NA]),
        (pd.Series(pd.to_datetime(["2026-01-01", None])), pd.Timestamp("2026-01-01"), "=", [True, pd.NA]),
    ],
)
def test_comparisons_preserve_typed_values(source, right, operator, expected):
    assert_series_equal(
        compare_values(source, right, operator, preserve_unknown=True),
        pd.Series(expected, dtype="boolean"),
    )


def test_comparison_does_not_coerce_numeric_text():
    source = pd.Series(["1", "2"], dtype="string")
    assert not compare_values(source, 1, "=", preserve_unknown=False).any()
    with pytest.raises(TypeError):
        compare_values(source, 1, ">", preserve_unknown=True)


def test_invalid_comparison_inputs_fail_explicitly():
    source = pd.Series([1, 2])
    with pytest.raises(ValueError, match="Unsupported comparison"):
        compare_values(source, 1, "LIKE", preserve_unknown=False)
    with pytest.raises(ValueError, match="identical indexes"):
        compare_values(source, pd.Series([1, 2], index=[1, 0]), "=", preserve_unknown=False)
    with pytest.raises(TypeError, match="scalar or Series"):
        compare_values(source, [1, 2], "=", preserve_unknown=False)


@pytest.mark.parametrize("negate", [False, True])
@pytest.mark.parametrize("preserve_unknown", [False, True])
@pytest.mark.parametrize("dtype", ["string", "object", "category"])
def test_membership_policy_preserves_index_and_inputs(negate, preserve_unknown, dtype):
    source = pd.Series(["BMW", "Volvo", "Ford", None], index=[3, 1, 1, 0], dtype=dtype)
    values = pd.Series(["BMW", "Volvo"], dtype=object)
    original = source.copy(deep=True)
    result = membership_mask(source, values, negate=negate, preserve_unknown=preserve_unknown)
    assert_series_equal(
        result,
        pd.Series(
            [not negate, not negate, negate, pd.NA if preserve_unknown else False],
            index=source.index,
            dtype="boolean" if preserve_unknown else bool,
        ),
    )
    assert_series_equal(source, original)
    assert_series_equal(values, pd.Series(["BMW", "Volvo"], dtype=object))


@pytest.mark.parametrize("negate", [False, True])
def test_missing_candidate_only_makes_unmatched_membership_unknown(negate):
    source = pd.Series([1, 2, None], dtype="Int64")
    values = pd.Series([1, None], dtype=object)
    assert_series_equal(
        membership_mask(source, values, negate=negate, preserve_unknown=True),
        pd.Series([not negate, pd.NA, pd.NA], dtype="boolean"),
    )
    assert_series_equal(
        membership_mask(source, values, negate=negate, preserve_unknown=False),
        pd.Series([not negate, negate, False]),
    )


@pytest.mark.parametrize("preserve_unknown", [False, True])
def test_empty_operands_keep_index_and_boolean_dtype(preserve_unknown):
    source = pd.Series([], dtype="Float64", index=pd.Index([], name="row"))
    expected = pd.Series([], index=source.index, dtype="boolean" if preserve_unknown else bool)
    assert_series_equal(compare_values(source, 1, "=", preserve_unknown=preserve_unknown), expected)
    assert_series_equal(
        membership_mask(source, pd.Series([], dtype=object), preserve_unknown=preserve_unknown),
        expected,
    )
