"""Unsupervised clustering of numeric DataFrame columns."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
from sklearn.cluster import DBSCAN, AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from expo_jbm329.services.analysis.columns import numeric_columns

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pandas as pd

MIN_SELECTED_COLUMNS = 2
MIN_OBSERVATIONS = 2
DEFAULT_CLUSTER_COUNT = 3
DEFAULT_DBSCAN_EPSILON = 0.5
DEFAULT_DBSCAN_MIN_SAMPLES = 5
MIN_CLUSTER_COUNT = 2
MAX_CLUSTER_COUNT = 100
MIN_DBSCAN_EPSILON = 0.01
MAX_DBSCAN_EPSILON = 100.0
MIN_DBSCAN_MIN_SAMPLES = 2
MAX_DBSCAN_MIN_SAMPLES = 100
PLOT_SAMPLE_SIZE = 5_000
_PLOT_SAMPLE_SEED = 0


class ClusteringMethod(StrEnum):
    """Supported clustering methods."""

    K_MEANS = "k_means"
    DBSCAN = "dbscan"
    AGGLOMERATIVE = "agglomerative"


class ClusteringError(StrEnum):
    """Reasons a clustering operation cannot produce a result."""

    NOT_ENOUGH_NUMERIC_COLUMNS = "not_enough_numeric_columns"
    NOT_ENOUGH_SELECTED_COLUMNS = "not_enough_selected_columns"
    INVALID_COLUMN = "invalid_column"
    NOT_ENOUGH_OBSERVATIONS = "not_enough_observations"
    NO_VARIATION = "no_variation"
    INVALID_CLUSTER_COUNT = "invalid_cluster_count"
    INVALID_DBSCAN_EPSILON = "invalid_dbscan_epsilon"
    INVALID_DBSCAN_MIN_SAMPLES = "invalid_dbscan_min_samples"


@dataclass(frozen=True, slots=True)
class ClusterSize:
    """The number of observations assigned to one label."""

    label: int
    count: int


@dataclass(frozen=True, slots=True)
class ClusteringResult:
    """A fitted clustering model and deterministic PCA plot projection."""

    method: ClusteringMethod
    columns: tuple[str, ...]
    available_columns: tuple[str, ...]
    standardize: bool
    cluster_count: int
    dbscan_epsilon: float
    dbscan_min_samples: int
    total_rows: int
    rows_used: int
    rows_dropped: int
    clusters: tuple[ClusterSize, ...]
    noise_count: int
    silhouette_score: float | None
    sample_pc1: tuple[float, ...]
    sample_pc2: tuple[float, ...]
    sample_labels: tuple[int, ...]
    sampled: bool
    error: ClusteringError | None


@dataclass(frozen=True, slots=True)
class _Configuration:
    """Validated or pending clustering inputs shared by success/error results."""

    method: ClusteringMethod
    columns: tuple[str, ...]
    available_columns: tuple[str, ...]
    standardize: bool
    cluster_count: int
    dbscan_epsilon: float
    dbscan_min_samples: int
    total_rows: int


def _unfitted_result(
    error: ClusteringError | None,
    *,
    configuration: _Configuration,
    rows_used: int = 0,
) -> ClusteringResult:
    """Build a result without fit data while retaining config and complete-case context.

    `error` is `None` only for the configuration-only result returned by
    `initialize_clustering`.
    """
    return ClusteringResult(
        method=configuration.method,
        columns=configuration.columns,
        available_columns=configuration.available_columns,
        standardize=configuration.standardize,
        cluster_count=configuration.cluster_count,
        dbscan_epsilon=configuration.dbscan_epsilon,
        dbscan_min_samples=configuration.dbscan_min_samples,
        total_rows=configuration.total_rows,
        rows_used=rows_used,
        rows_dropped=configuration.total_rows - rows_used,
        clusters=(),
        noise_count=0,
        silhouette_score=None,
        sample_pc1=(),
        sample_pc2=(),
        sample_labels=(),
        sampled=False,
        error=error,
    )


def _column_values(df: pd.DataFrame, columns: tuple[str, ...]) -> np.ndarray:
    """Return selected values as float64, replacing infinite values with NaN."""
    values = df.loc[:, list(columns)].to_numpy(dtype="float64", na_value=np.nan)
    values[~np.isfinite(values)] = np.nan
    return values


def _cluster_labels(
    values: np.ndarray,
    method: ClusteringMethod,
    *,
    cluster_count: int,
    dbscan_epsilon: float,
    dbscan_min_samples: int,
) -> np.ndarray:
    """Fit `method` and return its integer labels."""
    match method:
        case ClusteringMethod.K_MEANS:
            model = KMeans(n_clusters=cluster_count, n_init="auto", random_state=0)
        case ClusteringMethod.DBSCAN:
            model = DBSCAN(eps=dbscan_epsilon, min_samples=dbscan_min_samples)
        case ClusteringMethod.AGGLOMERATIVE:
            model = AgglomerativeClustering(n_clusters=cluster_count)
    return np.asarray(model.fit_predict(values), dtype=int)


def _cluster_sizes(labels: np.ndarray) -> tuple[tuple[ClusterSize, ...], int]:
    """Return non-noise cluster sizes ordered by label, plus DBSCAN noise."""
    unique, counts = np.unique(labels, return_counts=True)
    sizes = tuple(
        ClusterSize(label=int(label), count=int(count))
        for label, count in zip(unique, counts, strict=True)
        if label != -1
    )
    noise = next((int(count) for label, count in zip(unique, counts, strict=True) if label == -1), 0)
    return sizes, noise


def _silhouette(values: np.ndarray, labels: np.ndarray, clusters: tuple[ClusterSize, ...]) -> float | None:
    """Return a silhouette score for non-noise groups when it is defined."""
    non_noise = labels != -1
    filtered_values = values[non_noise]
    filtered_labels = labels[non_noise]
    if len(clusters) < MIN_CLUSTER_COUNT or len(filtered_values) <= len(clusters):
        return None
    return float(silhouette_score(filtered_values, filtered_labels))


def _plot_sample(values: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray, bool]:
    """Project observations to two PCA coordinates and sample them deterministically."""
    projection = PCA(n_components=2).fit_transform(values)
    if len(projection) <= PLOT_SAMPLE_SIZE:
        return projection, labels, False
    rng = np.random.default_rng(_PLOT_SAMPLE_SEED)
    positions = np.sort(rng.choice(len(projection), size=PLOT_SAMPLE_SIZE, replace=False))
    return projection[positions], labels[positions], True


def initialize_clustering(df: pd.DataFrame) -> ClusteringResult:
    """Return the default clustering configuration without fitting a model.

    Only column metadata is inspected, so this is cheap enough for the GUI
    thread. It lets the configuration be shown before the user applies it.

    Args:
        df: DataFrame to inspect. Never mutated.

    Returns:
        A result without fit data, using every numeric column and the
        default K-Means parameters. Its `error` is
        `NOT_ENOUGH_NUMERIC_COLUMNS` when clustering is not possible for the
        dataset, and `None` otherwise.
    """
    available = numeric_columns(df)
    configuration = _Configuration(
        method=ClusteringMethod.K_MEANS,
        columns=available,
        available_columns=available,
        standardize=True,
        cluster_count=DEFAULT_CLUSTER_COUNT,
        dbscan_epsilon=DEFAULT_DBSCAN_EPSILON,
        dbscan_min_samples=DEFAULT_DBSCAN_MIN_SAMPLES,
        total_rows=len(df),
    )
    error = ClusteringError.NOT_ENOUGH_NUMERIC_COLUMNS if len(available) < MIN_SELECTED_COLUMNS else None
    return _unfitted_result(error, configuration=configuration)


def analyze_clustering(
    df: pd.DataFrame,
    columns: Sequence[str] | None = None,
    *,
    method: ClusteringMethod = ClusteringMethod.K_MEANS,
    standardize: bool = True,
    cluster_count: int = DEFAULT_CLUSTER_COUNT,
    dbscan_epsilon: float = DEFAULT_DBSCAN_EPSILON,
    dbscan_min_samples: int = DEFAULT_DBSCAN_MIN_SAMPLES,
) -> ClusteringResult:
    """Cluster complete finite rows from selected numeric columns.

    Args:
        df: DataFrame to analyze. Never mutated.
        columns: Numeric feature columns, defaulting to all numeric columns.
        method: Clustering algorithm to fit.
        standardize: Scale features before fitting.
        cluster_count: Requested K-Means/Agglomerative cluster count.
        dbscan_epsilon: DBSCAN neighborhood radius.
        dbscan_min_samples: DBSCAN minimum neighborhood size.

    Returns:
        The fitted labels, summary and internal PCA plot coordinates, or a
        structured error result when the requested fit is invalid.
    """
    available = numeric_columns(df)
    total_rows = len(df)
    selected = available if columns is None else tuple(columns)
    configuration = _Configuration(
        method=method,
        columns=selected,
        available_columns=available,
        standardize=standardize,
        cluster_count=cluster_count,
        dbscan_epsilon=dbscan_epsilon,
        dbscan_min_samples=dbscan_min_samples,
        total_rows=total_rows,
    )

    if len(available) < MIN_SELECTED_COLUMNS:
        return _unfitted_result(ClusteringError.NOT_ENOUGH_NUMERIC_COLUMNS, configuration=configuration)
    if len(set(selected)) != len(selected) or any(column not in available for column in selected):
        return _unfitted_result(ClusteringError.INVALID_COLUMN, configuration=configuration)
    if len(selected) < MIN_SELECTED_COLUMNS:
        return _unfitted_result(ClusteringError.NOT_ENOUGH_SELECTED_COLUMNS, configuration=configuration)
    if not MIN_CLUSTER_COUNT <= cluster_count <= MAX_CLUSTER_COUNT:
        return _unfitted_result(ClusteringError.INVALID_CLUSTER_COUNT, configuration=configuration)
    if not MIN_DBSCAN_EPSILON <= dbscan_epsilon <= MAX_DBSCAN_EPSILON:
        return _unfitted_result(ClusteringError.INVALID_DBSCAN_EPSILON, configuration=configuration)
    if not MIN_DBSCAN_MIN_SAMPLES <= dbscan_min_samples <= MAX_DBSCAN_MIN_SAMPLES:
        return _unfitted_result(ClusteringError.INVALID_DBSCAN_MIN_SAMPLES, configuration=configuration)

    all_values = _column_values(df, selected)
    complete_values = all_values[np.isfinite(all_values).all(axis=1)]
    rows_used = len(complete_values)
    if rows_used < MIN_OBSERVATIONS:
        return _unfitted_result(
            ClusteringError.NOT_ENOUGH_OBSERVATIONS, configuration=configuration, rows_used=rows_used
        )
    if method is not ClusteringMethod.DBSCAN and cluster_count > rows_used:
        return _unfitted_result(ClusteringError.INVALID_CLUSTER_COUNT, configuration=configuration, rows_used=rows_used)

    fitted_values = StandardScaler().fit_transform(complete_values) if standardize else complete_values
    if bool(np.all(np.ptp(fitted_values, axis=0) == 0.0)):
        return _unfitted_result(ClusteringError.NO_VARIATION, configuration=configuration, rows_used=rows_used)

    labels = _cluster_labels(
        fitted_values,
        method,
        cluster_count=cluster_count,
        dbscan_epsilon=dbscan_epsilon,
        dbscan_min_samples=dbscan_min_samples,
    )
    clusters, noise_count = _cluster_sizes(labels)
    projection, sample_labels, sampled = _plot_sample(fitted_values, labels)

    return ClusteringResult(
        method=method,
        columns=selected,
        available_columns=available,
        standardize=standardize,
        cluster_count=cluster_count,
        dbscan_epsilon=dbscan_epsilon,
        dbscan_min_samples=dbscan_min_samples,
        total_rows=total_rows,
        rows_used=rows_used,
        rows_dropped=total_rows - rows_used,
        clusters=clusters,
        noise_count=noise_count,
        silhouette_score=_silhouette(fitted_values, labels, clusters),
        sample_pc1=tuple(float(value) for value in projection[:, 0]),
        sample_pc2=tuple(float(value) for value in projection[:, 1]),
        sample_labels=tuple(int(value) for value in sample_labels),
        sampled=sampled,
        error=None,
    )
