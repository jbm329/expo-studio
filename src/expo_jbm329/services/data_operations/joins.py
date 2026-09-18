"""Dataframe join and concatenation operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import pandas as pd
from pandas import CategoricalDtype
from pandas.api.types import is_numeric_dtype, is_string_dtype

if TYPE_CHECKING:
    from collections.abc import Sequence

JoinHow = Literal["inner", "left", "right", "outer"]


@dataclass(slots=True)
class JoinMetadata:
    """Metadata describing join quality and characteristics."""

    match_rate: float
    left_only: float
    right_only: float
    cardinality: str
    estimated_rows: int


@dataclass(frozen=True)
class JoinRequest:
    """Immutable join configuration passed from UI/controller layer.

    Attributes:
        left: Left dataframe.
        right: Right dataframe.
        left_on: Column names to join on in the left dataframe.
        right_on: Column names to join on in the right dataframe.
        how: Join type: 'inner', 'left', 'right', 'outer'.
        suffixes: Suffixes for conflicting column names.
    """

    left: pd.DataFrame
    right: pd.DataFrame
    left_on: Sequence[str]
    right_on: Sequence[str]
    how: JoinHow = "inner"
    suffixes: tuple[str, str] = ("_left", "_right")


def join_dataframes(cfg: JoinRequest) -> pd.DataFrame:
    """Perform a relational join between two DataFrames.

    Args:
        cfg: Fully specified join configuration.

    Returns:
        The resulting merged dataframe.

    Note:
        * Keys are aligned 1:1 (left_on[i] corresponds to right_on[i]).
        * Multi-key joins are supported.
    """
    if len(cfg.left_on) != len(cfg.right_on):
        msg = f"left_on and right_on must have same length (got {len(cfg.left_on)} vs {len(cfg.right_on)})"
        raise ValueError(msg)

    return cfg.left.merge(
        cfg.right,
        left_on=list(cfg.left_on),
        right_on=list(cfg.right_on),
        how=cfg.how,
        suffixes=cfg.suffixes,
        indicator="join_status",
    )


def detect_join_keys(left: pd.DataFrame, right: pd.DataFrame) -> list[str]:
    """Detect potential join keys based on matching column names AND compatible dtypes.

    Args:
        left: First dataframe.
        right: Second dataframe.

    Returns:
        Column names suitable as join keys.

    Note:
        This is a heuristic:
        * Column names must match.
        * Dtypes must be compatible (numeric with numeric, string with string).
        * More rules can be added as needed.
    """
    matches: list[str] = []

    for col in left.columns:
        if col not in right.columns:
            continue

        l_col = left[col]
        r_col = right[col]

        # Numeric to numeric
        if is_numeric_dtype(l_col) and is_numeric_dtype(r_col):
            matches.append(col)
            continue

        # String to string
        if is_string_dtype(l_col) and is_string_dtype(r_col):
            matches.append(col)
            continue

        # Categorical or object-like text
        if isinstance(l_col.dtype, CategoricalDtype) and isinstance(r_col.dtype, CategoricalDtype):
            matches.append(col)
            continue

        if l_col.dtype == "object" and r_col.dtype == "object":
            matches.append(col)
            continue

    return matches


def concat_rows(*frames: pd.DataFrame, join: Literal["outer", "inner"] = "outer") -> pd.DataFrame:
    """Concatenate multiple dataframes row-wise (append).

    Args:
        *frames: Dataframes to concatenate.
        join: Column alignment strategy.

    Returns:
        Combined dataframe with reset index.
    """
    if not frames:
        msg = "No dataframes were provided for concat_rows()."
        raise ValueError(msg)

    return pd.concat(frames, axis=0, join=join).reset_index(drop=True)


def concat_columns(*frames: pd.DataFrame, join: Literal["outer", "inner"] = "outer") -> pd.DataFrame:
    """Concatenate multiple dataframes column-wise.

    Args:
        *frames: Dataframes to concatenate.
        join: Row alignment strategy.

    Returns:
        Combined dataframe by columns.
    """
    if not frames:
        msg = "No dataframes were provided for concat_columns()."
        raise ValueError(msg)

    return pd.concat(frames, axis=1, join=join)
