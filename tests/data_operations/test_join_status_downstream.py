"""Verify chained join provenance through transformations and persisted outputs."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

import duckdb
import pandas as pd
import pytest
from openpyxl import load_workbook

from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
    create_derived_column,
)
from expo_jbm329.services.data_operations.joins import JoinRequest, JoinResult, join_dataframes_with_status
from expo_jbm329.services.file_writer import FileWriter

if TYPE_CHECKING:
    from pathlib import Path

STATUS_BASE = "join_status (Film LEFT Actor)"


@pytest.fixture
def chained() -> JoinResult:
    """Create distinct historical/current statuses and preserve nullable source data."""
    left = pd.DataFrame({
        "id": [1, 2, 3],
        "join_status": pd.Series(["source", pd.NA, "source"], dtype="string"),
        "_left_indicator": ["L1", "L2", "L3"],
    })
    right = pd.DataFrame({
        "id": [2, 3],
        "value": pd.Series([2**62 + 1, pd.NA], dtype="Int64"),
        "flag": pd.Series([False, pd.NA], dtype="boolean"),
        "_right_indicator": pd.Series(["R2", "R3"], dtype="string"),
    })
    originals = left.copy(deep=True), right.copy(deep=True)
    first = join_dataframes_with_status(
        JoinRequest(left, right, ["id"], ["id"], how="left", status_column_base=STATUS_BASE)
    )
    first_original = first.frame.copy(deep=True)
    lookup = pd.DataFrame({"id": [1, 3], "label": pd.Series(["one", "three"], dtype="string")})
    second = join_dataframes_with_status(
        JoinRequest(first.frame, lookup, ["id"], ["id"], how="left", status_column_base=STATUS_BASE)
    )
    assert second.status_column == f"{STATUS_BASE} 2"
    assert second.frame[STATUS_BASE].tolist() == ["left_only", "both", "both"]
    assert second.frame[second.status_column].tolist() == ["both", "left_only", "both"]
    assert list(second.frame.columns) == [
        "id",
        "join_status",
        "_left_indicator",
        "value",
        "flag",
        "_right_indicator",
        STATUS_BASE,
        "label",
        f"{STATUS_BASE} 2",
    ]
    pd.testing.assert_frame_equal(second.frame[first.frame.columns], first_original)
    pd.testing.assert_frame_equal(first.frame, first_original)
    pd.testing.assert_frame_equal(left, originals[0])
    pd.testing.assert_frame_equal(right, originals[1])
    return second


@pytest.mark.parametrize("suffix", [".df", ".feather", ".ft", ".parquet"])
def test_chained_status_datafile_roundtrip(tmp_path: Path, chained: JoinResult, suffix: str) -> None:
    """Persist both provenance generations, reserved names and exact typed values."""
    original = chained.frame.copy(deep=True)
    path = tmp_path / f"chained{suffix}"
    assert FileWriter().save_datafile(chained.frame, path) == path
    if suffix == ".df":
        restored = pd.read_pickle(path)
    elif suffix == ".parquet":
        restored = pd.read_parquet(path)
    else:
        restored = pd.read_feather(path)
    pd.testing.assert_frame_equal(restored, original)
    pd.testing.assert_frame_equal(chained.frame, original)
    next_join = join_dataframes_with_status(
        JoinRequest(restored, pd.DataFrame({"id": [2, 3]}), ["id"], ["id"], how="left", status_column_base=STATUS_BASE)
    )
    assert next_join.status_column == f"{STATUS_BASE} 3"
    assert next_join.frame[next_join.status_column].tolist() == ["left_only", "both", "both"]
    pd.testing.assert_frame_equal(next_join.frame[restored.columns], original)


@pytest.mark.parametrize("chunk_size", [None, 1])
def test_chained_status_csv_headers_values_and_exact_integers(
    tmp_path: Path, chained: JoinResult, chunk_size: int | None
) -> None:
    """CSV includes real descriptive headers and every historical status value."""
    original = chained.frame.copy(deep=True)
    path = tmp_path / "chained.csv"
    FileWriter().save_csv(chained.frame, path, chunk_size_rows=chunk_size, na_rep="")
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == list(original.columns)
        rows = list(reader)
    assert [row["value"] for row in rows] == ["", str(2**62 + 1), ""]
    assert [row["flag"] for row in rows] == ["", "False", ""]
    assert [row["join_status"] for row in rows] == ["source", "", "source"]
    assert [row[STATUS_BASE] for row in rows] == ["left_only", "both", "both"]
    assert [row[chained.status_column] for row in rows] == ["both", "left_only", "both"]
    pd.testing.assert_frame_equal(chained.frame, original)


@pytest.mark.parametrize("streaming", [False, True])
def test_chained_status_excel_headers_and_values(tmp_path: Path, chained: JoinResult, streaming: bool) -> None:
    """Both workbook writers preserve descriptive headers, NULLs and provenance."""
    frame = chained.frame.copy(deep=True)
    # Excel's documented numeric precision limit is separate from header preservation.
    frame["value"] = pd.Series([pd.NA, 10, pd.NA], dtype="Int64")
    original = frame.copy(deep=True)
    path = tmp_path / "chained.xlsx"
    FileWriter().save_excel(frame, path, streaming=streaming, index=False)
    workbook = load_workbook(path)
    try:
        rows = list(workbook["Data"].values)
        assert rows[0] == tuple(frame.columns)
        for column in ["join_status", STATUS_BASE, chained.status_column, "_left_indicator", "_right_indicator"]:
            index = list(frame.columns).index(column)
            expected = [None if pd.isna(value) else value for value in frame[column]]
            assert [row[index] for row in rows[1:]] == expected
        flag_index = list(frame.columns).index("flag")
        value_index = list(frame.columns).index("value")
        assert [row[flag_index] for row in rows[1:]] == [None, False, None]
        assert [row[value_index] for row in rows[1:]] == [None, 10, None]
        assert workbook["Data"].cell(row=3, column=flag_index + 1).data_type == "b"
    finally:
        workbook.close()
    pd.testing.assert_frame_equal(frame, original)


def test_chained_status_survives_derived_columns_and_analysis(chained: JoinResult) -> None:
    """Descriptive metadata does not change numeric classification or calculations."""
    original = chained.frame.copy(deep=True)
    derived = create_derived_column(chained.frame, DerivedColumnSpec("derived", "[value]+2"))
    assert str(derived["derived"].dtype) == "Int64"
    assert derived["derived"].dropna().tolist() == [2**62 + 3]
    pd.testing.assert_frame_equal(derived[original.columns], original)
    overview = analyze_dataset_overview(derived)
    columns = {column.column: column for column in overview.columns}
    assert columns["derived"].missing_count == 2
    assert STATUS_BASE in columns
    assert chained.status_column in columns
    statistics = analyze_descriptive_statistics(derived)
    numeric = next(column for column in statistics.columns if column.column == "value")
    assert numeric.count == 1
    assert numeric.missing_count == 2
    pd.testing.assert_frame_equal(chained.frame, original)


def test_descriptive_status_headers_are_queryable_with_quoted_identifiers(chained: JoinResult) -> None:
    """Exercise the guide's SQL quoting example against an actual chained result."""
    original = chained.frame.copy(deep=True)
    with duckdb.connect() as connection:
        connection.register("joined", chained.frame)
        rows = connection.execute(
            'SELECT "join_status (Film LEFT Actor)", "join_status (Film LEFT Actor) 2" '
            "FROM joined WHERE \"join_status (Film LEFT Actor) 2\" = 'left_only'"
        ).fetchall()
    assert rows == [("both", "left_only")]
    pd.testing.assert_frame_equal(chained.frame, original)
