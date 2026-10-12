from __future__ import annotations

import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

from expo_jbm329.services.analysis.logistic_charts import LogisticChartLabels
from expo_jbm329.services.analysis.regression import (
    SIGNIFICANCE_LEVEL,
    RegressionError,
    RegressionResult,
    analyze_regression,
)
from expo_jbm329.services.analysis.regression_charts import (
    CountChartLabels,
    CoxChartLabels,
    LinearChartLabels,
    RegressionChartLabels,
)
from expo_jbm329.services.analysis.regression_export import (
    RegressionExportComponent,
    RegressionExportRequest,
    RegressionExportSnapshot,
    RegressionMetric,
    regression_coefficients_table,
    regression_export_tables,
    regression_metrics_table,
    regression_model,
)
from expo_jbm329.services.analysis.regression_glm import (
    CountPlotError,
    GeneralizedRegressionResult,
    RegressionModel,
    analyze_generalized_regression,
)
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat
from expo_jbm329.services.analysis.survival import SurvivalResult, analyze_cox_regression

LINEAR_LABELS = LinearChartLabels(
    "Residuals vs fitted",
    "Fitted value",
    "Residual",
    "Actual vs predicted",
    "Predicted y",
    "Actual y",
    "Normal Q-Q plot",
    "Theoretical quantile",
    "Standardized residual",
)
COUNT_LABELS = CountChartLabels("Observed vs fitted", "Fitted count", "Observed count", "Pearson residuals", "Residual")
COX_LABELS = CoxChartLabels(
    "Hazard ratios",
    "Forest plot unavailable",
    "Hazard ratio (log scale)",
    "Kaplan-Meier",
    "No survival data",
    "Duration",
    "Survival probability",
    "At risk",
)


def logistic_labels(result: GeneralizedRegressionResult) -> LogisticChartLabels:
    """Return untranslated logistic labels with one annotation per predictor term."""
    predictor_count = len(result.terms) - 1
    return LogisticChartLabels(
        "Odds ratios",
        "Odds ratio",
        "No predictors",
        "Unavailable",
        "ROC",
        "False positive rate",
        "True positive rate",
        "AUC",
        "Calibration",
        "Mean probability",
        "Event fraction",
        "Diagnostics unavailable",
        tuple("effect" for _ in range(predictor_count)),
    )


def linear_result(size: int = 60) -> RegressionResult:
    rng = np.random.default_rng(3)
    frame = pd.DataFrame({
        "x": rng.normal(size=size),
        "g": rng.choice(["a", "b", "c"], size=size, p=[0.2, 0.5, 0.3]),
    })
    frame["y"] = 2 * frame["x"] + (frame["g"] == "c") * 3 + rng.normal(size=size)
    result = analyze_regression(frame, "y", ["x", "g"])
    assert result.error is None
    return result


def generalized_result(model: RegressionModel) -> GeneralizedRegressionResult:
    rng = np.random.default_rng(51)
    size = 120
    x = rng.normal(size=size)
    probability = 1 / (1 + np.exp(-(-0.3 + 0.5 * x)))
    frame = pd.DataFrame({"x": x, "binary": rng.binomial(1, probability, size=size)})
    frame["count"] = rng.poisson(np.exp(0.2 + 0.4 * x))
    target = "binary" if model is RegressionModel.LOGISTIC else "count"
    result = analyze_generalized_regression(frame, model, target, ["x"])
    assert result.error is None
    return result


def cox_result() -> SurvivalResult:
    rng = np.random.default_rng(17)
    size = 180
    x = rng.normal(size=size)
    event_time = rng.exponential(scale=np.exp(-0.4 * x), size=size)
    censor_time = rng.exponential(scale=1.7, size=size)
    frame = pd.DataFrame({
        "duration": np.minimum(event_time, censor_time),
        "event": (event_time <= censor_time).astype(int),
        "group": np.where(np.arange(size) % 2, "treated", "control"),
        "x": x,
    })
    result = analyze_cox_regression(frame, "duration", "event", ["x", "group"])
    assert result.error is None
    return result


def linear_snapshot(notes: tuple[str, ...] = ("Linear regression", "Target: y")) -> RegressionExportSnapshot:
    return RegressionExportSnapshot(linear_result(), RegressionChartLabels("Linear: y", LINEAR_LABELS), notes)


def generalized_snapshot(model: RegressionModel) -> RegressionExportSnapshot:
    result = generalized_result(model)
    labels = logistic_labels(result) if model is RegressionModel.LOGISTIC else COUNT_LABELS
    return RegressionExportSnapshot(result, RegressionChartLabels(f"{model.value}: target", labels), ("Comment",))


def cox_snapshot() -> RegressionExportSnapshot:
    return RegressionExportSnapshot(cox_result(), RegressionChartLabels("Cox", COX_LABELS), ("Cox comment",))


def logistic_snapshot() -> RegressionExportSnapshot:
    return generalized_snapshot(RegressionModel.LOGISTIC)


def poisson_snapshot() -> RegressionExportSnapshot:
    return generalized_snapshot(RegressionModel.POISSON)


def negative_binomial_snapshot() -> RegressionExportSnapshot:
    return generalized_snapshot(RegressionModel.NEGATIVE_BINOMIAL)


ALL_SNAPSHOTS = [linear_snapshot, logistic_snapshot, poisson_snapshot, negative_binomial_snapshot, cox_snapshot]


# ----------------------------------------------------------------------
# Snapshot validation and identity
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "model"),
    [
        (linear_snapshot, RegressionModel.LINEAR),
        (logistic_snapshot, RegressionModel.LOGISTIC),
        (poisson_snapshot, RegressionModel.POISSON),
        (negative_binomial_snapshot, RegressionModel.NEGATIVE_BINOMIAL),
        (cox_snapshot, RegressionModel.COX),
    ],
)
def test_snapshot_reports_model_family(factory, model):
    snapshot = factory()
    assert snapshot.model is model
    assert regression_model(snapshot.result) is model
    assert snapshot.has_charts


def test_snapshot_exposes_outcome_and_predictor_columns():
    assert linear_snapshot().outcome_columns == ("y",)
    assert linear_snapshot().predictors == ("x", "g")
    assert poisson_snapshot().outcome_columns == ("count",)
    assert cox_snapshot().outcome_columns == ("duration", "event")
    assert cox_snapshot().predictors == ("x", "group")


def test_snapshot_rejects_untyped_results():
    with pytest.raises(TypeError, match="typed regression result"):
        RegressionExportSnapshot(object(), RegressionChartLabels("h", LINEAR_LABELS))  # type: ignore[arg-type]


def test_snapshot_rejects_failed_results():
    failed = dataclasses.replace(linear_result(), error=RegressionError.CONSTANT_TARGET)
    with pytest.raises(ValueError, match="failed regression"):
        RegressionExportSnapshot(failed, RegressionChartLabels("h", LINEAR_LABELS))


def test_snapshot_rejects_results_without_terms():
    empty = dataclasses.replace(linear_result(), terms=())
    with pytest.raises(ValueError, match="model terms"):
        RegressionExportSnapshot(empty, RegressionChartLabels("h", LINEAR_LABELS))


@pytest.mark.parametrize("model", [RegressionModel.LINEAR, RegressionModel.COX])
def test_snapshot_rejects_generalized_results_claiming_other_models(model):
    result = dataclasses.replace(generalized_result(RegressionModel.POISSON), model=model)
    with pytest.raises(ValueError, match="Generalized results"):
        RegressionExportSnapshot(result, RegressionChartLabels("h", COUNT_LABELS))


@pytest.mark.parametrize(
    ("result_factory", "labels"),
    [
        (linear_result, COUNT_LABELS),
        (cox_result, LINEAR_LABELS),
        (lambda: generalized_result(RegressionModel.POISSON), COX_LABELS),
    ],
)
def test_snapshot_rejects_chart_labels_for_another_model(result_factory, labels):
    with pytest.raises(TypeError, match="Chart labels"):
        RegressionExportSnapshot(result_factory(), RegressionChartLabels("h", labels))


def test_charts_are_unavailable_without_displayed_chart_data():
    linear = RegressionExportSnapshot(
        dataclasses.replace(linear_result(), plot=None), RegressionChartLabels("h", LINEAR_LABELS)
    )
    count = RegressionExportSnapshot(
        dataclasses.replace(generalized_result(RegressionModel.POISSON), plot_data=None),
        RegressionChartLabels("h", COUNT_LABELS),
    )
    assert not linear.has_charts
    assert not count.has_charts
    logistic = generalized_result(RegressionModel.LOGISTIC)
    # Logistic odds ratios are drawn even when ROC/calibration data are unavailable.
    no_diagnostics = dataclasses.replace(logistic, logistic_plot_data=None)
    assert RegressionExportSnapshot(no_diagnostics, RegressionChartLabels("h", logistic_labels(logistic))).has_charts
    assert RegressionExportSnapshot(
        dataclasses.replace(cox_result(), plot_data=None), RegressionChartLabels("h", COX_LABELS)
    ).has_charts


# ----------------------------------------------------------------------
# Requests
# ----------------------------------------------------------------------


def test_excel_request_accepts_every_component():
    components = tuple(RegressionExportComponent)
    request = RegressionExportRequest(linear_snapshot(), components, StatisticsExportFormat.EXCEL)
    assert request.components == components


@pytest.mark.parametrize("export_format", [StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY])
@pytest.mark.parametrize(
    "components",
    [
        (RegressionExportComponent.COEFFICIENTS, RegressionExportComponent.MODEL_METRICS),
        (RegressionExportComponent.CHARTS,),
        (RegressionExportComponent.COEFFICIENTS, RegressionExportComponent.CHARTS),
    ],
)
def test_single_table_formats_reject_charts_and_multiple_tables(export_format, components):
    with pytest.raises(ValueError, match="exactly one table"):
        RegressionExportRequest(linear_snapshot(), components, export_format)


@pytest.mark.parametrize("export_format", [StatisticsExportFormat.CSV, StatisticsExportFormat.BINARY])
@pytest.mark.parametrize("component", [RegressionExportComponent.COEFFICIENTS, RegressionExportComponent.MODEL_METRICS])
def test_single_table_formats_accept_one_table(export_format, component):
    request = RegressionExportRequest(linear_snapshot(), (component,), export_format)
    assert request.format is export_format


@pytest.mark.parametrize(
    "components",
    [(), (RegressionExportComponent.COEFFICIENTS, RegressionExportComponent.COEFFICIENTS)],
)
def test_request_requires_distinct_components(components):
    with pytest.raises(ValueError, match="distinct"):
        RegressionExportRequest(linear_snapshot(), components, StatisticsExportFormat.EXCEL)


def test_request_rejects_unknown_components_and_formats():
    with pytest.raises(ValueError, match="Unknown regression export component"):
        RegressionExportRequest(linear_snapshot(), ("charts",), StatisticsExportFormat.EXCEL)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Unknown regression export format"):
        RegressionExportRequest(
            linear_snapshot(),
            (RegressionExportComponent.COEFFICIENTS,),
            "excel",  # type: ignore[arg-type]
        )


def test_request_rejects_charts_for_a_model_without_chart_data():
    snapshot = RegressionExportSnapshot(
        dataclasses.replace(linear_result(), plot=None), RegressionChartLabels("h", LINEAR_LABELS)
    )
    with pytest.raises(ValueError, match="no charts"):
        RegressionExportRequest(snapshot, (RegressionExportComponent.CHARTS,), StatisticsExportFormat.EXCEL)


# ----------------------------------------------------------------------
# Coefficients
# ----------------------------------------------------------------------


def test_linear_coefficients_are_numeric_and_match_terms():
    snapshot = linear_snapshot()
    result = snapshot.result
    assert isinstance(result, RegressionResult)
    frame = regression_coefficients_table(snapshot, intercept_label="(Konstant)")
    assert list(frame.columns) == [
        "term",
        "estimate",
        "std_error",
        "t_statistic",
        "p_value",
        "ci_low",
        "ci_high",
        "vif",
        "significant",
    ]
    assert len(frame) == len(result.terms)
    assert frame["term"].dtype == pd.StringDtype()
    assert frame["significant"].dtype == pd.BooleanDtype()
    assert frame["estimate"].dtype == np.float64
    assert frame.loc[0, "term"] == "(Konstant)"
    assert "x" in frame["term"].tolist()[1:]
    for row, term in enumerate(result.terms):
        assert frame.loc[row, "estimate"] == term.estimate
        assert frame.loc[row, "p_value"] == term.p_value
        assert frame.loc[row, "significant"] == (term.p_value < SIGNIFICANCE_LEVEL)
    assert math.isnan(frame.loc[0, "vif"])


@pytest.mark.parametrize("factory", [logistic_snapshot, poisson_snapshot, negative_binomial_snapshot])
def test_generalized_coefficients_include_exponentiated_effects(factory):
    snapshot = factory()
    result = snapshot.result
    assert isinstance(result, GeneralizedRegressionResult)
    frame = regression_coefficients_table(snapshot)
    assert list(frame.columns) == [
        "term",
        "estimate",
        "std_error",
        "z_statistic",
        "p_value",
        "ci_low",
        "ci_high",
        "effect",
        "effect_ci_low",
        "effect_ci_high",
        "significant",
    ]
    assert frame.loc[0, "term"] == "(Intercept)"
    assert frame["effect"].tolist() == [term.effect for term in result.terms]
    assert frame["effect_ci_high"].tolist() == [term.effect_ci_high for term in result.terms]


def test_cox_coefficients_include_hazard_ratios_without_intercept():
    snapshot = cox_snapshot()
    result = snapshot.result
    assert isinstance(result, SurvivalResult)
    frame = regression_coefficients_table(snapshot)
    assert list(frame.columns) == [
        "term",
        "estimate",
        "std_error",
        "z_statistic",
        "p_value",
        "ci_low",
        "ci_high",
        "hazard_ratio",
        "hazard_ratio_ci_low",
        "hazard_ratio_ci_high",
        "significant",
    ]
    assert "(Intercept)" not in frame["term"].tolist()
    assert frame["hazard_ratio"].tolist() == [term.hazard_ratio for term in result.terms]


def test_undefined_p_values_have_missing_significance():
    result = linear_result()
    first = dataclasses.replace(result.terms[0], p_value=math.nan)
    snapshot = RegressionExportSnapshot(
        dataclasses.replace(result, terms=(first, *result.terms[1:])), RegressionChartLabels("h", LINEAR_LABELS)
    )
    frame = regression_coefficients_table(snapshot)
    assert frame["significant"].isna().tolist()[0]
    assert not frame["significant"].isna().tolist()[1]


# ----------------------------------------------------------------------
# Model metrics
# ----------------------------------------------------------------------


def _metrics(snapshot: RegressionExportSnapshot) -> dict[str, float]:
    frame = regression_metrics_table(snapshot)
    return {
        str(metric): float(value)
        for metric, value in zip(frame["metric"], frame["value"], strict=True)
        if pd.notna(metric)
    }


def test_linear_metrics_cover_fit_and_diagnostics():
    snapshot = linear_snapshot()
    result = snapshot.result
    assert isinstance(result, RegressionResult)
    assert result.diagnostics is not None
    metrics = _metrics(snapshot)
    assert list(metrics) == [
        "rows_used",
        "rows_dropped",
        "r_squared",
        "adjusted_r_squared",
        "f_statistic",
        "f_p_value",
        "df_model",
        "df_residual",
        "rmse",
        "aic",
        "breusch_pagan_statistic",
        "breusch_pagan_p_value",
        "jarque_bera_statistic",
        "jarque_bera_p_value",
        "durbin_watson",
        "max_vif",
    ]
    assert metrics["rows_used"] == result.n_used
    assert metrics["r_squared"] == result.r_squared
    assert metrics["durbin_watson"] == result.diagnostics.durbin_watson


def test_linear_metrics_omit_diagnostics_when_unavailable():
    snapshot = RegressionExportSnapshot(
        dataclasses.replace(linear_result(), diagnostics=None), RegressionChartLabels("h", LINEAR_LABELS)
    )
    assert "durbin_watson" not in _metrics(snapshot)


def test_logistic_metrics_include_in_sample_auc():
    snapshot = logistic_snapshot()
    result = snapshot.result
    assert isinstance(result, GeneralizedRegressionResult)
    assert result.logistic_plot_data is not None
    metrics = _metrics(snapshot)
    assert metrics["auc"] == result.logistic_plot_data.auc
    assert metrics["pseudo_r_squared"] == result.pseudo_r_squared
    assert "dispersion_ratio" not in metrics
    without_auc = RegressionExportSnapshot(
        dataclasses.replace(result, logistic_plot_data=None),
        RegressionChartLabels("h", logistic_labels(result)),
    )
    assert "auc" not in _metrics(without_auc)


def test_count_metrics_include_dispersion_and_negative_binomial_alpha():
    poisson = _metrics(poisson_snapshot())
    assert "dispersion_ratio" in poisson
    assert "negative_binomial_alpha" not in poisson
    snapshot = negative_binomial_snapshot()
    result = snapshot.result
    assert isinstance(result, GeneralizedRegressionResult)
    assert result.negative_binomial_alpha is not None
    assert _metrics(snapshot)["negative_binomial_alpha"] == result.negative_binomial_alpha


@pytest.mark.parametrize("error", [CountPlotError.INVALID_PREDICTIONS, CountPlotError.INVALID_RESIDUALS])
def test_count_metrics_omit_dispersion_when_displayed_as_unavailable(error):
    result = dataclasses.replace(generalized_result(RegressionModel.POISSON), plot_data=None, plot_error=error)
    snapshot = RegressionExportSnapshot(result, RegressionChartLabels("h", COUNT_LABELS))
    assert "dispersion_ratio" not in _metrics(snapshot)


def test_cox_metrics_include_event_counts():
    snapshot = cox_snapshot()
    result = snapshot.result
    assert isinstance(result, SurvivalResult)
    metrics = _metrics(snapshot)
    assert list(metrics) == ["rows_used", "rows_dropped", "events", "censored"]
    assert metrics["events"] == result.n_events
    assert metrics["censored"] == result.n_censored


def test_metric_keys_are_stable_enum_values():
    for factory in ALL_SNAPSHOTS:
        for key in _metrics(factory()):
            assert RegressionMetric(key).value == key


def test_metrics_share_rows_with_notes_and_extend_when_needed():
    short = regression_metrics_table(linear_snapshot(notes=("first", "second")))
    assert list(short.columns) == ["metric", "value", "notes"]
    assert short["metric"].dtype == pd.StringDtype()
    assert short["notes"].dtype == pd.StringDtype()
    assert short["value"].dtype == np.float64
    assert short.loc[0, "notes"] == "first"
    assert short.loc[1, "notes"] == "second"
    assert pd.isna(short.loc[2, "notes"])

    notes = tuple(f"note {index}" for index in range(30))
    long = regression_metrics_table(linear_snapshot(notes=notes))
    assert len(long) == 30
    assert long["notes"].tolist() == list(notes)
    assert pd.isna(long.loc[29, "metric"])
    assert pd.isna(long.loc[29, "value"])


def test_export_tables_follow_selection_order_and_skip_charts():
    snapshot = linear_snapshot()
    tables = regression_export_tables(
        snapshot,
        (
            RegressionExportComponent.MODEL_METRICS,
            RegressionExportComponent.CHARTS,
            RegressionExportComponent.COEFFICIENTS,
        ),
        intercept_label="Konstant",
    )
    assert list(tables) == [RegressionExportComponent.MODEL_METRICS, RegressionExportComponent.COEFFICIENTS]
    assert tables[RegressionExportComponent.COEFFICIENTS].loc[0, "term"] == "Konstant"


@pytest.mark.parametrize("factory", ALL_SNAPSHOTS)
def test_tables_are_fresh_frames_for_every_call(factory):
    snapshot = factory()
    first = regression_coefficients_table(snapshot)
    first.loc[0, "estimate"] = 123456.0
    assert regression_coefficients_table(snapshot).loc[0, "estimate"] != 123456.0
