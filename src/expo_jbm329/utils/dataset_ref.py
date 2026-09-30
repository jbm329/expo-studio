"""Lightweight dataset reference model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DatasetRef:
    """Lightweight reference for a result-tab dataset.

    Used wherever a UI component needs to let the user pick one of the
    currently open datasets (e.g. result-tab pickers) without depending on
    the full result-tab machinery.

    Attributes:
        tab_id: Stable internal tab ID.
        title: Visible dataset title.
        row_count: Number of rows in the dataset.
        column_count: Number of columns in the dataset.
    """

    tab_id: str
    title: str
    row_count: int
    column_count: int
