"""Ordered row selection preserves values, grouping and preview semantics."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

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
    compute_reshape,
    compute_reshape_preview,
)


def ordered_metric(
    source: pd.DataFrame,
    function: ReshapeFunction,
    *,
    position: int = 1,
    order: int = 2,
    condition: str = "",
) -> ReshapeMetric:
    parsed = parse_condition(condition, condition_columns(list(source.columns), list(source.dtypes)))
    assert not parsed.diagnostics
    return ReshapeMetric(function.value, function, position, parsed.instructions, order)


@pytest.mark.parametrize("order_dtype", ["int64", "Int64", "uint64", "UInt64", "float64", "Float64"])
def test_independent_numeric_ordering_and_mixed_aggregations(order_dtype: str) -> None:
    source = pd.DataFrame({
        "group": ["B", "A", "B", "A", "B", "A"],
        "value": ["b-high", "a-high", "b-low-first", "a-low", "b-low-last", "a-mid"],
        "order": pd.Series([3, 3, 1, 1, 1, 2], dtype=order_dtype),
        "other": [0, 0, 5, 7, 1, 1],
    })
    original = source.copy(deep=True)
    request = ReshapeRequest(
        (0,),
        (
            ordered_metric(source, ReshapeFunction.FIRST),
            ordered_metric(source, ReshapeFunction.LAST, order=3),
            ReshapeMetric("SUM", ReshapeFunction.SUM, 2),
            ReshapeMetric("MEDIAN", ReshapeFunction.MEDIAN, 2),
        ),
    )
    result = compute_reshape(source, request)
    assert result is not None
    assert result["group"].tolist() == ["B", "A"]
    assert result["FIRST"].tolist() == ["b-low-first", "a-low"]
    assert result["LAST"].tolist() == ["b-low-first", "a-low"]
    assert result["SUM"].tolist() == [5, 6]
    assert result["MEDIAN"].tolist() == [1, 2]
    pd.testing.assert_frame_equal(source, original)


@pytest.mark.parametrize("timezone", [None, "UTC", "Europe/Stockholm"])
def test_datetime_ordering_excludes_nat_and_breaks_ties(timezone: str | None) -> None:
    source = pd.DataFrame({
        "group": ["A"] * 5,
        "value": ["late-first", "early", "late-last", "unknown", "early-last"],
        "order": pd.Series(
            pd.DatetimeIndex(["2026-02-01", "2026-01-01", "2026-02-01", None, "2026-01-01"], tz=timezone)
        ),
    })
    request = ReshapeRequest(
        (0,), tuple(ordered_metric(source, function) for function in (ReshapeFunction.FIRST, ReshapeFunction.LAST))
    )
    result = compute_reshape(source, request)
    assert result is not None
    assert result["FIRST"].tolist() == ["early"]
    assert result["LAST"].tolist() == ["late-last"]


@pytest.mark.parametrize("function", [ReshapeFunction.FIRST, ReshapeFunction.LAST])
def test_conditions_precede_ordering_and_selected_null_is_not_skipped(function: ReshapeFunction) -> None:
    source = pd.DataFrame({
        "group": ["A"] * 5 + ["B", "C"],
        "value": pd.Series(
            ["excluded-low", None, "middle", None, "excluded-high", "unknown", "filtered"], dtype="string"
        ),
        "order": pd.Series([0, 1, 2, 3, 4, None, 1], dtype="Int64"),
        "eligible": [False, True, True, True, False, True, False],
    })
    request = ReshapeRequest((0,), (ordered_metric(source, function, condition="[eligible] = True"),))
    result = compute_reshape(source, request)
    assert result is not None
    assert result["group"].tolist() == ["A", "B", "C"]
    assert result[function].isna().all()
    nonnull = compute_reshape(
        source,
        ReshapeRequest(
            (0,), (ordered_metric(source, function, condition="[eligible] = True AND [value] IS NOT NULL"),)
        ),
    )
    assert nonnull is not None
    assert nonnull[function].iloc[0] == "middle"
    assert nonnull[function].iloc[1:].isna().all()


@pytest.mark.parametrize(
    "values",
    [
        pd.Series(["first", "last", None], dtype="string"),
        pd.Series([1, 2, None], dtype="Int64"),
        pd.Series([1, 2, None], dtype="Int8"),
        pd.Series([1, 2, None], dtype="UInt64"),
        pd.Series([1, 2, None], dtype="UInt16"),
        pd.Series([1.5, 2.5, None], dtype="Float64"),
        pd.Series([True, False, None], dtype="boolean"),
        pd.Series(pd.Categorical(["first", "last", None], categories=["unused", "first", "last"])),
        pd.Series(pd.to_datetime(["2026-01-01", "2026-02-01", None])),
        pd.Series(pd.to_datetime(["2026-01-01", "2026-02-01", None], utc=True)),
        pd.Series(pd.to_timedelta([1, 2, None], unit="D")),
        pd.Series([1 + 2j, 3 + 4j, None], dtype="complex128"),
        pd.Series([[1], {"key": 2}, None], dtype=object),
        pd.Series([True, 1, None], dtype=object),
    ],
)
@pytest.mark.parametrize("function", [ReshapeFunction.FIRST, ReshapeFunction.LAST])
def test_arbitrary_value_dtypes_are_preserved(values: pd.Series, function: ReshapeFunction) -> None:
    source = pd.DataFrame({"group": ["A", "A", "B"], "value": values, "order": [1.0, 2.0, None]})
    result = compute_reshape(source, ReshapeRequest((0,), (ordered_metric(source, function),)))
    assert result is not None
    expected = values.iloc[[0 if function == ReshapeFunction.FIRST else 1, 2]].reset_index(drop=True)
    if values.dtype == object:
        expected.iloc[1] = float("nan")
    expected.name = function.value
    pd.testing.assert_series_equal(result[function], expected)


@pytest.mark.parametrize("dtype", ["int8", "uint32", "bool", "float32"])
@pytest.mark.parametrize("missing_group", [False, True])
def test_numpy_values_preserve_dtype_unless_missing_output_requires_nullable(dtype: str, missing_group: bool) -> None:
    values = pd.Series([1, 0], dtype=dtype)
    source = pd.DataFrame({"group": ["A", "B"], "value": values, "order": [1, None if missing_group else 2]})
    result = compute_reshape(source, ReshapeRequest((0,), (ordered_metric(source, ReshapeFunction.FIRST),)))
    assert result is not None
    expected = values.copy()
    if missing_group:
        if dtype == "bool":
            expected = expected.astype("boolean")
        elif dtype.startswith("uint"):
            expected = expected.astype("UInt64")
        elif dtype.startswith("int"):
            expected = expected.astype("Int64")
        expected.iloc[1] = pd.NA if dtype != "float32" else float("nan")
    expected.name = "FIRST"
    pd.testing.assert_series_equal(result["FIRST"], expected)


@pytest.mark.parametrize("dimensions", [(0, 1), ()])
def test_positional_identity_multiple_dimensions_and_shared_source_order(dimensions: tuple[int, ...]) -> None:
    source = pd.DataFrame(
        [["B", None, 2, 9], ["A", "x", 8, 4], ["B", None, 2, 7], ["A", "x", 1, 4]],
        columns=["duplicate", "key", "duplicate", "duplicate"],
        index=[8, 8, 0, 0],
    )
    original = source.copy(deep=True)
    request = ReshapeRequest(
        dimensions,
        (
            ordered_metric(source, ReshapeFunction.FIRST, position=3, order=2),
            ordered_metric(source, ReshapeFunction.LAST, position=2, order=2),
        ),
    )
    result = compute_reshape(source, request)
    assert result is not None
    assert result["FIRST"].tolist() == ([9, 4] if dimensions else [4])
    assert result["LAST"].tolist() == ([2, 8] if dimensions else [8])
    pd.testing.assert_frame_equal(source, original)


@pytest.mark.parametrize("dimensions", [(0,), ()])
@pytest.mark.parametrize("empty", [False, True])
def test_empty_and_all_missing_order_preserve_group_semantics(dimensions: tuple[int, ...], empty: bool) -> None:
    source = pd.DataFrame({
        "group": pd.Series([] if empty else ["B", "A"], dtype="string"),
        "value": pd.Series([] if empty else [True, False], dtype=bool),
        "order": pd.Series([] if empty else [None, None], dtype="Float64"),
    })
    request = ReshapeRequest(
        dimensions,
        tuple(ordered_metric(source, function) for function in (ReshapeFunction.FIRST, ReshapeFunction.LAST)),
    )
    result = compute_reshape(source, request)
    preview = compute_reshape_preview(source, request)
    assert result is not None and preview is not None
    assert len(result) == (0 if empty and dimensions else 2 if dimensions else 1)
    pd.testing.assert_frame_equal(result, preview.frame)
    assert result["FIRST"].isna().all() and result["LAST"].isna().all()


def test_full_source_preview_matches_complete_output_and_progress() -> None:
    source = pd.DataFrame({"group": list("gfedcba") * 3, "value": range(21), "order": list(range(7)) * 3})
    request = ReshapeRequest(
        (0,), tuple(ordered_metric(source, function) for function in (ReshapeFunction.FIRST, ReshapeFunction.LAST))
    )
    progress: list[int] = []
    result = compute_reshape(source, request, progress_cb=progress.append)
    preview = compute_reshape_preview(source, request)
    assert result is not None and preview is not None
    assert result["FIRST"].tolist() == list(range(7))
    assert result["LAST"].tolist() == list(range(14, 21))
    assert preview.total_rows == 7 and len(preview.frame) == 5
    pd.testing.assert_frame_equal(result.head(5), preview.frame)
    assert progress == [0, 10, 55, 100]


@pytest.mark.parametrize("dtype", ["int8", "uint64", "bool"])
def test_missing_group_outside_preview_still_matches_complete_output_dtype(dtype: str) -> None:
    source = pd.DataFrame({
        "group": list("ABCDEFG"),
        "value": pd.Series([1] * 7, dtype=dtype),
        "order": [1, 2, 3, 4, 5, None, 7],
    })
    request = ReshapeRequest(
        (0,), tuple(ordered_metric(source, function) for function in (ReshapeFunction.FIRST, ReshapeFunction.LAST))
    )
    result = compute_reshape(source, request)
    preview = compute_reshape_preview(source, request)
    assert result is not None and preview is not None
    pd.testing.assert_frame_equal(result.head(5), preview.frame)
    assert pd.isna(result["FIRST"].iloc[5]) and pd.isna(result["LAST"].iloc[5])


@pytest.mark.parametrize("dtype", ["bool", "boolean", "complex128", "category", "timedelta64[ns]", "string", "object"])
def test_ineligible_order_dtypes_are_configuration_errors(dtype: str) -> None:
    value = pd.Timedelta(days=1) if dtype == "timedelta64[ns]" else "2026-01-01" if dtype in {"string", "object"} else 1
    source = pd.DataFrame({"value": ["text"], "order": pd.Series([value], dtype=dtype)})
    request = ReshapeRequest((), (ReshapeMetric("FIRST", ReshapeFunction.FIRST, 0, order_position=1),))
    with pytest.raises(ReshapeError) as caught:
        compute_reshape(source, request)
    assert caught.value.problem == ReshapeProblem.CONFIGURATION
    assert caught.value.name == "FIRST"


@pytest.mark.parametrize("order", [None, -1, 2])
@pytest.mark.parametrize("function", [ReshapeFunction.FIRST, ReshapeFunction.LAST])
def test_missing_and_invalid_order_positions_are_rejected(order: int | None, function: ReshapeFunction) -> None:
    source = pd.DataFrame({"value": ["text"], "order": [1]})
    request = ReshapeRequest((), (ReshapeMetric("Selected", function, 0, order_position=order),))
    with pytest.raises(ReshapeError) as caught:
        compute_reshape_preview(source, request)
    assert caught.value.problem == ReshapeProblem.CONFIGURATION
    assert caught.value.name == "Selected"


@pytest.mark.parametrize(
    "function",
    [function for function in ReshapeFunction if function not in {ReshapeFunction.FIRST, ReshapeFunction.LAST}],
)
def test_ordinary_functions_reject_ordering_metadata(function: ReshapeFunction) -> None:
    source = pd.DataFrame({"value": [1], "order": [2]})
    with pytest.raises(ReshapeError) as caught:
        compute_reshape(source, ReshapeRequest((), (ReshapeMetric("Metric", function, 0, order_position=1),)))
    assert caught.value.problem == ReshapeProblem.CONFIGURATION


def test_ordering_is_frozen_and_legacy_condition_constructor_is_unchanged() -> None:
    legacy = ReshapeMetric("SUM", ReshapeFunction.SUM, 0, ())
    assert legacy.order_position is None
    with pytest.raises(FrozenInstanceError):
        legacy.order_position = 1


@pytest.mark.parametrize("phase", ["before_sort", "after_sort", "after_selection"])
def test_cancellation_at_selection_boundaries_is_not_success(monkeypatch: pytest.MonkeyPatch, phase: str) -> None:
    source = pd.DataFrame({"group": ["A", "A"], "value": ["first", "last"], "order": [2, 1]})
    original = source.copy(deep=True)
    cancelled = False
    sort_values = pd.Series.sort_values
    duplicated = pd.Series.duplicated
    notna = pd.Series.notna

    def present(series: pd.Series) -> pd.Series:
        nonlocal cancelled
        result = notna(series)
        if phase == "before_sort" and series.name == "order":
            cancelled = True
        return result

    def sort(series: pd.Series, *args: object, **kwargs: object) -> pd.Series:
        nonlocal cancelled
        result = sort_values(series, *args, **kwargs)
        if phase == "after_sort":
            cancelled = True
        return result

    def duplicates(series: pd.Series, *args: object, **kwargs: object) -> pd.Series:
        nonlocal cancelled
        result = duplicated(series, *args, **kwargs)
        if phase == "after_selection":
            cancelled = True
        return result

    monkeypatch.setattr(pd.Series, "sort_values", sort)
    monkeypatch.setattr(pd.Series, "duplicated", duplicates)
    monkeypatch.setattr(pd.Series, "notna", present)

    def cancel() -> bool:
        return cancelled

    request = ReshapeRequest((0,), (ordered_metric(source, ReshapeFunction.FIRST),))
    assert compute_reshape(source, request, cancel_cb=cancel) is None
    pd.testing.assert_frame_equal(source, original)


@pytest.mark.parametrize("missing", [None, pd.NA, pd.NaT])
@pytest.mark.parametrize("function", [ReshapeFunction.FIRST, ReshapeFunction.LAST])
def test_selected_object_missing_value_is_preserved_exactly(missing: object, function: ReshapeFunction) -> None:
    source = pd.DataFrame({
        "group": ["A", "A", "A"],
        "value": pd.Series([missing, "nonmissing", missing], dtype=object),
        "order": [0, 1, 2],
    })
    result = compute_reshape(source, ReshapeRequest((0,), (ordered_metric(source, function),)))
    assert result is not None
    assert result[function].dtype == object
    assert result[function].iloc[0] is missing


@pytest.mark.parametrize(
    "order",
    [
        pd.Series([-0.5, -1.5, 0.25], dtype="Float64"),
        pd.Series([2**64 - 2, 2**64 - 3, 2**64 - 1], dtype="uint64"),
        pd.Series([0, -(2**63), 2**63 - 1], dtype="int64"),
        pd.Series([0, float("-inf"), float("inf")], dtype="float64"),
    ],
)
def test_numeric_ordering_does_not_round_or_convert_keys(order: pd.Series) -> None:
    source = pd.DataFrame({"group": ["A"] * 3, "value": ["middle", "lowest", "highest"], "order": order})
    request = ReshapeRequest(
        (0,), tuple(ordered_metric(source, function) for function in (ReshapeFunction.FIRST, ReshapeFunction.LAST))
    )
    result = compute_reshape(source, request)
    assert result is not None
    assert result["FIRST"].tolist() == ["lowest"]
    assert result["LAST"].tolist() == ["highest"]


def test_ordering_column_can_also_be_a_dimension() -> None:
    source = pd.DataFrame({
        "value": ["two-first", "one", "two-last", "unknown"],
        "order": pd.Series([2, 1, 2, None], dtype="Int64"),
    })
    request = ReshapeRequest(
        (1,),
        tuple(
            ordered_metric(source, function, position=0, order=1)
            for function in (ReshapeFunction.FIRST, ReshapeFunction.LAST)
        ),
    )
    result = compute_reshape(source, request)
    assert result is not None
    pd.testing.assert_series_equal(result["order"], pd.Series([2, 1, None], dtype="Int64", name="order"))
    assert result["FIRST"].iloc[:2].tolist() == ["two-first", "one"]
    assert result["LAST"].iloc[:2].tolist() == ["two-last", "one"]
    assert pd.isna(result["FIRST"].iloc[2]) and pd.isna(result["LAST"].iloc[2])
