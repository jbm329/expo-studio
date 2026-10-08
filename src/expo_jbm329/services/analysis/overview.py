"""Dataset Overview analysis.

Computes a high-level, structural summary of a DataFrame: row/column
counts, missing-value coverage, duplicate rows, and a breakdown of column
counts by semantic type. Intentionally limited to structural/descriptive
information - outlier detection and correlation/relationship hints are
covered by their own dedicated analyses (Outlier Detection, Correlation
Explorer) rather than duplicated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import pandas as pd

from expo_jbm329.services.analysis.columns import NUMERIC_DTYPES
from expo_jbm329.services.data_operations.dtypes import SemanticDType, classify_series_dtype

# A column is flagged as a "high missing" warning once its share of missing
# values crosses this fraction. 20% is a common, conservative data-quality
# heuristic: low enough to surface genuinely sparse columns, high enough to
# avoid flagging every column in typically-messy real-world datasets.
HIGH_MISSING_FRACTION_THRESHOLD = 0.2

# Number of leading rows kept as a preview of the raw data. Enough to spot
# encoding/parsing problems and get a feel for the values without turning
# the overview into a second data grid.
SAMPLE_ROW_LIMIT = 100


class OverviewExportTable(StrEnum):
    """Structured Overview tables available for data export."""

    COLUMNS = "Columns"
    SAMPLE = "Sample"


class OverviewExportFormat(StrEnum):
    """Export pipelines supported for Overview tables."""

    CSV = "csv"
    EXCEL = "excel"
    BINARY = "binary"


@dataclass(frozen=True, slots=True)
class ColumnOverview:
    """Per-column structural summary shown in the overview's column table.

    Attributes:
        column: Column name.
        semantic_dtype: The column's simplified semantic type.
        dtype_name: The underlying pandas dtype, for users who need the
            exact storage type rather than the semantic bucket.
        missing_count: Number of missing values in the column.
        missing_fraction: Share of missing values, in the ``[0, 1]`` range.
        unique_count: Number of distinct non-missing values.
    """

    column: str
    semantic_dtype: SemanticDType
    dtype_name: str
    missing_count: int
    missing_fraction: float
    unique_count: int


@dataclass(frozen=True, slots=True)
class DatasetOverviewResult:
    """Structural overview of a DataFrame.

    All `*_fraction` fields are stored as a fraction in the ``[0, 1]`` range
    (not already multiplied by 100), matching the input convention expected
    by `expo_jbm329.utils.format_utils.fmt_pct`.

    Attributes:
        row_count: Total number of rows.
        column_count: Total number of columns.
        missing_cell_count: Total number of missing (NaN/None/NaT) cells.
        missing_cell_fraction: Fraction of all cells that are missing.
        duplicate_row_count: Number of fully duplicated rows.
        duplicate_row_fraction: Fraction of rows that are duplicates.
        numeric_column_count: Columns classified as int or float.
        categorical_column_count: Columns classified as category or string.
        datetime_column_count: Columns classified as datetime.
        boolean_column_count: Columns classified as bool.
        other_column_count: Columns that fit none of the above buckets.
        high_missing_columns: Columns whose missing fraction is at or above
            `HIGH_MISSING_FRACTION_THRESHOLD`, as (column_name, fraction)
            pairs sorted by missing fraction, descending.
        columns: Per-column summaries, in the DataFrame's column order.
        sample_columns: Column names backing `sample_rows`.
        sample_rows: The first `SAMPLE_ROW_LIMIT` rows as raw values, kept
            unformatted so the view owns all locale-aware presentation.
        sample_truncated: Whether the dataset has more rows than the sample.
        sample_frame: Owned, bounded dtype-preserving snapshot for export.
            Consumers must never mutate it; export helpers return independent
            frames. None supports results created without an export snapshot.
    """

    row_count: int
    column_count: int

    missing_cell_count: int
    missing_cell_fraction: float

    duplicate_row_count: int
    duplicate_row_fraction: float

    numeric_column_count: int
    categorical_column_count: int
    datetime_column_count: int
    boolean_column_count: int
    other_column_count: int

    high_missing_columns: tuple[tuple[str, float], ...] = field(default_factory=tuple)

    columns: tuple[ColumnOverview, ...] = field(default_factory=tuple)

    sample_columns: tuple[str, ...] = field(default_factory=tuple)
    sample_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    sample_truncated: bool = False
    # This owned, bounded snapshot must not be mutated after publication.
    sample_frame: pd.DataFrame | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class OverviewExportRequest:
    """A selection tied to the exact displayed Overview result."""

    result: DatasetOverviewResult
    tables: tuple[OverviewExportTable, ...]
    format: OverviewExportFormat


def overview_export_tables(
    result: DatasetOverviewResult,
    tables: tuple[OverviewExportTable, ...],
) -> dict[str, pd.DataFrame]:
    """Build independent export frames from structured Overview data.

    Missing fractions remain numeric fractions, not formatted percentages.
    Samples contain at most the first 100 rows and never access the dataset.
    Empty tables are not exportable, matching the single-frame exporters.

    Args:
        result: The displayed, stable analysis snapshot.
        tables: Nonempty, distinct supported table choices.

    Returns:
        Ordered named frames owned by the export operation.

    Raises:
        ValueError: If a selection is empty, repeated, unsupported or unavailable.
    """
    if not tables or len(set(tables)) != len(tables):
        message = "Select distinct Overview tables."
        raise ValueError(message)
    frames: dict[str, pd.DataFrame] = {}
    for table in tables:
        if table is not OverviewExportTable.COLUMNS and table is not OverviewExportTable.SAMPLE:
            message = "Unsupported Overview table."
            raise ValueError(message)
        match table:
            case OverviewExportTable.COLUMNS:
                frame = pd.DataFrame(
                    [
                        (
                            column.column,
                            column.semantic_dtype.value,
                            column.dtype_name,
                            column.missing_count,
                            column.missing_fraction,
                            column.unique_count,
                        )
                        for column in result.columns
                    ],
                    columns=["column", "type", "storage_type", "missing_count", "missing_fraction", "unique_count"],
                ).astype({"column": pd.StringDtype(), "type": pd.StringDtype(), "storage_type": pd.StringDtype()})
            case OverviewExportTable.SAMPLE:
                frame = (
                    result.sample_frame.head(SAMPLE_ROW_LIMIT).copy(deep=True)
                    if result.sample_frame is not None
                    else pd.DataFrame(result.sample_rows[:SAMPLE_ROW_LIMIT], columns=list(result.sample_columns))
                )
                frame.columns = list(result.sample_columns)
            case _:
                message = "Unsupported Overview table."
                raise ValueError(message)
        if frame.empty:
            message = f"Overview table {table.value} is empty."
            raise ValueError(message)
        frames[table.value] = frame
    return frames


_CATEGORICAL_DTYPES = frozenset({SemanticDType.CATEGORY, SemanticDType.STRING})


def _column_overviews(df: pd.DataFrame) -> tuple[ColumnOverview, ...]:
    """Summarize every column once, for both the table and the type counts."""
    row_count = int(df.shape[0])
    overviews: list[ColumnOverview] = []

    for position, column in enumerate(df.columns):
        # Positional access, because duplicate column labels would make
        # df[column] return a DataFrame instead of a Series.
        series = df.iloc[:, position]
        missing_count = int(series.isna().sum())
        overviews.append(
            ColumnOverview(
                column=str(column),
                semantic_dtype=classify_series_dtype(series),
                dtype_name=str(series.dtype),
                missing_count=missing_count,
                missing_fraction=(missing_count / row_count) if row_count > 0 else 0.0,
                unique_count=int(series.nunique(dropna=True)),
            )
        )

    return tuple(overviews)


def _high_missing_columns(columns: tuple[ColumnOverview, ...]) -> tuple[tuple[str, float], ...]:
    """Return columns whose missing fraction meets the warning threshold."""
    flagged = [
        (column.column, column.missing_fraction)
        for column in columns
        if column.missing_fraction >= HIGH_MISSING_FRACTION_THRESHOLD
    ]
    # Stable sort: equally-sparse columns keep their original column order.
    flagged.sort(key=lambda item: item[1], reverse=True)
    return tuple(flagged)


def _sample_rows(df: pd.DataFrame) -> tuple[tuple[object, ...], ...]:
    """Return the first `SAMPLE_ROW_LIMIT` rows as plain value tuples."""
    if df.shape[0] == 0 or df.shape[1] == 0:
        return ()
    head = df.head(SAMPLE_ROW_LIMIT)
    return tuple(tuple(row) for row in head.itertuples(index=False, name=None))


def analyze_dataset_overview(df: pd.DataFrame) -> DatasetOverviewResult:
    """Compute a structural Dataset Overview for a DataFrame.

    Args:
        df: The DataFrame to analyze. Never mutated.

    Returns:
        A populated `DatasetOverviewResult`.
    """
    row_count = int(df.shape[0])
    column_count = int(df.shape[1])
    total_cells = row_count * column_count

    columns = _column_overviews(df)

    missing_cell_count = sum(column.missing_count for column in columns)
    missing_cell_fraction = (missing_cell_count / total_cells) if total_cells > 0 else 0.0

    duplicate_row_count = int(df.duplicated().sum()) if row_count > 0 else 0
    duplicate_row_fraction = (duplicate_row_count / row_count) if row_count > 0 else 0.0

    type_counts: dict[SemanticDType, int] = {}
    for column in columns:
        type_counts[column.semantic_dtype] = type_counts.get(column.semantic_dtype, 0) + 1

    numeric_column_count = sum(type_counts.get(t, 0) for t in NUMERIC_DTYPES)
    categorical_column_count = sum(type_counts.get(t, 0) for t in _CATEGORICAL_DTYPES)
    datetime_column_count = type_counts.get(SemanticDType.DATETIME, 0)
    boolean_column_count = type_counts.get(SemanticDType.BOOL, 0)
    other_column_count = type_counts.get(SemanticDType.OTHER, 0)

    return DatasetOverviewResult(
        row_count=row_count,
        column_count=column_count,
        missing_cell_count=missing_cell_count,
        missing_cell_fraction=missing_cell_fraction,
        duplicate_row_count=duplicate_row_count,
        duplicate_row_fraction=duplicate_row_fraction,
        numeric_column_count=numeric_column_count,
        categorical_column_count=categorical_column_count,
        datetime_column_count=datetime_column_count,
        boolean_column_count=boolean_column_count,
        other_column_count=other_column_count,
        high_missing_columns=_high_missing_columns(columns),
        columns=columns,
        sample_columns=tuple(str(column) for column in df.columns),
        sample_rows=_sample_rows(df),
        sample_truncated=row_count > SAMPLE_ROW_LIMIT,
        sample_frame=df.head(SAMPLE_ROW_LIMIT).copy(deep=True),
    )
