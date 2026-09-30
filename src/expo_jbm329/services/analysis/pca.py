"""Principal component analysis for numeric DataFrame columns.

The service deliberately separates the complete-case data preparation and
numerical PCA fit from the Qt presentation layer. It computes every possible
component so the view can show explained variance, loadings, and PC1-vs-PC2
without another fit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from expo_jbm329.services.analysis.columns import numeric_columns

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pandas as pd

MIN_SELECTED_COLUMNS = 2
MIN_OBSERVATIONS = 2
SCATTER_SAMPLE_SIZE = 5_000
_SCATTER_SEED = 0


class _PCAFitError(RuntimeError):
    """Raised only when a fitted sklearn PCA instance omits required attributes."""


class PCAError(StrEnum):
    """Reasons a PCA computation cannot produce a meaningful result."""

    NOT_ENOUGH_NUMERIC_COLUMNS = "not_enough_numeric_columns"
    NOT_ENOUGH_SELECTED_COLUMNS = "not_enough_selected_columns"
    INVALID_COLUMN = "invalid_column"
    NOT_ENOUGH_OBSERVATIONS = "not_enough_observations"
    NO_VARIATION = "no_variation"


@dataclass(frozen=True, slots=True)
class PCAResult:
    """The complete PCA fit and data needed to render it.

    Attributes:
        columns: Numeric columns included in the fit, in feature order.
        available_columns: Every numeric dataset column usable in the config.
        standardize: Whether every selected feature was standardized first.
        total_rows: Rows in the source DataFrame.
        rows_used: Complete finite rows included in the fit.
        rows_dropped: Rows excluded because at least one selected value was
            missing or infinite.
        explained_variance: Variance explained by each component.
        explained_variance_ratio: Fraction of total variance explained by
            each component.
        cumulative_variance_ratio: Cumulative explained-variance fraction.
        loadings: Row-major feature loadings, one row per `columns` item.
        sample_pc1: PC1 scores for the deterministic plot sample.
        sample_pc2: PC2 scores for the deterministic plot sample.
        sampled: Whether the plot sample is smaller than `rows_used`.
        error: Structured error code, or `None` after a successful fit.
    """

    columns: tuple[str, ...]
    available_columns: tuple[str, ...]
    standardize: bool
    total_rows: int
    rows_used: int
    rows_dropped: int
    explained_variance: tuple[float, ...]
    explained_variance_ratio: tuple[float, ...]
    cumulative_variance_ratio: tuple[float, ...]
    loadings: tuple[tuple[float, ...], ...]
    sample_pc1: tuple[float, ...]
    sample_pc2: tuple[float, ...]
    sampled: bool
    error: PCAError | None


def _unfitted_result(
    error: PCAError | None,
    *,
    columns: tuple[str, ...],
    available_columns: tuple[str, ...],
    standardize: bool,
    total_rows: int,
    rows_used: int = 0,
) -> PCAResult:
    """Build a result without fit data while retaining its configuration context.

    `error` is `None` only for the configuration-only result returned by
    `initialize_pca`.
    """
    return PCAResult(
        columns=columns,
        available_columns=available_columns,
        standardize=standardize,
        total_rows=total_rows,
        rows_used=rows_used,
        rows_dropped=total_rows - rows_used,
        explained_variance=(),
        explained_variance_ratio=(),
        cumulative_variance_ratio=(),
        loadings=(),
        sample_pc1=(),
        sample_pc2=(),
        sampled=False,
        error=error,
    )


def _column_values(df: pd.DataFrame, columns: tuple[str, ...]) -> np.ndarray:
    """Return selected values as float64, replacing infinite values with NaN."""
    values = df.loc[:, list(columns)].to_numpy(dtype="float64", na_value=np.nan)
    values[~np.isfinite(values)] = np.nan
    return values


def _sample_scores(scores: np.ndarray) -> tuple[np.ndarray, bool]:
    """Return all or a deterministic subset of PC1/PC2 scores."""
    if len(scores) <= SCATTER_SAMPLE_SIZE:
        return scores, False
    rng = np.random.default_rng(_SCATTER_SEED)
    positions = np.sort(rng.choice(len(scores), size=SCATTER_SAMPLE_SIZE, replace=False))
    return scores[positions], True


def initialize_pca(df: pd.DataFrame) -> PCAResult:
    """Return the default PCA configuration without fitting a model.

    Only column metadata is inspected, so this is cheap enough for the GUI
    thread. It lets the configuration be shown before the user applies it.

    Args:
        df: DataFrame to inspect. It is never mutated.

    Returns:
        A result without fit data, selecting every numeric column. Its
        `error` is `NOT_ENOUGH_NUMERIC_COLUMNS` when PCA is not possible for
        the dataset, and `None` otherwise.
    """
    available = numeric_columns(df)
    error = PCAError.NOT_ENOUGH_NUMERIC_COLUMNS if len(available) < MIN_SELECTED_COLUMNS else None
    return _unfitted_result(
        error,
        columns=available,
        available_columns=available,
        standardize=True,
        total_rows=len(df),
    )


def analyze_pca(
    df: pd.DataFrame,
    columns: Sequence[str] | None = None,
    *,
    standardize: bool = True,
) -> PCAResult:
    """Fit PCA to complete cases from selected numeric columns.

    Every numeric column is selected by default. Missing and infinite values
    cause the entire row to be excluded, rather than applying per-feature
    deletion that would make PCA's multivariate geometry ill-defined.

    Args:
        df: DataFrame to analyze. It is never mutated.
        columns: Numeric columns to fit. Defaults to every numeric column.
        standardize: Standardize features to zero mean and unit variance
            before the PCA fit.

    Returns:
        All PCA quantities for a successful fit, or a structured error result.
    """
    available = numeric_columns(df)
    total_rows = len(df)
    selected = available if columns is None else tuple(columns)

    if len(available) < MIN_SELECTED_COLUMNS:
        return _unfitted_result(
            PCAError.NOT_ENOUGH_NUMERIC_COLUMNS,
            columns=selected,
            available_columns=available,
            standardize=standardize,
            total_rows=total_rows,
        )
    if len(set(selected)) != len(selected) or any(column not in available for column in selected):
        return _unfitted_result(
            PCAError.INVALID_COLUMN,
            columns=selected,
            available_columns=available,
            standardize=standardize,
            total_rows=total_rows,
        )
    if len(selected) < MIN_SELECTED_COLUMNS:
        return _unfitted_result(
            PCAError.NOT_ENOUGH_SELECTED_COLUMNS,
            columns=selected,
            available_columns=available,
            standardize=standardize,
            total_rows=total_rows,
        )

    all_values = _column_values(df, selected)
    complete_mask = np.isfinite(all_values).all(axis=1)
    complete_values = all_values[complete_mask]
    rows_used = len(complete_values)
    if rows_used < MIN_OBSERVATIONS:
        return _unfitted_result(
            PCAError.NOT_ENOUGH_OBSERVATIONS,
            columns=selected,
            available_columns=available,
            standardize=standardize,
            total_rows=total_rows,
            rows_used=rows_used,
        )

    fitted_values = StandardScaler().fit_transform(complete_values) if standardize else complete_values
    if bool(np.all(np.ptp(fitted_values, axis=0) == 0.0)):
        return _unfitted_result(
            PCAError.NO_VARIATION,
            columns=selected,
            available_columns=available,
            standardize=standardize,
            total_rows=total_rows,
            rows_used=rows_used,
        )

    model = PCA()
    scores = np.asarray(model.fit_transform(fitted_values), dtype=float)
    sample_scores, sampled = _sample_scores(scores)
    ratios = np.asarray(model.explained_variance_ratio_, dtype=float)
    cumulative = np.cumsum(ratios)
    components = model.components_
    explained_variance = model.explained_variance_
    if components is None or explained_variance is None:
        raise _PCAFitError
    loadings = components.T * np.sqrt(np.asarray(explained_variance, dtype=float))

    return PCAResult(
        columns=selected,
        available_columns=available,
        standardize=standardize,
        total_rows=total_rows,
        rows_used=rows_used,
        rows_dropped=total_rows - rows_used,
        explained_variance=tuple(float(value) for value in explained_variance),
        explained_variance_ratio=tuple(float(value) for value in ratios),
        cumulative_variance_ratio=tuple(float(value) for value in cumulative),
        loadings=tuple(tuple(float(value) for value in row) for row in loadings),
        sample_pc1=tuple(float(value) for value in sample_scores[:, 0]),
        sample_pc2=tuple(float(value) for value in sample_scores[:, 1]),
        sampled=sampled,
        error=None,
    )
