"""Typed exports of a successfully displayed regression model."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from expo_jbm329.services.analysis.logistic_charts import LogisticChartLabels
from expo_jbm329.services.analysis.regression import SIGNIFICANCE_LEVEL, RegressionResult, TermKind, term_name
from expo_jbm329.services.analysis.regression_charts import (
    CountChartLabels,
    CoxChartLabels,
    LinearChartLabels,
    RegressionChartLabels,
)
from expo_jbm329.services.analysis.regression_glm import (
    CountPlotError,
    GeneralizedRegressionResult,
    RegressionModel,
    generalized_term_name,
)
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat
from expo_jbm329.services.analysis.survival import SurvivalResult, survival_term_name

if TYPE_CHECKING:
    from collections.abc import Sequence

RegressionExportResult = RegressionResult | GeneralizedRegressionResult | SurvivalResult

_EXPECTED_LABELS: dict[RegressionModel, type] = {
    RegressionModel.LINEAR: LinearChartLabels,
    RegressionModel.LOGISTIC: LogisticChartLabels,
    RegressionModel.POISSON: CountChartLabels,
    RegressionModel.NEGATIVE_BINOMIAL: CountChartLabels,
    RegressionModel.COX: CoxChartLabels,
}
# Dispersion is shown as unavailable when fitted counts or residuals are invalid.
_INVALID_DISPERSION_ERRORS = frozenset({CountPlotError.INVALID_PREDICTIONS, CountPlotError.INVALID_RESIDUALS})


class RegressionExportComponent(StrEnum):
    """Selectable displayed results; charts are Excel-only."""

    COEFFICIENTS = "coefficients"
    MODEL_METRICS = "model_metrics"
    CHARTS = "charts"


class RegressionMetric(StrEnum):
    """Stable keys of the model-metrics table, localized at the UI boundary."""

    ROWS_USED = "rows_used"
    ROWS_DROPPED = "rows_dropped"
    R_SQUARED = "r_squared"
    ADJUSTED_R_SQUARED = "adjusted_r_squared"
    F_STATISTIC = "f_statistic"
    F_P_VALUE = "f_p_value"
    DF_MODEL = "df_model"
    DF_RESIDUAL = "df_residual"
    RMSE = "rmse"
    AIC = "aic"
    BREUSCH_PAGAN_STATISTIC = "breusch_pagan_statistic"
    BREUSCH_PAGAN_P_VALUE = "breusch_pagan_p_value"
    JARQUE_BERA_STATISTIC = "jarque_bera_statistic"
    JARQUE_BERA_P_VALUE = "jarque_bera_p_value"
    DURBIN_WATSON = "durbin_watson"
    MAX_VIF = "max_vif"
    LOG_LIKELIHOOD = "log_likelihood"
    NULL_LOG_LIKELIHOOD = "null_log_likelihood"
    PSEUDO_R_SQUARED = "pseudo_r_squared"
    AUC = "auc"
    DISPERSION_RATIO = "dispersion_ratio"
    NEGATIVE_BINOMIAL_ALPHA = "negative_binomial_alpha"
    EVENTS = "events"
    CENSORED = "censored"


def regression_model(result: RegressionExportResult) -> RegressionModel:
    """Return the model family of a regression result."""
    match result:
        case RegressionResult():
            return RegressionModel.LINEAR
        case SurvivalResult():
            return RegressionModel.COX
        case GeneralizedRegressionResult():
            return result.model


@dataclass(frozen=True, slots=True)
class RegressionExportSnapshot:
    """Own the displayed fitted model, its translated notes and chart text.

    Attributes:
        result: The fitted model shown in the content pane.
        chart_labels: Translated chart text captured from the displayed view.
        notes: Plain-text lines of the displayed model comments.
    """

    result: RegressionExportResult
    chart_labels: RegressionChartLabels
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject failed results, empty models and chart text for another model."""
        result = self.result
        if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            result,
            (RegressionResult, GeneralizedRegressionResult, SurvivalResult),
        ):
            message = "A typed regression result is required."
            raise TypeError(message)
        if result.error is not None:
            message = "A failed regression result cannot be exported."
            raise ValueError(message)
        if not result.terms:
            message = "A fitted regression result must contain model terms."
            raise ValueError(message)
        if isinstance(result, GeneralizedRegressionResult) and result.model in {
            RegressionModel.LINEAR,
            RegressionModel.COX,
        }:
            message = "Generalized results must be logistic, Poisson or negative binomial models."
            raise ValueError(message)
        if not isinstance(self.chart_labels.model, _EXPECTED_LABELS[self.model]):
            message = "Chart labels do not match the exported regression model."
            raise TypeError(message)

    @property
    def model(self) -> RegressionModel:
        """Return the exported model family."""
        return regression_model(self.result)

    @property
    def has_charts(self) -> bool:
        """Return whether the displayed view drew charts for this model."""
        result = self.result
        match result:
            case RegressionResult():
                return result.plot is not None
            case SurvivalResult():
                return True
            case GeneralizedRegressionResult() if result.model is RegressionModel.LOGISTIC:
                return True
            case GeneralizedRegressionResult():
                return result.plot_data is not None

    @property
    def outcome_columns(self) -> tuple[str, ...]:
        """Return the target, or the duration and event columns for Cox."""
        result = self.result
        if isinstance(result, SurvivalResult):
            return result.duration, result.event
        return (result.target,)

    @property
    def predictors(self) -> tuple[str, ...]:
        """Return the applied predictor columns."""
        return self.result.predictors


@dataclass(frozen=True, slots=True)
class RegressionExportRequest:
    """Selected components from one immutable displayed snapshot."""

    snapshot: RegressionExportSnapshot
    components: tuple[RegressionExportComponent, ...]
    format: StatisticsExportFormat

    def __post_init__(self) -> None:
        """Validate the selection without altering retained dialog choices."""
        if not self.components or len(set(self.components)) != len(self.components):
            message = "Select distinct available regression components."
            raise ValueError(message)
        if any(
            not isinstance(item, RegressionExportComponent)  # pyright: ignore[reportUnnecessaryIsInstance]
            for item in self.components
        ):
            message = "Unknown regression export component."
            raise ValueError(message)
        if not isinstance(self.format, StatisticsExportFormat):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Unknown regression export format."
            raise TypeError(message)
        if RegressionExportComponent.CHARTS in self.components and not self.snapshot.has_charts:
            message = "The exported regression model has no charts."
            raise ValueError(message)
        if self.format is not StatisticsExportFormat.EXCEL and (
            RegressionExportComponent.CHARTS in self.components or len(self.components) != 1
        ):
            message = "CSV and binary exports require exactly one table and no charts."
            raise ValueError(message)


def regression_export_tables(
    snapshot: RegressionExportSnapshot,
    components: Sequence[RegressionExportComponent],
    *,
    intercept_label: str = "(Intercept)",
) -> dict[RegressionExportComponent, pd.DataFrame]:
    """Build fresh numeric tables for the selected non-chart components.

    Args:
        snapshot: The displayed fitted model.
        components: Selected components; charts are ignored.
        intercept_label: Translated display name of the intercept term.

    Returns:
        Tables in selection order, keyed by component.
    """
    tables: dict[RegressionExportComponent, pd.DataFrame] = {}
    for component in components:
        match component:
            case RegressionExportComponent.COEFFICIENTS:
                tables[component] = regression_coefficients_table(snapshot, intercept_label=intercept_label)
            case RegressionExportComponent.MODEL_METRICS:
                tables[component] = regression_metrics_table(snapshot)
            case RegressionExportComponent.CHARTS:
                continue
    return tables


def _significant(p_value: float) -> bool | None:
    """Return the displayed significance mark, or missing for an undefined p-value."""
    return None if math.isnan(p_value) else p_value < SIGNIFICANCE_LEVEL


def regression_coefficients_table(
    snapshot: RegressionExportSnapshot,
    *,
    intercept_label: str = "(Intercept)",
) -> pd.DataFrame:
    """Return one numeric row per displayed model term.

    Linear models add VIF; logistic and count models add the exponentiated
    effect (odds or rate ratio); Cox models add hazard ratios.

    Args:
        snapshot: The displayed fitted model.
        intercept_label: Translated display name of the intercept term.

    Returns:
        A table with stable snake_case column names.
    """
    result = snapshot.result
    rows: list[dict[str, object]] = []
    match result:
        case RegressionResult():
            rows = [
                {
                    "term": intercept_label if term.kind is TermKind.INTERCEPT else term_name(term),
                    "estimate": term.estimate,
                    "std_error": term.std_error,
                    "t_statistic": term.t_statistic,
                    "p_value": term.p_value,
                    "ci_low": term.ci_low,
                    "ci_high": term.ci_high,
                    "vif": term.vif,
                    "significant": _significant(term.p_value),
                }
                for term in result.terms
            ]
        case GeneralizedRegressionResult():
            rows = [
                {
                    "term": intercept_label if term.kind is TermKind.INTERCEPT else generalized_term_name(term),
                    "estimate": term.estimate,
                    "std_error": term.std_error,
                    "z_statistic": term.z_statistic,
                    "p_value": term.p_value,
                    "ci_low": term.ci_low,
                    "ci_high": term.ci_high,
                    "effect": term.effect,
                    "effect_ci_low": term.effect_ci_low,
                    "effect_ci_high": term.effect_ci_high,
                    "significant": _significant(term.p_value),
                }
                for term in result.terms
            ]
        case SurvivalResult():
            rows = [
                {
                    "term": intercept_label if term.kind is TermKind.INTERCEPT else survival_term_name(term),
                    "estimate": term.estimate,
                    "std_error": term.std_error,
                    "z_statistic": term.z_statistic,
                    "p_value": term.p_value,
                    "ci_low": term.ci_low,
                    "ci_high": term.ci_high,
                    "hazard_ratio": term.hazard_ratio,
                    "hazard_ratio_ci_low": term.hazard_ratio_ci_low,
                    "hazard_ratio_ci_high": term.hazard_ratio_ci_high,
                    "significant": _significant(term.p_value),
                }
                for term in result.terms
            ]
    frame = pd.DataFrame(rows)
    frame["term"] = frame["term"].astype(pd.StringDtype())
    numeric = [column for column in frame.columns if column not in {"term", "significant"}]
    frame[numeric] = frame[numeric].astype("float64")
    frame["significant"] = frame["significant"].astype(pd.BooleanDtype())
    return frame


def _metric_values(result: RegressionExportResult) -> list[tuple[RegressionMetric, float]]:
    """Return the numeric fit statistics displayed for the model, in display order."""
    values: list[tuple[RegressionMetric, float]] = [
        (RegressionMetric.ROWS_USED, result.n_used),
        (RegressionMetric.ROWS_DROPPED, result.n_dropped),
    ]
    match result:
        case RegressionResult():
            values += [
                (RegressionMetric.R_SQUARED, result.r_squared),
                (RegressionMetric.ADJUSTED_R_SQUARED, result.adjusted_r_squared),
                (RegressionMetric.F_STATISTIC, result.f_statistic),
                (RegressionMetric.F_P_VALUE, result.f_p_value),
                (RegressionMetric.DF_MODEL, result.df_model),
                (RegressionMetric.DF_RESIDUAL, result.df_residual),
                (RegressionMetric.RMSE, result.rmse),
                (RegressionMetric.AIC, result.aic),
            ]
            diagnostics = result.diagnostics
            if diagnostics is not None:
                values += [
                    (RegressionMetric.BREUSCH_PAGAN_STATISTIC, diagnostics.breusch_pagan_statistic),
                    (RegressionMetric.BREUSCH_PAGAN_P_VALUE, diagnostics.breusch_pagan_p_value),
                    (RegressionMetric.JARQUE_BERA_STATISTIC, diagnostics.jarque_bera_statistic),
                    (RegressionMetric.JARQUE_BERA_P_VALUE, diagnostics.jarque_bera_p_value),
                    (RegressionMetric.DURBIN_WATSON, diagnostics.durbin_watson),
                    (RegressionMetric.MAX_VIF, diagnostics.max_vif),
                ]
        case GeneralizedRegressionResult():
            values += [
                (RegressionMetric.LOG_LIKELIHOOD, result.log_likelihood),
                (RegressionMetric.NULL_LOG_LIKELIHOOD, result.null_log_likelihood),
                (RegressionMetric.PSEUDO_R_SQUARED, result.pseudo_r_squared),
                (RegressionMetric.AIC, result.aic),
                (RegressionMetric.DF_RESIDUAL, result.df_residual),
            ]
            if result.model is RegressionModel.LOGISTIC:
                if result.logistic_plot_data is not None:
                    values.append((RegressionMetric.AUC, result.logistic_plot_data.auc))
            elif result.plot_error not in _INVALID_DISPERSION_ERRORS:
                values.append((RegressionMetric.DISPERSION_RATIO, result.dispersion_ratio))
            if result.model is RegressionModel.NEGATIVE_BINOMIAL and result.negative_binomial_alpha is not None:
                values.append((RegressionMetric.NEGATIVE_BINOMIAL_ALPHA, result.negative_binomial_alpha))
        case SurvivalResult():
            values += [
                (RegressionMetric.EVENTS, result.n_events),
                (RegressionMetric.CENSORED, result.n_censored),
            ]
    return values


def regression_metrics_table(snapshot: RegressionExportSnapshot) -> pd.DataFrame:
    """Return fit statistics as metric/value rows, with the displayed comments as notes.

    Args:
        snapshot: The displayed fitted model.

    Returns:
        Columns ``metric`` (a `RegressionMetric` key), ``value`` and ``notes``.
        Notes share metric rows where possible, adding rows only when necessary.
    """
    values = _metric_values(snapshot.result)
    row_count = max(len(values), len(snapshot.notes))
    metrics = [metric.value for metric, _ in values]
    numbers = [float(value) for _, value in values]
    return pd.DataFrame({
        "metric": pd.Series(metrics, dtype=pd.StringDtype()).reindex(range(row_count)),
        "value": pd.Series(numbers, dtype="float64").reindex(range(row_count)),
        "notes": pd.Series(snapshot.notes, dtype=pd.StringDtype()).reindex(range(row_count)),
    })
