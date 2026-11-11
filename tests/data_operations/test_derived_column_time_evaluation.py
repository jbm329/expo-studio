"""Exact time hierarchy values, nullable output and positional preview parity."""

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from expo_jbm329.services.data_operations.derived_column.derived_column_evaluation import evaluate_expression
from expo_jbm329.services.data_operations.derived_column.derived_column_expression import (
    expression_columns,
    parse_expression_formula,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
    create_derived_column,
    preview_derived_column,
)
from expo_jbm329.services.data_operations.derived_column.derived_column_time import MonthLabels

CASES = [
    ("TIME", ["14:33", "00:00", "23:59"], "string"),
    ("WEEK", ["W01", "W09", "W53"], "string"),
    ("WEEK#", [1, 9, 53], "Int64"),
    ("MONTH", ["January", "February", "January"], "string"),
    ("MONTHSHORT", ["Jan", "Feb", "Jan"], "string"),
    ("MONTH#", [1, 2, 1], "Int64"),
    ("TERTIAL", ["T1", "T1", "T1"], "string"),
    ("TERTIAL#", [1, 1, 1], "Int64"),
    ("QUARTER", ["Q1", "Q1", "Q1"], "string"),
    ("QUARTER#", [1, 1, 1], "Int64"),
    ("YEAR", [2026, 2024, 2021], "Int64"),
    ("ISOYEAR", [2026, 2024, 2020], "Int64"),
    ("YEARWEEK", ["2026-W01", "2024-W09", "2020-W53"], "string"),
    ("YEARMONTH", ["2026-01", "2024-02", "2021-01"], "string"),
    ("YEARQUARTER", ["2026-Q1", "2024-Q1", "2021-Q1"], "string"),
    ("YEARTERTIAL", ["2026-T1", "2024-T1", "2021-T1"], "string"),
]


@pytest.mark.parametrize(("function", "values", "dtype"), CASES)
@pytest.mark.parametrize("index_kind", ["duplicate", "multi"])
def test_all_functions_exact_values_dtypes_source_immutability_and_preview(function, values, dtype, index_kind):
    source = pd.DataFrame({
        "When": pd.to_datetime(["2026-01-01 14:33:59", "2024-02-29 00:00:00", "2021-01-01 23:59:59", None]),
    })
    source.index = (
        pd.Index([7, 7, 2, 7], name="row")
        if index_kind == "duplicate"
        else pd.MultiIndex.from_tuples([("a", 1), ("a", 1), ("b", 2), ("c", 1)])
    )
    original = source.copy(deep=True)
    spec = DerivedColumnSpec("Result", f"{function}([When])")
    result = create_derived_column(source, spec)["Result"]
    expected = pd.Series([*values, pd.NA], dtype=dtype, index=source.index, name="Result")
    assert_series_equal(result, expected)
    preview = preview_derived_column(source, spec, rows=4)
    assert preview.ok
    assert list(preview.data.columns) == ["When", "Result"]
    assert_series_equal(preview.data["Result"], expected)
    assert_frame_equal(source, original)


@pytest.mark.parametrize(("function", "_values", "dtype"), CASES)
@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
@pytest.mark.parametrize("empty", [False, True])
def test_empty_and_all_nat_keep_output_dtype(function, _values, dtype, unit, empty):
    source = pd.DataFrame({"When": pd.Series([] if empty else [pd.NaT, pd.NaT], dtype=f"datetime64[{unit}]")})
    result = create_derived_column(source, DerivedColumnSpec("Result", f"{function}([When])"))["Result"]
    assert_series_equal(result, pd.Series(pd.NA, index=source.index, dtype=dtype, name="Result"))


@pytest.mark.parametrize(("function", "_values", "_dtype"), CASES)
@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_nonmissing_datetime_units_agree(function, _values, _dtype, unit):
    source = pd.DataFrame({"When": pd.to_datetime(["2026-09-01 05:06:59", None]).as_unit(unit)})
    spec = DerivedColumnSpec("Result", f"{function}([When])")
    ns_source = source.astype({"When": "datetime64[ns]"})
    assert_series_equal(create_derived_column(source, spec)["Result"], create_derived_column(ns_source, spec)["Result"])


def test_every_month_quarter_and_tertial_boundary():
    dates = [
        date
        for month in range(1, 13)
        for date in (pd.Timestamp(2026, month, 1), pd.Timestamp(2026, month, 1) + pd.offsets.MonthEnd())
    ]
    source = pd.DataFrame({"When": pd.to_datetime(dates)})
    for function, expected in (
        ("MONTH#", [month for month in range(1, 13) for _ in range(2)]),
        ("QUARTER#", [(month - 1) // 3 + 1 for month in range(1, 13) for _ in range(2)]),
        ("TERTIAL#", [(month - 1) // 4 + 1 for month in range(1, 13) for _ in range(2)]),
    ):
        result = create_derived_column(source, DerivedColumnSpec("Result", f"{function}([When])"))["Result"]
        assert_series_equal(result, pd.Series(expected, dtype="Int64", name="Result"))


def test_iso_week_and_calendar_year_differ_at_both_sides_of_new_year():
    source = pd.DataFrame({"When": pd.to_datetime(["2019-12-30", "2020-12-31", "2021-01-01", "2021-01-04"])})
    for function, expected, dtype in (
        ("YEAR", [2019, 2020, 2021, 2021], "Int64"),
        ("ISOYEAR", [2020, 2020, 2020, 2021], "Int64"),
        ("YEARWEEK", ["2020-W01", "2020-W53", "2020-W53", "2021-W01"], "string"),
        ("WEEK#", [1, 53, 53, 1], "Int64"),
    ):
        result = create_derived_column(source, DerivedColumnSpec("Result", f"{function}([When])"))["Result"]
        assert_series_equal(result, pd.Series(expected, dtype=dtype, name="Result"))


@pytest.mark.parametrize(("function", "_values", "_dtype"), CASES)
def test_stored_timezone_is_used_without_conversion(function, _values, _dtype):
    utc = pd.to_datetime(["2025-12-31 23:30:59Z", "2026-03-29 00:30:00Z", "2026-03-29 01:30:00Z", None], utc=True)
    local = utc.tz_convert("Europe/Stockholm")
    source = pd.DataFrame({"When": local})
    wall_clock = pd.DataFrame({"When": local.tz_localize(None)})
    spec = DerivedColumnSpec("Result", f"{function}([When])")
    assert_series_equal(
        create_derived_column(source, spec)["Result"], create_derived_column(wall_clock, spec)["Result"]
    )
    if function == "TIME":
        assert create_derived_column(source, spec)["Result"].iloc[:3].tolist() == ["00:30", "01:30", "03:30"]
    if function == "YEAR":
        assert create_derived_column(source, spec)["Result"].iloc[0] == 2026


def test_fall_dst_repeated_hour_remains_stored_local_time():
    dates = pd.to_datetime(["2026-10-25 00:30Z", "2026-10-25 01:30Z"], utc=True).tz_convert("Europe/Stockholm")
    result = create_derived_column(pd.DataFrame({"When": dates}), DerivedColumnSpec("Result", "TIME([When])"))
    assert result["Result"].tolist() == ["02:30", "02:30"]


@pytest.mark.parametrize(
    ("formula", "expected", "dtype"),
    [
        ("IF([When] IS NULL; 'Missing'; MONTH([When]))", ["January", "September", "Missing"], "string"),
        ("IF(MONTH#([When]) <= 6; 'H1'; 'H2')", ["H1", "H2", "H2"], "string"),
        ("YEAR([When]) + MONTH#([When])", [2027, 2035, pd.NA], "Int64"),
        ("IF(TRUE; YEARWEEK([When]); MONTH([When]))", ["2026-W01", "2026-W36", pd.NA], "string"),
        ("IF(FALSE; MONTH#([When]); 0)", [0, 0, 0], "Int64"),
    ],
)
def test_time_functions_inside_conditions_arithmetic_and_selected_branches(formula, expected, dtype):
    source = pd.DataFrame({"When": pd.to_datetime(["2026-01-01", "2026-09-01", None])})
    result = create_derived_column(source, DerivedColumnSpec("Result", formula))["Result"]
    assert_series_equal(result, pd.Series(expected, dtype=dtype, name="Result"))


@pytest.mark.parametrize("function", ["MONTH", "MONTHSHORT"])
def test_captured_month_labels_are_used_in_evaluation_creation_and_preview(function):
    labels = MonthLabels(
        full=tuple(f"Full {month}" for month in range(1, 13)),
        short=tuple(f"Short {month}" for month in range(1, 13)),
    )
    source = pd.DataFrame({"When": pd.to_datetime([f"2026-{month:02d}-01" for month in range(1, 13)] + [None])})
    spec = DerivedColumnSpec("Result", f"{function}([When])", month_labels=labels)
    parsed = parse_expression_formula(spec.formula, expression_columns(list(source.columns), list(source.dtypes)))
    direct = evaluate_expression(source, parsed.expression, month_labels=labels)
    expected = pd.Series([*(labels.full if function == "MONTH" else labels.short), pd.NA], dtype="string")
    assert_series_equal(direct, expected, check_names=False)
    created = create_derived_column(source, spec)["Result"]
    assert_series_equal(created, expected.rename("Result"))
    assert_series_equal(preview_derived_column(source, spec).data["Result"], created)


def test_month_label_snapshot_is_frozen_and_rejects_invalid_values():
    labels = MonthLabels()
    with pytest.raises(FrozenInstanceError):
        labels.full = ()
    for invalid in ((), ("x",) * 11, ("",) * 12, (" ",) * 12, (None,) * 12, ["x"] * 12):
        with pytest.raises(ValueError, match="twelve nonempty"):
            MonthLabels(full=invalid)


def test_time_extraction_only_visits_selected_if_rows(monkeypatch):
    from expo_jbm329.services.data_operations.derived_column import derived_column_evaluation as evaluation

    original = evaluation.extract_time_part
    visits = []

    def observe(values, operation, labels):
        visits.append((operation.value, len(values), values.isna().sum()))
        return original(values, operation, labels)

    monkeypatch.setattr(evaluation, "extract_time_part", observe)
    source = pd.DataFrame({"When": pd.to_datetime(["2026-01-01", None, "2026-09-01"])})
    spec = DerivedColumnSpec("Result", "IF([When] IS NULL; 'Missing'; MONTH([When]))")
    assert create_derived_column(source, spec)["Result"].tolist() == ["January", "Missing", "September"]
    assert visits == [("MONTH", 2, 0)]


def test_explicit_numeric_output_policy_and_overwrite_remain_supported():
    source = pd.DataFrame({"When": pd.to_datetime(["2026-01-01", None]), "Result": [0, 0]})
    spec = DerivedColumnSpec("Result", "YEAR([When])", overwrite_existing=True, output_dtype="Float64")
    assert_series_equal(
        create_derived_column(source, spec)["Result"], pd.Series([2026, pd.NA], dtype="Float64", name="Result")
    )
    invalid = DerivedColumnSpec("Label", "MONTH([When])", output_dtype="Float64")
    preview = preview_derived_column(source, invalid)
    assert not preview.ok
    assert preview.message == "result_conversion_failed"
