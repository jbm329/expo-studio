"""Dataframe concatenation services."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class ConcatRequest:
    """Configuration for concatenating two dataframes.

    Attributes:
        left: The first dataframe.
        right: The second dataframe.
        remove_duplicates: If True, behaves like SQL UNION (deduplicates).
            If False (default), behaves like SQL UNION ALL.
    """
    left: pd.DataFrame
    right: pd.DataFrame
    remove_duplicates: bool = False


def concat_dataframes(req: ConcatRequest) -> pd.DataFrame:
    """Perform a vertical concat (union) of two dataframes.

    Rules:
        * Name-based column union (Pandas default).
        * Missing columns filled with NaN.
        * Row order preserved: left-rows first, then right-rows.
        * Index ignored (new sequential index).
        * Optional deduplication (slow -> only done when requested).

    This behavior matches:
        * PowerQuery's default "Append Queries"
        * Pandas.concat
        * Excel PQ Combine
        * SQL UNION ALL (default)

    Args:
        req: The concatenation request configuration.

    Returns:
        The concatenated dataframe.
    """
    left = req.left
    right = req.right

    # --- Perform concat ---
    result = pd.concat(
        [left, right],
        axis=0,
        ignore_index=True,
        sort=False,    # preserve column order; don't sort automatically
    )

    # --- Optional deduplicate ---
    if req.remove_duplicates:
        # Pandas drop_duplicates keeps first occurrence, similar to SQL UNION
        result = result.drop_duplicates(ignore_index=True)

    return result
