"""Tests for the shared analysis column helpers."""

from __future__ import annotations

import pandas as pd

from expo_jbm329.services.analysis.columns import NUMERIC_DTYPES, numeric_columns
from expo_jbm329.services.data_operations.dtypes import SemanticDType


def test_numeric_dtypes_are_int_and_float() -> None:
    assert frozenset({SemanticDType.INT, SemanticDType.FLOAT}) == NUMERIC_DTYPES


def test_numeric_columns_keeps_only_int_and_float_in_column_order() -> None:
    df = pd.DataFrame({
        "f": [1.5, 2.5],
        "s": ["a", "b"],
        "i": [1, 2],
        "b": [True, False],
        "d": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "ni": pd.array([1, None], dtype="Int64"),
        "c": pd.Categorical(["x", "y"]),
    })

    assert numeric_columns(df) == ("f", "i", "ni")


def test_numeric_columns_returns_string_names() -> None:
    df = pd.DataFrame({0: [1, 2], 1: ["a", "b"]})

    assert numeric_columns(df) == ("0",)


def test_numeric_columns_of_empty_frame_is_empty() -> None:
    assert numeric_columns(pd.DataFrame()) == ()
