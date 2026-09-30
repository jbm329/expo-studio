"""Shared column classification rules for the analysis services.

Keeps a single definition of what counts as a "numeric" column, so every
analysis agrees on which columns it offers and analyzes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from expo_jbm329.services.data_operations.dtypes import SemanticDType, classify_series_dtype

if TYPE_CHECKING:
    import pandas as pd

# Booleans are deliberately excluded: they are better analyzed as categories.
NUMERIC_DTYPES = frozenset({SemanticDType.INT, SemanticDType.FLOAT})


def numeric_columns(df: pd.DataFrame) -> tuple[str, ...]:
    """Return every numeric (int or float) column name, in column order.

    Args:
        df: The DataFrame to inspect. Never mutated.

    Returns:
        Names of every column whose semantic dtype is in `NUMERIC_DTYPES`.
    """
    return tuple(str(column) for column in df.columns if classify_series_dtype(df[column]) in NUMERIC_DTYPES)
