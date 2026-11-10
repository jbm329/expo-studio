"""Compatibility checks using actual concatenation output with absent columns."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook

from expo_jbm329.services.analysis.correlation import analyze_correlation_matrix
from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.regression import analyze_regression, classify_predictor_columns
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
from expo_jbm329.services.data_operations.column_defaults import ColumnFill
from expo_jbm329.services.data_operations.concat import ConcatRequest, concat_dataframes
from expo_jbm329.services.file_writer import FileWriter

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("defaults", [False, True])
def test_concat_nullable_columns_in_analysis(defaults: bool) -> None:
    rng = np.random.default_rng(42)
    size = 40
    source = pd.DataFrame({
        "id": np.arange(size),
        "x": pd.Series(rng.integers(1, 100, size), dtype="Int64"),
        "z": rng.integers(1, 100, size),
        "flag": pd.Series(np.arange(size) % 2 == 0, dtype="boolean"),
    })
    source["y"] = 2 * source["x"] - source["z"] + rng.integers(-10, 11, size)
    source.loc[3, ["x", "flag"]] = pd.NA
    fills = {"x": ColumnFill(0), "flag": ColumnFill(False)} if defaults else {}
    frame = concat_dataframes(ConcatRequest(source, pd.DataFrame({"id": [40, 41, 42]}), left_fill=fills))
    original = frame.copy(deep=True)
    assert str(frame["x"].dtype) == "Int64"
    assert str(frame["flag"].dtype) == "boolean"
    assert frame.loc[3, ["x", "flag"]].isna().all()
    overview = analyze_dataset_overview(frame)
    columns = {column.column: column for column in overview.columns}
    assert columns["x"].missing_count == (1 if defaults else 4)
    assert columns["flag"].missing_count == (1 if defaults else 4)
    statistics = analyze_descriptive_statistics(frame)
    values = next(column for column in statistics.columns if column.column == "x")
    assert values.count == (42 if defaults else 39)
    assert values.missing_count == (1 if defaults else 4)
    assert values.mean == pytest.approx(frame["x"].mean())
    assert sum(values.histogram_counts) == values.count
    reference = frame[["x", "z", "y"]].astype("float64")
    matrix = analyze_correlation_matrix(frame, ["x", "z", "y"])
    expected_matrix = analyze_correlation_matrix(reference, ["x", "z", "y"])
    assert matrix is not None and expected_matrix is not None
    assert matrix.error is None
    assert matrix.pairs == expected_matrix.pairs
    predictors = classify_predictor_columns(frame)
    assert "x" in predictors.numeric
    assert "flag" in predictors.categorical
    result = analyze_regression(frame, "y", ["x", "z", "flag"])
    complete = (
        frame[["x", "z", "y", "flag"]]
        .dropna()
        .astype({
            "x": "float64",
            "z": "float64",
            "y": "float64",
            "flag": "bool",
        })
    )
    expected = analyze_regression(complete, "y", ["x", "z", "flag"])
    assert result.error is None and expected.error is None
    assert result.n_used == 39
    assert result.n_dropped == 4
    assert result.r_squared == pytest.approx(expected.r_squared)
    assert [term.estimate for term in result.terms] == pytest.approx([term.estimate for term in expected.terms])
    pd.testing.assert_frame_equal(frame, original)


def _export_concat(*, source_first: bool, defaults: bool, large: bool = False) -> pd.DataFrame:
    """Include generated gaps and genuine source NULLs in both source orders."""
    source = pd.DataFrame({
        "id": [2, 3, 4],
        "value": pd.Series([2**62 + 1, pd.NA, 2**62 + 3] if large else [10, pd.NA, 20], dtype="Int64"),
        "flag": pd.Series([False, pd.NA, True], dtype="boolean"),
        "text": pd.Series(["hello", pd.NA, "world"], dtype="string"),
        "category": pd.Series(["a", None, "b"], dtype="category"),
        "date": pd.to_datetime(["2020-01-01", None, "2020-01-02"]),
    })
    other = pd.DataFrame({"id": [0, 1]})
    source_original = source.copy(deep=True)
    fills = (
        {
            "value": ColumnFill(0),
            "flag": ColumnFill(False),
            "text": ColumnFill("absent"),
            "category": ColumnFill("absent"),
            "date": ColumnFill(pd.Timestamp("2000-01-01")),
        }
        if defaults
        else {}
    )
    request = (
        ConcatRequest(source, other, left_fill=fills)
        if source_first
        else ConcatRequest(other, source, right_fill=fills)
    )
    frame = concat_dataframes(request)
    assert str(frame["value"].dtype) == "Int64"
    assert str(frame["flag"].dtype) == "boolean"
    assert isinstance(frame["category"].dtype, pd.CategoricalDtype)
    assert frame.loc[frame["id"] == 3, ["value", "flag", "text", "category", "date"]].isna().all().all()
    pd.testing.assert_frame_equal(source, source_original)
    pd.testing.assert_frame_equal(other, pd.DataFrame({"id": [0, 1]}))
    return frame


@pytest.mark.parametrize("source_first", [False, True])
@pytest.mark.parametrize("defaults", [False, True])
@pytest.mark.parametrize("suffix", [".df", ".feather", ".ft", ".parquet"])
def test_concat_datafile_roundtrip(tmp_path: Path, source_first: bool, defaults: bool, suffix: str) -> None:
    frame = _export_concat(source_first=source_first, defaults=defaults, large=True)
    original = frame.copy(deep=True)
    path = tmp_path / f"concatenated{suffix}"
    assert FileWriter().save_datafile(frame, path) == path
    if suffix == ".df":
        restored = pd.read_pickle(path)
    elif suffix == ".parquet":
        restored = pd.read_parquet(path)
    else:
        restored = pd.read_feather(path)
    pd.testing.assert_frame_equal(restored, frame)
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("source_first", [False, True])
@pytest.mark.parametrize("defaults", [False, True])
@pytest.mark.parametrize("chunk_size", [None, 1])
def test_concat_csv_preserves_exact_integer_digits_and_nulls(
    tmp_path: Path, source_first: bool, defaults: bool, chunk_size: int | None
) -> None:
    frame = _export_concat(source_first=source_first, defaults=defaults, large=True)
    original = frame.copy(deep=True)
    path = tmp_path / "concatenated.csv"
    FileWriter().save_csv(frame, path, chunk_size_rows=chunk_size, na_rep="")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = {int(row["id"]): row for row in csv.DictReader(stream)}
    for row_id in (0, 1):
        assert rows[row_id]["value"] == ("0" if defaults else "")
        assert rows[row_id]["flag"] == ("False" if defaults else "")
    assert rows[2]["value"] == str(2**62 + 1)
    assert rows[4]["value"] == str(2**62 + 3)
    assert rows[2]["flag"] == "False"
    assert rows[4]["flag"] == "True"
    assert all(rows[3][column] == "" for column in ("value", "flag", "text", "category", "date"))
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("source_first", [False, True])
@pytest.mark.parametrize("defaults", [False, True])
@pytest.mark.parametrize("streaming", [False, True])
def test_concat_excel_preserves_blanks_booleans_categories_and_dates(
    tmp_path: Path, source_first: bool, defaults: bool, streaming: bool
) -> None:
    frame = _export_concat(source_first=source_first, defaults=defaults)
    original = frame.copy(deep=True)
    path = tmp_path / "concatenated.xlsx"
    FileWriter().save_excel(frame, path, streaming=streaming, index=False)
    workbook = load_workbook(path)
    try:
        sheet = workbook["Data"]
        rows = list(sheet.values)
        assert rows[0] == tuple(frame.columns)
        by_id = {row[0]: dict(zip(frame.columns, row, strict=True)) for row in rows[1:]}
        for row_id in (0, 1):
            assert by_id[row_id]["value"] == (0 if defaults else None)
            assert by_id[row_id]["flag"] is (False if defaults else None)
            assert by_id[row_id]["text"] == ("absent" if defaults else None)
            assert by_id[row_id]["category"] == ("absent" if defaults else None)
            assert by_id[row_id]["date"] == (pd.Timestamp("2000-01-01").to_pydatetime() if defaults else None)
        assert by_id[2]["value"] == 10
        assert by_id[4]["value"] == 20
        assert by_id[2]["flag"] is False
        assert by_id[4]["flag"] is True
        assert by_id[2]["category"] == "a"
        assert by_id[4]["category"] == "b"
        assert by_id[2]["date"] == pd.Timestamp("2020-01-01").to_pydatetime()
        assert all(by_id[3][column] is None for column in ("value", "flag", "text", "category", "date"))
        flag_column = list(frame.columns).index("flag") + 1
        for row_number, row in enumerate(rows[1:], start=2):
            if row[0] in (2, 4) or (defaults and row[0] in (0, 1)):
                assert sheet.cell(row_number, flag_column).data_type == "b"
    finally:
        workbook.close()
    pd.testing.assert_frame_equal(frame, original)
