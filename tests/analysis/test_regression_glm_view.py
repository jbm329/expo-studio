from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget

from expo_jbm329.gui.dialogs.analysis.regression_glm_view import GeneralizedRegressionView
from expo_jbm329.services.analysis.regression_glm import (
    CountPlotError,
    CountRegressionPlotData,
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
    assert view.findChild(FigureCanvasQTAgg) is None


@pytest.mark.parametrize("model", [RegressionModel.POISSON, RegressionModel.NEGATIVE_BINOMIAL])
def test_count_layout_and_charts_render_exact_fitted_data(model):
    result = _result(model)
    view = GeneralizedRegressionView(result)
    view.resize(950, 800)
    view.show()
    QCoreApplication.processEvents()
    try:
        splitter = view.findChild(QSplitter)
        assert splitter is not None
        assert splitter.orientation() is Qt.Orientation.Vertical
        assert splitter.count() == 3
        assert not splitter.childrenCollapsible()
        assert splitter.widget(0).findChild(QTableWidget) is view.table()
        assert view.summary_label() in splitter.widget(2).findChildren(QLabel)
        canvas = splitter.widget(1).findChild(FigureCanvasQTAgg)
        assert canvas is not None
        canvas.draw()
        comparison, residuals = canvas.figure.axes
        data = result.plot_data
        assert data is not None
        np.testing.assert_allclose(
            comparison.collections[0].get_offsets(), np.column_stack((data.fitted, data.observed))
        )
        np.testing.assert_allclose(
            residuals.collections[0].get_offsets(), np.column_stack((data.fitted, data.pearson_residuals))
        )
        np.testing.assert_array_equal(comparison.lines[0].get_xdata(), comparison.lines[0].get_ydata())
        np.testing.assert_array_equal(residuals.lines[0].get_ydata(), [0, 0])
        assert comparison.get_xlabel() == "Fitted count"
        assert comparison.get_ylabel() == "Observed count"
        assert residuals.get_ylabel() == "Pearson residual"
        assert "in-sample" in _text(view)
        if model is RegressionModel.POISSON:
            assert "variance equal to the fitted count" in _text(view)
        else:
            assert "NB2 variance" in _text(view)
            assert "Fitted NB2 alpha" in _text(view)
            assert "distinct from the advisory Pearson dispersion" in _text(view)
            assert "variance equal to the fitted count" not in _text(view)
        assert "deterministic sample" not in _text(view)
    finally:
        view.close()


@pytest.mark.parametrize("model", [RegressionModel.LOGISTIC])
def test_other_model_layouts_remain_unchanged(model):
    view = GeneralizedRegressionView(_result(model))
    assert view.findChild(QSplitter) is None
    assert view.findChild(FigureCanvasQTAgg) is None
    assert "in-sample" not in _text(view)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (CountPlotError.INVALID_PREDICTIONS, "fitted counts are not finite"),
        (CountPlotError.INVALID_RESIDUALS, "Pearson residuals are not finite"),
        (None, "No count-model chart data"),
    ],
)
def test_unavailable_poisson_charts_show_reason_without_hiding_model_results(error, message):
    result = dataclasses.replace(_result(RegressionModel.POISSON), plot_data=None, plot_error=error)
    view = GeneralizedRegressionView(result)
    assert message in _text(view)
    assert view.table() is not None
    assert view.summary_label() is not None
    assert view.findChild(FigureCanvasQTAgg) is None
    if error is not None:
        assert "Dispersion diagnostic unavailable" in _text(view)
        assert "does not exceed" not in _text(view)


@pytest.mark.parametrize("model", [RegressionModel.POISSON, RegressionModel.NEGATIVE_BINOMIAL])
def test_sampled_count_charts_explain_full_cohort_estimation(model):
    result = _result(model)
    assert result.plot_data is not None
    result = dataclasses.replace(result, n_used=6000, plot_data=dataclasses.replace(result.plot_data, sampled=True))
    view = GeneralizedRegressionView(result)
    assert "sample of 120 of 6" in _text(view)
    assert "Coefficient estimates and dispersion diagnostics use all fitted rows" in _text(view)


@pytest.mark.parametrize("error", list(CountPlotError))
def test_negative_binomial_chart_errors_do_not_hide_coefficients(error):
    result = dataclasses.replace(_result(RegressionModel.NEGATIVE_BINOMIAL), plot_data=None, plot_error=error)
    view = GeneralizedRegressionView(result)
    assert "Charts unavailable" in _text(view)
    assert view.table() is not None
    assert view.findChild(FigureCanvasQTAgg) is None
    if error is CountPlotError.INVALID_VARIANCE:
        assert "Negative Binomial variance is invalid" in _text(view)
        assert "Pearson dispersion =" in _text(view)
        assert "Dispersion diagnostic unavailable" not in _text(view)


@pytest.mark.parametrize("fitted", [(1.0, 1.0), (1e100, 2e100)])
def test_narrow_and_large_finite_counts_render_without_warnings(fitted):
    result = dataclasses.replace(
        _result(RegressionModel.POISSON),
        plot_data=CountRegressionPlotData(
            observed=(0.0, fitted[1]),
            fitted=fitted,
            pearson_residuals=(-np.sqrt(fitted[0]), 0.0),
            sampled=False,
        ),
    )
    view = GeneralizedRegressionView(result)
    view.resize(950, 800)
    view.show()
    QCoreApplication.processEvents()
    try:
        canvas = view.findChild(FigureCanvasQTAgg)
        assert canvas is not None
        canvas.draw()
    finally:
        view.close()
