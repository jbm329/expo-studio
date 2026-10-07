"""Tests for Cox proportional-hazards regression."""

from __future__ import annotations

import warnings
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from statsmodels.duration.hazard_regression import PHReg

from expo_jbm329.services.analysis.regression import PredictorKind, build_regression_design
from expo_jbm329.services.analysis.survival import (
    SurvivalError,
    _survival_plot_data,  # noqa: PLC2701
    analyze_cox_regression,
    initialize_survival_columns,
    survival_term_name,
)


def _frame(size: int = 300, seed: int = 61) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=size)
    group = np.where(np.arange(size) % 2 == 0, "control", "treatment")
    event_time = rng.exponential(scale=np.exp(-0.45 * x), size=size)
    censor_time = rng.exponential(scale=1.8, size=size)
    observed = event_time <= censor_time
    return pd.DataFrame({
        "duration": np.minimum(event_time, censor_time),
        "event": observed.astype(int),
        "x": x,
        "group": group,
        "flag": observed,
        "invalid_event": np.where(observed, 2, 0),
    })


def test_initializer_offers_numeric_durations_and_strict_binary_event_columns():
    frame = pd.DataFrame({
        "duration": [1.0, 2.0, 3.0],
        "event": [0, 1, 0],
        "boolean": [True, False, True],
        "not_binary": [0, 1, 2],
        "text": ["0", "1", "0"],
    })

    columns = initialize_survival_columns(frame)

    assert columns.durations == ("duration", "event", "not_binary")
    assert columns.events == ("event", "boolean")


def test_cox_fit_reports_hazard_ratios_counts_ties_method_design_and_references():
    frame = _frame()
    result = analyze_cox_regression(frame, "duration", "event", ["x", "group"])

    assert result.error is None
    assert result.n_used == len(frame)
    assert result.n_dropped == 0
    assert result.n_events == int(frame["event"].sum())
    assert result.n_censored == len(frame) - result.n_events
    assert result.references[0].column == "group"
    assert result.references[0].reference_level in {"control", "treatment"}

    design_data = frame[["x", "group"]]
    design = build_regression_design(
        design_data,
        ("x", "group"),
        {"x": PredictorKind.NUMERIC, "group": PredictorKind.CATEGORICAL},
    )
    expected = PHReg(
        frame["duration"].to_numpy(),
        design.matrix[:, 1:],
        status=frame["event"].to_numpy(),
        ties="efron",
    ).fit(disp=False, maxiter=200)
    assert [term.estimate for term in result.terms] == pytest.approx(expected.params)
    assert [term.p_value for term in result.terms] == pytest.approx(expected.pvalues)
    assert [term.ci_low for term in result.terms] == pytest.approx(expected.conf_int()[:, 0])
    assert [term.hazard_ratio for term in result.terms] == pytest.approx(np.exp(expected.params))
    assert survival_term_name(result.terms[0]) == "x"
    assert survival_term_name(result.terms[1]).startswith("group = ")


def test_boolean_event_uses_true_for_event_and_false_for_censoring():
    frame = _frame()
    result = analyze_cox_regression(frame, "duration", "flag", ["x"])

    assert result.error is None
    assert result.n_events == int(frame["flag"].sum())
    assert result.n_censored == len(frame) - result.n_events


def test_uncensored_data_can_be_selected_and_fitted():
    frame = _frame()
    frame["event"] = 1

    assert "event" in initialize_survival_columns(frame).events
    result = analyze_cox_regression(frame, "duration", "event", ["x"])

    assert result.error is None
    assert result.n_events == len(frame)
    assert result.n_censored == 0
    assert result.plot_data is not None
    assert sum(result.plot_data.censored) == 0
    assert result.plot_data.survival[-1] == 0.0


def test_constant_linear_combination_is_not_identifiable_against_baseline_hazard():
    frame = _frame()
    frame["other"] = 2.0 - frame["x"]

    result = analyze_cox_regression(frame, "duration", "event", ["x", "other"])

    assert result.error is SurvivalError.PERFECT_MULTICOLLINEARITY


def test_complete_cases_drop_missing_and_nonfinite_predictors_with_counts():
    frame = _frame()
    frame.loc[0, "x"] = np.nan
    frame.loc[1, "x"] = np.inf
    frame.loc[2, "group"] = None
    frame.loc[3, "event"] = np.nan

    result = analyze_cox_regression(frame, "duration", "event", ["x", "group"])

    assert result.error is None
    assert result.n_used == len(frame) - 4
    assert result.n_dropped == 4
    assert result.n_events + result.n_censored == result.n_used
    complete = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=["duration", "event", "x", "group"])
    assert result.plot_data == _survival_plot_data(
        complete["duration"].to_numpy(),
        complete["event"].to_numpy(),
    )
    assert result.plot_data is not None
    assert result.plot_data.at_risk[0] == result.n_used
    assert sum(result.plot_data.events) == result.n_events
    assert sum(result.plot_data.censored) == result.n_censored


@pytest.mark.parametrize(
    ("duration_values", "event_values", "expected"),
    [
        ([1.0, 2.0, 0.0, 4.0], [0, 1, 0, 1], SurvivalError.INVALID_DURATION),
        ([1.0, 2.0, np.inf, 4.0], [0, 1, 0, 1], SurvivalError.INVALID_DURATION),
        ([1.0, 2.0, 3.0, 4.0], [0, 2, 0, 1], SurvivalError.INVALID_EVENT),
        ([1.0, 2.0, 3.0, 4.0], ["no", "yes", "no", "yes"], SurvivalError.INVALID_EVENT),
    ],
)
def test_invalid_duration_and_event_values_are_reported_not_silently_dropped(duration_values, event_values, expected):
    frame = pd.DataFrame({"duration": duration_values, "event": event_values, "x": [1.0, 2.0, 3.0, 4.0]})

    result = analyze_cox_regression(frame, "duration", "event", ["x"])

    assert result.error is expected


def test_missing_duration_is_dropped_but_a_nonmissing_invalid_duration_is_rejected():
    frame = _frame()
    frame.loc[0, "duration"] = np.nan
    result = analyze_cox_regression(frame, "duration", "event", ["x"])
    assert result.error is None
    assert result.n_dropped == 1

    frame.loc[1, "duration"] = 0
    result = analyze_cox_regression(frame, "duration", "event", ["x"])
    assert result.error is SurvivalError.INVALID_DURATION


def test_too_few_events_and_outcomes_used_as_predictors_are_structured_errors():
    frame = pd.DataFrame({
        "duration": [1.0, 2.0, 3.0, 4.0, 5.0],
        "event": [1, 0, 0, 0, 0],
        "x": [0.0, 1.0, 2.0, 3.0, 4.0],
    })
    assert analyze_cox_regression(frame, "duration", "event", ["x"]).error is SurvivalError.NOT_ENOUGH_EVENTS
    assert analyze_cox_regression(_frame(), "duration", "event", ["event"]).error is SurvivalError.INVALID_COLUMN
    assert analyze_cox_regression(_frame(), "duration", "event", ["duration"]).error is SurvivalError.INVALID_COLUMN


def test_no_complete_rows_and_constant_predictors_have_structured_errors():
    frame = _frame()
    frame["x"] = np.nan
    empty = analyze_cox_regression(frame, "duration", "event", ["x"])
    assert empty.error is SurvivalError.NOT_ENOUGH_OBSERVATIONS
    assert empty.n_used == 0

    frame = _frame()
    frame["constant"] = 1
    constant = analyze_cox_regression(frame, "duration", "event", ["constant"])
    assert constant.error is SurvivalError.CONSTANT_PREDICTOR


def test_perfectly_collinear_predictors_are_rejected():
    frame = _frame()
    frame["x_copy"] = frame["x"]

    result = analyze_cox_regression(frame, "duration", "event", ["x", "x_copy"])

    assert result.error is SurvivalError.PERFECT_MULTICOLLINEARITY


def test_fit_failure_and_nonfinite_fit_results_are_structured(monkeypatch):
    frame = _frame()

    def _raise(*_args, **_kwargs):
        raise np.linalg.LinAlgError("singular")

    monkeypatch.setattr("expo_jbm329.services.analysis.survival.PHReg.fit", _raise)
    result = analyze_cox_regression(frame, "duration", "event", ["x"])

    assert result.error is SurvivalError.FIT_FAILED


def test_convergence_warning_and_nonfinite_estimates_are_not_reported_as_success(monkeypatch):
    frame = _frame()

    def _warn(*_args, **_kwargs):
        warnings.warn("optimizer failed to converge", RuntimeWarning, stacklevel=2)

    monkeypatch.setattr("expo_jbm329.services.analysis.survival.PHReg.fit", _warn)
    warned = analyze_cox_regression(frame, "duration", "event", ["x"])
    assert warned.error is SurvivalError.FIT_FAILED

    failed_fit = SimpleNamespace(
        params=np.array([np.nan]),
        bse=np.array([1.0]),
        tvalues=np.array([0.0]),
        pvalues=np.array([1.0]),
        conf_int=lambda **_kwargs: np.array([[-1.0, 1.0]]),
    )
    monkeypatch.setattr("expo_jbm329.services.analysis.survival.PHReg.fit", lambda *_args, **_kwargs: failed_fit)
    nonfinite = analyze_cox_regression(frame, "duration", "event", ["x"])
    assert nonfinite.error is SurvivalError.FIT_FAILED


def test_kaplan_meier_hand_calculated_ties_censor_only_times_and_final_followup():
    durations = np.array([4.0, 1.0, 2.0, 1.0, 3.0, 1.0])
    events = np.array([0, 1, 0, 0, 1, 1])
    data = _survival_plot_data(durations, events)

    assert data.times == (0.0, 1.0, 2.0, 3.0, 4.0)
    assert data.at_risk == (6, 6, 3, 2, 1)
    assert data.events == (0, 2, 0, 1, 0)
    assert data.censored == (0, 1, 1, 0, 1)
    assert data.survival == pytest.approx((1.0, 2 / 3, 2 / 3, 1 / 3, 1 / 3))
    assert data.risk_times == (0.0, 1.0, 2.0, 3.0, 4.0)
    assert data.risk_counts == (6, 6, 3, 2, 1)
    assert all(0 <= probability <= 1 for probability in data.survival)
    assert all(left >= right for left, right in zip(data.survival, data.survival[1:], strict=False))


def test_kaplan_meier_all_events_reaches_zero_and_handles_tied_events():
    data = _survival_plot_data(np.array([3.0, 1.0, 2.0, 2.0]), np.ones(4, dtype=int))
    assert data.times == (0.0, 1.0, 2.0, 3.0)
    assert data.survival == pytest.approx((1.0, 3 / 4, 1 / 4, 0.0))
    assert data.at_risk == (4, 4, 3, 1)
    assert data.events == (0, 1, 2, 1)
    assert data.censored == (0, 0, 0, 0)


def test_kaplan_meier_same_time_events_precede_censoring():
    data = _survival_plot_data(np.ones(4), np.array([1, 1, 0, 0]))
    assert data.times == (0.0, 1.0)
    assert data.survival == (1.0, 0.5)
    assert data.at_risk == (4, 4)
    assert data.censored == (0, 2)
    assert data.risk_times == (0.0, 0.25, 0.5, 0.75, 1.0)
    assert data.risk_counts == (4, 4, 4, 4, 4)


def test_display_risk_counts_include_subjects_at_the_tick_but_not_earlier_exits():
    data = _survival_plot_data(np.array([1.0, 3.0, 5.0, 8.0]), np.array([1, 0, 1, 0]))
    assert data.risk_times == (0.0, 2.0, 4.0, 6.0, 8.0)
    assert data.risk_counts == (4, 3, 2, 1, 1)


def test_survival_chart_retains_entire_large_cohort_without_sampling():
    frame = _frame(size=5500)
    result = analyze_cox_regression(frame, "duration", "event", ["x"])
    assert result.error is None
    assert result.plot_data is not None
    assert len(result.plot_data.times) == len(frame) + 1
    assert result.plot_data.at_risk[0] == len(frame)
    assert sum(result.plot_data.events) == result.n_events
    assert sum(result.plot_data.censored) == result.n_censored


def test_survival_error_and_initializer_have_no_plot_payload():
    frame = _frame()
    result = analyze_cox_regression(frame, "duration", "event", [])
    assert result.error is SurvivalError.NO_PREDICTORS_SELECTED
    assert result.plot_data is None
    columns = initialize_survival_columns(frame)
    assert columns.events
