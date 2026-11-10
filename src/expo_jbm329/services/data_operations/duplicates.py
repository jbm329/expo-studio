"""Shared duplicate-row removal for tabular data operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def remove_duplicate_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicate rows using pandas equality across all columns.

    Keep the first occurrence in input order without modifying the source.
    Source index labels do not participate in duplicate comparison. Values,
    including nested objects, are not normalized before comparison.

    Args:
        frame: The dataframe to deduplicate.

    Returns:
        A dataframe with duplicate rows removed and its index reset by pandas.
        For empty frames, pandas preserves the existing index. Column order
        and dtypes are preserved.

    Raises:
        TypeError: If pandas cannot deduplicate the supplied values.
    """
    return frame.drop_duplicates(ignore_index=True)
