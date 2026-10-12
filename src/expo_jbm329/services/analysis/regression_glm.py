"""Binary and count generalized linear regression services."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tools.sm_exceptions import ConvergenceWarning, PerfectSeparationError, PerfectSeparationWarning

from expo_jbm329.services.analysis.columns import numeric_columns
from expo_jbm329.services.analysis.regression import (
    CONFIDENCE_LEVEL,
    MAX_MODEL_TERMS,
    MAX_PREDICTORS,
    PLOT_SAMPLE_SIZE,
    CategoricalReference,
    PredictorColumns,
    PredictorKind,
    TermKind,
    build_regression_design,
    classify_predictor_columns,
)
from expo_jbm329.services.data_operations.dtypes import SemanticDType, classify_series_dtype

_NAN = float("nan")
_MIN_DISTINCT = 2
_MIN_RESIDUAL_DF = 1
OVERDISPERSION_THRESHOLD = 1.5
_PLOT_SEED = 0
_CALIBRATION_MAX_BINS = 10


class RegressionModel(StrEnum):
    """Models offered by the Regression analysis."""

    LINEAR = "linear"
    LOGISTIC = "logistic"
    POISSON = "poisson"
    NEGATIVE_BINOMIAL = "negative_binomial"
    COX = "cox"


class GeneralizedRegressionError(StrEnum):
    """Reasons a generalized regression could not be fitted."""

    NO_TARGET = "no_target"
    INVALID_TARGET = "invalid_target"
    NO_PREDICTORS_SELECTED = "no_predictors_selected"
    TOO_MANY_PREDICTORS = "too_many_predictors"
    INVALID_COLUMN = "invalid_column"
    TOO_MANY_TERMS = "too_many_terms"
    NOT_ENOUGH_OBSERVATIONS = "not_enough_observations"
    CONSTANT_TARGET = "constant_target"
    CONSTANT_PREDICTOR = "constant_predictor"
    PERFECT_MULTICOLLINEARITY = "perfect_multicollinearity"
    FIT_FAILED = "fit_failed"


@dataclass(frozen=True, slots=True)
class GeneralizedTargetColumns:
    """Columns eligible as binary or count regression targets."""

    binary: tuple[str, ...]
    count: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GeneralizedRegressionTerm:
    """A generalized regression coefficient with its exponentiated effect."""

    kind: TermKind
    column: str
    level: str | None
    estimate: float
    std_error: float
    z_statistic: float
    p_value: float
    ci_low: float
    ci_high: float
    effect: float
    effect_ci_low: float
    effect_ci_high: float


@dataclass(frozen=True, slots=True)
class CountRegressionPlotData:
    """Row-aligned response-scale counts and residuals, possibly sampled."""

    observed: tuple[float, ...]
    fitted: tuple[float, ...]
    pearson_residuals: tuple[float, ...]
    sampled: bool


class CountPlotError(StrEnum):
    """Reasons fitted count-model diagnostics cannot be displayed."""

    INVALID_PREDICTIONS = "invalid_predictions"
    INVALID_RESIDUALS = "invalid_residuals"
    INVALID_VARIANCE = "invalid_variance"


class LogisticPlotError(StrEnum):
    """Reasons fitted logistic diagnostics cannot be displayed."""

    INVALID_PREDICTIONS = "invalid_predictions"
    INVALID_OUTCOMES = "invalid_outcomes"


@dataclass(frozen=True, slots=True)
class LogisticRegressionPlotData:
    """Full fitted-cohort ROC and tie-preserving quantile calibration data."""

    false_positive_rates: tuple[float, ...]
    true_positive_rates: tuple[float, ...]
    auc: float
    mean_probabilities: tuple[float, ...]
    event_fractions: tuple[float, ...]
    bin_counts: tuple[int, ...]
    n_used: int


@dataclass(frozen=True, slots=True)
class GeneralizedRegressionResult:
    """Fit metadata and estimates for logistic or count regression."""

    model: RegressionModel
    target: str
    predictors: tuple[str, ...]
    available_targets: tuple[str, ...]
    predictor_columns: PredictorColumns
    target_levels: tuple[str, ...]
    n_used: int
    n_dropped: int
    log_likelihood: float
    null_log_likelihood: float
    pseudo_r_squared: float
    aic: float
    df_residual: int
    terms: tuple[GeneralizedRegressionTerm, ...]
    references: tuple[CategoricalReference, ...]
    dispersion_ratio: float
    overdispersed: bool
    error: GeneralizedRegressionError | None
    error_column: str | None = None
    plot_data: CountRegressionPlotData | None = None
    plot_error: CountPlotError | None = None
    negative_binomial_alpha: float | None = None
    logistic_plot_data: LogisticRegressionPlotData | None = None
    logistic_plot_error: LogisticPlotError | None = None


def initialize_generalized_targets(df: pd.DataFrame) -> GeneralizedTargetColumns:
    """Identify binary and count target columns without fitting a model."""
    binary_targets: list[str] = []
    count_targets: list[str] = []
    numeric = set(numeric_columns(df))
    categorical_types = {SemanticDType.STRING, SemanticDType.CATEGORY, SemanticDType.BOOL}

    for column in df.columns:
        series = df[column]
        dtype = classify_series_dtype(series)
        values = series.dropna()
        if len(values) == 0:
            continue
        if dtype in categorical_types and values.nunique() == _MIN_DISTINCT:
            binary_targets.append(column)
        elif column in numeric:
            numeric_values = pd.to_numeric(values, errors="coerce").to_numpy(dtype=np.float64)
            finite_values = numeric_values[np.isfinite(numeric_values)]
            if len(finite_values) == 0:
                continue
            if len(np.unique(finite_values)) == _MIN_DISTINCT:
                binary_targets.append(column)
            if np.all(finite_values >= 0) and np.all(finite_values == np.floor(finite_values)):
                count_targets.append(column)

    return GeneralizedTargetColumns(binary=tuple(binary_targets), count=tuple(count_targets))


def analyze_generalized_regression(
    df: pd.DataFrame,
    model: RegressionModel,
    target: str,
    predictors: tuple[str, ...] | list[str],
) -> GeneralizedRegressionResult:
    """Fit logistic, Poisson, or negative-binomial regression.

    Categorical predictors use the same most-frequent reference and dummy
    coding as linear regression. Missing or non-finite observations are
    excluded listwise. The selected count model is always respected; the
    overdispersion diagnostic is advisory only.
    """
    selected_predictors = tuple(predictors)
    targets = initialize_generalized_targets(df)
    available_targets = targets.binary if model is RegressionModel.LOGISTIC else targets.count
    predictor_columns = classify_predictor_columns(df)
    kinds = dict.fromkeys(predictor_columns.numeric, PredictorKind.NUMERIC)
    kinds |= dict.fromkeys(predictor_columns.categorical, PredictorKind.CATEGORICAL)

    if model in {RegressionModel.LINEAR, RegressionModel.COX}:
        return _empty_result(
            model,
            target,
            selected_predictors,
            available_targets,
            predictor_columns,
            GeneralizedRegressionError.INVALID_TARGET,
        )
    if not target:
        return _empty_result(
            model,
            target,
            selected_predictors,
            available_targets,
            predictor_columns,
            GeneralizedRegressionError.NO_TARGET,
        )
    if target not in available_targets:
        return _empty_result(
            model,
            target,
            selected_predictors,
            available_targets,
            predictor_columns,
            GeneralizedRegressionError.INVALID_TARGET,
        )
    if not selected_predictors:
        return _empty_result(
            model,
            target,
            selected_predictors,
            available_targets,
            predictor_columns,
            GeneralizedRegressionError.NO_PREDICTORS_SELECTED,
        )
    if len(selected_predictors) > MAX_PREDICTORS:
        return _empty_result(
            model,
            target,
            selected_predictors,
            available_targets,
            predictor_columns,
            GeneralizedRegressionError.TOO_MANY_PREDICTORS,
        )
    if (
        len(set(selected_predictors)) != len(selected_predictors)
        or target in selected_predictors
        or any(column not in kinds for column in selected_predictors)
    ):
        return _empty_result(
            model,
            target,
            selected_predictors,
            available_targets,
            predictor_columns,
            GeneralizedRegressionError.INVALID_COLUMN,
        )

    data = pd.DataFrame(index=df.index)
    if model is RegressionModel.LOGISTIC:
        raw_target = df[target]
        target_values = raw_target.dropna()
        levels = _sorted_levels(target_values)
        if len(levels) != _MIN_DISTINCT:
            return _empty_result(
                model,
                target,
                selected_predictors,
                available_targets,
                predictor_columns,
                GeneralizedRegressionError.INVALID_TARGET,
            )
        data[target] = raw_target.map({levels[0]: 0.0, levels[1]: 1.0})
        target_levels = tuple(str(level) for level in levels)
    else:
        numeric_target = pd.to_numeric(df[target], errors="coerce").astype("float64")
        finite_target = np.isfinite(numeric_target)
        invalid_target = finite_target & ((numeric_target < 0) | (numeric_target != np.floor(numeric_target)))
        if invalid_target.any():
            return _empty_result(
                model,
                target,
                selected_predictors,
                available_targets,
                predictor_columns,
                GeneralizedRegressionError.INVALID_TARGET,
            )
        data[target] = numeric_target.where(finite_target)
        target_levels = ()

    for column in selected_predictors:
        if kinds[column] is PredictorKind.NUMERIC:
            values = pd.to_numeric(df[column], errors="coerce").astype("float64")
            data[column] = values.where(np.isfinite(values))
        else:
            data[column] = df[column]
    data = data.dropna()
    n_used = len(data)
    n_dropped = len(df) - n_used

    if data.empty or data[target].nunique() < _MIN_DISTINCT:
        return _empty_result(
            model,
            target,
            selected_predictors,
            available_targets,
            predictor_columns,
            GeneralizedRegressionError.CONSTANT_TARGET,
            n_used=n_used,
            n_dropped=n_dropped,
        )
    for column in selected_predictors:
        if data[column].nunique() < _MIN_DISTINCT:
            return _empty_result(
                model,
                target,
                selected_predictors,
                available_targets,
                predictor_columns,
                GeneralizedRegressionError.CONSTANT_PREDICTOR,
                n_used=n_used,
                n_dropped=n_dropped,
                error_column=column,
            )

    term_count = sum(
        1 if kinds[column] is PredictorKind.NUMERIC else int(data[column].nunique()) - 1
        for column in selected_predictors
    )
    if term_count > MAX_MODEL_TERMS:
        error = GeneralizedRegressionError.TOO_MANY_TERMS
    elif n_used <= term_count + _MIN_RESIDUAL_DF:
        error = GeneralizedRegressionError.NOT_ENOUGH_OBSERVATIONS
    else:
        error = None
    if error is not None:
        return _empty_result(
            model, target, selected_predictors, available_targets, predictor_columns, error, n_used, n_dropped
        )

    design = build_regression_design(data, selected_predictors, kinds)
    if np.linalg.matrix_rank(design.matrix) < design.matrix.shape[1]:
        return _empty_result(
            model,
            target,
            selected_predictors,
            available_targets,
            predictor_columns,
            GeneralizedRegressionError.PERFECT_MULTICOLLINEARITY,
            n_used,
            n_dropped,
        )

    y = data[target].to_numpy(dtype=np.float64)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            warnings.simplefilter("error", PerfectSeparationWarning)
            if model is RegressionModel.LOGISTIC:
                fit = sm.Logit(y, design.matrix).fit(disp=False, maxiter=200)
            elif model is RegressionModel.POISSON:
                fit = sm.Poisson(y, design.matrix).fit(disp=False, maxiter=200)
            else:
                fit = sm.NegativeBinomial(y, design.matrix).fit(disp=False, maxiter=200)
    except (
        ConvergenceWarning,
        PerfectSeparationWarning,
        PerfectSeparationError,
        np.linalg.LinAlgError,
        ValueError,
        RuntimeError,
        FloatingPointError,
    ):
        return _empty_result(
            model,
            target,
            selected_predictors,
            available_targets,
            predictor_columns,
            GeneralizedRegressionError.FIT_FAILED,
            n_used,
            n_dropped,
        )
    if not bool(getattr(fit, "mle_retvals", {}).get("converged", True)):
        return _empty_result(
            model,
            target,
            selected_predictors,
            available_targets,
            predictor_columns,
            GeneralizedRegressionError.FIT_FAILED,
            n_used,
            n_dropped,
        )

    design_width = design.matrix.shape[1]
    params = np.asarray(fit.params, dtype=np.float64)[:design_width]
    std_errors = np.asarray(fit.bse, dtype=np.float64)[:design_width]
    z_values = np.asarray(fit.tvalues, dtype=np.float64)[:design_width]
    p_values = np.asarray(fit.pvalues, dtype=np.float64)[:design_width]
    intervals = np.asarray(fit.conf_int(alpha=1.0 - CONFIDENCE_LEVEL), dtype=np.float64)[:design_width]
    if not all(np.all(np.isfinite(values)) for values in (params, std_errors, z_values, p_values, intervals)):
        return _empty_result(
            model,
            target,
            selected_predictors,
            available_targets,
            predictor_columns,
            GeneralizedRegressionError.FIT_FAILED,
            n_used,
            n_dropped,
        )
    terms = tuple(
        GeneralizedRegressionTerm(
            kind=design.kinds[index],
            column=design.columns[index],
            level=design.levels[index],
            estimate=float(params[index]),
            std_error=float(std_errors[index]),
            z_statistic=float(z_values[index]),
            p_value=float(p_values[index]),
            ci_low=float(intervals[index, 0]),
            ci_high=float(intervals[index, 1]),
            effect=_safe_exp(float(params[index])),
            effect_ci_low=_safe_exp(float(intervals[index, 0])),
            effect_ci_high=_safe_exp(float(intervals[index, 1])),
        )
        for index in range(design_width)
    )
    fitted_values = np.asarray(fit.predict(design.matrix), dtype=np.float64)
    alpha = float(np.asarray(fit.params)[design_width]) if model is RegressionModel.NEGATIVE_BINOMIAL else None
    plot_data, plot_error = (
        _count_plot_data(y, fitted_values, alpha)
        if model in {RegressionModel.POISSON, RegressionModel.NEGATIVE_BINOMIAL}
        else (None, None)
    )
    logistic_plot_data, logistic_plot_error = (
        prepare_logistic_plot_data(y, fitted_values) if model is RegressionModel.LOGISTIC else (None, None)
    )
    dispersion_ratio = (
        _pearson_dispersion(y, fitted_values, int(fit.df_resid))
        if model is not RegressionModel.LOGISTIC and plot_error in {None, CountPlotError.INVALID_VARIANCE}
        else _NAN
    )
    log_likelihood = float(fit.llf)
    null_log_likelihood = float(fit.llnull)

    return GeneralizedRegressionResult(
        model=model,
        target=target,
        predictors=selected_predictors,
        available_targets=available_targets,
        predictor_columns=predictor_columns,
        target_levels=target_levels,
        n_used=n_used,
        n_dropped=n_dropped,
        log_likelihood=log_likelihood,
        null_log_likelihood=null_log_likelihood,
        pseudo_r_squared=float(1.0 - log_likelihood / null_log_likelihood) if null_log_likelihood != 0 else _NAN,
        aic=float(fit.aic),
        df_residual=int(fit.df_resid),
        terms=terms,
        references=design.references,
        dispersion_ratio=dispersion_ratio,
        overdispersed=dispersion_ratio > OVERDISPERSION_THRESHOLD,
        error=None,
        plot_data=plot_data,
        plot_error=plot_error,
        negative_binomial_alpha=alpha,
        logistic_plot_data=logistic_plot_data,
        logistic_plot_error=logistic_plot_error,
    )


def prepare_logistic_plot_data(
    observed: np.ndarray,
    fitted: np.ndarray,
) -> tuple[LogisticRegressionPlotData | None, LogisticPlotError | None]:
    """Prepare in-sample diagnostics without sampling or clipping predictions.

    Args:
        observed: Complete-case binary outcomes encoded as zero and one.
        fitted: Row-aligned event probabilities for the full fitted cohort.

    Returns:
        Immutable diagnostic data, or a structured validation error.
    """
    if (
        observed.ndim != 1
        or observed.size == 0
        or observed.dtype.kind not in "biuf"
        or not np.isfinite(observed).all()
        or not np.array_equal(np.unique(observed), [0, 1])
    ):
        return None, LogisticPlotError.INVALID_OUTCOMES
    if (
        fitted.shape != observed.shape
        or fitted.dtype.kind not in "biuf"
        or not np.isfinite(fitted).all()
        or np.any((fitted < 0) | (fitted > 1))
    ):
        return None, LogisticPlotError.INVALID_PREDICTIONS

    order = np.argsort(-fitted, kind="stable")
    scores = fitted[order]
    outcomes = observed[order]
    endpoints = np.r_[np.flatnonzero(np.diff(scores)), len(scores) - 1]
    positives = np.cumsum(outcomes)[endpoints]
    negatives = endpoints + 1 - positives
    tpr = np.r_[0.0, positives / positives[-1]]
    fpr = np.r_[0.0, negatives / negatives[-1]]
    auc = float(np.sum(np.diff(fpr) * (tpr[:-1] + tpr[1:]) / 2))

    # Duplicate quantile edges collapse; identical probabilities always stay together.
    bin_count = min(_CALIBRATION_MAX_BINS, len(fitted))
    cut_indices = np.ceil(np.arange(1, bin_count) * len(fitted) / bin_count).astype(int)
    edges = np.unique(np.sort(fitted)[cut_indices])
    assignments = np.searchsorted(edges, fitted, side="right")
    means: list[float] = []
    fractions: list[float] = []
    counts: list[int] = []
    for bin_id in np.unique(assignments):
        selected = assignments == bin_id
        means.append(float(np.mean(fitted[selected])))
        fractions.append(float(np.mean(observed[selected])))
        counts.append(int(np.count_nonzero(selected)))
    return LogisticRegressionPlotData(
        false_positive_rates=tuple(float(value) for value in fpr),
        true_positive_rates=tuple(float(value) for value in tpr),
        auc=auc,
        mean_probabilities=tuple(means),
        event_fractions=tuple(fractions),
        bin_counts=tuple(counts),
        n_used=len(observed),
    ), None


def _count_plot_data(
    observed: np.ndarray,
    fitted: np.ndarray,
    alpha: float | None = None,
) -> tuple[CountRegressionPlotData | None, CountPlotError | None]:
    """Prepare count residuals using Poisson or NB2 variance before row sampling.

    Args:
        observed: Complete-case observed counts.
        fitted: Response-scale expected counts in the same row order.
        alpha: Fitted NB2 dispersion, or None for Poisson variance.

    Returns:
        Aligned chart data or an explicit diagnostic error.
    """
    if fitted.shape != observed.shape or not np.isfinite(fitted).all() or np.any(fitted <= 0):
        return None, CountPlotError.INVALID_PREDICTIONS
    if alpha is not None and (not math.isfinite(alpha) or alpha < 0):
        return None, CountPlotError.INVALID_VARIANCE
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        variance = fitted if alpha is None or alpha == 0 else fitted + alpha * np.square(fitted)
        if not np.isfinite(variance).all() or np.any(variance <= 0):
            return None, CountPlotError.INVALID_VARIANCE
        residuals = (observed - fitted) / np.sqrt(variance)
    if not np.isfinite(residuals).all():
        return None, CountPlotError.INVALID_RESIDUALS
    count = len(observed)
    if count > PLOT_SAMPLE_SIZE:
        rng = np.random.default_rng(_PLOT_SEED)
        indices = np.sort(rng.choice(count, size=PLOT_SAMPLE_SIZE, replace=False))
    else:
        indices = np.arange(count)
    return CountRegressionPlotData(
        observed=tuple(float(value) for value in observed[indices]),
        fitted=tuple(float(value) for value in fitted[indices]),
        pearson_residuals=tuple(float(value) for value in residuals[indices]),
        sampled=count > PLOT_SAMPLE_SIZE,
    ), None


def _empty_result(
    model: RegressionModel,
    target: str,
    predictors: tuple[str, ...],
    available_targets: tuple[str, ...],
    predictor_columns: PredictorColumns,
    error: GeneralizedRegressionError,
    n_used: int = 0,
    n_dropped: int = 0,
    error_column: str | None = None,
) -> GeneralizedRegressionResult:
    """Build a structured result for an unavailable or failed model."""
    return GeneralizedRegressionResult(
        model=model,
        target=target,
        predictors=predictors,
        available_targets=available_targets,
        predictor_columns=predictor_columns,
        target_levels=(),
        n_used=n_used,
        n_dropped=n_dropped,
        log_likelihood=_NAN,
        null_log_likelihood=_NAN,
        pseudo_r_squared=_NAN,
        aic=_NAN,
        df_residual=0,
        terms=(),
        references=(),
        dispersion_ratio=_NAN,
        overdispersed=False,
        error=error,
        error_column=error_column,
    )


def _sorted_levels(values: pd.Series) -> list[Any]:
    """Sort outcome levels deterministically, including mixed comparable types."""
    levels = list(pd.unique(values))
    try:
        return sorted(levels)
    except TypeError:
        return sorted(levels, key=str)


def _safe_exp(value: float) -> float:
    """Exponentiate a coefficient while representing overflow as infinity."""
    try:
        return math.exp(value)
    except OverflowError:
        return math.inf


def _pearson_dispersion(observed: np.ndarray, fitted: np.ndarray, df_residual: int) -> float:
    """Return the Pearson chi-square per residual degree of freedom."""
    if df_residual <= 0 or np.any(fitted <= 0):
        return _NAN
    return float(np.sum(np.square(observed - fitted) / fitted) / df_residual)


def generalized_term_name(term: GeneralizedRegressionTerm) -> str:
    """Return a display name using the shared linear-regression term convention."""
    if term.kind is TermKind.DUMMY:
        return f"{term.column} = {term.level}"
    return term.column
