from __future__ import annotations

import pandas as pd

from expo_jbm329.services.analysis.overview import (
    HIGH_MISSING_FRACTION_THRESHOLD,
    analyze_dataset_overview,
)


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
