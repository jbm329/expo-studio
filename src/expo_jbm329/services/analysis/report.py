"""Session report entries and document state for Advanced Analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from expo_jbm329.app.metadata import get_app_metadata
from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.services.analysis.clustering_export import (
    CLUSTERING_COMPONENTS,
    ClusteringExportSnapshot,
)
from expo_jbm329.services.analysis.correlation_export import CorrelationExportSnapshot
from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportSnapshot
from expo_jbm329.services.analysis.outliers_export import (
    MultivariateOutlierExportSnapshot,
    OutlierExportComponent,
    OutlierExportSnapshot,
    UnivariateOutlierExportSnapshot,
)
from expo_jbm329.services.analysis.overview import DatasetOverviewResult
from expo_jbm329.services.analysis.pca_export import PCAExportSnapshot
from expo_jbm329.services.analysis.regression_export import RegressionExportSnapshot
from expo_jbm329.services.analysis.statistics import DescriptiveStatisticsResult
from expo_jbm329.services.analysis.timeseries_export import TimeSeriesExportSnapshot

if TYPE_CHECKING:
    from expo_jbm329.utils.dataset_ref import DatasetRef

type ReportSnapshot = (
    DatasetOverviewResult
    | DescriptiveStatisticsResult
    | HypothesisExportSnapshot
    | CorrelationExportSnapshot
    | RegressionExportSnapshot
    | OutlierExportSnapshot
    | ClusteringExportSnapshot
    | PCAExportSnapshot
    | TimeSeriesExportSnapshot
)


@dataclass(frozen=True, slots=True)
class ReportComponent:
    """One available table or chart that may be included in a report."""

    key: str
    label: str
    kind: str

    def __post_init__(self) -> None:
        """Validate the stable identity and content kind."""
        if not self.key or not self.label or self.kind not in {"table", "chart"}:
            message = "A report component requires a key, label, and supported kind."
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class ReportEntry:
    """One immutable applied analysis captured in a report draft."""

    entry_id: str
    dataset_id: str
    dataset_name: str
    dataset_rows: int
    dataset_columns: int
    category: AnalysisCategory
    analysis_date: str
    app_version: str
    snapshot: ReportSnapshot
    components: tuple[ReportComponent, ...]
    selected_components: tuple[str, ...]
    note: str = ""

    def __post_init__(self) -> None:
        """Ensure identity, metadata, and selected components are coherent."""
        if not self.entry_id or not self.dataset_id or not self.dataset_name:
            message = "A report entry requires dataset identity and an entry key."
            raise ValueError(message)
        if self.dataset_rows < 0 or self.dataset_columns < 0:
            message = "Report dataset dimensions cannot be negative."
            raise ValueError(message)
        component_keys = tuple(component.key for component in self.components)
        if not component_keys or len(component_keys) != len(set(component_keys)):
            message = "Report components must have distinct keys."
            raise ValueError(message)
        if (
            not self.selected_components
            or len(self.selected_components) != len(set(self.selected_components))
            or any(key not in component_keys for key in self.selected_components)
        ):
            message = "Select at least one distinct available report component."
            raise ValueError(message)

    def with_selection(self, selected_components: tuple[str, ...], note: str) -> ReportEntry:
        """Return the same captured analysis with updated report presentation."""
        return ReportEntry(
            entry_id=self.entry_id,
            dataset_id=self.dataset_id,
            dataset_name=self.dataset_name,
            dataset_rows=self.dataset_rows,
            dataset_columns=self.dataset_columns,
            category=self.category,
            analysis_date=self.analysis_date,
            app_version=self.app_version,
            snapshot=self.snapshot,
            components=self.components,
            selected_components=selected_components,
            note=note,
        )


@dataclass(slots=True)
class ReportDocument:
    """In-memory report draft that may contain analyses from multiple datasets."""

    title: str = ""
    description: str = ""
    _entries: list[ReportEntry] = field(default_factory=list, repr=False)

    @property
    def entries(self) -> tuple[ReportEntry, ...]:
        """Return entries in report order."""
        return tuple(self._entries)

    def get(self, entry_id: str) -> ReportEntry | None:
        """Find an entry by its stable analysis identity."""
        return next((entry for entry in self._entries if entry.entry_id == entry_id), None)

    def upsert(self, entry: ReportEntry) -> None:
        """Insert or replace an entry without creating a duplicate identity."""
        for index, existing in enumerate(self._entries):
            if existing.entry_id == entry.entry_id:
                self._entries[index] = entry
                return
        self._entries.append(entry)

    def remove(self, entry_id: str) -> bool:
        """Remove an entry and report whether it existed."""
        for index, entry in enumerate(self._entries):
            if entry.entry_id == entry_id:
                del self._entries[index]
                return True
        return False

    def move(self, entry_id: str, offset: int) -> bool:
        """Move an entry by one position in the requested direction."""
        index = next((i for i, entry in enumerate(self._entries) if entry.entry_id == entry_id), None)
        if index is None:
            return False
        target = index + offset
        if offset not in {-1, 1} or not 0 <= target < len(self._entries):
            return False
        self._entries[index], self._entries[target] = self._entries[target], self._entries[index]
        return True


def create_report_entry(
    category: AnalysisCategory,
    dataset: DatasetRef,
    snapshot: ReportSnapshot,
) -> ReportEntry:
    """Create a fully selected report entry from one applied result snapshot."""
    identity = report_entry_identity(category, dataset.tab_id, snapshot)
    components = available_report_components(category, snapshot)
    metadata = get_app_metadata()
    return ReportEntry(
        entry_id=identity,
        dataset_id=dataset.tab_id,
        dataset_name=dataset.title,
        dataset_rows=dataset.row_count,
        dataset_columns=dataset.column_count,
        category=category,
        analysis_date=datetime.now().astimezone().date().isoformat(),
        app_version=metadata["version"],
        snapshot=snapshot,
        components=components,
        selected_components=tuple(component.key for component in components),
    )


def available_report_components(category: AnalysisCategory, snapshot: ReportSnapshot) -> tuple[ReportComponent, ...]:
    """Return the non-empty reportable components for an applied analysis."""
    component_values: tuple[tuple[str, str, str], ...]
    match category:
        case AnalysisCategory.OVERVIEW if isinstance(snapshot, DatasetOverviewResult):
            candidates = [
                ("Summary", "Summary", "table"),
                ("Columns", "Columns metadata", "table"),
                ("Sample", "Sample (first 100 rows)", "table"),
            ]
            component_values = tuple(item for item in candidates if _overview_component_available(snapshot, item[0]))
        case AnalysisCategory.STATISTICS if isinstance(snapshot, DescriptiveStatisticsResult):
            candidates = []
            if snapshot.columns:
                candidates.extend([("Continuous", "Continuous", "table"), ("Charts", "Charts", "chart")])
            if snapshot.categorical_columns:
                candidates.append(("Categorical", "Categorical", "table"))
            component_values = tuple(candidates)
        case AnalysisCategory.HYPOTHESIS_TESTS if isinstance(snapshot, HypothesisExportSnapshot):
            summary_label = {
                "group_comparison": "Group summary",
                "chi_square": "Contingency table",
                "paired_comparison": "Measurement summary",
            }[snapshot.test.value]
            component_values = (
                ("summary", summary_label, "table"),
                ("test_results", "Test results", "table"),
                ("charts", "Charts", "chart"),
            )
        case AnalysisCategory.CORRELATION if isinstance(snapshot, CorrelationExportSnapshot):
            component_values = (
                ("strongest_correlations", "Strongest correlations", "table"),
                ("matrix_plot", "Matrix plot", "chart"),
                ("scatterplots", "Scatterplots", "chart"),
            )
        case AnalysisCategory.REGRESSION if isinstance(snapshot, RegressionExportSnapshot):
            components = [("coefficients", "Coefficients", "table"), ("model_metrics", "Model metrics", "table")]
            if snapshot.has_charts:
                components.append(("charts", "Charts", "chart"))
            component_values = tuple(components)
        case AnalysisCategory.OUTLIERS if isinstance(snapshot, OutlierExportSnapshot):
            outlier_labels: dict[OutlierExportComponent, str] = {
                OutlierExportComponent.COLUMN_SUMMARY: "Column summary",
                OutlierExportComponent.COLUMN_DETAILS: "Column details",
                OutlierExportComponent.MODEL_SUMMARY: "Model summary",
                OutlierExportComponent.POTENTIAL_OUTLIERS: "Potential outliers",
                OutlierExportComponent.CHARTS: "Charts",
            }
            outlier_components: list[tuple[str, str, str]] = []
            for component in snapshot.components:
                if snapshot.is_available(component):
                    kind = "chart" if component is OutlierExportComponent.CHARTS else "table"
                    outlier_components.append((component.value, outlier_labels[component], kind))
            component_values = tuple(outlier_components)
        case AnalysisCategory.CLUSTERING if isinstance(snapshot, ClusteringExportSnapshot):
            component_values = tuple(
                (component.value, label, "chart" if component.value == "charts" else "table")
                for component, label in zip(
                    CLUSTERING_COMPONENTS, ("Cluster sizes", "Model summary", "Charts"), strict=True
                )
            )
        case AnalysisCategory.PCA if isinstance(snapshot, PCAExportSnapshot):
            component_values = (
                ("feature_loadings", "Feature loadings", "table"),
                ("explained_variance", "Explained variance", "table"),
                ("model_summary", "Model summary", "table"),
                ("charts", "Charts", "chart"),
            )
        case AnalysisCategory.TIME_SERIES if isinstance(snapshot, TimeSeriesExportSnapshot):
            time_series_labels: dict[str, tuple[str, str]] = {
                "series": ("Series", "table"),
                "autocorrelation": ("Autocorrelation", "table"),
                "model_summary": ("Model summary", "table"),
                "charts": ("Charts", "chart"),
            }
            component_values = tuple(
                (
                    component.value,
                    time_series_labels[component.value][0],
                    time_series_labels[component.value][1],
                )
                for component in snapshot.components
            )
        case _:
            message = "The analysis category and applied report snapshot do not match."
            raise TypeError(message)
    return tuple(ReportComponent(key, label, kind) for key, label, kind in component_values)


def report_entry_identity(category: AnalysisCategory, dataset_id: str, snapshot: ReportSnapshot) -> str:
    """Create a stable identity from dataset, analysis category, and applied configuration."""
    config: tuple[object, ...]
    match category:
        case AnalysisCategory.OVERVIEW if isinstance(snapshot, DatasetOverviewResult):
            config = ()
        case AnalysisCategory.STATISTICS if isinstance(snapshot, DescriptiveStatisticsResult):
            config = ()
        case AnalysisCategory.HYPOTHESIS_TESTS if isinstance(snapshot, HypothesisExportSnapshot):
            config = (snapshot.test.value, snapshot.columns)
        case AnalysisCategory.CORRELATION if isinstance(snapshot, CorrelationExportSnapshot):
            config = (snapshot.matrix.method.value, snapshot.matrix.columns)
        case AnalysisCategory.REGRESSION if isinstance(snapshot, RegressionExportSnapshot):
            regression_result = snapshot.result
            terms = tuple((term.kind.value, term.column, term.level) for term in regression_result.terms)
            config = (snapshot.model.value, snapshot.outcome_columns, snapshot.predictors, terms)
        case AnalysisCategory.OUTLIERS if isinstance(snapshot, UnivariateOutlierExportSnapshot):
            config = (
                "univariate",
                snapshot.summary.method.value,
                snapshot.summary.threshold,
                snapshot.summary.available_columns,
                None if snapshot.detail is None else snapshot.detail.summary.column,
            )
        case AnalysisCategory.OUTLIERS if isinstance(snapshot, MultivariateOutlierExportSnapshot):
            multivariate_result = snapshot.result
            config = (
                "multivariate",
                multivariate_result.method.value,
                multivariate_result.columns,
                multivariate_result.standardize,
                multivariate_result.contamination,
                multivariate_result.lof_neighbors,
            )
        case AnalysisCategory.CLUSTERING if isinstance(snapshot, ClusteringExportSnapshot):
            clustering_result = snapshot.result
            config = (
                clustering_result.method.value,
                clustering_result.columns,
                clustering_result.standardize,
                clustering_result.cluster_count,
                clustering_result.dbscan_epsilon,
                clustering_result.dbscan_min_samples,
            )
        case AnalysisCategory.PCA if isinstance(snapshot, PCAExportSnapshot):
            config = (snapshot.result.columns, snapshot.result.standardize)
        case AnalysisCategory.TIME_SERIES if isinstance(snapshot, TimeSeriesExportSnapshot):
            time_series_result = snapshot.result
            config = (
                time_series_result.datetime_column,
                time_series_result.value_column,
                time_series_result.resample_frequency,
                time_series_result.seasonal_period,
                time_series_result.decomposition_model.value,
            )
        case _:
            message = "The analysis category and applied report snapshot do not match."
            raise TypeError(message)
    payload = [dataset_id, category.value, _json_value(config)]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _overview_component_available(result: DatasetOverviewResult, component: str) -> bool:
    return {
        "Summary": True,
        "Columns": bool(result.columns),
        "Sample": result.sample_frame is not None and not result.sample_frame.empty,
    }[component]


def _json_value(value: object) -> object:
    """Convert enum/tuple configuration values to deterministic JSON values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)
