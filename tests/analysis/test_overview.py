from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.services.analysis.overview import (
    HIGH_MISSING_FRACTION_THRESHOLD,
    SAMPLE_ROW_LIMIT,
    OverviewExportTable,
    analyze_dataset_overview,
    overview_export_tables,
)
from expo_jbm329.services.data_operations.dtypes import SemanticDType
from expo_jbm329.services.file_writer import FileWriter


def test_export_columns_preserves_numeric_counts_and_fractions():
    result = analyze_dataset_overview(pd.DataFrame({"amount": pd.Series([1, None, 1, 2], dtype="Int64")}))
    frame = overview_export_tables(result, (OverviewExportTable.COLUMNS,))["Columns"]
    assert list(frame.columns) == [
        "column",
        "type",
        "storage_type",
        "missing_count",
        "missing_fraction",
        "unique_count",
    ]
    assert frame.iloc[0].tolist() == ["amount", "int", "Int64", 1, 0.25, 2]
    assert pd.api.types.is_integer_dtype(frame["missing_count"].dtype)
    assert pd.api.types.is_float_dtype(frame["missing_fraction"].dtype)
    assert isinstance(frame["column"].dtype, pd.StringDtype)


def test_export_summary_preserves_metrics_type_counts_and_warning_values():
    source = pd.DataFrame({
        "amount": pd.Series([1, None, 1, 2], dtype="Int64"),
        "category": pd.Series(["a", "b", "c", "d"], dtype="string"),
        "sparse": [None, None, 3.0, 4.0],
    })
    result = analyze_dataset_overview(source)
    frame = overview_export_tables(result, (OverviewExportTable.SUMMARY,))["Summary"]

    assert list(frame.columns) == ["section", "metric", "column", "count", "fraction"]
    assert frame[["section", "metric", "count"]].to_numpy().tolist()[:4] == [
        ["dataset", "row_count", 4],
        ["dataset", "column_count", 3],
        ["dataset", "missing_cell_count", 3],
        ["dataset", "duplicate_row_count", 0],
    ]
    assert frame.loc[2, "fraction"] == pytest.approx(0.25)
    assert frame.loc[3, "fraction"] == pytest.approx(0.0)
    assert frame.loc[4:8, ["section", "metric", "count"]].to_numpy().tolist() == [
        ["column_type", "numeric", 2],
        ["column_type", "categorical", 1],
        ["column_type", "datetime", 0],
        ["column_type", "boolean", 0],
        ["column_type", "other", 0],
    ]
    warnings = frame.loc[frame["section"] == "warning"]
    assert warnings[["metric", "column", "count"]].to_numpy().tolist() == [
        ["high_missing_values", "sparse", 2],
        ["high_missing_values", "amount", 1],
    ]
    assert warnings.iloc[0]["fraction"] == pytest.approx(0.5)
    assert pd.api.types.is_integer_dtype(frame["count"].dtype)
    assert pd.api.types.is_float_dtype(frame["fraction"].dtype)
    assert isinstance(frame["section"].dtype, pd.StringDtype)
    assert isinstance(frame["column"].dtype, pd.StringDtype)


def test_export_summary_includes_no_warning_row_for_clean_data():
    frame = overview_export_tables(
        analyze_dataset_overview(pd.DataFrame({"value": [1, 2]})),
        (OverviewExportTable.SUMMARY,),
    )["Summary"]
    warning = frame.iloc[-1]

    assert warning["section"] == "warning"
    assert warning["metric"] == "no_high_missing_columns"
    assert pd.isna(warning["column"])
    assert warning["count"] == 0
    assert warning["fraction"] == 0.0


def test_export_summary_supports_zero_row_and_zero_column_datasets():
    for source in (pd.DataFrame(), pd.DataFrame(index=range(3)), pd.DataFrame({"value": pd.Series(dtype="int64")})):
        summary = overview_export_tables(analyze_dataset_overview(source), (OverviewExportTable.SUMMARY,))["Summary"]
        assert summary.iloc[0]["count"] == source.shape[0]
        assert summary.iloc[1]["count"] == source.shape[1]
        assert summary.iloc[-1]["metric"] == "no_high_missing_columns"


def test_export_summary_roundtrips_through_named_excel_sheet(tmp_path):
    summary = overview_export_tables(
        analyze_dataset_overview(pd.DataFrame({"value": [1, None, 3, 4]})),
        (OverviewExportTable.SUMMARY,),
    )["Summary"]
    path = tmp_path / "overview.xlsx"
    FileWriter().save_excel_sheets({"Summary": summary}, path, index=False, streaming=False)

    roundtripped = pd.read_excel(path, sheet_name="Summary")
    assert list(roundtripped.columns) == ["section", "metric", "column", "count", "fraction"]
    assert roundtripped.loc[0, ["metric", "count"]].tolist() == ["row_count", 4]
    assert roundtripped.loc[2, "fraction"] == pytest.approx(0.25)
    assert roundtripped.iloc[-1]["metric"] == "high_missing_values"
    assert roundtripped.iloc[-1]["count"] == 1


def test_export_sample_is_bounded_typed_and_independent():
    source = pd.DataFrame({
        "integer": pd.Series(range(120), dtype="Int64"),
        "text": pd.Series(["a"] * 120, dtype="string"),
        "category": pd.Categorical(["x", "y"] * 60, categories=["x", "y", "unused"]),
        "flag": pd.Series([True, None] * 60, dtype="boolean"),
        "date": pd.date_range("2024-01-01", periods=120, tz="UTC"),
    })
    expected = source.head(100).copy(deep=True)
    result = analyze_dataset_overview(source)
    source.loc[0, "integer"] = 999
    exported = overview_export_tables(result, (OverviewExportTable.SAMPLE,))["Sample"]
    pd.testing.assert_frame_equal(exported, expected)
    exported.loc[0, "integer"] = 888
    second = overview_export_tables(result, (OverviewExportTable.SAMPLE,))["Sample"]
    pd.testing.assert_frame_equal(second, expected)


def test_export_sample_legacy_structured_rows_preserves_values_and_caps_rows():
    from dataclasses import replace

    result = analyze_dataset_overview(pd.DataFrame({"value": [1]}))
    result = replace(result, sample_frame=None, sample_rows=tuple((index,) for index in range(110)))
    sample = overview_export_tables(result, (OverviewExportTable.SAMPLE,))["Sample"]
    assert sample.shape == (100, 1)
    assert sample.iloc[-1, 0] == 99


@pytest.mark.parametrize("source", [pd.DataFrame(), pd.DataFrame(index=range(3))])
@pytest.mark.parametrize("table", [OverviewExportTable.COLUMNS, OverviewExportTable.SAMPLE])
def test_export_no_columns_is_unavailable(source, table):
    with pytest.raises(ValueError, match="empty"):
        overview_export_tables(analyze_dataset_overview(source), (table,))


def test_export_zero_rows_allows_metadata_only():
    result = analyze_dataset_overview(pd.DataFrame({"integer": pd.Series(dtype="Int64")}))
    assert overview_export_tables(result, (OverviewExportTable.COLUMNS,))["Columns"].shape == (1, 6)
    with pytest.raises(ValueError, match="empty"):
        overview_export_tables(result, (OverviewExportTable.SAMPLE,))
    with pytest.raises(ValueError, match="distinct"):
        overview_export_tables(result, ())
    with pytest.raises(ValueError, match="distinct"):
        overview_export_tables(result, (OverviewExportTable.COLUMNS, OverviewExportTable.COLUMNS))


def test_analyze_dataset_overview_counts_columns_by_semantic_type():
    df = pd.DataFrame({
        "col_int": [1, 2, 3, 4, 5],
        "col_float": [1.1, 2.2, None, 4.4, 5.5],
        "col_bool": [True, False, True, False, True],
        "col_datetime": pd.to_datetime([
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
        ]),
        "col_string": ["a", "b", "c", "d", "e"],
        "col_category": pd.Categorical(["x", "y", "x", "y", "x"]),
        "col_other": [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)],
        "col_high_missing": [None, None, None, 4.0, 5.0],
    })

    result = analyze_dataset_overview(df)

    assert result.row_count == 5
    assert result.column_count == 8
    # col_float has 1 missing, col_high_missing has 3 missing: 4 / (5 * 8) cells.
    assert result.missing_cell_count == 4
    assert result.missing_cell_fraction == 0.1
    # col_int + col_float + col_high_missing.
    assert result.numeric_column_count == 3
    # col_string + col_category.
    assert result.categorical_column_count == 2
    assert result.datetime_column_count == 1
    assert result.boolean_column_count == 1
    # col_other: object dtype containing tuples, not text-like.
    assert result.other_column_count == 1


def test_analyze_dataset_overview_flags_high_missing_columns_sorted_descending():
    df = pd.DataFrame({
        "col_int": [1, 2, 3, 4, 5],
        "col_float": [1.1, 2.2, None, 4.4, 5.5],  # 1/5 = 20% -> at threshold
        "col_high_missing": [None, None, None, 4.0, 5.0],  # 3/5 = 60%
    })

    result = analyze_dataset_overview(df)

    assert result.high_missing_columns == (
        ("col_high_missing", 0.6),
        ("col_float", 0.2),
    )


def test_analyze_dataset_overview_does_not_flag_columns_below_threshold():
    # 1 missing out of 10 rows = 10%, comfortably below the 20% threshold.
    df = pd.DataFrame({"col": [None, *[1.0] * 9]})
    assert HIGH_MISSING_FRACTION_THRESHOLD > 1 / 10

    result = analyze_dataset_overview(df)

    assert result.high_missing_columns == ()


def test_analyze_dataset_overview_counts_duplicate_rows():
    df = pd.DataFrame({
        "a": [1, 2, 1, 4, 1],
        "b": [10, 20, 10, 40, 10],
    })

    result = analyze_dataset_overview(df)

    # Rows at index 2 and 4 duplicate the row at index 0 (pandas keeps the
    # first occurrence as non-duplicate).
    assert result.duplicate_row_count == 2
    assert result.duplicate_row_fraction == 0.4


def test_analyze_dataset_overview_handles_dataframe_with_no_duplicates():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

    result = analyze_dataset_overview(df)

    assert result.duplicate_row_count == 0
    assert result.duplicate_row_fraction == 0.0


def test_analyze_dataset_overview_handles_completely_empty_dataframe():
    result = analyze_dataset_overview(pd.DataFrame())

    assert result.row_count == 0
    assert result.column_count == 0
    assert result.missing_cell_count == 0
    assert result.missing_cell_fraction == 0.0
    assert result.duplicate_row_count == 0
    assert result.duplicate_row_fraction == 0.0
    assert result.numeric_column_count == 0
    assert result.categorical_column_count == 0
    assert result.datetime_column_count == 0
    assert result.boolean_column_count == 0
    assert result.other_column_count == 0
    assert result.high_missing_columns == ()


def test_analyze_dataset_overview_handles_rows_with_no_columns():
    df = pd.DataFrame(index=range(5))

    result = analyze_dataset_overview(df)

    assert result.row_count == 5
    assert result.column_count == 0
    assert result.missing_cell_fraction == 0.0
    assert result.duplicate_row_count == 0
    assert result.duplicate_row_fraction == 0.0


def test_analyze_dataset_overview_handles_columns_with_no_rows():
    df = pd.DataFrame({"a": pd.Series(dtype="int64"), "b": pd.Series(dtype="float64")})

    result = analyze_dataset_overview(df)

    assert result.row_count == 0
    assert result.column_count == 2
    assert result.numeric_column_count == 2
    assert result.missing_cell_fraction == 0.0
    assert result.duplicate_row_fraction == 0.0
    assert result.sample_rows == ()
    assert result.sample_truncated is False
    assert [column.missing_fraction for column in result.columns] == [0.0, 0.0]


def test_analyze_dataset_overview_summarizes_every_column():
    df = pd.DataFrame({
        "col_int": [1, 2, 2, None],
        "col_text": ["a", "b", "b", "c"],
    })

    result = analyze_dataset_overview(df)

    by_name = {column.column: column for column in result.columns}
    assert [column.column for column in result.columns] == ["col_int", "col_text"]
    assert by_name["col_int"].semantic_dtype is SemanticDType.FLOAT
    assert by_name["col_int"].missing_count == 1
    assert by_name["col_int"].missing_fraction == 0.25
    # nunique ignores the missing value.
    assert by_name["col_int"].unique_count == 2
    assert by_name["col_text"].semantic_dtype is SemanticDType.STRING
    assert by_name["col_text"].dtype_name == str(df["col_text"].dtype)
    assert by_name["col_text"].missing_count == 0
    assert by_name["col_text"].unique_count == 3


def test_analyze_dataset_overview_samples_raw_values_up_to_the_limit():
    df = pd.DataFrame({"a": range(SAMPLE_ROW_LIMIT + 10), "b": ["x"] * (SAMPLE_ROW_LIMIT + 10)})

    result = analyze_dataset_overview(df)

    assert result.sample_columns == ("a", "b")
    assert len(result.sample_rows) == SAMPLE_ROW_LIMIT
    assert result.sample_truncated is True
    # Raw, unformatted values: presentation belongs to the view.
    assert result.sample_rows[0] == (0, "x")


def test_analyze_dataset_overview_keeps_every_row_when_below_the_sample_limit():
    df = pd.DataFrame({"a": [1, 2, 3]})

    result = analyze_dataset_overview(df)

    assert len(result.sample_rows) == 3
    assert result.sample_truncated is False


def test_analyze_dataset_overview_handles_duplicate_column_labels():
    df = pd.DataFrame([[1, 2], [3, 4]], columns=["a", "a"])

    result = analyze_dataset_overview(df)

    assert [column.column for column in result.columns] == ["a", "a"]
    assert [column.unique_count for column in result.columns] == [2, 2]
    assert result.numeric_column_count == 2
