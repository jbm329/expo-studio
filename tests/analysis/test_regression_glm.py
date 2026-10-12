"""Tests for binary and count generalized regression."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from expo_jbm329.services.analysis.regression import PLOT_SAMPLE_SIZE
from expo_jbm329.services.analysis.regression_glm import (
    CountPlotError,
    GeneralizedRegressionError,
    LogisticPlotError,
    RegressionModel,
    _count_plot_data,  # noqa: PLC2701
    analyze_generalized_regression,
    generalized_term_name,
    initialize_generalized_targets,
    prepare_logistic_plot_data,
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


def test_logistic_diagnostics_exact_hand_calculated_roc_and_auc():
    data, error = prepare_logistic_plot_data(np.array([0, 0, 1, 1]), np.array([0.1, 0.4, 0.35, 0.8]))
    assert error is None
    assert data is not None
    assert data.false_positive_rates == (0, 0, 0.5, 0.5, 1)
    assert data.true_positive_rates == (0, 0.5, 0.5, 1, 1)
    assert data.auc == 0.75
    assert data.mean_probabilities == (0.1, 0.35, 0.4, 0.8)
    assert data.event_fractions == (0, 1, 0, 1)
    assert data.bin_counts == (1, 1, 1, 1)


@pytest.mark.parametrize("scores", [[0.5, 0.5, 0.5, 0.5], [0.1, 0.1, 0.9, 0.9]])
def test_logistic_diagnostics_roc_ties_are_not_order_dependent(scores):
    observed = np.array([0, 1, 0, 1])
    data, error = prepare_logistic_plot_data(observed, np.array(scores))
    assert error is None
    assert data is not None
    assert data.auc == 0.5
    reversed_data, _ = prepare_logistic_plot_data(observed[::-1], np.array(scores)[::-1])
    assert reversed_data == data
    assert sum(data.bin_counts) == 4
    if len(set(scores)) == 1:
        assert data.bin_counts == (4,)
        assert data.mean_probabilities == (0.5,)
        assert data.event_fractions == (0.5,)
        assert data.false_positive_rates == (0, 1)
        assert data.true_positive_rates == (0, 1)
    else:
        assert data.bin_counts == (2, 2)


@pytest.mark.parametrize("size", [2, 3, 9, 10, 11, 101, 6000])
def test_logistic_calibration_quantiles_cover_all_rows_without_sampling(size):
    fitted = np.linspace(0, 1, size)
    data, error = prepare_logistic_plot_data(np.arange(size) % 2, fitted)
    assert error is None
    assert data is not None
    assert data.n_used == size
    assert sum(data.bin_counts) == size
    assert len(data.bin_counts) <= 10
    assert max(data.bin_counts) - min(data.bin_counts) <= 1
    assert tuple(sorted(data.mean_probabilities)) == data.mean_probabilities


def test_logistic_calibration_never_splits_large_tied_groups():
    fitted = np.repeat([0.1, 0.4, 0.6, 0.9], [30, 2, 13, 5])
    data, error = prepare_logistic_plot_data(np.arange(len(fitted)) % 2, fitted)
    assert error is None
    assert data is not None
    assert sum(data.bin_counts) == len(fitted)
    assert len(data.bin_counts) <= 4
    assert data.bin_counts[0] == 30


@pytest.mark.parametrize(
    "fitted",
    [
        [-0.1, 0.5],
        [0.5, 1.1],
        [np.nan, 0.5],
        [np.inf, 0.5],
        [0.5],
        [[0.5], [0.5]],
        ["0.1", "0.5"],
        [0.1 + 1j, 0.5],
        [None, 0.5],
    ],
)
def test_logistic_diagnostics_reject_invalid_predictions(fitted):
    data, error = prepare_logistic_plot_data(np.array([0, 1]), np.array(fitted))
    assert data is None
    assert error is LogisticPlotError.INVALID_PREDICTIONS


@pytest.mark.parametrize(
    "observed",
    [[], [0, 0], [1, 1], [0, 2], [0, np.nan], [0, np.inf], [[0], [1]], ["no", "yes"], [0, 1j], [None, 1]],
)
def test_logistic_diagnostics_reject_invalid_outcomes(observed):
    data, error = prepare_logistic_plot_data(np.array(observed), np.array([0.2, 0.8]))
    assert data is None
    assert error is LogisticPlotError.INVALID_OUTCOMES


def test_logistic_diagnostics_accept_boolean_labels_and_endpoint_probabilities():
    data, error = prepare_logistic_plot_data(np.array([False, True]), np.array([0.0, 1.0]))
    assert error is None
    assert data is not None
    assert data.auc == 1
    assert data.bin_counts == (1, 1)
    assert data.mean_probabilities == (0, 1)


@pytest.mark.parametrize("encoding", ["number", "bool", "text", "category"])
def test_logistic_diagnostics_use_existing_event_encoding_and_complete_case_cohort(encoding):
    df = _binary_frame()
    if encoding in {"number", "bool"}:
        df["outcome"] = (df["outcome"] == "control").astype("boolean" if encoding == "bool" else "Int64")
    elif encoding == "category":
        df["outcome"] = df["outcome"].astype("category")
    df.loc[0, "x"] = np.nan
    df.loc[1, "x"] = np.inf
    df.loc[2, "outcome"] = None
    result = analyze_generalized_regression(df, RegressionModel.LOGISTIC, "outcome", ["x"])
    assert result.error is None
    assert result.logistic_plot_error is None
    assert result.n_used == 497
    assert result.n_dropped == 3
    data = result.logistic_plot_data
    assert data is not None
    complete = df.replace([np.inf, -np.inf], np.nan).dropna()
    observed = (complete["outcome"].astype(str) == result.target_levels[1]).to_numpy(dtype=float)
    coefficient = result.terms[1].estimate
    intercept = result.terms[0].estimate
    probability = 1 / (1 + np.exp(-(intercept + coefficient * complete["x"].to_numpy())))
    expected, _ = prepare_logistic_plot_data(observed, probability)
    assert expected is not None
    assert data.auc == pytest.approx(expected.auc)
    np.testing.assert_allclose(data.mean_probabilities, expected.mean_probabilities)
    assert data.bin_counts == expected.bin_counts
    assert sum(data.bin_counts) == result.n_used


def test_logistic_chart_only_validation_failure_preserves_fitted_coefficients(monkeypatch):
    original_fit = sm.Logit.fit

    def fit_with_invalid_predictions(self, *args, **kwargs):
        fit = original_fit(self, *args, **kwargs)
        fit.predict = lambda matrix: np.full(len(matrix), np.nan)
        return fit

    monkeypatch.setattr(sm.Logit, "fit", fit_with_invalid_predictions)
    result = analyze_generalized_regression(_binary_frame(), RegressionModel.LOGISTIC, "outcome", ["x"])
    assert result.error is None
    assert len(result.terms) == 2
    assert result.logistic_plot_data is None
    assert result.logistic_plot_error is LogisticPlotError.INVALID_PREDICTIONS


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


def test_poisson_charts_match_response_predictions_and_pearson_residuals_on_complete_rows():
    df = _count_frame()
    df.loc[0, "x"] = np.nan
    df.loc[1, "x"] = np.inf
    df.loc[2, "count"] = np.nan
    result = analyze_generalized_regression(df, RegressionModel.POISSON, "count", ["x"])
    complete = df.replace([np.inf, -np.inf], np.nan).dropna()
    expected_fit = sm.Poisson(complete["count"], sm.add_constant(complete[["x"]])).fit(disp=False)
    expected = expected_fit.predict()

    assert result.error is None
    assert result.plot_error is None
    data = result.plot_data
    assert data is not None
    assert not data.sampled
    assert len(data.observed) == result.n_used == 497
    np.testing.assert_array_equal(data.observed, complete["count"])
    np.testing.assert_allclose(data.fitted, expected)
    np.testing.assert_allclose(data.pearson_residuals, (complete["count"] - expected) / np.sqrt(expected))
    assert 0 in data.observed
    assert not np.allclose(data.fitted, expected_fit.fittedvalues)


@pytest.mark.parametrize("size", [PLOT_SAMPLE_SIZE, PLOT_SAMPLE_SIZE + 1])
def test_poisson_chart_sampling_preserves_alignment_and_full_fit(size: int):
    df = _count_frame(size=size)
    result = analyze_generalized_regression(df, RegressionModel.POISSON, "count", ["x"])
    repeated = analyze_generalized_regression(df, RegressionModel.POISSON, "count", ["x"])
    data = result.plot_data
    assert data is not None
    assert data == repeated.plot_data
    assert len(data.observed) == min(size, PLOT_SAMPLE_SIZE)
    assert data.sampled == (size > PLOT_SAMPLE_SIZE)
    indices = (
        np.sort(np.random.default_rng(0).choice(size, PLOT_SAMPLE_SIZE, replace=False))
        if size > PLOT_SAMPLE_SIZE
        else np.arange(size)
    )
    expected_fit = sm.Poisson(df["count"], sm.add_constant(df[["x"]])).fit(disp=False)
    fitted = np.asarray(expected_fit.predict())
    np.testing.assert_array_equal(data.observed, df["count"].to_numpy()[indices])
    np.testing.assert_allclose(data.fitted, fitted[indices])
    np.testing.assert_allclose(data.pearson_residuals, ((df["count"].to_numpy() - fitted) / np.sqrt(fitted))[indices])
    assert result.n_used == size
    assert result.dispersion_ratio == pytest.approx(
        np.sum((df["count"].to_numpy() - fitted) ** 2 / fitted) / expected_fit.df_resid
    )
    assert result.terms[1].estimate == pytest.approx(expected_fit.params.iloc[1])


@pytest.mark.parametrize(
    "fitted", [np.array([0.0]), np.array([-1.0]), np.array([np.nan]), np.array([np.inf]), np.array([])]
)
def test_poisson_plot_data_rejects_invalid_predictions_without_dropping_rows(fitted: np.ndarray):
    data, error = _count_plot_data(np.array([1.0]), fitted)
    assert data is None
    assert error is CountPlotError.INVALID_PREDICTIONS


def test_poisson_plot_data_surfaces_residual_overflow():
    data, error = _count_plot_data(np.array([1e308]), np.array([1e-300]))
    assert data is None
    assert error is CountPlotError.INVALID_RESIDUALS


def test_invalid_poisson_predictions_preserve_coefficients_and_surface_chart_error(monkeypatch):
    original_fit = sm.Poisson.fit

    def fit_with_invalid_predictions(model, *args, **kwargs):
        fit = original_fit(model, *args, **kwargs)
        fit.predict = lambda matrix: np.full(len(matrix), np.nan)
        return fit

    monkeypatch.setattr(sm.Poisson, "fit", fit_with_invalid_predictions)
    result = analyze_generalized_regression(_count_frame(), RegressionModel.POISSON, "count", ["x"])
    assert result.error is None
    assert result.terms
    assert result.plot_data is None
    assert result.plot_error is CountPlotError.INVALID_PREDICTIONS
    assert math.isnan(result.dispersion_ratio)


@pytest.mark.parametrize("model", [RegressionModel.LOGISTIC])
def test_other_models_do_not_gain_chart_data_in_the_poisson_step(model: RegressionModel):
    df = _binary_frame() if model is RegressionModel.LOGISTIC else _count_frame(overdispersed=True)
    target = "outcome" if model is RegressionModel.LOGISTIC else "count"
    result = analyze_generalized_regression(df, model, target, ["x"])
    assert result.error is None
    assert result.plot_data is None
    assert result.plot_error is None


def test_negative_binomial_charts_use_fitted_nb2_alpha_and_exact_complete_cases():
    df = _count_frame(overdispersed=True)
    df.loc[0, "x"] = np.nan
    df.loc[1, "x"] = np.inf
    result = analyze_generalized_regression(df, RegressionModel.NEGATIVE_BINOMIAL, "count", ["x"])
    complete = df.replace([np.inf, -np.inf], np.nan).dropna()
    expected_fit = sm.NegativeBinomial(complete["count"], sm.add_constant(complete[["x"]])).fit(disp=False)
    fitted = np.asarray(expected_fit.predict())
    alpha = float(expected_fit.params.iloc[-1])

    assert result.error is None
    assert result.plot_error is None
    assert result.negative_binomial_alpha == pytest.approx(alpha)
    assert alpha > 0
    assert result.n_used == 498
    data = result.plot_data
    assert data is not None
    np.testing.assert_array_equal(data.observed, complete["count"])
    np.testing.assert_allclose(data.fitted, fitted)
    np.testing.assert_allclose(
        data.pearson_residuals, (complete["count"] - fitted) / np.sqrt(fitted + alpha * fitted**2)
    )
    assert not np.allclose(data.pearson_residuals, (complete["count"] - fitted) / np.sqrt(fitted))
    assert result.dispersion_ratio == pytest.approx(
        np.sum((complete["count"].to_numpy() - fitted) ** 2 / fitted) / expected_fit.df_resid
    )


def test_negative_binomial_sampling_preserves_row_alignment_and_full_fit():
    size = PLOT_SAMPLE_SIZE + 1
    df = _count_frame(size=size, overdispersed=True)
    result = analyze_generalized_regression(df, RegressionModel.NEGATIVE_BINOMIAL, "count", ["x"])
    repeated = analyze_generalized_regression(df, RegressionModel.NEGATIVE_BINOMIAL, "count", ["x"])
    data = result.plot_data
    assert data is not None
    assert data == repeated.plot_data
    assert data.sampled
    assert len(data.fitted) == PLOT_SAMPLE_SIZE
    indices = np.sort(np.random.default_rng(0).choice(size, PLOT_SAMPLE_SIZE, replace=False))
    fit = sm.NegativeBinomial(df["count"], sm.add_constant(df[["x"]])).fit(disp=False)
    fitted = np.asarray(fit.predict())
    alpha = float(fit.params.iloc[-1])
    np.testing.assert_array_equal(data.observed, df["count"].to_numpy()[indices])
    np.testing.assert_allclose(data.fitted, fitted[indices])
    residuals = (df["count"].to_numpy() - fitted) / np.sqrt(fitted + alpha * fitted**2)
    np.testing.assert_allclose(data.pearson_residuals, residuals[indices])
    assert result.n_used == size
    assert result.terms[1].estimate == pytest.approx(fit.params.iloc[1])


@pytest.mark.parametrize("alpha", [0.0, 1e-12])
def test_nb2_residuals_approach_poisson_when_alpha_approaches_zero(alpha: float):
    observed = np.array([0.0, 1.0, 7.0])
    fitted = np.array([0.5, 2.0, 5.0])
    poisson, _ = _count_plot_data(observed, fitted)
    negative_binomial, error = _count_plot_data(observed, fitted, alpha)
    assert error is None
    assert poisson is not None
    assert negative_binomial is not None
    np.testing.assert_allclose(negative_binomial.pearson_residuals, poisson.pearson_residuals)


@pytest.mark.parametrize("alpha", [-1.0, np.nan, np.inf])
def test_invalid_nb2_alpha_is_reported_without_poisson_fallback(alpha: float):
    data, error = _count_plot_data(np.array([1.0]), np.array([2.0]), alpha)
    assert data is None
    assert error is CountPlotError.INVALID_VARIANCE


def test_nb2_variance_overflow_is_reported():
    data, error = _count_plot_data(np.array([1.0]), np.array([1e200]), 1.0)
    assert data is None
    assert error is CountPlotError.INVALID_VARIANCE


def test_invalid_fitted_nb2_alpha_preserves_model_and_reports_diagnostic_error(monkeypatch):
    original_fit = sm.NegativeBinomial.fit

    def invalid_alpha_fit(model, *args, **kwargs):
        fit = original_fit(model, *args, **kwargs)
        if model.exog.shape[1] > 1:
            # Cache model statistics before injecting a diagnostic-only invalid alpha.
            _ = fit.llnull, fit.llf, fit.aic
            fit.params[-1] = np.nan
        return fit

    monkeypatch.setattr(sm.NegativeBinomial, "fit", invalid_alpha_fit)
    result = analyze_generalized_regression(
        _count_frame(overdispersed=True), RegressionModel.NEGATIVE_BINOMIAL, "count", ["x"]
    )
    assert result.error is None
    assert result.terms
    assert result.plot_data is None
    assert result.plot_error is CountPlotError.INVALID_VARIANCE
    assert math.isfinite(result.dispersion_ratio)


def test_failed_poisson_fit_has_no_chart_data():
    result = analyze_generalized_regression(_count_frame(), RegressionModel.POISSON, "count", [])
    assert result.error is GeneralizedRegressionError.NO_PREDICTORS_SELECTED
    assert result.plot_data is None
    assert result.plot_error is None
