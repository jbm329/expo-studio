"""Qt-free datetime presentation metadata for result tabs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pandas.api.types import is_datetime64_any_dtype

if TYPE_CHECKING:
    import pandas as pd

DATETIME_SCAN_CHUNK_ROWS = 65_536


def build_datetime_date_only_columns(df: pd.DataFrame) -> dict[int, bool]:
    """Determine which datetime columns contain only exact midnight values.

    Inspect every populated value, using stored local wall-clock components
    for timezone-aware columns. Missing values are ignored; empty and
    all-missing columns are not classified as date-only.

    This function does not mutate the dataset or infer types from text. Run it
    in a worker against the existing dataset snapshot before GUI presentation.
    Temporary scan memory is bounded independently of the dataset's row count.

    Args:
        df: Dataset whose datetime presentation is being prepared.

    Returns:
        Positional datetime column indices mapped to their date-only status.
    """
    return {
        column: _is_date_only(df.iloc[:, column])
        for column, dtype in enumerate(df.dtypes)
        if is_datetime64_any_dtype(dtype)
    }


def _is_date_only(series: pd.Series) -> bool:
    """Check all datetime values without losing submicrosecond precision."""
    has_value = False
    for start in range(0, len(series), DATETIME_SCAN_CHUNK_ROWS):
        values = series.iloc[start : start + DATETIME_SCAN_CHUNK_ROWS].dropna()
        if values.empty:
            continue
        has_value = True
        components = values.dt
        if (
            bool((components.hour != 0).any())
            or bool((components.minute != 0).any())
            or bool((components.second != 0).any())
            or bool((components.microsecond != 0).any())
            or bool((components.nanosecond != 0).any())
        ):
            return False
    return has_value
