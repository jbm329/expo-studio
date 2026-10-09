"""Regression diagnostic renderer tests using a Qt-free Agg canvas."""

from __future__ import annotations

import dataclasses
import math
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from expo_jbm329.services.analysis.logistic_charts import LogisticChartLabels, build_logistic_charts
from expo_jbm329.services.analysis.regression import TermKind
from expo_jbm329.services.analysis.regression_glm import RegressionModel, analyze_generalized_regression


@pytest.fixture
def result():
    rng = np.random.default_rng(35)
    x = rng.normal(size=150)
    frame = pd.DataFrame({"x": x, "outcome": rng.binomial(1, 1 / (1 + np.exp(-x)))})
    result = analyze_generalized_regression(frame, RegressionModel.LOGISTIC, "outcome", ["x"])
    assert result.error is None
    return result


def _labels(result):
    return LogisticChartLabels(
        odds_title="Odds with 95% CI",
        odds_axis="OR (log scale)",
        no_predictors="Intercept only",
        unavailable_effect="Unavailable odds / CI",
        roc_title="ROC (in-sample)",
        false_positive_axis="FPR",
        true_positive_axis="TPR",
        auc_annotation=f"AUC = {result.logistic_plot_data.auc}" if result.logistic_plot_data else "",
        calibration_title="Calibration (in-sample)",
        probability_axis="Mean probability",
        event_fraction_axis="Event fraction",
        unavailable_diagnostics="Unavailable diagnostics",
        effect_annotations=tuple("Effect [low, high]" for term in result.terms if term.kind is not TermKind.INTERCEPT),
    )


def _render(result):
    figure = Figure(figsize=(11, 8), constrained_layout=True)
    canvas = FigureCanvasAgg(figure)
    build_logistic_charts(figure, result, _labels(result))
    canvas.draw()
    return figure


def test_three_plots_preserve_intervals_reference_lines_and_worker_data(result):
    figure = _render(result)
    odds, roc, calibration = figure.axes
    assert odds.get_xscale() == "log"
    assert [tick.get_text() for tick in odds.get_yticklabels()] == ["x"]
    np.testing.assert_array_equal(odds.lines[0].get_xdata(), [1, 1])
    term = result.terms[1]
    np.testing.assert_array_equal(odds.lines[1].get_xdata(), [term.effect_ci_low, term.effect_ci_high])
    np.testing.assert_array_equal(odds.lines[1].get_ydata(), [0, 0])
    np.testing.assert_array_equal(odds.lines[2].get_xdata(), [term.effect])
    data = result.logistic_plot_data
    assert data is not None
    np.testing.assert_array_equal(roc.lines[1].get_xdata(), data.false_positive_rates)
    np.testing.assert_array_equal(roc.lines[1].get_ydata(), data.true_positive_rates)
    assert "AUC" in roc.get_legend().get_texts()[0].get_text()
    np.testing.assert_array_equal(calibration.lines[1].get_xdata(), data.mean_probabilities)
    np.testing.assert_array_equal(calibration.lines[1].get_ydata(), data.event_fractions)
    for axes in (roc, calibration):
        assert axes.get_xlim() == (0, 1)
        assert axes.get_ylim() == (0, 1)
        np.testing.assert_array_equal(axes.lines[0].get_xdata(), [0, 1])
        np.testing.assert_array_equal(axes.lines[0].get_ydata(), [0, 1])


@pytest.mark.parametrize(
    ("effect", "low", "high"),
    [
        (0, 0, 1),
        (math.inf, 1, math.inf),
        (1, 0, math.inf),
        (math.nan, 0.5, 2),
        (-1, 0.5, 2),
        (1, 2, 0.5),
    ],
)
def test_unavailable_odds_rows_are_explained_not_silently_removed(result, effect, low, high):
    term = dataclasses.replace(result.terms[1], effect=effect, effect_ci_low=low, effect_ci_high=high)
    changed = dataclasses.replace(result, terms=(result.terms[0], term))
    odds = _render(changed).axes[0]
    assert len(odds.lines) == 1
    assert [tick.get_text() for tick in odds.get_yticklabels()] == ["x"]
    assert odds.texts[0].get_text() == "Unavailable odds / CI"


@pytest.mark.parametrize("low, high", [(1e-300, 1e300), (np.nextafter(0.0, 1.0), np.finfo(float).max)])
def test_extreme_finite_odds_intervals_render_without_overflow(result, low, high):
    term = dataclasses.replace(result.terms[1], effect=1, effect_ci_low=low, effect_ci_high=high)
    odds = _render(dataclasses.replace(result, terms=(result.terms[0], term))).axes[0]
    assert len(odds.lines) == 3
    assert odds.get_xlim()[0] <= low
    assert odds.get_xlim()[1] >= high


def test_expanded_categorical_terms_keep_original_labels(result):
    term = dataclasses.replace(result.terms[1], kind=TermKind.DUMMY, column="<group & $x$>", level="a = b")
    odds = _render(dataclasses.replace(result, terms=(result.terms[0], term))).axes[0]
    assert odds.get_yticklabels()[0].get_text() == "<group & $x$> = a = b"
    assert not odds.get_yticklabels()[0].get_parse_math()


def test_intercept_only_and_missing_diagnostics_have_meaningful_placeholders(result):
    changed = dataclasses.replace(result, terms=result.terms[:1], logistic_plot_data=None)
    odds, roc, calibration = _render(changed).axes
    assert odds.texts[0].get_text() == "Intercept only"
    assert odds.get_yticklabels() == []
    for axes in (roc, calibration):
        assert axes.texts[0].get_text() == "Unavailable diagnostics"


def test_intercept_only_constant_predictions_have_meaningful_diagnostics(result):
    from expo_jbm329.services.analysis.regression_glm import prepare_logistic_plot_data

    data, error = prepare_logistic_plot_data(np.array([0, 1, 0, 1]), np.full(4, 0.5))
    assert error is None
    changed = dataclasses.replace(result, terms=result.terms[:1], logistic_plot_data=data)
    odds, roc, calibration = _render(changed).axes
    assert odds.texts[0].get_text() == "Intercept only"
    np.testing.assert_array_equal(roc.lines[1].get_xdata(), [0, 1])
    np.testing.assert_array_equal(calibration.lines[1].get_xdata(), [0.5])
    np.testing.assert_array_equal(calibration.lines[1].get_ydata(), [0.5])


def test_chart_module_does_not_import_qt_directly_or_indirectly():
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import expo_jbm329.services.analysis.logistic_charts; "
                "assert not any(name.startswith(('PyQt', 'PySide')) for name in sys.modules)"
            ),
        ],
        check=True,
    )
