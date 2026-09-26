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
from typing import TYPE_CHECKING

from expo_jbm329.services.data_operations.analytics import null_stats
from expo_jbm329.services.data_operations.dtypes import SemanticDType, classify_series_dtype

if TYPE_CHECKING:
    import pandas as pd

# A column is flagged as a "high missing" warning once its share of missing
# values crosses this fraction. 20% is a common, conservative data-quality
# heuristic: low enough to surface genuinely sparse columns, high enough to
# avoid flagging every column in typically-messy real-world datasets.
HIGH_MISSING_FRACTION_THRESHOLD = 0.2


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


_NUMERIC_DTYPES = frozenset({SemanticDType.INT, SemanticDType.FLOAT})
_CATEGORICAL_DTYPES = frozenset({SemanticDType.CATEGORY, SemanticDType.STRING})


def _count_columns_by_semantic_type(df: pd.DataFrame) -> dict[SemanticDType | None, int]:
    """Return the number of columns per semantic dtype bucket."""
    counts: dict[SemanticDType | None, int] = {}
    for column in df.columns:
        semantic = classify_series_dtype(df[column])
        counts[semantic] = counts.get(semantic, 0) + 1
    return counts


def _high_missing_columns(df: pd.DataFrame) -> tuple[tuple[str, float], ...]:
    """Return columns whose missing fraction meets the warning threshold."""
    if df.shape[0] == 0 or df.shape[1] == 0:
        return ()

    # null_stats() reports pct_null already scaled to 0-100; convert back to
    # a 0-1 fraction to keep this result's fields consistently fraction-based.
    stats = null_stats(df)
    fractions = (stats["pct_null"] / 100.0).astype(float)

    flagged = fractions[fractions >= HIGH_MISSING_FRACTION_THRESHOLD]
    flagged = flagged.sort_values(ascending=False)

    return tuple((str(name), float(pct)) for name, pct in flagged.items())


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

    missing_cell_count = int(df.isna().sum().sum()) if total_cells > 0 else 0
    missing_cell_fraction = (missing_cell_count / total_cells) if total_cells > 0 else 0.0

    duplicate_row_count = int(df.duplicated().sum()) if row_count > 0 else 0
    duplicate_row_fraction = (duplicate_row_count / row_count) if row_count > 0 else 0.0

    type_counts = _count_columns_by_semantic_type(df)

    numeric_column_count = sum(type_counts.get(t, 0) for t in _NUMERIC_DTYPES)
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
        high_missing_columns=_high_missing_columns(df),
    )
