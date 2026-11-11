"""Verify exact derived integers using actual combined datasets and outputs."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING, Literal

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from expo_jbm329.services.analysis.overview import analyze_dataset_overview
from expo_jbm329.services.analysis.regression import classify_predictor_columns
from expo_jbm329.services.analysis.statistics import analyze_descriptive_statistics
from expo_jbm329.services.data_operations.concat import ConcatRequest, concat_dataframes
from expo_jbm329.services.data_operations.derived_column.derived_column_parser import DerivedColumnFormulaError
from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
    create_derived_column,
    preview_derived_column,
)
from expo_jbm329.services.data_operations.dtypes import get_numeric_columns
from expo_jbm329.services.data_operations.joins import JoinRequest, join_dataframes
from expo_jbm329.services.file_writer import FileWriter

if TYPE_CHECKING:
    from pathlib import Path

Workflow = Literal["join", "concat-first", "concat-second"]
WORKFLOWS: list[Workflow] = ["join", "concat-first", "concat-second"]


def combine(workflow: Workflow, dtype: str, *, large: bool = True) -> pd.DataFrame:
    """Combine real inputs with one source NULL and two generated gaps."""
    value = 2**53 + 1 if large else 10
    numeric = pd.Series([value, None, value + 2], dtype="Int64" if dtype == "category" else dtype)
    if dtype == "category":
        numeric = numeric.astype("category")
    source = pd.DataFrame({
        "id": [2, 3, 4],
        "value": numeric,
        "when": pd.to_datetime(pd.Series(["2026-01-01", None, "2026-09-01"], dtype="string")),
    })
    other = pd.DataFrame({"id": [0, 1]})
    original, other_original = source.copy(deep=True), other.copy(deep=True)
    if workflow == "join":
        frame = join_dataframes(JoinRequest(pd.DataFrame({"id": [0, 1, 2, 3, 4]}), source, ["id"], ["id"], how="left"))
    elif workflow == "concat-first":
        frame = concat_dataframes(ConcatRequest(source, other))
    else:
        frame = concat_dataframes(ConcatRequest(other, source))
    assert_frame_equal(source, original)
    assert_frame_equal(other, other_original)
    assert frame.loc[frame.id.isin([0, 1, 3]), "value"].isna().all()
    return frame


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize("dtype", ["Int64", "UInt64", "int64[pyarrow]", "uint64[pyarrow]", "category"])
@pytest.mark.parametrize(
    "formula",
    ["[value]+2", "+([value]*2)", "IF([value] IS NULL; 0; [value]+2)", "YEAR([when])+1"],
)
def test_combined_integer_values_remain_exact_in_creation_preview_and_overwrite(
    workflow: Workflow, dtype: str, formula: str
) -> None:
    source = combine(workflow, dtype)
    source.index = pd.MultiIndex.from_tuples([("row", 1)] * len(source), names=["group", "number"])
    original = source.copy(deep=True)
    output_dtype = "UInt64" if dtype.lower().startswith("u") and not formula.startswith("YEAR") else "Int64"
    expected_values: list[int | None] = []
    for row_id in source.id:
        if row_id in {2, 4}:
            value = 2**53 + 1 + (2 if row_id == 4 else 0)
            expected_values.append(2027 if formula.startswith("YEAR") else value * 2 if "*" in formula else value + 2)
        else:
            expected_values.append(0 if formula.startswith("IF") else None)
    expected = pd.Series(expected_values, index=source.index, dtype=output_dtype, name="Result")
    spec = DerivedColumnSpec("Result", formula)
    created = create_derived_column(source, spec, insertion_index=1)
    assert created.columns[1] == "Result"
    assert_series_equal(created.Result, expected)
    preview = preview_derived_column(source, spec, rows=4)
    assert preview.ok and preview.data is not None
    assert_series_equal(preview.data.Result, created.Result.head(4))
    overwritten = create_derived_column(source, DerivedColumnSpec("value", formula, overwrite_existing=True))
    assert_series_equal(overwritten.value, expected.rename("value"))
    assert_frame_equal(source, original)


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_derived_integer_is_recognized_by_existing_numeric_analysis(workflow: Workflow) -> None:
    source = combine(workflow, "Int64", large=False)
    frame = create_derived_column(source, DerivedColumnSpec("Result", "[value]*2"))
    original = frame.copy(deep=True)
    assert "Result" in get_numeric_columns(frame)
    assert "Result" in classify_predictor_columns(frame).numeric
    overview = analyze_dataset_overview(frame)
    column = next(column for column in overview.columns if column.column == "Result")
    assert column.missing_count == 3
    statistics = analyze_descriptive_statistics(frame)
    values = next(column for column in statistics.columns if column.column == "Result")
    assert values.count == 2
    assert values.missing_count == 3
    assert values.mean == pytest.approx(22)
    assert sum(values.histogram_counts) == 2
    assert_frame_equal(frame, original)


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize("dtype", ["Int64", "UInt64"])
@pytest.mark.parametrize("chunk_size", [None, 1])
def test_actual_derived_csv_preserves_exact_digits_and_nulls(
    tmp_path: Path, workflow: Workflow, dtype: str, chunk_size: int | None
) -> None:
    source = combine(workflow, dtype)
    frame = create_derived_column(source, DerivedColumnSpec("Result", "[value]+2"))
    original = frame.copy(deep=True)
    path = tmp_path / "derived.csv"
    FileWriter().save_csv(frame, path, chunk_size_rows=chunk_size, na_rep="")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = {int(row["id"]): row for row in csv.DictReader(stream)}
    assert rows[2]["Result"] == str(2**53 + 3)
    assert rows[4]["Result"] == str(2**53 + 5)
    assert all(rows[row_id]["Result"] == "" for row_id in (0, 1, 3))
    assert_frame_equal(frame, original)


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize("dtype", ["Int64", "UInt64"])
@pytest.mark.parametrize("suffix", [".parquet", ".feather"])
def test_actual_derived_binary_roundtrip_preserves_values_and_schema(
    tmp_path: Path, workflow: Workflow, dtype: str, suffix: str
) -> None:
    frame = create_derived_column(combine(workflow, dtype), DerivedColumnSpec("Result", "[value]+2"))
    original = frame.copy(deep=True)
    path = tmp_path / f"derived{suffix}"
    assert FileWriter().save_datafile(frame, path) == path
    restored = pd.read_parquet(path) if suffix == ".parquet" else pd.read_feather(path)
    assert_frame_equal(restored, frame)
    assert_frame_equal(frame, original)


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_combined_outputs_preserve_float_override_text_and_structured_errors(workflow: Workflow) -> None:
    source = combine(workflow, "Int64")
    original = source.copy(deep=True)
    integer = create_derived_column(source, DerivedColumnSpec("Result", "[value]+2"))
    floating = create_derived_column(source, DerivedColumnSpec("Result", "[value]+2", output_dtype="Float64"))
    assert_series_equal(floating.Result, integer.Result.astype("Float64"))
    text = create_derived_column(source, DerivedColumnSpec("Result", "IF([value] IS NULL; 'Missing'; 'Present')"))
    assert_series_equal(
        text.Result,
        pd.Series(
            ["Present" if row_id in {2, 4} else "Missing" for row_id in source.id], dtype="string", name="Result"
        ),
    )
    spec = DerivedColumnSpec("Result", "[value]*2048")
    with pytest.raises(DerivedColumnFormulaError) as caught:
        create_derived_column(source, spec)
    assert caught.value.code == "integer_overflow"
    preview = preview_derived_column(source, spec, rows=len(source))
    assert not preview.ok and preview.data is None and preview.message == "integer_overflow"
    assert_frame_equal(source, original)
