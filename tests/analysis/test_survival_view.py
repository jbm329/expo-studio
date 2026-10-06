from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtWidgets import QLabel, QTableWidget

from expo_jbm329.gui.dialogs.analysis.survival_view import SurvivalRegressionView
from expo_jbm329.services.analysis.survival import SurvivalError, analyze_cox_regression


def _result():
    rng = np.random.default_rng(17)
    size = 180
    x = rng.normal(size=size)
    event_time = rng.exponential(scale=np.exp(-0.4 * x), size=size)
    censor_time = rng.exponential(scale=1.7, size=size)
    event = event_time <= censor_time
    frame = pd.DataFrame({
        "duration": np.minimum(event_time, censor_time),
        "event": event.astype(int),
        "group": np.where(np.arange(size) % 2, "treated", "control"),
        "x": x,
    })
    return analyze_cox_regression(frame, "duration", "event", ["x", "group"])


def _text(view: SurvivalRegressionView) -> str:
    return "\n".join(label.text() for label in view.findChildren(QLabel))


def test_cox_view_shows_hazard_ratio_table_counts_reference_and_caveats():
    result = _result()
    assert result.error is None
    view = SurvivalRegressionView(result)

    table = view.table()
    assert table is not None
    assert table.selectionMode() is QTableWidget.SelectionMode.NoSelection
    assert table.horizontalHeaderItem(2).text() == "Hazard ratio"
    assert table.rowCount() == len(result.terms)
    text = _text(view)
    assert "Event coding: 1 = event; 0 = censored." in text
    assert f"Events: {result.n_events}; censored: {result.n_censored}" in text
    assert "Reference for group:" in text
    assert "Efron" in text
    assert "proportional-hazards assumption was not assessed" in text


@pytest.mark.parametrize("error", list(SurvivalError))
def test_structured_errors_are_shown_without_a_coefficient_table(error):
    failed = dataclasses.replace(_result(), error=error)
    view = SurvivalRegressionView(failed)

    assert _text(view)
    assert view.table() is None
    assert view.summary_label() is None
