"""Shared real-data configuration for ordered reshape workflow tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest
from PyQt6.QtCore import Qt

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.gui.dialogs.workflows.reshape.reshape_dialog import ReshapeDialog


@pytest.fixture
def ordered_reshape_case() -> tuple[pd.DataFrame, pd.DataFrame, Callable[[ReshapeDialog], None]]:
    """Provide seven groups, independent order keys, ties and missing outputs."""
    groups = list("GFEDCBA")
    source = pd.DataFrame({
        "group": groups * 4,
        "status": pd.Series(
            [f"excluded {group}" for group in groups]
            + [f"early {group}" for group in groups]
            + [f"late {group}" for group in groups]
            + [None if group == "D" else f"end {group}" for group in groups],
            dtype="string",
        ),
        "date": pd.to_datetime(
            [None if group == "F" else f"2026-01-{phase + 1:02d}" for phase in range(4) for group in groups],
            utc=True,
        ),
        "rank": pd.Series(
            [None if group == "F" else rank for rank in (100, 5, 1, 5) for group in groups], dtype="Int64"
        ),
        "amount": pd.Series(range(28), dtype="Int64"),
        "active": [phase != 0 and group != "E" for phase in range(4) for group in groups],
    })
    source.index = [3, 3, 1, 0, 0, 9, 9] * 4
    expected = pd.DataFrame({
        "group": groups,
        "Total": pd.Series([42 + 4 * offset for offset in range(7)], dtype="Int64"),
        "Earliest status": pd.Series(
            [None if group in {"F", "E"} else f"early {group}" for group in groups], dtype="string"
        ),
        "Highest rank status": pd.Series(
            [None if group in {"F", "E", "D"} else f"end {group}" for group in groups], dtype="string"
        ),
    })

    def configure(dialog: ReshapeDialog) -> None:
        dialog.dimensions.item(0).setCheckState(Qt.CheckState.Checked)
        for row, (name, function, value, order) in enumerate((
            ("Total", "SUM", 4, None),
            ("Earliest status", "FIRST", 1, 2),
            ("Highest rank status", "LAST", 1, 3),
        )):
            if row:
                dialog.add_metric_button.click()
            dialog.metrics.cellWidget(row, 1).setCurrentText(function)
            cell = dialog.metrics.cellWidget(row, 2)
            cell.value.setCurrentIndex(cell.value.findData(value))
            if order is not None:
                cell.order.setCurrentIndex(cell.order.findData(order))
                dialog.metrics.cellWidget(row, 3).text.setText("[active] = True")
            dialog.metrics.item(row, 0).setText(name)
        assert dialog.validate_conditions()
        assert dialog.apply_button.isEnabled()

    return source, expected, configure
