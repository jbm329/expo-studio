"""Tests for binary and count generalized regression."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis.regression_glm import (
    GeneralizedRegressionError,
    RegressionModel,
    analyze_generalized_regression,
    generalized_term_name,
    initialize_generalized_targets,
)


def _binary_frame(size: int = 500, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=size)
    probability = 1 / (1 + np.exp(-(-0.4 + 0.9 * x)))
    outcome = rng.binomial(1, probability, size=size)
    return pd.DataFrame({"outcome": np.where(outcome == 1, "case", "control"), "x": x})


def _count_frame(size: int = 500, seed: int = 8, *, overdispersed: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=size)
    mean = np.exp(0.3 + 0.35 * x)
    if overdispersed:
        shape = 1.8
        count = rng.negative_binomial(shape, shape / (shape + mean), size=size)
    else:
        count = rng.poisson(mean)
    return pd.DataFrame({"count": count, "x": x})


def _term(result, name: str):
    return next(term for term in result.terms if generalized_term_name(term) == name)


def test_initializer_classifies_binary_and_nonnegative_integer_targets():
    df = pd.DataFrame({
        "binary_text": ["yes", "no", "yes", "no"],
        "binary_number": [0, 1, 0, 1],
        "count": [0, 1, 2, 3],
        "fraction": [0.0, 1.5, 2.0, 3.0],
        "negative": [-1, 0, 1, 2],
        "constant": [4, 4, 4, 4],
    })

    targets = initialize_generalized_targets(df)

    assert targets.binary == ("binary_text", "binary_number")
    assert targets.count == ("binary_number", "count", "constant")


def test_logistic_regression_reports_odds_ratios_and_confidence_intervals():
    result = analyze_generalized_regression(_binary_frame(), RegressionModel.LOGISTIC, "outcome", ["x"])
    term = _term(result, "x")

    assert result.error is None
    assert result.model is RegressionModel.LOGISTIC
    assert result.target_levels == ("case", "control")
    assert result.n_used == 500
    assert term.effect == pytest.approx(math.exp(term.estimate))
    assert term.effect_ci_low == pytest.approx(math.exp(term.ci_low))
    assert term.effect_ci_high == pytest.approx(math.exp(term.ci_high))
    assert term.effect < 1
    assert term.p_value < 0.05
    assert math.isnan(result.dispersion_ratio)


@pytest.mark.parametrize("model", [RegressionModel.POISSON, RegressionModel.NEGATIVE_BINOMIAL])
def test_count_regression_reports_rate_ratios_and_preserves_model_choice(model: RegressionModel):
    result = analyze_generalized_regression(_count_frame(overdispersed=True), model, "count", ["x"])
    term = _term(result, "x")

    assert result.error is None
    assert result.model is model
    assert result.n_used == 500
    assert term.effect == pytest.approx(math.exp(term.estimate))
    assert term.effect_ci_low == pytest.approx(math.exp(term.ci_low))
    assert term.effect_ci_high == pytest.approx(math.exp(term.ci_high))
    assert term.effect > 1
    assert result.dispersion_ratio > 1
    assert result.overdispersed is (result.dispersion_ratio > 1.5)


def test_categorical_predictors_use_shared_reference_coding():
    df = _binary_frame()
    df["group"] = np.where(np.arange(len(df)) % 2, "treatment", "control")
    result = analyze_generalized_regression(df, RegressionModel.LOGISTIC, "outcome", ["group"])

    assert result.error is None
    assert result.references[0].reference_level in ("control", "treatment")
    assert len(result.terms) == 2
    assert generalized_term_name(result.terms[1]).startswith("group = ")


def test_complete_cases_exclude_missing_and_non_finite_predictors():
    df = _count_frame(size=20)
    df.loc[0, "x"] = np.nan
    df.loc[1, "x"] = np.inf

    result = analyze_generalized_regression(df, RegressionModel.POISSON, "count", ["x"])

    assert result.error is None
    assert result.n_used == 18
    assert result.n_dropped == 2


def test_non_finite_count_outcomes_are_excluded_as_incomplete_rows():
    df = pd.DataFrame({"count": [1.0, 2.0, np.inf, 4.0, 3.0], "x": [1.0, 2.0, 3.0, 4.0, 5.0]})

    result = analyze_generalized_regression(df, RegressionModel.POISSON, "count", ["x"])

    assert result.error is None
    assert result.n_used == 4
    assert result.n_dropped == 1


@pytest.mark.parametrize(
    ("model", "target", "predictors", "expected"),
    [
        (RegressionModel.LOGISTIC, "", ("x",), GeneralizedRegressionError.NO_TARGET),
        (RegressionModel.LOGISTIC, "count", ("x",), GeneralizedRegressionError.INVALID_TARGET),
        (RegressionModel.POISSON, "binary_text", ("x",), GeneralizedRegressionError.INVALID_TARGET),
        (RegressionModel.POISSON, "fraction", ("x",), GeneralizedRegressionError.INVALID_TARGET),
        (RegressionModel.POISSON, "negative", ("x",), GeneralizedRegressionError.INVALID_TARGET),
        (RegressionModel.POISSON, "count", (), GeneralizedRegressionError.NO_PREDICTORS_SELECTED),
        (RegressionModel.POISSON, "count", ("missing",), GeneralizedRegressionError.INVALID_COLUMN),
    ],
)
def test_invalid_target_or_selection_returns_structured_error(model, target, predictors, expected):
    df = pd.DataFrame({
        "binary": [0, 1, 0, 1],
        "binary_text": ["yes", "no", "yes", "no"],
        "count": [0, 1, 2, 3],
        "fraction": [0.0, 1.5, 2.0, 3.0],
        "negative": [-1, 0, 1, 2],
        "x": [1.0, 2.0, 3.0, 4.0],
    })

    result = analyze_generalized_regression(df, model, target, predictors)

    assert result.error is expected
    assert result.terms == ()


def test_complete_cases_with_only_one_binary_level_report_constant_target():
    df = pd.DataFrame({"target": [0, 0, 1, 1], "x": [1.0, np.nan, np.nan, np.nan]})

    result = analyze_generalized_regression(df, RegressionModel.LOGISTIC, "target", ["x"])

    assert result.error is GeneralizedRegressionError.CONSTANT_TARGET
    assert result.n_used == 1


def test_invalid_count_observations_are_not_silently_dropped():
    df = pd.DataFrame({"count": [1.0, 2.0, 1.5, 4.0], "x": [1.0, 2.0, 3.0, 4.0]})

    result = analyze_generalized_regression(df, RegressionModel.POISSON, "count", ["x"])

    assert result.error is GeneralizedRegressionError.INVALID_TARGET


def test_fit_failure_returns_structured_error(monkeypatch):
    df = _binary_frame()

    def _raise(*_args, **_kwargs):
        message = "singular model"
        raise np.linalg.LinAlgError(message)

    monkeypatch.setattr("expo_jbm329.services.analysis.regression_glm.sm.Logit.fit", _raise)

    result = analyze_generalized_regression(df, RegressionModel.LOGISTIC, "outcome", ["x"])

    assert result.error is GeneralizedRegressionError.FIT_FAILED
