"""Contracts for precision-safe raw column finalization."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from functools import partial
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from expo_jbm329.utils.dataframe_construction import dataframe_from_raw_columns, dataframe_from_raw_values

if TYPE_CHECKING:
    from collections.abc import Iterator


def raise_when_cancelled(checks: Iterator[bool]) -> None:
    """Raise once the selected cancellation boundary is reached."""
    if next(checks, True):
        raise RuntimeError("cancelled")


@pytest.mark.parametrize("coerce_float", [False, True])
@pytest.mark.parametrize(
    "values",
    [
        [None, None],
        [float("nan"), float("nan")],
        ["001", None],
        [1.0, None],
        [1, "text", None],
        [True, 1, None],
        [Decimal("1.25"), None],
        [Decimal("1.25"), "text", None],
        [b"data", None],
        [datetime.fromisoformat("2025-01-01T00:00:00+02:00"), None],
        [[1], {"key": 2}, None],
        [2**64, None],
        [-1, 2**63, None],
    ],
)
def test_unrelated_column_inference_matches_legacy(values: list[object], coerce_float: bool) -> None:
    raw = pd.DataFrame({"value": pd.Series(values, dtype=object)})
    original = raw.copy(deep=True)
    expected = (
        pd.DataFrame.from_records([(value,) for value in values], columns=["value"], coerce_float=True)
        if coerce_float
        else pd.DataFrame({"value": pd.Series(values)})
    )
    if values == [2**64, None] or values == [-1, 2**63, None]:
        expected = raw.copy()
    actual = dataframe_from_raw_columns(raw, check_cancel=lambda: None, coerce_float=coerce_float)
    pd.testing.assert_frame_equal(actual, expected)
    pd.testing.assert_frame_equal(raw, original)


def test_columnar_construction_preserves_duplicate_labels_and_index() -> None:
    raw = pd.DataFrame([[2**53 + 1, True], [None, None]], columns=["same", "same"], dtype=object)
    raw.index = pd.Index([7, 7], name="source")
    original = raw.copy(deep=True)
    result = dataframe_from_raw_columns(raw, check_cancel=lambda: None)
    assert result.dtypes.astype(str).tolist() == ["Int64", "boolean"]
    assert result.iloc[0, 0] == 2**53 + 1
    pd.testing.assert_index_equal(result.index, raw.index)
    pd.testing.assert_index_equal(result.columns, raw.columns)
    pd.testing.assert_frame_equal(raw, original)


@pytest.mark.parametrize("shape", [(0, 2), (2, 0)])
def test_empty_columnar_frames_preserve_schema_and_rows(shape: tuple[int, int]) -> None:
    raw = pd.DataFrame(index=range(shape[0]), columns=range(shape[1]), dtype=object)
    pd.testing.assert_frame_equal(dataframe_from_raw_columns(raw, check_cancel=lambda: None), raw)


def test_columnar_construction_rejects_already_inferred_values() -> None:
    with pytest.raises(ValueError, match="object storage"):
        dataframe_from_raw_columns(pd.DataFrame({"value": [1.0, None]}), check_cancel=lambda: None)


@pytest.mark.parametrize("row_input", [False, True])
def test_construction_checks_cancellation_at_each_boundary(row_input: bool) -> None:
    rows = [[1, True], [None, None]]
    raw = pd.DataFrame(rows, columns=["value", "flag"], dtype=object)
    count = 0

    def check() -> None:
        nonlocal count
        count += 1

    if row_input:
        dataframe_from_raw_values(rows, list(raw.columns), check_cancel=check)
    else:
        dataframe_from_raw_columns(raw, check_cancel=check)
    for boundary in range(count):
        checks = iter([False] * boundary)

        cancel = partial(raise_when_cancelled, checks)
        with pytest.raises(RuntimeError, match="cancelled"):
            if row_input:
                dataframe_from_raw_values(rows, list(raw.columns), check_cancel=cancel)
            else:
                dataframe_from_raw_columns(raw, check_cancel=cancel)
