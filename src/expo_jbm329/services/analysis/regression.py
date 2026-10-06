"""Multiple linear regression (ordinary least squares).

Fits a numeric target on one or more predictors with statsmodels OLS.
Numeric predictors enter the model as-is. Categorical predictors (text,
category or boolean columns with an acceptable number of levels, see
`group_comparison.classify_grouping_columns`) are dummy-coded against
their most frequent level, which becomes the reference.

Rows with a missing value in the target or any predictor are dropped
(listwise deletion). Statistics always use every remaining row; only the
diagnostic plot data is capped at `PLOT_SAMPLE_SIZE` points.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.stattools import durbin_watson, jarque_bera

from expo_jbm329.services.analysis.columns import numeric_columns
from expo_jbm329.services.analysis.group_comparison import ExcludedColumn, classify_grouping_columns
from expo_jbm329.services.data_operations.dtypes import SemanticDType, classify_series_dtype

if TYPE_CHECKING:
    from collections.abc import Sequence

_NAN = float("nan")

MAX_PREDICTORS = 20
# Dummy coding can multiply the number of model terms; cap the design
# matrix width to keep memory and fitting time reasonable on large data.
MAX_MODEL_TERMS = 50

CONFIDENCE_LEVEL = 0.95
SIGNIFICANCE_LEVEL = 0.05

# Conventional rule of thumb: a VIF above 10 signals problematic
# multicollinearity.
HIGH_VIF_THRESHOLD = 10.0
# Durbin-Watson values outside this range suggest autocorrelated residuals.
DURBIN_WATSON_LOW = 1.5
DURBIN_WATSON_HIGH = 2.5

PLOT_SAMPLE_SIZE = 5_000
# A fixed seed keeps the plotted sample identical across runs.
_PLOT_SEED = 0

_CATEGORICAL_DTYPES = frozenset({SemanticDType.STRING, SemanticDType.CATEGORY, SemanticDType.BOOL})

# A predictor or target needs two distinct values to vary at all.
_MIN_DISTINCT = 2

# Blom's plotting positions for normal Q-Q plots.
_BLOM_OFFSET = 0.375


class PredictorKind(StrEnum):
    """How a predictor column enters the model."""

    NUMERIC = "numeric"
    CATEGORICAL = "categorical"


class TermKind(StrEnum):
    """Kind of a fitted model term."""

    INTERCEPT = "intercept"
    NUMERIC = "numeric"
    DUMMY = "dummy"


class RegressionError(StrEnum):
    """Reasons a regression could not be fitted.

    Kept UI-text-free (a plain reason code) so the GUI layer owns
    translation, matching the other analysis services.
    """

    NO_NUMERIC_COLUMN = "no_numeric_column"
    NO_PREDICTORS_SELECTED = "no_predictors_selected"
    TOO_MANY_PREDICTORS = "too_many_predictors"
    INVALID_COLUMN = "invalid_column"
    TOO_MANY_TERMS = "too_many_terms"
    NOT_ENOUGH_OBSERVATIONS = "not_enough_observations"
    CONSTANT_TARGET = "constant_target"
    CONSTANT_PREDICTOR = "constant_predictor"
    PERFECT_MULTICOLLINEARITY = "perfect_multicollinearity"


class RegressionWarningReason(StrEnum):
    """Non-blocking caveats about a fitted model."""

    HIGH_MULTICOLLINEARITY = "high_multicollinearity"
    HETEROSCEDASTICITY = "heteroscedasticity"
    NON_NORMAL_RESIDUALS = "non_normal_residuals"
    AUTOCORRELATION = "autocorrelation"


@dataclass(frozen=True, slots=True)
class PredictorColumns:
    """Every column usable as a predictor, by kind.

    Attributes:
        numeric: Numeric (int or float) columns, in column order.
        categorical: Text, category and boolean columns with an acceptable
            number of distinct values, in column order.
        excluded: Text, category and boolean columns with too few or too
            many distinct values, with the reason.
    """

    numeric: tuple[str, ...]
    categorical: tuple[str, ...]
    excluded: tuple[ExcludedColumn, ...]


@dataclass(frozen=True, slots=True)
class RegressionTerm:
    """One fitted coefficient.

    Attributes:
        kind: Intercept, numeric predictor or dummy variable.
        column: The predictor column (``""`` for the intercept).
        level: The dummy's level (`None` unless `kind` is `DUMMY`).
        estimate: The coefficient.
        std_error: Its standard error.
        t_statistic: Its t statistic.
        p_value: Two-sided p-value for "coefficient is zero".
        ci_low: Lower bound of the `CONFIDENCE_LEVEL` confidence interval.
        ci_high: Upper bound of the `CONFIDENCE_LEVEL` confidence interval.
        vif: Variance inflation factor; NaN for the intercept.
    """

    kind: TermKind
    column: str
    level: str | None
    estimate: float
    std_error: float
    t_statistic: float
    p_value: float
    ci_low: float
    ci_high: float
    vif: float


@dataclass(frozen=True, slots=True)
class CategoricalReference:
    """The reference (baseline) level of one dummy-coded predictor.

    Attributes:
        column: The categorical predictor column.
        reference_level: Its most frequent level, left out of the dummies.
        level_count: Number of distinct levels in the rows used.
    """

    column: str
    reference_level: str
    level_count: int


@dataclass(frozen=True, slots=True)
class RegressionDiagnostics:
    """Residual and multicollinearity diagnostics.

    Attributes:
        breusch_pagan_statistic: Breusch-Pagan LM statistic.
        breusch_pagan_p_value: Its p-value (small means heteroscedasticity).
        jarque_bera_statistic: Jarque-Bera statistic of the residuals.
        jarque_bera_p_value: Its p-value (small means non-normal residuals).
        durbin_watson: Durbin-Watson statistic (about 2 means no
            first-order autocorrelation, in row order).
        max_vif: The largest VIF over all non-intercept terms.
    """

    breusch_pagan_statistic: float
    breusch_pagan_p_value: float
    jarque_bera_statistic: float
    jarque_bera_p_value: float
    durbin_watson: float
    max_vif: float


@dataclass(frozen=True, slots=True)
class RegressionWarning:
    """One non-blocking caveat.

    Attributes:
        reason: What the caveat is about.
        terms: Display names of the affected terms (high multicollinearity
            only), otherwise empty.
    """

    reason: RegressionWarningReason
    terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RegressionPlotData:
    """Point data for the diagnostic plots, possibly sampled.

    Attributes:
        actual: Observed target values of the sampled rows.
        fitted: Fitted values of the same rows.
        residuals: Raw residuals of the same rows.
        qq_theoretical: Theoretical standard normal quantiles.
        qq_sample: Sorted standardized residuals of the sampled rows.
        sampled: Whether fewer points than rows used are included.
    """

    actual: tuple[float, ...]
    fitted: tuple[float, ...]
    residuals: tuple[float, ...]
    qq_theoretical: tuple[float, ...]
    qq_sample: tuple[float, ...]
    sampled: bool


@dataclass(frozen=True, slots=True)
class RegressionResult:
    """A fitted linear regression, or the reason none could be fitted.

    Attributes:
        target: The target column (``""`` without numeric columns).
        predictors: The requested predictor columns, in the given order.
        available_targets: Every numeric column, for the target picker.
        predictor_columns: Every column usable as a predictor.
        n_used: Rows used after listwise deletion.
        n_dropped: Rows dropped because of a missing value.
        r_squared: Coefficient of determination.
        adjusted_r_squared: R-squared adjusted for the number of terms.
        f_statistic: Overall F statistic.
        f_p_value: Its p-value.
        df_model: Model degrees of freedom (non-intercept terms).
        df_residual: Residual degrees of freedom.
        rmse: Root mean squared error (residual standard error).
        aic: Akaike information criterion.
        terms: The intercept followed by every predictor term.
        references: The reference level of every categorical predictor.
        diagnostics: Residual and multicollinearity diagnostics.
        warnings: Non-blocking caveats derived from `diagnostics`.
        plot: Diagnostic plot data.
        error: A structured reason no model was fitted, or `None`.
        error_column: The column the error is about, when applicable.
    """

    target: str
    predictors: tuple[str, ...]
    available_targets: tuple[str, ...]
    predictor_columns: PredictorColumns
    n_used: int
    n_dropped: int
    r_squared: float
    adjusted_r_squared: float
    f_statistic: float
    f_p_value: float
    df_model: int
    df_residual: int
    rmse: float
    aic: float
    terms: tuple[RegressionTerm, ...]
    references: tuple[CategoricalReference, ...]
    diagnostics: RegressionDiagnostics | None
    warnings: tuple[RegressionWarning, ...]
    plot: RegressionPlotData | None
    error: RegressionError | None
    error_column: str | None = None


# ----------------------------------------------------------------------
# Public helpers
# ----------------------------------------------------------------------


def classify_predictor_columns(df: pd.DataFrame) -> PredictorColumns:
    """Split the columns into numeric, categorical and excluded predictors.

    Datetime and other column types are not usable and are left out.

    Args:
        df: The DataFrame to inspect. Never mutated.

    Returns:
        The usable predictor columns, by kind.
    """
    categorical_candidates = [
        column for column in df.columns if classify_series_dtype(df[column]) in _CATEGORICAL_DTYPES
    ]
    grouping = classify_grouping_columns(df[categorical_candidates])
    return PredictorColumns(
        numeric=numeric_columns(df),
        categorical=grouping.eligible,
        excluded=grouping.excluded,
    )


def term_name(term: RegressionTerm) -> str:
    """Return a term's display name: the column, or ``"column = level"`` for dummies.

    The intercept's name is ``""``; the GUI shows a translated label.
    """
    if term.kind is TermKind.DUMMY:
        return f"{term.column} = {term.level}"
    return term.column


def initialize_regression(df: pd.DataFrame) -> RegressionResult:
    """Build the initial regression selection state without fitting a model.

    Args:
        df: The DataFrame whose available targets and predictors are needed.

    Returns:
        A regression result containing selection metadata and the appropriate
        initial prompt or missing-numeric-column error.
    """
    available_targets, predictor_columns = _regression_columns(df)
    target = available_targets[0] if available_targets else ""
    error = RegressionError.NO_PREDICTORS_SELECTED if available_targets else RegressionError.NO_NUMERIC_COLUMN
    return _error_result(
        error,
        target=target,
        predictors=(),
        available_targets=available_targets,
        predictor_columns=predictor_columns,
    )


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegressionDesign:
    """The model's design matrix and the terms its columns represent."""

    matrix: np.ndarray
    kinds: tuple[TermKind, ...]
    columns: tuple[str, ...]
    levels: tuple[str | None, ...]
    references: tuple[CategoricalReference, ...]


def _numeric_values(series: pd.Series) -> pd.Series:
    """Return a column as float64 with missing and infinite values as NaN."""
    values = pd.to_numeric(series, errors="coerce").astype("float64")
    return values.where(np.isfinite(values))


def _regression_columns(df: pd.DataFrame) -> tuple[tuple[str, ...], PredictorColumns]:
    """Return target and predictor metadata for regression configuration."""
    return numeric_columns(df), classify_predictor_columns(df)


def _sorted_levels(values: pd.Series) -> list[Any]:
    """Return a column's distinct values in ascending order (as text if not comparable)."""
    levels = list(pd.unique(values))
    try:
        return sorted(levels)
    except TypeError:
        return sorted(levels, key=str)


def _categorical_terms(column: str, values: pd.Series) -> tuple[list[np.ndarray], list[str], CategoricalReference]:
    """Dummy-code one categorical column against its most frequent level."""
    levels = _sorted_levels(values)
    counts: dict[Any, int] = values.value_counts().to_dict()
    # The most frequent level; ties are broken by level order.
    reference = max(levels, key=lambda level: (counts[level], -levels.index(level)))

    dummies: list[np.ndarray] = []
    labels: list[str] = []
    for level in levels:
        if level == reference:
            continue
        dummies.append((values == level).to_numpy(dtype="float64"))
        labels.append(str(level))

    return dummies, labels, CategoricalReference(column, str(reference), len(levels))


def build_regression_design(
    data: pd.DataFrame,
    predictors: tuple[str, ...],
    kinds: dict[str, PredictorKind],
) -> RegressionDesign:
    """Build the design matrix (intercept first) for NaN-free `data`."""
    matrix_columns: list[np.ndarray] = [np.ones(len(data))]
    term_kinds: list[TermKind] = [TermKind.INTERCEPT]
    term_columns: list[str] = [""]
    term_levels: list[str | None] = [None]
    references: list[CategoricalReference] = []

    for column in predictors:
        if kinds[column] is PredictorKind.NUMERIC:
            matrix_columns.append(data[column].to_numpy(dtype="float64"))
            term_kinds.append(TermKind.NUMERIC)
            term_columns.append(column)
            term_levels.append(None)
            continue

        dummies, labels, reference = _categorical_terms(column, data[column])
        matrix_columns.extend(dummies)
        term_kinds.extend([TermKind.DUMMY] * len(dummies))
        term_columns.extend([column] * len(dummies))
        term_levels.extend(labels)
        references.append(reference)

    return RegressionDesign(
        matrix=np.column_stack(matrix_columns),
        kinds=tuple(term_kinds),
        columns=tuple(term_columns),
        levels=tuple(term_levels),
        references=tuple(references),
    )


def _variance_inflation_factors(matrix: np.ndarray) -> np.ndarray:
    """Return the VIF of every non-intercept design column.

    For a model with an intercept, VIFs are the diagonal of the inverse
    correlation matrix of the other columns - equivalent to regressing
    each column on the rest, but far cheaper.
    """
    predictors = matrix[:, 1:]
    if predictors.shape[1] == 1:
        return np.ones(1)
    correlation = np.corrcoef(predictors, rowvar=False)
    return np.diag(np.linalg.inv(correlation))


def _plot_data(actual: np.ndarray, fitted: np.ndarray, residuals: np.ndarray, rmse: float) -> RegressionPlotData:
    """Build the (possibly sampled) diagnostic plot data."""
    n = len(actual)
    if n > PLOT_SAMPLE_SIZE:
        rng = np.random.default_rng(_PLOT_SEED)
        indices = np.sort(rng.choice(n, size=PLOT_SAMPLE_SIZE, replace=False))
    else:
        indices = np.arange(n)

    sample_residuals = residuals[indices]
    standardized = np.sort(sample_residuals / rmse) if rmse > 0 else np.sort(sample_residuals)
    m = len(standardized)
    positions = (np.arange(1, m + 1) - _BLOM_OFFSET) / (m + 1 - 2 * _BLOM_OFFSET)

    return RegressionPlotData(
        actual=tuple(float(value) for value in actual[indices]),
        fitted=tuple(float(value) for value in fitted[indices]),
        residuals=tuple(float(value) for value in sample_residuals),
        qq_theoretical=tuple(float(value) for value in norm.ppf(positions)),
        qq_sample=tuple(float(value) for value in standardized),
        sampled=m < n,
    )


def _warnings(diagnostics: RegressionDiagnostics, terms: tuple[RegressionTerm, ...]) -> tuple[RegressionWarning, ...]:
    """Derive the non-blocking caveats from the diagnostics."""
    found: list[RegressionWarning] = []

    high_vif = tuple(term_name(term) for term in terms if term.vif > HIGH_VIF_THRESHOLD)
    if high_vif:
        found.append(RegressionWarning(RegressionWarningReason.HIGH_MULTICOLLINEARITY, high_vif))
    if diagnostics.breusch_pagan_p_value < SIGNIFICANCE_LEVEL:
        found.append(RegressionWarning(RegressionWarningReason.HETEROSCEDASTICITY))
    if diagnostics.jarque_bera_p_value < SIGNIFICANCE_LEVEL:
        found.append(RegressionWarning(RegressionWarningReason.NON_NORMAL_RESIDUALS))
    if not DURBIN_WATSON_LOW <= diagnostics.durbin_watson <= DURBIN_WATSON_HIGH:
        found.append(RegressionWarning(RegressionWarningReason.AUTOCORRELATION))

    return tuple(found)


def _error_result(
    error: RegressionError,
    *,
    target: str,
    predictors: tuple[str, ...],
    available_targets: tuple[str, ...],
    predictor_columns: PredictorColumns,
    n_used: int = 0,
    n_dropped: int = 0,
    error_column: str | None = None,
) -> RegressionResult:
    """Build a `RegressionResult` carrying only a structured error."""
    return RegressionResult(
        target=target,
        predictors=predictors,
        available_targets=available_targets,
        predictor_columns=predictor_columns,
        n_used=n_used,
        n_dropped=n_dropped,
        r_squared=_NAN,
        adjusted_r_squared=_NAN,
        f_statistic=_NAN,
        f_p_value=_NAN,
        df_model=0,
        df_residual=0,
        rmse=_NAN,
        aic=_NAN,
        terms=(),
        references=(),
        diagnostics=None,
        warnings=(),
        plot=None,
        error=error,
        error_column=error_column,
    )


def _selection_error(
    target: str,
    predictors: tuple[str, ...],
    available_targets: tuple[str, ...],
    kinds: dict[str, PredictorKind],
) -> RegressionError | None:
    """Validate the target/predictor selection, returning the first problem found."""
    if target not in available_targets:
        return RegressionError.INVALID_COLUMN
    if not predictors:
        return RegressionError.NO_PREDICTORS_SELECTED
    if len(predictors) > MAX_PREDICTORS:
        return RegressionError.TOO_MANY_PREDICTORS
    if len(set(predictors)) != len(predictors) or target in predictors or any(p not in kinds for p in predictors):
        return RegressionError.INVALID_COLUMN
    return None


def _prepare_data(
    df: pd.DataFrame,
    target: str,
    predictors: tuple[str, ...],
    kinds: dict[str, PredictorKind],
) -> pd.DataFrame:
    """Return the target and predictors with numeric columns cleaned and incomplete rows dropped."""
    data = pd.DataFrame(index=df.index)
    data[target] = _numeric_values(df[target])
    for column in predictors:
        data[column] = _numeric_values(df[column]) if kinds[column] is PredictorKind.NUMERIC else df[column]
    return data.dropna()


def _constant_predictor(data: pd.DataFrame, predictors: tuple[str, ...]) -> str | None:
    """Return the first predictor with fewer than two distinct values, if any."""
    return next((column for column in predictors if data[column].nunique() < _MIN_DISTINCT), None)


def _term_count(data: pd.DataFrame, predictors: tuple[str, ...], kinds: dict[str, PredictorKind]) -> int:
    """Return the number of non-intercept model terms, without building the design."""
    return sum(
        1 if kinds[column] is PredictorKind.NUMERIC else max(int(data[column].nunique()) - 1, 0)
        for column in predictors
    )


# ----------------------------------------------------------------------
# Analysis
# ----------------------------------------------------------------------


def analyze_regression(
    df: pd.DataFrame,
    target: str | None = None,
    predictors: Sequence[str] = (),
) -> RegressionResult:
    """Fit an ordinary least squares regression of `target` on `predictors`.

    Args:
        df: The DataFrame to analyze. Never mutated.
        target: The numeric target column. Defaults to the first numeric
            column when `None`.
        predictors: Predictor columns: numeric, or categorical as
            classified by `classify_predictor_columns`. With none, the
            result carries `NO_PREDICTORS_SELECTED` (but is still usable
            to populate the configuration).

    Returns:
        The fitted model, or a result with `error` set when the selection
        is unusable or the model can't be estimated.
    """
    available_targets, predictor_columns = _regression_columns(df)
    requested = tuple(predictors)
    chosen_target = (available_targets[0] if available_targets else "") if target is None else target

    def _error(
        error: RegressionError,
        *,
        n_used: int = 0,
        n_dropped: int = 0,
        error_column: str | None = None,
    ) -> RegressionResult:
        return _error_result(
            error,
            target=chosen_target,
            predictors=requested,
            available_targets=available_targets,
            predictor_columns=predictor_columns,
            n_used=n_used,
            n_dropped=n_dropped,
            error_column=error_column,
        )

    if not available_targets:
        return _error(RegressionError.NO_NUMERIC_COLUMN)

    kinds = dict.fromkeys(predictor_columns.numeric, PredictorKind.NUMERIC)
    kinds |= dict.fromkeys(predictor_columns.categorical, PredictorKind.CATEGORICAL)
    selection_error = _selection_error(chosen_target, requested, available_targets, kinds)
    if selection_error is not None:
        return _error(selection_error)

    data = _prepare_data(df, chosen_target, requested, kinds)
    n_used = len(data)
    n_dropped = len(df) - n_used

    term_count = _term_count(data, requested, kinds)
    if term_count > MAX_MODEL_TERMS:
        return _error(RegressionError.TOO_MANY_TERMS, n_used=n_used, n_dropped=n_dropped)
    # At least one residual degree of freedom is needed beyond the terms
    # and the intercept.
    if n_used <= term_count + 1:
        return _error(RegressionError.NOT_ENOUGH_OBSERVATIONS, n_used=n_used, n_dropped=n_dropped)
    if data[chosen_target].nunique() < _MIN_DISTINCT:
        return _error(RegressionError.CONSTANT_TARGET, n_used=n_used, n_dropped=n_dropped)
    constant_column = _constant_predictor(data, requested)
    if constant_column is not None:
        return _error(
            RegressionError.CONSTANT_PREDICTOR,
            n_used=n_used,
            n_dropped=n_dropped,
            error_column=constant_column,
        )

    design = build_regression_design(data, requested, kinds)
    y = data[chosen_target].to_numpy(dtype="float64")
    with warnings.catch_warnings():
        # Degenerate fits are reported via structured errors instead.
        warnings.simplefilter("ignore")
        model: Any = sm.OLS(y, design.matrix)
        fit = model.fit()

    if int(model.rank) < design.matrix.shape[1]:
        return _error(RegressionError.PERFECT_MULTICOLLINEARITY, n_used=n_used, n_dropped=n_dropped)

    return _fitted_result(
        fit,
        design,
        y,
        target=chosen_target,
        predictors=requested,
        available_targets=available_targets,
        predictor_columns=predictor_columns,
        n_dropped=n_dropped,
    )


def _fitted_result(
    fit: Any,  # noqa: ANN401 - statsmodels results are untyped
    design: RegressionDesign,
    y: np.ndarray,
    *,
    target: str,
    predictors: tuple[str, ...],
    available_targets: tuple[str, ...],
    predictor_columns: PredictorColumns,
    n_dropped: int,
) -> RegressionResult:
    """Assemble the result of a successful fit."""
    params = np.asarray(fit.params, dtype=float)
    std_errors = np.asarray(fit.bse, dtype=float)
    t_values = np.asarray(fit.tvalues, dtype=float)
    p_values = np.asarray(fit.pvalues, dtype=float)
    intervals = np.asarray(fit.conf_int(alpha=1.0 - CONFIDENCE_LEVEL), dtype=float)
    residuals = np.asarray(fit.resid, dtype=float)
    fitted = np.asarray(fit.fittedvalues, dtype=float)
    rmse = math.sqrt(float(fit.mse_resid))

    vifs = np.concatenate(([_NAN], _variance_inflation_factors(design.matrix)))
    terms = tuple(
        RegressionTerm(
            kind=design.kinds[index],
            column=design.columns[index],
            level=design.levels[index],
            estimate=float(params[index]),
            std_error=float(std_errors[index]),
            t_statistic=float(t_values[index]),
            p_value=float(p_values[index]),
            ci_low=float(intervals[index, 0]),
            ci_high=float(intervals[index, 1]),
            vif=float(vifs[index]),
        )
        for index in range(len(params))
    )

    breusch_pagan = het_breuschpagan(residuals, design.matrix)
    jarque = jarque_bera(residuals)
    diagnostics = RegressionDiagnostics(
        breusch_pagan_statistic=float(breusch_pagan[0]),
        breusch_pagan_p_value=float(breusch_pagan[1]),
        jarque_bera_statistic=float(jarque[0]),
        jarque_bera_p_value=float(jarque[1]),
        durbin_watson=float(durbin_watson(residuals)),
        max_vif=float(np.max(vifs[1:])),
    )

    return RegressionResult(
        target=target,
        predictors=predictors,
        available_targets=available_targets,
        predictor_columns=predictor_columns,
        n_used=len(y),
        n_dropped=n_dropped,
        r_squared=float(fit.rsquared),
        adjusted_r_squared=float(fit.rsquared_adj),
        f_statistic=float(fit.fvalue),
        f_p_value=float(fit.f_pvalue),
        df_model=round(float(fit.df_model)),
        df_residual=round(float(fit.df_resid)),
        rmse=rmse,
        aic=float(fit.aic),
        terms=terms,
        references=design.references,
        diagnostics=diagnostics,
        warnings=_warnings(diagnostics, terms),
        plot=_plot_data(y, fitted, residuals, rmse),
        error=None,
    )
