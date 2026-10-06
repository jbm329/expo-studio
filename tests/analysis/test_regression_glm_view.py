from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtWidgets import QLabel, QTableWidget

from expo_jbm329.gui.dialogs.analysis.regression_glm_view import GeneralizedRegressionView
from expo_jbm329.services.analysis.regression_glm import (
    GeneralizedRegressionError,
    RegressionModel,
    analyze_generalized_regression,
)


def _result(model: RegressionModel = RegressionModel.LOGISTIC):
    rng = np.random.default_rng(51)
    size = 120
    x = rng.normal(size=size)
    probability = 1 / (1 + np.exp(-(-0.3 + 0.5 * x)))
    frame = pd.DataFrame({"x": x, "binary": rng.binomial(1, probability, size=size)})
    if model is RegressionModel.LOGISTIC:
        return analyze_generalized_regression(frame, model, "binary", ["x"])
    frame["count"] = rng.poisson(np.exp(0.2 + 0.4 * x))
    return analyze_generalized_regression(frame, model, "count", ["x"])


def _text(view: GeneralizedRegressionView) -> str:
    return "\n".join(label.text() for label in view.findChildren(QLabel))


@pytest.mark.parametrize(
    ("model", "header"),
    [
        (RegressionModel.LOGISTIC, "Odds ratio"),
        (RegressionModel.POISSON, "Rate ratio"),
        (RegressionModel.NEGATIVE_BINOMIAL, "Rate ratio"),
    ],
)
def test_displays_exponentiated_coefficients_and_model_summary(model, header):
    result = _result(model)
    assert result.error is None
    view = GeneralizedRegressionView(result)

    table = view.table()
    assert table is not None
    assert table.selectionMode() is QTableWidget.SelectionMode.NoSelection
    assert table.horizontalHeaderItem(2).text() == header
    assert table.rowCount() == len(result.terms)
    assert "Rows used: 120" in _text(view)
    assert "AIC" in _text(view)


def test_logistic_summary_explains_binary_outcome_encoding():
    view = GeneralizedRegressionView(_result())

    assert "Outcome coding:" in _text(view)


def test_count_summary_shows_dispersion_guidance_without_switching_models():
    result = _result(RegressionModel.POISSON)
    view = GeneralizedRegressionView(result)
    text = _text(view)

    assert "Pearson dispersion" in text
    assert "selected model was not changed" in text
    assert result.model is RegressionModel.POISSON


@pytest.mark.parametrize("error", list(GeneralizedRegressionError))
def test_structured_errors_are_shown_without_a_result_table(error):
    result = _result()
    failed = dataclasses.replace(result, error=error)
    view = GeneralizedRegressionView(failed)

    assert _text(view)
    assert view.table() is None
    assert view.summary_label() is None
