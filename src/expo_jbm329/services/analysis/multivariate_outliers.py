"""Multivariate anomaly screening with Isolation Forest and Local Outlier Factor."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast

import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

from expo_jbm329.services.analysis.columns import numeric_columns

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pandas as pd

MIN_SELECTED_COLUMNS = 2
MIN_OBSERVATIONS = 3
DEFAULT_CONTAMINATION = 0.05
DEFAULT_LOF_NEIGHBORS = 20
MIN_CONTAMINATION = 0.01
MAX_CONTAMINATION = 0.5
MIN_LOF_NEIGHBORS = 2
MAX_LOF_NEIGHBORS = 100
MAX_EXTREME_OBSERVATIONS = 100
PLOT_SAMPLE_SIZE = 5_000
_PLOT_SAMPLE_SEED = 0


class MultivariateOutlierMethod(StrEnum):
    """Supported multivariate anomaly-detection algorithms."""

    ISOLATION_FOREST = "isolation_forest"
    LOCAL_OUTLIER_FACTOR = "local_outlier_factor"


class MultivariateOutlierError(StrEnum):
    """Reasons multivariate anomaly screening cannot run."""

    NOT_ENOUGH_NUMERIC_COLUMNS = "not_enough_numeric_columns"
    NOT_ENOUGH_SELECTED_COLUMNS = "not_enough_selected_columns"
    INVALID_COLUMN = "invalid_column"
    NOT_ENOUGH_OBSERVATIONS = "not_enough_observations"
    NO_VARIATION = "no_variation"
    INVALID_CONTAMINATION = "invalid_contamination"
    INVALID_LOF_NEIGHBORS = "invalid_lof_neighbors"


@dataclass(frozen=True, slots=True)
class MultivariateExtremeObservation:
    """One flagged row, ordered by descending anomaly score."""

    row_number: int
    score: float
    row_values: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class MultivariateOutlierResult:
    """A multivariate anomaly fit, plot projection and most anomalous rows."""

    method: MultivariateOutlierMethod
    columns: tuple[str, ...]
    available_columns: tuple[str, ...]
    standardize: bool
    contamination: float
    lof_neighbors: int
    total_rows: int
    rows_used: int
    rows_dropped: int
    outlier_count: int
    inlier_count: int
    sample_pc1: tuple[float, ...]
    sample_pc2: tuple[float, ...]
    sample_outliers: tuple[bool, ...]
    sampled: bool
    row_columns: tuple[str, ...]
    extremes: tuple[MultivariateExtremeObservation, ...]
    error: MultivariateOutlierError | None


@dataclass(frozen=True, slots=True)
class _Configuration:
    """The user-supplied fit inputs used by success and error results."""

    method: MultivariateOutlierMethod
    columns: tuple[str, ...]
    available_columns: tuple[str, ...]
    standardize: bool
    contamination: float
    lof_neighbors: int
    total_rows: int


def _error_result(
    error: MultivariateOutlierError,
    *,
    configuration: _Configuration,
    rows_used: int = 0,
) -> MultivariateOutlierResult:
    """Build a structured failure result while retaining configuration context."""
    return MultivariateOutlierResult(
        method=configuration.method,
        columns=configuration.columns,
        available_columns=configuration.available_columns,
        standardize=configuration.standardize,
        contamination=configuration.contamination,
        lof_neighbors=configuration.lof_neighbors,
        total_rows=configuration.total_rows,
        rows_used=rows_used,
        rows_dropped=configuration.total_rows - rows_used,
        outlier_count=0,
        inlier_count=0,
        sample_pc1=(),
        sample_pc2=(),
        sample_outliers=(),
        sampled=False,
        row_columns=(),
        extremes=(),
        error=error,
    )


def _values_and_positions(df: pd.DataFrame, columns: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    """Return complete finite feature rows and their original row positions."""
    values = df.loc[:, list(columns)].to_numpy(dtype="float64", na_value=np.nan)
    complete = np.isfinite(values).all(axis=1)
    return values[complete], np.flatnonzero(complete)


def _fit_labels_and_scores(
    values: np.ndarray,
    method: MultivariateOutlierMethod,
    *,
    contamination: float,
    lof_neighbors: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit `method`, returning flagged labels and ascending-normality scores."""
    match method:
        case MultivariateOutlierMethod.ISOLATION_FOREST:
            # sklearn's runtime accepts a float; the installed stub declares only "auto".
            model = IsolationForest(contamination=cast("str", contamination), random_state=0)
            labels = model.fit_predict(values)
            scores = -model.score_samples(values)
        case MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR:
            model = LocalOutlierFactor(
                contamination=cast("str", contamination),
                n_neighbors=lof_neighbors,
            )
            labels = model.fit_predict(values)
            scores = -model.negative_outlier_factor_
    return labels == -1, np.asarray(scores, dtype=float)


def _plot_sample(
    values: np.ndarray,
    outliers: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Return two PCA coordinates and anomaly flags, sampled deterministically."""
    projection = PCA(n_components=2).fit_transform(values)
    if len(projection) <= PLOT_SAMPLE_SIZE:
        return projection, outliers, False
    rng = np.random.default_rng(_PLOT_SAMPLE_SEED)
    positions = np.sort(rng.choice(len(projection), size=PLOT_SAMPLE_SIZE, replace=False))
    return projection[positions], outliers[positions], True


def analyze_multivariate_outliers(
    df: pd.DataFrame,
    columns: Sequence[str] | None = None,
    *,
    method: MultivariateOutlierMethod = MultivariateOutlierMethod.ISOLATION_FOREST,
    standardize: bool = True,
    contamination: float = DEFAULT_CONTAMINATION,
    lof_neighbors: int = DEFAULT_LOF_NEIGHBORS,
) -> MultivariateOutlierResult:
    """Screen complete numeric feature rows for multivariate anomalies.

    The anomaly score is useful for ranking detected observations, but it is
    not a universal statistical distance and should only be compared within
    one fit. The PCA projection is presentation-only; both algorithms are
    fitted on all selected dimensions.

    Args:
        df: DataFrame to analyze. Never mutated.
        columns: Selected numeric features, defaulting to all numeric columns.
        method: Isolation Forest or Local Outlier Factor.
        standardize: Whether to standardize selected features before fitting.
        contamination: Expected fraction of flagged observations.
        lof_neighbors: Number of neighbors used by Local Outlier Factor.

    Returns:
        Fit result, plot data and most anomalous rows, or a structured error.
    """
    available = numeric_columns(df)
    selected = available if columns is None else tuple(columns)
    configuration = _Configuration(
        method=method,
        columns=selected,
        available_columns=available,
        standardize=standardize,
        contamination=contamination,
        lof_neighbors=lof_neighbors,
        total_rows=len(df),
    )

    if len(available) < MIN_SELECTED_COLUMNS:
        return _error_result(MultivariateOutlierError.NOT_ENOUGH_NUMERIC_COLUMNS, configuration=configuration)
    if len(set(selected)) != len(selected) or any(column not in available for column in selected):
        return _error_result(MultivariateOutlierError.INVALID_COLUMN, configuration=configuration)
    if len(selected) < MIN_SELECTED_COLUMNS:
        return _error_result(MultivariateOutlierError.NOT_ENOUGH_SELECTED_COLUMNS, configuration=configuration)
    if not MIN_CONTAMINATION <= contamination <= MAX_CONTAMINATION:
        return _error_result(MultivariateOutlierError.INVALID_CONTAMINATION, configuration=configuration)
    if not MIN_LOF_NEIGHBORS <= lof_neighbors <= MAX_LOF_NEIGHBORS:
        return _error_result(MultivariateOutlierError.INVALID_LOF_NEIGHBORS, configuration=configuration)

    complete_values, positions = _values_and_positions(df, selected)
    rows_used = len(complete_values)
    if rows_used < MIN_OBSERVATIONS:
        return _error_result(
            MultivariateOutlierError.NOT_ENOUGH_OBSERVATIONS,
            configuration=configuration,
            rows_used=rows_used,
        )
    if method is MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR and lof_neighbors >= rows_used:
        return _error_result(
            MultivariateOutlierError.INVALID_LOF_NEIGHBORS,
            configuration=configuration,
            rows_used=rows_used,
        )

    fitted_values = StandardScaler().fit_transform(complete_values) if standardize else complete_values
    if bool(np.all(np.ptp(fitted_values, axis=0) == 0.0)):
        return _error_result(MultivariateOutlierError.NO_VARIATION, configuration=configuration, rows_used=rows_used)

    outliers, scores = _fit_labels_and_scores(
        fitted_values,
        method,
        contamination=contamination,
        lof_neighbors=lof_neighbors,
    )
    projection, sample_outliers, sampled = _plot_sample(fitted_values, outliers)
    order = np.argsort(-scores[outliers], kind="stable")[:MAX_EXTREME_OBSERVATIONS]
    flagged_positions = positions[outliers][order]
    flagged_scores = scores[outliers][order]
    row_columns = tuple(str(column) for column in df.columns)
    extremes = tuple(
        MultivariateExtremeObservation(
            row_number=int(position) + 1,
            score=float(score),
            row_values=tuple(df.iloc[int(position)].tolist()),
        )
        for position, score in zip(flagged_positions, flagged_scores, strict=True)
    )
    outlier_count = int(outliers.sum())
    return MultivariateOutlierResult(
        method=method,
        columns=selected,
        available_columns=available,
        standardize=standardize,
        contamination=contamination,
        lof_neighbors=lof_neighbors,
        total_rows=len(df),
        rows_used=rows_used,
        rows_dropped=len(df) - rows_used,
        outlier_count=outlier_count,
        inlier_count=rows_used - outlier_count,
        sample_pc1=tuple(float(value) for value in projection[:, 0]),
        sample_pc2=tuple(float(value) for value in projection[:, 1]),
        sample_outliers=tuple(bool(value) for value in sample_outliers),
        sampled=sampled,
        row_columns=row_columns,
        extremes=extremes,
        error=None,
    )
