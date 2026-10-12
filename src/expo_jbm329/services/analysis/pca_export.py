"""Typed exports of a displayed principal component analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from expo_jbm329.services.analysis.pca import PCAResult
from expo_jbm329.services.analysis.pca_charts import PCAChartLabels
from expo_jbm329.services.analysis.statistics import StatisticsExportFormat

if TYPE_CHECKING:
    from collections.abc import Sequence


class PCAExportComponent(StrEnum):
    """Selectable displayed results; charts are Excel-only."""

    FEATURE_LOADINGS = "feature_loadings"
    EXPLAINED_VARIANCE = "explained_variance"
    MODEL_SUMMARY = "model_summary"
    CHARTS = "charts"


class PCAMetric(StrEnum):
    """Stable keys of the model summary, localized at the UI boundary."""

    FEATURES = "features"
    TOTAL_ROWS = "total_rows"
    ROWS_USED = "rows_used"
    ROWS_DROPPED = "rows_dropped"


PCA_COMPONENTS = tuple(PCAExportComponent)


def component_name(index: int) -> str:
    """Return the displayed name of a 0-based principal component index."""
    return f"PC{index + 1}"


@dataclass(frozen=True, slots=True)
class PCAExportSnapshot:
    """Own the displayed PCA fit, its comments and chart text.

    Attributes:
        result: The successful fit shown in the content pane.
        chart_labels: Translated plot text captured on the GUI thread.
        notes: Plain-text lines of the displayed model comments.
    """

    result: PCAResult
    chart_labels: PCAChartLabels
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject failed or unfitted results."""
        result = self.result
        if not isinstance(result, PCAResult):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "A typed PCA result is required."
            raise TypeError(message)
        if result.error is not None:
            message = "A failed PCA result cannot be exported."
            raise ValueError(message)
        if result.rows_used == 0 or not result.loadings or not result.sample_pc1:
            message = "An applied PCA result must be fitted."
            raise ValueError(message)
        if not isinstance(self.chart_labels, PCAChartLabels):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "PCA chart labels are required."
            raise TypeError(message)

    @property
    def components(self) -> tuple[PCAExportComponent, ...]:
        """Return the components offered for PCA."""
        return PCA_COMPONENTS


@dataclass(frozen=True, slots=True)
class PCAExportRequest:
    """Selected components from one immutable displayed snapshot."""

    snapshot: PCAExportSnapshot
    components: tuple[PCAExportComponent, ...]
    format: StatisticsExportFormat

    def __post_init__(self) -> None:
        """Validate the selection without altering retained dialog choices."""
        if not isinstance(self.snapshot, PCAExportSnapshot):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "A typed PCA export snapshot is required."
            raise TypeError(message)
        if not self.components or len(set(self.components)) != len(self.components):
            message = "Select distinct PCA components."
            raise ValueError(message)
        if any(
            not isinstance(item, PCAExportComponent)  # pyright: ignore[reportUnnecessaryIsInstance]
            for item in self.components
        ):
            message = "Unknown PCA export component."
            raise ValueError(message)
        if not isinstance(self.format, StatisticsExportFormat):  # pyright: ignore[reportUnnecessaryIsInstance]
            message = "Unknown PCA export format."
            raise TypeError(message)
        if self.format is not StatisticsExportFormat.EXCEL and (
            PCAExportComponent.CHARTS in self.components or len(self.components) != 1
        ):
            message = "CSV and binary exports require exactly one table and no charts."
            raise ValueError(message)


def pca_export_tables(
    snapshot: PCAExportSnapshot,
    components: Sequence[PCAExportComponent],
) -> dict[PCAExportComponent, pd.DataFrame]:
    """Build fresh tables for the selected non-chart components.

    Args:
        snapshot: The displayed PCA fit.
        components: Selected components; charts are ignored.

    Returns:
        Tables in selection order, keyed by component.
    """
    tables: dict[PCAExportComponent, pd.DataFrame] = {}
    for component in components:
        match component:
            case PCAExportComponent.FEATURE_LOADINGS:
                tables[component] = feature_loadings_table(snapshot)
            case PCAExportComponent.EXPLAINED_VARIANCE:
                tables[component] = explained_variance_table(snapshot)
            case PCAExportComponent.MODEL_SUMMARY:
                tables[component] = pca_model_summary_table(snapshot)
            case PCAExportComponent.CHARTS:
                pass
    return tables


def feature_loadings_table(snapshot: PCAExportSnapshot) -> pd.DataFrame:
    """Return the displayed loadings with one row per feature.

    Args:
        snapshot: The displayed PCA fit.

    Returns:
        Column ``feature`` followed by one float column per component, ``PC1`` to ``PCn``.
    """
    result = snapshot.result
    component_count = len(result.loadings[0])
    data: dict[str, pd.Series] = {"feature": pd.Series(result.columns, dtype=pd.StringDtype())}
    for index in range(component_count):
        data[component_name(index)] = pd.Series([row[index] for row in result.loadings], dtype="float64")
    return pd.DataFrame(data)


def explained_variance_table(snapshot: PCAExportSnapshot) -> pd.DataFrame:
    """Return the per-component variance behind the displayed scree plot.

    Args:
        snapshot: The displayed PCA fit.

    Returns:
        Columns ``component``, ``variance`` (eigenvalue), ``share`` and ``cumulative_share``.
    """
    result = snapshot.result
    names = [component_name(index) for index in range(len(result.explained_variance))]
    return pd.DataFrame({
        "component": pd.Series(names, dtype=pd.StringDtype()),
        "variance": pd.Series(result.explained_variance, dtype="float64"),
        "share": pd.Series(result.explained_variance_ratio, dtype="float64"),
        "cumulative_share": pd.Series(result.cumulative_variance_ratio, dtype="float64"),
    })


def pca_model_summary_table(snapshot: PCAExportSnapshot) -> pd.DataFrame:
    """Return the fit's feature and row counts with its displayed comments.

    Args:
        snapshot: The displayed PCA fit.

    Returns:
        Columns ``metric`` (a `PCAMetric` key), ``value`` and ``notes``.
    """
    result = snapshot.result
    values: list[tuple[PCAMetric, int]] = [
        (PCAMetric.FEATURES, len(result.columns)),
        (PCAMetric.TOTAL_ROWS, result.total_rows),
        (PCAMetric.ROWS_USED, result.rows_used),
        (PCAMetric.ROWS_DROPPED, result.rows_dropped),
    ]
    notes = snapshot.notes
    row_count = max(len(values), len(notes))
    return pd.DataFrame({
        "metric": pd.Series([metric.value for metric, _ in values], dtype=pd.StringDtype()).reindex(range(row_count)),
        "value": pd.Series([float(value) for _, value in values], dtype="float64").reindex(range(row_count)),
        "notes": pd.Series(notes, dtype=pd.StringDtype()).reindex(range(row_count)),
    })
