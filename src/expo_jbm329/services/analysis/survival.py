"""Cox proportional-hazards regression services."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype
from statsmodels.duration.hazard_regression import PHReg
from statsmodels.tools.sm_exceptions import ConvergenceWarning

from expo_jbm329.services.analysis.columns import numeric_columns
from expo_jbm329.services.analysis.regression import (
    CONFIDENCE_LEVEL,
    MAX_MODEL_TERMS,
    MAX_PREDICTORS,
    CategoricalReference,
    PredictorColumns,
    PredictorKind,
    TermKind,
    build_regression_design,
    classify_predictor_columns,
)

_NAN = float("nan")
_MIN_DISTINCT = 2


class SurvivalError(StrEnum):
    """Reasons a Cox regression could not be fitted."""

    NO_DURATION = "no_duration"
    NO_EVENT = "no_event"
    NO_PREDICTORS_SELECTED = "no_predictors_selected"
    TOO_MANY_PREDICTORS = "too_many_predictors"
    INVALID_COLUMN = "invalid_column"
    INVALID_DURATION = "invalid_duration"
    INVALID_EVENT = "invalid_event"
    TOO_MANY_TERMS = "too_many_terms"
    NOT_ENOUGH_OBSERVATIONS = "not_enough_observations"
    NOT_ENOUGH_EVENTS = "not_enough_events"
    CONSTANT_PREDICTOR = "constant_predictor"
    PERFECT_MULTICOLLINEARITY = "perfect_multicollinearity"
    FIT_FAILED = "fit_failed"


@dataclass(frozen=True, slots=True)
class SurvivalColumns:
    """Columns available for survival outcomes."""

    durations: tuple[str, ...]
    events: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SurvivalTerm:
    """A Cox model coefficient and its exponentiated hazard ratio."""

    kind: TermKind
    column: str
    level: str | None
    estimate: float
    std_error: float
    z_statistic: float
    p_value: float
    ci_low: float
    ci_high: float
    hazard_ratio: float
    hazard_ratio_ci_low: float
    hazard_ratio_ci_high: float


@dataclass(frozen=True, slots=True)
class SurvivalPlotData:
    """Exact complete-cohort Kaplan-Meier steps and risk counts.

    Arrays include time zero, then every unique observed time. Survival is
    evaluated after events at each time; at_risk counts precede both events
    and censoring. Censor counts at time zero are zero. Risk times/counts
    provide five uniformly spaced display times and exact preceding risk sets.
    """

    times: tuple[float, ...]
    survival: tuple[float, ...]
    at_risk: tuple[int, ...]
    events: tuple[int, ...]
    censored: tuple[int, ...]
    risk_times: tuple[float, ...]
    risk_counts: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SurvivalResult:
    """Cox regression result or structured validation/fitting error."""

    duration: str
    event: str
    predictors: tuple[str, ...]
    columns: SurvivalColumns
    predictor_columns: PredictorColumns
    n_used: int
    n_dropped: int
    n_events: int
    n_censored: int
    terms: tuple[SurvivalTerm, ...]
    references: tuple[CategoricalReference, ...]
    error: SurvivalError | None
    error_column: str | None = None
    plot_data: SurvivalPlotData | None = None


def initialize_survival_columns(df: pd.DataFrame) -> SurvivalColumns:
    """Find numeric duration and strictly binary numeric/boolean event columns."""
    numeric = numeric_columns(df)
    events: list[str] = []
    for column in df.columns:
        is_boolean = is_bool_dtype(df[column].dtype)
        if not is_boolean and column not in numeric:
            continue
        values = df[column].dropna()
        if len(values) == 0:
            continue
        if is_boolean:
            events.append(column)
        elif column in numeric:
            observed = pd.to_numeric(values, errors="coerce").to_numpy(dtype=np.float64)
            if np.isfinite(observed).all() and np.isin(observed, (0.0, 1.0)).all():
                events.append(column)
    return SurvivalColumns(durations=numeric, events=tuple(events))


def analyze_cox_regression(
    df: pd.DataFrame,
    duration: str,
    event: str,
    predictors: tuple[str, ...] | list[str],
) -> SurvivalResult:
    """Fit a Cox proportional-hazards model with Efron handling of tied events.

    Missing values are handled by complete-case deletion, but invalid
    non-missing duration and event values are rejected before that deletion.
    """
    selected_predictors = tuple(predictors)
    columns = initialize_survival_columns(df)
    predictor_columns = classify_predictor_columns(df)
    kinds = dict.fromkeys(predictor_columns.numeric, PredictorKind.NUMERIC)
    kinds |= dict.fromkeys(predictor_columns.categorical, PredictorKind.CATEGORICAL)

    if not duration:
        return _empty_result(
            duration, event, selected_predictors, columns, predictor_columns, SurvivalError.NO_DURATION
        )
    if not event:
        return _empty_result(duration, event, selected_predictors, columns, predictor_columns, SurvivalError.NO_EVENT)
    if duration == event or duration not in columns.durations or event not in df.columns:
        return _empty_result(
            duration, event, selected_predictors, columns, predictor_columns, SurvivalError.INVALID_COLUMN
        )
    if not selected_predictors:
        return _empty_result(
            duration, event, selected_predictors, columns, predictor_columns, SurvivalError.NO_PREDICTORS_SELECTED
        )
    if len(selected_predictors) > MAX_PREDICTORS:
        return _empty_result(
            duration, event, selected_predictors, columns, predictor_columns, SurvivalError.TOO_MANY_PREDICTORS
        )
    if (
        len(set(selected_predictors)) != len(selected_predictors)
        or duration in selected_predictors
        or event in selected_predictors
        or any(column not in kinds for column in selected_predictors)
    ):
        return _empty_result(
            duration, event, selected_predictors, columns, predictor_columns, SurvivalError.INVALID_COLUMN
        )

    raw_duration = df[duration]
    numeric_duration = pd.to_numeric(raw_duration, errors="coerce").astype("float64")
    nonmissing_duration = raw_duration.notna()
    invalid_duration = nonmissing_duration & (~np.isfinite(numeric_duration) | (numeric_duration <= 0))
    if invalid_duration.any():
        return _empty_result(
            duration,
            event,
            selected_predictors,
            columns,
            predictor_columns,
            SurvivalError.INVALID_DURATION,
            error_column=duration,
        )

    raw_event = df[event]
    if not (is_bool_dtype(raw_event.dtype) or is_numeric_dtype(raw_event.dtype)):
        return _empty_result(
            duration,
            event,
            selected_predictors,
            columns,
            predictor_columns,
            SurvivalError.INVALID_EVENT,
            error_column=event,
        )
    numeric_event = pd.to_numeric(raw_event, errors="coerce").astype("float64")
    nonmissing_event = raw_event.notna()
    invalid_event = nonmissing_event & (~np.isfinite(numeric_event) | ~numeric_event.isin((0.0, 1.0)))
    if invalid_event.any():
        return _empty_result(
            duration,
            event,
            selected_predictors,
            columns,
            predictor_columns,
            SurvivalError.INVALID_EVENT,
            error_column=event,
        )

    data = pd.DataFrame(index=df.index)
    data[duration] = numeric_duration.where(np.isfinite(numeric_duration))
    data[event] = numeric_event
    for column in selected_predictors:
        if kinds[column] is PredictorKind.NUMERIC:
            values = pd.to_numeric(df[column], errors="coerce").astype("float64")
            data[column] = values.where(np.isfinite(values))
        else:
            data[column] = df[column]
    data = data.dropna()
    n_used = len(data)
    n_dropped = len(df) - n_used
    n_events = int(data[event].sum())
    n_censored = n_used - n_events
    if n_used <= 1:
        return _empty_result(
            duration,
            event,
            selected_predictors,
            columns,
            predictor_columns,
            SurvivalError.NOT_ENOUGH_OBSERVATIONS,
            n_used,
            n_dropped,
            n_events,
            n_censored,
        )

    for column in selected_predictors:
        if data[column].nunique() < _MIN_DISTINCT:
            return _empty_result(
                duration,
                event,
                selected_predictors,
                columns,
                predictor_columns,
                SurvivalError.CONSTANT_PREDICTOR,
                n_used,
                n_dropped,
                n_events,
                n_censored,
                column,
            )
    term_count = sum(
        1 if kinds[column] is PredictorKind.NUMERIC else int(data[column].nunique()) - 1
        for column in selected_predictors
    )
    if term_count > MAX_MODEL_TERMS:
        error = SurvivalError.TOO_MANY_TERMS
    elif n_used <= term_count:
        error = SurvivalError.NOT_ENOUGH_OBSERVATIONS
    elif n_events <= term_count:
        error = SurvivalError.NOT_ENOUGH_EVENTS
    else:
        error = None
    if error is not None:
        return _empty_result(
            duration,
            event,
            selected_predictors,
            columns,
            predictor_columns,
            error,
            n_used,
            n_dropped,
            n_events,
            n_censored,
        )

    design = build_regression_design(data, selected_predictors, kinds)
    exog = design.matrix[:, 1:]
    # A constant linear combination is absorbed by the unspecified baseline hazard.
    if np.linalg.matrix_rank(design.matrix) < design.matrix.shape[1]:
        return _empty_result(
            duration,
            event,
            selected_predictors,
            columns,
            predictor_columns,
            SurvivalError.PERFECT_MULTICOLLINEARITY,
            n_used,
            n_dropped,
            n_events,
            n_censored,
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            warnings.simplefilter("error", RuntimeWarning)
            fit = PHReg(
                data[duration].to_numpy(dtype=np.float64),
                exog,
                status=data[event].to_numpy(dtype=np.int64),
                ties="efron",
                missing="raise",
            ).fit(disp=False, maxiter=200)
            params = np.asarray(fit.params, dtype=np.float64)
            std_errors = np.asarray(fit.bse, dtype=np.float64)
            z_values = np.asarray(fit.tvalues, dtype=np.float64)
            p_values = np.asarray(fit.pvalues, dtype=np.float64)
            intervals = np.asarray(fit.conf_int(alpha=1.0 - CONFIDENCE_LEVEL), dtype=np.float64)
    except (ConvergenceWarning, RuntimeWarning, np.linalg.LinAlgError, ValueError, RuntimeError, FloatingPointError):
        return _empty_result(
            duration,
            event,
            selected_predictors,
            columns,
            predictor_columns,
            SurvivalError.FIT_FAILED,
            n_used,
            n_dropped,
            n_events,
            n_censored,
        )

    if not all(np.all(np.isfinite(values)) for values in (params, std_errors, z_values, p_values, intervals)):
        return _empty_result(
            duration,
            event,
            selected_predictors,
            columns,
            predictor_columns,
            SurvivalError.FIT_FAILED,
            n_used,
            n_dropped,
            n_events,
            n_censored,
        )
    terms = tuple(
        SurvivalTerm(
            kind=design.kinds[index + 1],
            column=design.columns[index + 1],
            level=design.levels[index + 1],
            estimate=float(params[index]),
            std_error=float(std_errors[index]),
            z_statistic=float(z_values[index]),
            p_value=float(p_values[index]),
            ci_low=float(intervals[index, 0]),
            ci_high=float(intervals[index, 1]),
            hazard_ratio=_safe_exp(float(params[index])),
            hazard_ratio_ci_low=_safe_exp(float(intervals[index, 0])),
            hazard_ratio_ci_high=_safe_exp(float(intervals[index, 1])),
        )
        for index in range(len(params))
    )
    if any(
        not math.isfinite(value)
        for term in terms
        for value in (term.hazard_ratio, term.hazard_ratio_ci_low, term.hazard_ratio_ci_high)
    ):
        return _empty_result(
            duration,
            event,
            selected_predictors,
            columns,
            predictor_columns,
            SurvivalError.FIT_FAILED,
            n_used,
            n_dropped,
            n_events,
            n_censored,
        )
    return SurvivalResult(
        duration=duration,
        event=event,
        predictors=selected_predictors,
        columns=columns,
        predictor_columns=predictor_columns,
        n_used=n_used,
        n_dropped=n_dropped,
        n_events=n_events,
        n_censored=n_censored,
        terms=terms,
        references=design.references,
        error=None,
        plot_data=_survival_plot_data(
            data[duration].to_numpy(dtype=np.float64),
            data[event].to_numpy(dtype=np.int64),
        ),
    )


def _survival_plot_data(durations: np.ndarray, events: np.ndarray) -> SurvivalPlotData:
    """Calculate Kaplan-Meier steps on the validated Cox complete-case cohort.

    Subjects censored at an event time remain at risk for that time's events.
    Every unique time is retained, including censor-only times and final follow-up.
    """
    times, inverse, counts = np.unique(durations, return_inverse=True, return_counts=True)
    event_counts = np.bincount(inverse, weights=events).astype(np.int64)
    censored_counts = counts - event_counts
    at_risk = len(durations) - np.concatenate(([0], np.cumsum(counts[:-1])))
    survival = np.cumprod(1.0 - event_counts / at_risk)
    risk_times = np.linspace(0.0, times[-1], 5)
    risk_counts = len(durations) - np.searchsorted(np.sort(durations), risk_times, side="left")
    return SurvivalPlotData(
        times=(0.0, *(float(value) for value in times)),
        survival=(1.0, *(float(value) for value in survival)),
        at_risk=(len(durations), *(int(value) for value in at_risk)),
        events=(0, *(int(value) for value in event_counts)),
        censored=(0, *(int(value) for value in censored_counts)),
        risk_times=tuple(float(value) for value in risk_times),
        risk_counts=tuple(int(value) for value in risk_counts),
    )


def _empty_result(
    duration: str,
    event: str,
    predictors: tuple[str, ...],
    columns: SurvivalColumns,
    predictor_columns: PredictorColumns,
    error: SurvivalError,
    n_used: int = 0,
    n_dropped: int = 0,
    n_events: int = 0,
    n_censored: int = 0,
    error_column: str | None = None,
) -> SurvivalResult:
    """Create a structured error result."""
    return SurvivalResult(
        duration=duration,
        event=event,
        predictors=predictors,
        columns=columns,
        predictor_columns=predictor_columns,
        n_used=n_used,
        n_dropped=n_dropped,
        n_events=n_events,
        n_censored=n_censored,
        terms=(),
        references=(),
        error=error,
        error_column=error_column,
    )


def survival_term_name(term: SurvivalTerm) -> str:
    """Return a human-readable coefficient term."""
    if term.kind is TermKind.DUMMY:
        return f"{term.column} = {term.level}"
    return term.column


def _safe_exp(value: float) -> float:
    """Exponentiate a coefficient, returning infinity on overflow."""
    try:
        return math.exp(value)
    except OverflowError:
        return math.inf
