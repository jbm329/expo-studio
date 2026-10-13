"""Session report entries and document state for Advanced Analysis."""

from __future__ import annotations

import json
import math
import numbers
from base64 import b64encode
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from html import escape
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from expo_jbm329.app.metadata import get_app_metadata
from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.clustering_charts import render_clustering_charts
from expo_jbm329.services.analysis.clustering_export import (
    CLUSTERING_COMPONENTS,
    ClusteringExportComponent,
    ClusteringExportSnapshot,
    ClusteringMetric,
    clustering_export_tables,
)
from expo_jbm329.services.analysis.correlation import MIN_OBSERVATIONS, SIGNIFICANCE_LEVEL, CorrelationMethod
from expo_jbm329.services.analysis.correlation_charts import CorrelationChartLabels, render_correlation_charts
from expo_jbm329.services.analysis.correlation_export import (
    CorrelationExportComponent,
    CorrelationExportSnapshot,
    correlation_export_table,
)
from expo_jbm329.services.analysis.hypothesis_charts import HypothesisChartLabels, render_hypothesis_charts
from expo_jbm329.services.analysis.hypothesis_export import (
    HypothesisExportComponent,
    HypothesisExportSnapshot,
    hypothesis_export_tables,
)
from expo_jbm329.services.analysis.outliers import ColumnOutlierStatus, OutlierMethod
from expo_jbm329.services.analysis.outliers_charts import (
    render_multivariate_outlier_charts,
    render_univariate_outlier_charts,
)
from expo_jbm329.services.analysis.outliers_export import (
    MultivariateOutlierExportSnapshot,
    OutlierExportComponent,
    OutlierExportSnapshot,
    OutlierMetric,
    UnivariateOutlierExportSnapshot,
    outlier_export_tables,
)
from expo_jbm329.services.analysis.overview import DatasetOverviewResult, OverviewExportTable, overview_export_tables
from expo_jbm329.services.analysis.pca_charts import render_pca_charts
from expo_jbm329.services.analysis.pca_export import PCAExportComponent, PCAExportSnapshot, PCAMetric, pca_export_tables
from expo_jbm329.services.analysis.regression import SIGNIFICANCE_LEVEL as REGRESSION_SIGNIFICANCE
from expo_jbm329.services.analysis.regression_charts import render_regression_charts
from expo_jbm329.services.analysis.regression_export import (
    RegressionExportComponent,
    RegressionExportSnapshot,
    RegressionMetric,
    regression_export_tables,
)
from expo_jbm329.services.analysis.regression_glm import RegressionModel
from expo_jbm329.services.analysis.statistics import (
    DescriptiveStatisticsResult,
    StatisticsExportTable,
    statistics_export_tables,
)
from expo_jbm329.services.analysis.statistics_charts import StatisticsChartLabels, render_statistics_charts
from expo_jbm329.services.analysis.timeseries_charts import render_time_series_charts
from expo_jbm329.services.analysis.timeseries_export import (
    TimeSeriesExportComponent,
    TimeSeriesExportSnapshot,
    TimeSeriesMetric,
    time_series_export_tables,
)
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage
from expo_jbm329.utils.format_utils import fmt_int, fmt_num, fmt_pct

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

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

_PROGRESS_COMPLETE = 100


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


@dataclass(frozen=True, slots=True)
class PreparedReportTable:
    """A localized table represented as structured values, not HTML."""

    key: str
    title: str
    headers: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]

    def __post_init__(self) -> None:
        """Keep each prepared row aligned with its accessible table headers."""
        if not self.key or not self.title or not self.headers:
            message = "A prepared report table requires a key, title, and headers."
            raise ValueError(message)
        if any(len(row) != len(self.headers) for row in self.rows):
            message = "Prepared report table rows must match the header count."
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class PreparedOverviewSummary:
    """Readable Overview facts, type counts and captured issue messages."""

    facts: tuple[tuple[str, str], ...]
    types_heading: str
    column_types: tuple[tuple[str, str], ...]
    issues_heading: str
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreparedReportComponent:
    """One selected report component, with domain tables or worker-rendered charts."""

    key: str
    label: str
    kind: str
    tables: tuple[PreparedReportTable, ...] = ()
    charts: tuple[ExcelChartImage, ...] = ()
    overview_summary: PreparedOverviewSummary | None = None

    def __post_init__(self) -> None:
        """Ensure prepared content agrees with its selected component kind."""
        if not self.key or not self.label or self.kind not in {"table", "chart"}:
            message = "A prepared report component requires a key, label, and supported kind."
            raise ValueError(message)
        if self.overview_summary is not None:
            if self.kind != "table" or self.tables or self.charts:
                message = "A prepared Overview summary must contain text content only."
                raise ValueError(message)
            return
        if self.kind == "table" and (len(self.tables) != 1 or self.charts):
            message = "A prepared table component must contain exactly one table."
            raise ValueError(message)
        if self.kind == "chart" and (self.tables or not self.charts):
            message = "A prepared chart component must contain chart images only."
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class PreparedReportEntry:
    """A report entry's captured metadata and selected, prepared components."""

    entry_id: str
    dataset_name: str
    dataset_rows: int
    dataset_columns: int
    category: str
    analysis_date: str
    app_version: str
    note: str
    components: tuple[PreparedReportComponent, ...]


@dataclass(frozen=True, slots=True)
class PreparedReportDocument:
    """Presentation-independent report data ready for HTML or future PDF output."""

    title: str
    description: str
    entries: tuple[PreparedReportEntry, ...]
    missing_value_label: str
    metadata_labels: tuple[str, str, str, str, str] = (
        "Dataset",
        "Rows",
        "Columns",
        "Analysis date",
        "Expo version",
    )


def _identity_translate(_context: str, text: str) -> str:
    """Return source text when no localization callback is supplied."""
    return text


@dataclass(frozen=True, slots=True)
class ReportRenderOptions:
    """Immutable, worker-safe translated labels and locale formatters for reports."""

    translated_labels: tuple[tuple[str, str, str], ...]
    number_format: Callable[[float], str] = fmt_num
    count_format: Callable[[int], str] = fmt_int

    def translate(self, context: str, text: str) -> str:
        """Return the captured translation for a context/source string pair."""
        for captured_context, source, translated in self.translated_labels:
            if captured_context == context and source == text:
                return translated
        return text


_REPORT_LABEL_SOURCES: dict[str, tuple[str, ...]] = {
    "AnalysisDialog": (
        "Overview",
        "Statistics",
        "Hypothesis Tests",
        "Correlation",
        "Regression",
        "Outliers",
        "Clustering",
        "PCA",
        "Time Series",
    ),
    "OverviewView": (
        "Summary",
        "Columns",
        "Columns metadata",
        "Sample",
        "Sample (first 100 rows)",
        "Column",
        "Type",
        "Storage type",
        "Missing",
        "Missing fraction",
        "Unique",
        "Section",
        "Metric",
        "Count",
        "Fraction",
        "Rows",
        "Missing values",
        "Duplicate rows",
        "Column types",
        "Numeric columns",
        "Categorical columns",
        "Datetime columns",
        "Boolean columns",
        "Other columns",
        "Potential issues",
        "No issues detected.",
        "⚠ {column} has {pct} missing values.",
    ),
    "StatisticsView": (
        "Continuous",
        "Categorical",
        "Charts",
        "Column",
        "Count",
        "Missing count",
        "Missing fraction",
        "Mean",
        "Median",
        "Std Dev",
        "Variance",
        "Min",
        "Max",
        "Range",
        "Q1",
        "Q3",
        "IQR",
        "Skewness",
        "Kurtosis",
        "Mean ± SD",
        "Median (Q1 to Q3)",
        "Shapiro-Wilk W",
        "Shapiro-Wilk p-value",
        "Recommended summary",
        "Category",
        "Fraction (non-missing)",
        "Valid count",
        "Histogram",
        "Boxplot",
        "No data",
        "Histogram and boxplot",
    ),
    "AnalysisExportDialog": (
        "Group summary",
        "Contingency table",
        "Measurement summary",
        "Test results",
        "Total",
        "Measurement",
        "Test",
        "Test statistic",
        "p-value",
        "Degrees of freedom",
        "Mean difference",
        "95% CI lower",
        "95% CI upper",
        "Effect size",
        "Effect value",
        "Numeric column",
        "Grouping column",
        "Row column",
        "Column column",
        "Sample count",
        "Yates' continuity correction",
        "Cochran's rule violated",
        "Fraction of expected counts below 5",
        "Minimum expected count",
        "Odds ratio",
        "Total subjects",
        "Excluded subjects",
        "Notes",
        "Welch's t-test",
        "Student's t-test",
        "Mann-Whitney U",
        "One-way ANOVA",
        "Kruskal-Wallis",
        "Pearson's chi-square test",
        "Fisher's exact test",
        "Wilcoxon signed-rank test",
        "Friedman test",
        "Cohen's d",
        "Rank-biserial correlation",
        "Eta²",
        "Epsilon²",
        "Cramér's V",
        "Kendall's W",
        "Strongest correlations",
        "Coefficient",
        "Significant after Holm",
        "Correlation method",
        "Ranking and Holm explanation",
        "(Intercept)",
        "Term",
        "Estimate",
        "Std. error",
        "t statistic",
        "z statistic",
        "VIF",
        "Hazard ratio",
        "{name}, 95% CI lower",
        "{name}, 95% CI upper",
        "Significant at p < {alpha}",
        "Rows used",
        "Rows dropped because of missing values",
        "Coefficients",
        "Model metrics",
        "Cluster sizes",
        "R²",
        "Adjusted R²",
        "F statistic",
        "F-test p-value",
        "Model degrees of freedom",
        "Residual degrees of freedom",
        "RMSE",
        "AIC",
        "Breusch-Pagan LM",
        "Breusch-Pagan p-value",
        "Jarque-Bera JB",
        "Jarque-Bera p-value",
        "Durbin-Watson",
        "Largest VIF",
        "Log-likelihood",
        "Null-model log-likelihood",
        "McFadden pseudo R²",
        "AUC (in-sample)",
        "Pearson dispersion",
        "NB2 alpha",
        "Events",
        "Censored",
        "Metric",
        "Value",
        "Status",
        "Column summary",
        "Column details",
        "Model summary",
        "Potential outliers",
        "Threshold",
        "Values",
        "Missing",
        "Potential outlier share",
        "Low potential outliers",
        "High potential outliers",
        "Lower fence",
        "Upper fence",
        "Q1",
        "Q3",
        "IQR",
        "Mean",
        "Standard deviation",
        "Median",
        "MAD",
        "Features",
        "Expected outlier fraction",
        "LOF neighbors",
        "Total rows",
        "Rows dropped because of missing or infinite values",
        "Inliers",
        "Cluster",
        "Rows",
        "Share",
        "Number of clusters",
        "Neighborhood radius (eps)",
        "Minimum samples",
        "Clusters found",
        "Noise rows",
        "Silhouette score",
        "Feature",
        "Component",
        "Variance",
        "Cumulative share",
        "Feature loadings",
        "Explained variance",
        "Series",
        "Autocorrelation",
        "Timestamp",
        "Trend",
        "Seasonal",
        "Residual",
        "Lag",
        "Source rows",
        "Invalid rows dropped",
        "Duplicate rows averaged",
        "Time points",
        "Seasonal period",
        "N/A",
        "Dataset",
        "Columns",
        "Analysis date",
        "Expo version",
        "Charts",
        "Least-squares line: y = ({slope}) x + ({intercept})",
        (
            "Pairs are ranked by absolute coefficient. Significance is based on "
            "p < {alpha} after Holm adjustment for {count} tests."
        ),
    ),
    "GroupComparisonView": (
        "Group summary",
        "Group",
        "Count",
        "Mean",
        "Median",
        "Std Dev",
        "Shapiro W",
        "Shapiro p",
        "Normal?",
        "Distribution by group",
    ),
    "ChiSquareView": (
        "Contingency table",
        "Adjusted standardized residuals",
        "Row",
        "Column",
        "Group",
        "Total",
    ),
    "PairedComparisonView": (
        "Measurement summary",
        "Measurement",
        "Count",
        "Mean",
        "Median",
        "Std Dev",
        "Q1",
        "Q3",
        "Subject trajectories",
        "Value",
        "Measurement occasion",
        "Distribution by occasion",
    ),
    "CorrelationView": (
        "Variable 1",
        "Variable 2",
        "p",
        "Holm p",
        "n",
        "Strength",
        "Pearson",
        "Spearman",
        "Kendall's tau-b",
        "Negligible",
        "Weak",
        "Moderate",
        "Strong",
        "N/A",
        "Strongest correlations",
        "Matrix plot",
        "Scatterplots",
        "{method} correlation",
        (
            "The line is a linear fit shown for reference. {method} measures monotonic, "
            "not necessarily linear, association."
        ),
        "Showing a random sample of {shown} of {total} points. Statistics use all points.",
        "Fewer than {minimum} rows have values in both columns, so no correlation can be computed.",
        "At least one of the columns is constant over the rows with values in both, so no correlation can be computed.",
    ),
    "OutliersView": (
        "Column",
        "Values",
        "Missing",
        "Outliers",
        "Share",
        "Low",
        "High",
        "Lower fence",
        "Upper fence",
        "Distance past fence",
        "z",
        "Modified z",
        "Row",
        "Too few values",
        "No spread",
    ),
    "MultivariateOutliersView": ("Anomaly score",),
}


def capture_report_labels(
    translate: Callable[[str, str], str] = _identity_translate,
    number_format: Callable[[float], str] = fmt_num,
    count_format: Callable[[int], str] = fmt_int,
) -> ReportRenderOptions:
    """Capture report translations on the caller thread for later worker use.

    Args:
        translate: UI-thread translation function accepting a context and source.
        number_format: Formatter retained by the report worker for numeric values.
        count_format: Formatter retained by the report worker for integer values.

    Returns:
        Immutable report options. The translation callable is not retained or
        invoked after this function returns.
    """
    captured = tuple(
        (context, source, translate(context, source))
        for context, sources in _REPORT_LABEL_SOURCES.items()
        for source in dict.fromkeys(sources)
    )
    return ReportRenderOptions(captured, number_format, count_format)


def localized_report_tables(
    category: AnalysisCategory,
    snapshot: ReportSnapshot,
    components: Sequence[str],
    *,
    translate: Callable[[str, str], str] = _identity_translate,
    number_format: Callable[[float], str] = fmt_num,
    count_format: Callable[[int], str] = fmt_int,
    labels: ReportRenderOptions | None = None,
) -> dict[str, pd.DataFrame]:
    """Build the selected report tables using each analysis export's conventions.

    The returned mapping uses translated export table titles as keys and
    contains fresh DataFrames with translated headers and presentation values.
    Chart components are ignored; callers should render them through the
    corresponding Qt-free chart renderer.

    Args:
        category: The category that owns the applied snapshot.
        snapshot: The exact applied analysis result captured in a report entry.
        components: Selected report component keys, in display order.
        translate: Translation callback accepting a context and source text.
        number_format: Locale-aware number formatter for explanatory values.
        count_format: Locale-aware integer formatter for explanatory counts.
        labels: Optional translations and locale formatters captured before worker execution.

    Returns:
        Localized tables keyed by their visible export titles.

    Raises:
        TypeError: If the category and snapshot do not match.
        ValueError: If a selected table is unavailable or translated titles collide.
    """
    if labels is not None:
        translate = labels.translate
        number_format = labels.number_format
        count_format = labels.count_format
    available_keys = {component.key for component in available_report_components(category, snapshot)}
    if len(components) != len(set(components)) or any(key not in available_keys for key in components):
        message = "Select distinct available report components."
        raise ValueError(message)
    frames: dict[str, pd.DataFrame] = {}

    def add(title: str, frame: pd.DataFrame) -> None:
        if title in frames:
            message = "Translated report table titles must be unique."
            raise ValueError(message)
        frames[title] = frame

    match category:
        case AnalysisCategory.OVERVIEW if isinstance(snapshot, DatasetOverviewResult):
            overview_table_keys = {
                "Summary": OverviewExportTable.SUMMARY,
                "Columns": OverviewExportTable.COLUMNS,
                "Sample": OverviewExportTable.SAMPLE,
            }
            for key in components:
                overview_table = overview_table_keys[key]
                frame = overview_export_tables(snapshot, (overview_table,))[overview_table.value]
                context = "OverviewView"
                overview_headers = {
                    "column": "Column",
                    "type": "Type",
                    "storage_type": "Storage type",
                    "missing_count": "Missing",
                    "missing_fraction": "Missing fraction",
                    "unique_count": "Unique",
                    "section": "Section",
                    "metric": "Metric",
                    "count": "Count",
                    "fraction": "Fraction",
                }
                add(
                    translate(context, overview_table.value),
                    frame.rename(columns={name: translate(context, label) for name, label in overview_headers.items()}),
                )
        case AnalysisCategory.STATISTICS if isinstance(snapshot, DescriptiveStatisticsResult):
            statistics_table_keys = {
                "Continuous": StatisticsExportTable.CONTINUOUS,
                "Categorical": StatisticsExportTable.CATEGORICAL,
            }
            statistics_continuous_headers = {
                "column": "Column",
                "count": "Count",
                "missing_count": "Missing count",
                "missing_fraction": "Missing fraction",
                "mean": "Mean",
                "median": "Median",
                "std": "Std Dev",
                "variance": "Variance",
                "minimum": "Min",
                "maximum": "Max",
                "range": "Range",
                "q1": "Q1",
                "q3": "Q3",
                "iqr": "IQR",
                "skewness": "Skewness",
                "kurtosis": "Kurtosis",
                "mean_sd_summary": "Mean ± SD",
                "median_iqr_summary": "Median (Q1 to Q3)",
                "shapiro_statistic": "Shapiro-Wilk W",
                "shapiro_p_value": "Shapiro-Wilk p-value",
                "recommended_summary_method": "Recommended summary",
            }
            statistics_categorical_headers = {
                "column": "Column",
                "value": "Category",
                "count": "Count",
                "fraction": "Fraction (non-missing)",
                "valid_count": "Valid count",
                "missing_count": "Missing count",
                "missing_fraction": "Missing fraction",
            }
            for key in components:
                statistics_table = statistics_table_keys.get(key)
                if statistics_table is None:
                    continue
                frame = statistics_export_tables(snapshot, (statistics_table,))[statistics_table.value]
                statistics_headers = (
                    statistics_continuous_headers
                    if statistics_table is StatisticsExportTable.CONTINUOUS
                    else statistics_categorical_headers
                )
                add(
                    translate("StatisticsView", statistics_table.value),
                    frame.rename(
                        columns={name: translate("StatisticsView", label) for name, label in statistics_headers.items()}
                    ),
                )
        case AnalysisCategory.HYPOTHESIS_TESTS if isinstance(snapshot, HypothesisExportSnapshot):
            context = {
                HypothesisTest.GROUP_COMPARISON: "GroupComparisonView",
                HypothesisTest.CHI_SQUARE: "ChiSquareView",
                HypothesisTest.PAIRED_COMPARISON: "PairedComparisonView",
            }[snapshot.test]
            summary_title = {
                HypothesisTest.GROUP_COMPARISON: "Group summary",
                HypothesisTest.CHI_SQUARE: "Contingency table",
                HypothesisTest.PAIRED_COMPARISON: "Measurement summary",
            }[snapshot.test]
            common_headers = {
                "group": "Group",
                "count": "Count",
                "mean": "Mean",
                "median": "Median",
                "std": "Std Dev",
                "shapiro_statistic": "Shapiro W",
                "shapiro_p_value": "Shapiro p",
                "normal": "Normal?",
                "measurement": "Measurement",
                "q1": "Q1",
                "q3": "Q3",
            }
            result_headers = {
                "test": "Test",
                "statistic": "Test statistic",
                "p_value": "p-value",
                "degrees_of_freedom": "Degrees of freedom",
                "mean_difference": "Mean difference",
                "ci_low": "95% CI lower",
                "ci_high": "95% CI upper",
                "effect_name": "Effect size",
                "effect_size": "Effect value",
                "numeric_column": "Numeric column",
                "grouping_column": "Grouping column",
                "row_column": "Row column",
                "column_column": "Column column",
                "sample_count": "Sample count",
                "yates_correction": "Yates' continuity correction",
                "cochran_violated": "Cochran's rule violated",
                "low_expected_fraction": "Fraction of expected counts below 5",
                "min_expected": "Minimum expected count",
                "odds_ratio": "Odds ratio",
                "total_subjects": "Total subjects",
                "excluded_subjects": "Excluded subjects",
                "notes": "Notes",
            }
            hypothesis_table_keys = {
                "summary": HypothesisExportComponent.SUMMARY,
                "test_results": HypothesisExportComponent.TEST_RESULTS,
            }
            for key in components:
                hypothesis_table = hypothesis_table_keys.get(key)
                if hypothesis_table is None:
                    continue
                frame = hypothesis_export_tables(snapshot, (hypothesis_table,))[hypothesis_table]
                if hypothesis_table is HypothesisExportComponent.SUMMARY:
                    title = translate(context, summary_title)
                    if snapshot.test is HypothesisTest.CHI_SQUARE:
                        from expo_jbm329.services.analysis.chi_square import ChiSquareResult

                        if not isinstance(snapshot.result, ChiSquareResult):
                            message = "A chi-square snapshot must contain a chi-square result."
                            raise TypeError(message)
                        total = translate(context, "Total")
                        frame.columns = [
                            snapshot.columns[0],
                            *snapshot.result.column_labels,
                            total,
                        ]
                        frame.iloc[-1, 0] = total
                    else:
                        frame = frame.rename(
                            columns={name: translate(context, label) for name, label in common_headers.items()}
                        )
                else:
                    title = translate(context, "Test results")
                    frame = frame.rename(
                        columns={
                            name: translate("AnalysisExportDialog", result_headers.get(name, "Measurement"))
                            + (f" {name.removeprefix('measurement_')}" if name.startswith("measurement_") else "")
                            for name in frame.columns
                        }
                    )
                    test_header = translate("AnalysisExportDialog", "Test")
                    effect_header = translate("AnalysisExportDialog", "Effect size")
                    if test_header in frame:
                        frame[test_header] = frame[test_header].map(
                            lambda value: translate("AnalysisExportDialog", value) if isinstance(value, str) else value
                        )
                    if effect_header in frame:
                        frame[effect_header] = frame[effect_header].map(
                            lambda value: translate("AnalysisExportDialog", value) if isinstance(value, str) else value
                        )
                add(title, frame)
        case AnalysisCategory.CORRELATION if isinstance(snapshot, CorrelationExportSnapshot):
            if "strongest_correlations" in components:
                frame = correlation_export_table(
                    snapshot,
                    (CorrelationExportComponent.STRONGEST_CORRELATIONS,),
                )
                strengths = {
                    "negligible": translate("CorrelationView", "Negligible"),
                    "weak": translate("CorrelationView", "Weak"),
                    "moderate": translate("CorrelationView", "Moderate"),
                    "strong": translate("CorrelationView", "Strong"),
                }
                methods = {
                    CorrelationMethod.PEARSON: translate("CorrelationView", "Pearson"),
                    CorrelationMethod.SPEARMAN: translate("CorrelationView", "Spearman"),
                    CorrelationMethod.KENDALL: translate("CorrelationView", "Kendall's tau-b"),
                }
                frame["strength"] = frame["strength"].map(
                    lambda value: strengths[value] if isinstance(value, str) else translate("CorrelationView", "N/A")
                )
                frame["method"] = frame["method"].map(lambda value: methods[CorrelationMethod(str(value))])
                frame["ranking_explanation"] = translate(
                    "AnalysisExportDialog",
                    "Pairs are ranked by absolute coefficient. Significance is based on "
                    "p < {alpha} after Holm adjustment for {count} tests.",
                ).format(
                    alpha=number_format(SIGNIFICANCE_LEVEL),
                    count=count_format(len(snapshot.matrix.pairs)),
                )
                correlation_headers = {
                    "variable_1": ("CorrelationView", "Variable 1"),
                    "variable_2": ("CorrelationView", "Variable 2"),
                    "coefficient": ("AnalysisExportDialog", "Coefficient"),
                    "ci_low": ("AnalysisExportDialog", "95% CI lower"),
                    "ci_high": ("AnalysisExportDialog", "95% CI upper"),
                    "p_value": ("CorrelationView", "p"),
                    "adjusted_p_value": ("CorrelationView", "Holm p"),
                    "n": ("CorrelationView", "n"),
                    "strength": ("CorrelationView", "Strength"),
                    "significant": ("AnalysisExportDialog", "Significant after Holm"),
                    "method": ("AnalysisExportDialog", "Correlation method"),
                    "ranking_explanation": ("AnalysisExportDialog", "Ranking and Holm explanation"),
                }
                add(
                    translate("AnalysisExportDialog", "Strongest correlations"),
                    frame.rename(
                        columns={
                            name: translate(context, label) for name, (context, label) in correlation_headers.items()
                        }
                    ),
                )
        case AnalysisCategory.REGRESSION if isinstance(snapshot, RegressionExportSnapshot):
            effect_names = {
                RegressionModel.LOGISTIC: translate("AnalysisExportDialog", "Odds ratio"),
                RegressionModel.POISSON: translate("AnalysisExportDialog", "Rate ratio"),
                RegressionModel.NEGATIVE_BINOMIAL: translate("AnalysisExportDialog", "Rate ratio"),
            }
            effect_name = effect_names.get(snapshot.model, "")
            hazard_name = translate("AnalysisExportDialog", "Hazard ratio")
            ci_low = translate("AnalysisExportDialog", "{name}, 95% CI lower")
            ci_high = translate("AnalysisExportDialog", "{name}, 95% CI upper")
            regression_coefficient_headers = {
                "term": "Term",
                "estimate": "Estimate",
                "std_error": "Std. error",
                "t_statistic": "t statistic",
                "z_statistic": "z statistic",
                "p_value": "p-value",
                "ci_low": "95% CI lower",
                "ci_high": "95% CI upper",
                "vif": "VIF",
                "effect": effect_name,
                "effect_ci_low": ci_low.format(name=effect_name),
                "effect_ci_high": ci_high.format(name=effect_name),
                "hazard_ratio": hazard_name,
                "hazard_ratio_ci_low": ci_low.format(name=hazard_name),
                "hazard_ratio_ci_high": ci_high.format(name=hazard_name),
                "significant": translate("AnalysisExportDialog", "Significant at p < {alpha}").format(
                    alpha=number_format(REGRESSION_SIGNIFICANCE)
                ),
            }
            regression_metric_labels = {
                RegressionMetric.ROWS_USED: "Rows used",
                RegressionMetric.ROWS_DROPPED: "Rows dropped because of missing values",
                RegressionMetric.R_SQUARED: "R²",
                RegressionMetric.ADJUSTED_R_SQUARED: "Adjusted R²",
                RegressionMetric.F_STATISTIC: "F statistic",
                RegressionMetric.F_P_VALUE: "F-test p-value",
                RegressionMetric.DF_MODEL: "Model degrees of freedom",
                RegressionMetric.DF_RESIDUAL: "Residual degrees of freedom",
                RegressionMetric.RMSE: "RMSE",
                RegressionMetric.AIC: "AIC",
                RegressionMetric.BREUSCH_PAGAN_STATISTIC: "Breusch-Pagan LM",
                RegressionMetric.BREUSCH_PAGAN_P_VALUE: "Breusch-Pagan p-value",
                RegressionMetric.JARQUE_BERA_STATISTIC: "Jarque-Bera JB",
                RegressionMetric.JARQUE_BERA_P_VALUE: "Jarque-Bera p-value",
                RegressionMetric.DURBIN_WATSON: "Durbin-Watson",
                RegressionMetric.MAX_VIF: "Largest VIF",
                RegressionMetric.LOG_LIKELIHOOD: "Log-likelihood",
                RegressionMetric.NULL_LOG_LIKELIHOOD: "Null-model log-likelihood",
                RegressionMetric.PSEUDO_R_SQUARED: "McFadden pseudo R²",
                RegressionMetric.AUC: "AUC (in-sample)",
                RegressionMetric.DISPERSION_RATIO: "Pearson dispersion",
                RegressionMetric.NEGATIVE_BINOMIAL_ALPHA: "NB2 alpha",
                RegressionMetric.EVENTS: "Events",
                RegressionMetric.CENSORED: "Censored",
            }
            regression_table_keys = {
                "coefficients": RegressionExportComponent.COEFFICIENTS,
                "model_metrics": RegressionExportComponent.MODEL_METRICS,
            }
            for key in components:
                regression_table = regression_table_keys.get(key)
                if regression_table is None:
                    continue
                frame = regression_export_tables(
                    snapshot,
                    (regression_table,),
                    intercept_label=translate("AnalysisExportDialog", "(Intercept)"),
                )[regression_table]
                if regression_table is RegressionExportComponent.MODEL_METRICS:
                    frame["metric"] = frame["metric"].map(
                        lambda metric: (
                            translate("AnalysisExportDialog", regression_metric_labels[RegressionMetric(metric)])
                            if isinstance(metric, str)
                            else metric
                        )
                    )
                    regression_headers = {"metric": "Metric", "value": "Value", "notes": "Notes"}
                else:
                    regression_headers = regression_coefficient_headers
                title = translate(
                    "AnalysisExportDialog",
                    "Coefficients" if regression_table is RegressionExportComponent.COEFFICIENTS else "Model metrics",
                )
                add(
                    title,
                    frame.rename(
                        columns={
                            name: translate("AnalysisExportDialog", label) for name, label in regression_headers.items()
                        }
                    ),
                )
        case AnalysisCategory.OUTLIERS if isinstance(snapshot, OutlierExportSnapshot):
            outlier_metric_labels = {
                OutlierMetric.THRESHOLD: "Threshold",
                OutlierMetric.VALUES: "Values",
                OutlierMetric.MISSING: "Missing",
                OutlierMetric.OUTLIERS: "Potential outliers",
                OutlierMetric.OUTLIER_SHARE: "Potential outlier share",
                OutlierMetric.LOW: "Low potential outliers",
                OutlierMetric.HIGH: "High potential outliers",
                OutlierMetric.LOWER_FENCE: "Lower fence",
                OutlierMetric.UPPER_FENCE: "Upper fence",
                OutlierMetric.Q1: "Q1",
                OutlierMetric.Q3: "Q3",
                OutlierMetric.IQR: "IQR",
                OutlierMetric.MEAN: "Mean",
                OutlierMetric.STD: "Standard deviation",
                OutlierMetric.MEDIAN: "Median",
                OutlierMetric.MAD: "MAD",
                OutlierMetric.FEATURES: "Features",
                OutlierMetric.CONTAMINATION: "Expected outlier fraction",
                OutlierMetric.LOF_NEIGHBORS: "LOF neighbors",
                OutlierMetric.TOTAL_ROWS: "Total rows",
                OutlierMetric.ROWS_USED: "Rows used",
                OutlierMetric.ROWS_DROPPED: "Rows dropped because of missing or infinite values",
                OutlierMetric.INLIERS: "Inliers",
            }
            if isinstance(snapshot, MultivariateOutlierExportSnapshot):
                score_label = translate("MultivariateOutliersView", "Anomaly score")
            else:
                score_label = {
                    OutlierMethod.IQR: translate("OutliersView", "Distance past fence"),
                    OutlierMethod.Z_SCORE: translate("OutliersView", "z"),
                    OutlierMethod.MODIFIED_Z_SCORE: translate("OutliersView", "Modified z"),
                }[snapshot.summary.method]
            outlier_table_keys = {
                item.value: item for item in OutlierExportComponent if item is not OutlierExportComponent.CHARTS
            }
            for key in components:
                outlier_table = outlier_table_keys.get(key)
                if outlier_table is None:
                    continue
                frame = outlier_export_tables(
                    snapshot,
                    (outlier_table,),
                    row_label=translate("OutliersView", "Row"),
                    score_label=score_label,
                )[outlier_table]
                if outlier_table is OutlierExportComponent.COLUMN_SUMMARY:
                    frame["status"] = frame["status"].map(
                        lambda status: (
                            translate(
                                "OutliersView",
                                {
                                    ColumnOutlierStatus.NOT_ENOUGH_OBSERVATIONS: "Too few values",
                                    ColumnOutlierStatus.ZERO_SPREAD: "No spread",
                                }[ColumnOutlierStatus(status)],
                            )
                            if isinstance(status, str)
                            else status
                        )
                    )
                    outlier_headers = {
                        "column": ("OutliersView", "Column"),
                        "values": ("OutliersView", "Values"),
                        "missing": ("OutliersView", "Missing"),
                        "outliers": ("OutliersView", "Outliers"),
                        "share": ("OutliersView", "Share"),
                        "low": ("OutliersView", "Low"),
                        "high": ("OutliersView", "High"),
                        "lower_fence": ("OutliersView", "Lower fence"),
                        "upper_fence": ("OutliersView", "Upper fence"),
                        "status": ("AnalysisExportDialog", "Status"),
                        "notes": ("AnalysisExportDialog", "Notes"),
                    }
                elif outlier_table in (OutlierExportComponent.COLUMN_DETAILS, OutlierExportComponent.MODEL_SUMMARY):
                    frame["metric"] = frame["metric"].map(
                        lambda metric: (
                            translate("AnalysisExportDialog", outlier_metric_labels[OutlierMetric(metric)])
                            if isinstance(metric, str)
                            else metric
                        )
                    )
                    outlier_headers = {
                        "metric": ("AnalysisExportDialog", "Metric"),
                        "value": ("AnalysisExportDialog", "Value"),
                        "notes": ("AnalysisExportDialog", "Notes"),
                    }
                else:
                    outlier_headers = {}
                title = translate(
                    "AnalysisExportDialog",
                    {
                        OutlierExportComponent.COLUMN_SUMMARY: "Column summary",
                        OutlierExportComponent.COLUMN_DETAILS: "Column details",
                        OutlierExportComponent.MODEL_SUMMARY: "Model summary",
                        OutlierExportComponent.POTENTIAL_OUTLIERS: "Potential outliers",
                    }[outlier_table],
                )
                add(
                    title,
                    frame.rename(
                        columns={name: translate(context, label) for name, (context, label) in outlier_headers.items()}
                    ),
                )
        case AnalysisCategory.CLUSTERING if isinstance(snapshot, ClusteringExportSnapshot):
            clustering_metric_labels = {
                ClusteringMetric.FEATURES: "Features",
                ClusteringMetric.CLUSTER_COUNT: "Number of clusters",
                ClusteringMetric.DBSCAN_EPSILON: "Neighborhood radius (eps)",
                ClusteringMetric.DBSCAN_MIN_SAMPLES: "Minimum samples",
                ClusteringMetric.TOTAL_ROWS: "Total rows",
                ClusteringMetric.ROWS_USED: "Rows used",
                ClusteringMetric.ROWS_DROPPED: "Rows dropped because of missing or infinite values",
                ClusteringMetric.CLUSTERS_FOUND: "Clusters found",
                ClusteringMetric.NOISE_ROWS: "Noise rows",
                ClusteringMetric.SILHOUETTE: "Silhouette score",
            }
            clustering_headers = {
                "cluster": "Cluster",
                "rows": "Rows",
                "share": "Share",
                "metric": "Metric",
                "value": "Value",
                "notes": "Notes",
            }
            clustering_table_keys = {
                "cluster_sizes": ClusteringExportComponent.CLUSTER_SIZES,
                "model_summary": ClusteringExportComponent.MODEL_SUMMARY,
            }
            for key in components:
                clustering_table = clustering_table_keys.get(key)
                if clustering_table is None:
                    continue
                frame = clustering_export_tables(snapshot, (clustering_table,))[clustering_table]
                if clustering_table is ClusteringExportComponent.MODEL_SUMMARY:
                    frame["metric"] = frame["metric"].map(
                        lambda metric: (
                            translate("AnalysisExportDialog", clustering_metric_labels[ClusteringMetric(metric)])
                            if isinstance(metric, str)
                            else metric
                        )
                    )
                title = translate(
                    "AnalysisExportDialog",
                    "Cluster sizes" if clustering_table is ClusteringExportComponent.CLUSTER_SIZES else "Model summary",
                )
                add(
                    title,
                    frame.rename(
                        columns={
                            name: translate("AnalysisExportDialog", label) for name, label in clustering_headers.items()
                        }
                    ),
                )
        case AnalysisCategory.PCA if isinstance(snapshot, PCAExportSnapshot):
            pca_metric_labels = {
                PCAMetric.FEATURES: "Features",
                PCAMetric.TOTAL_ROWS: "Total rows",
                PCAMetric.ROWS_USED: "Rows used",
                PCAMetric.ROWS_DROPPED: "Rows dropped because of missing or infinite values",
            }
            pca_headers = {
                "feature": "Feature",
                "component": "Component",
                "variance": "Variance",
                "share": "Share",
                "cumulative_share": "Cumulative share",
                "metric": "Metric",
                "value": "Value",
                "notes": "Notes",
            }
            pca_table_keys = {
                "feature_loadings": PCAExportComponent.FEATURE_LOADINGS,
                "explained_variance": PCAExportComponent.EXPLAINED_VARIANCE,
                "model_summary": PCAExportComponent.MODEL_SUMMARY,
            }
            for key in components:
                pca_table = pca_table_keys.get(key)
                if pca_table is None:
                    continue
                frame = pca_export_tables(snapshot, (pca_table,))[pca_table]
                if pca_table is PCAExportComponent.MODEL_SUMMARY:
                    frame["metric"] = frame["metric"].map(
                        lambda metric: (
                            translate("AnalysisExportDialog", pca_metric_labels[PCAMetric(metric)])
                            if isinstance(metric, str)
                            else metric
                        )
                    )
                title = translate(
                    "AnalysisExportDialog",
                    {
                        PCAExportComponent.FEATURE_LOADINGS: "Feature loadings",
                        PCAExportComponent.EXPLAINED_VARIANCE: "Explained variance",
                        PCAExportComponent.MODEL_SUMMARY: "Model summary",
                    }[pca_table],
                )
                add(
                    title,
                    frame.rename(
                        columns={name: translate("AnalysisExportDialog", label) for name, label in pca_headers.items()}
                    ),
                )
        case AnalysisCategory.TIME_SERIES if isinstance(snapshot, TimeSeriesExportSnapshot):
            time_series_metric_labels = {
                TimeSeriesMetric.SOURCE_ROWS: "Source rows",
                TimeSeriesMetric.INVALID_ROWS: "Invalid rows dropped",
                TimeSeriesMetric.DUPLICATE_ROWS: "Duplicate rows averaged",
                TimeSeriesMetric.TIME_POINTS: "Time points",
                TimeSeriesMetric.SEASONAL_PERIOD: "Seasonal period",
            }
            time_series_headers = {
                "timestamp": "Timestamp",
                "value": "Value",
                "trend": "Trend",
                "seasonal": "Seasonal",
                "residual": "Residual",
                "lag": "Lag",
                "autocorrelation": "Autocorrelation",
                "metric": "Metric",
                "notes": "Notes",
            }
            time_series_table_keys = {
                "series": TimeSeriesExportComponent.SERIES,
                "autocorrelation": TimeSeriesExportComponent.AUTOCORRELATION,
                "model_summary": TimeSeriesExportComponent.MODEL_SUMMARY,
            }
            for key in components:
                time_series_table = time_series_table_keys.get(key)
                if time_series_table is None:
                    continue
                frame = time_series_export_tables(snapshot, (time_series_table,))[time_series_table]
                if time_series_table is TimeSeriesExportComponent.MODEL_SUMMARY:
                    frame["metric"] = frame["metric"].map(
                        lambda metric: (
                            translate("AnalysisExportDialog", time_series_metric_labels[TimeSeriesMetric(metric)])
                            if isinstance(metric, str)
                            else metric
                        )
                    )
                title = translate(
                    "AnalysisExportDialog",
                    {
                        TimeSeriesExportComponent.SERIES: "Series",
                        TimeSeriesExportComponent.AUTOCORRELATION: "Autocorrelation",
                        TimeSeriesExportComponent.MODEL_SUMMARY: "Model summary",
                    }[time_series_table],
                )
                add(
                    title,
                    frame.rename(
                        columns={
                            name: translate("AnalysisExportDialog", label)
                            for name, label in time_series_headers.items()
                        }
                    ),
                )
        case _:
            message = "The analysis category and applied report snapshot do not match."
            raise TypeError(message)
    return frames


def prepare_report_content(
    document: ReportDocument,
    *,
    translate: Callable[[str, str], str] = _identity_translate,
    number_format: Callable[[float], str] = fmt_num,
    count_format: Callable[[int], str] = fmt_int,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
    labels: ReportRenderOptions | None = None,
) -> PreparedReportDocument:
    """Prepare selected tables and charts from immutable applied snapshots.

    Table builders and chart renderers operate only on captured analysis
    results; this function never reads a live dataset or GUI widget.

    Args:
        document: Report draft to snapshot in its current entry order.
        translate: Translation callback accepting a context and source text.
        number_format: Locale-aware numeric cell and chart formatter.
        count_format: Locale-aware integer cell and chart formatter.
        progress_cb: Optional monotonic callback receiving percentages 0-100.
        cancel_cb: Optional cooperative cancellation callback.
        labels: Optional translations and locale formatters captured before worker execution.

    Returns:
        Structured report content with raw cell values and PNG image bytes.

    Raises:
        ExcelChartCancelledError: If cancellation is requested.
        TypeError: If an entry's category and snapshot do not match.
        ValueError: If selected report content cannot be prepared.
    """
    if labels is not None:
        translate = labels.translate
        number_format = labels.number_format
        count_format = labels.count_format
    document_title = document.title
    description = document.description
    entries = document.entries
    component_count = sum(len(entry.selected_components) for entry in entries)
    completed = 0
    last_progress = 0
    prepared_entries: list[PreparedReportEntry] = []

    def check_cancel() -> None:
        if cancel_cb is not None and cancel_cb():
            raise ExcelChartCancelledError

    def report_progress(fraction: int = 100) -> None:
        nonlocal last_progress
        if progress_cb is not None:
            percent = (completed * 100 + fraction) // max(component_count, 1)
            percent = min(percent, 100)
            if percent > last_progress:
                last_progress = percent
                progress_cb(percent)

    for entry in entries:
        check_cancel()
        selected = tuple(
            next(component for component in entry.components if component.key == key)
            for key in entry.selected_components
        )
        overview = entry.snapshot if isinstance(entry.snapshot, DatasetOverviewResult) else None
        table_keys = tuple(
            component.key
            for component in selected
            if component.kind == "table" and not (overview is not None and component.key == "Summary")
        )
        localized_tables = iter(
            localized_report_tables(
                entry.category,
                entry.snapshot,
                table_keys,
                translate=translate,
                number_format=number_format,
                count_format=count_format,
            ).items()
        )
        chart_keys = tuple(component.key for component in selected if component.kind == "chart")
        rendered_charts = (
            _render_entry_charts(
                entry.category,
                entry.snapshot,
                chart_keys,
                translate=translate,
                number_format=number_format,
                count_format=count_format,
                progress_cb=report_progress,
                cancel_cb=cancel_cb,
            )
            if chart_keys
            else {}
        )
        prepared_components: list[PreparedReportComponent] = []
        for component in selected:
            check_cancel()
            label = translate(
                _component_translation_context(entry.category, entry.snapshot, component.key),
                component.label,
            )
            if overview is not None and component.key == "Summary":
                prepared_components.append(
                    PreparedReportComponent(
                        component.key,
                        label,
                        component.kind,
                        overview_summary=_prepare_overview_summary(overview, translate, count_format),
                    )
                )
            elif component.kind == "table":
                table_title, frame = next(localized_tables)
                prepared_table = (
                    _prepare_overview_columns(overview, table_title, translate, count_format)
                    if overview is not None and component.key == "Columns"
                    else _prepare_table(component.key, table_title, frame)
                )
                prepared_components.append(
                    PreparedReportComponent(component.key, label, component.kind, (prepared_table,))
                )
            else:
                images = rendered_charts.get(component.key, ())
                if not images:
                    message = f"The selected report chart component {component.key!r} produced no images."
                    raise ValueError(message)
                prepared_components.append(PreparedReportComponent(component.key, label, component.kind, charts=images))
            completed += 1
            report_progress()
        prepared_entries.append(
            PreparedReportEntry(
                entry.entry_id,
                entry.dataset_name,
                entry.dataset_rows,
                entry.dataset_columns,
                translate("AnalysisDialog", _category_title(entry.category)),
                entry.analysis_date,
                entry.app_version,
                entry.note,
                tuple(prepared_components),
            )
        )
    check_cancel()
    if progress_cb is not None and last_progress < _PROGRESS_COMPLETE:
        progress_cb(_PROGRESS_COMPLETE)
    return PreparedReportDocument(
        document_title,
        description,
        tuple(prepared_entries),
        translate("AnalysisExportDialog", "N/A"),
        (
            translate("AnalysisExportDialog", "Dataset"),
            translate("AnalysisExportDialog", "Rows"),
            translate("AnalysisExportDialog", "Columns"),
            translate("AnalysisExportDialog", "Analysis date"),
            translate("AnalysisExportDialog", "Expo version"),
        ),
    )


def _prepare_overview_summary(
    result: DatasetOverviewResult,
    translate: Callable[[str, str], str],
    count_format: Callable[[int], str],
) -> PreparedOverviewSummary:
    """Prepare the view's Overview facts without constructing or inspecting widgets."""

    def label(text: str) -> str:
        return translate("OverviewView", text)

    return PreparedOverviewSummary(
        facts=(
            (label("Rows"), count_format(result.row_count)),
            (label("Columns"), count_format(result.column_count)),
            (
                label("Missing values"),
                f"{count_format(result.missing_cell_count)} ({fmt_pct(result.missing_cell_fraction)})",
            ),
            (
                label("Duplicate rows"),
                f"{count_format(result.duplicate_row_count)} ({fmt_pct(result.duplicate_row_fraction)})",
            ),
        ),
        types_heading=label("Column types"),
        column_types=tuple(
            (label(text), count_format(count))
            for text, count in (
                ("Numeric columns", result.numeric_column_count),
                ("Categorical columns", result.categorical_column_count),
                ("Datetime columns", result.datetime_column_count),
                ("Boolean columns", result.boolean_column_count),
                ("Other columns", result.other_column_count),
            )
        ),
        issues_heading=label("Potential issues"),
        issues=tuple(
            label("⚠ {column} has {pct} missing values.").format(column=column, pct=fmt_pct(fraction))
            for column, fraction in result.high_missing_columns
        )
        or (label("No issues detected."),),
    )


def _prepare_overview_columns(
    result: DatasetOverviewResult,
    title: str,
    translate: Callable[[str, str], str],
    count_format: Callable[[int], str],
) -> PreparedReportTable:
    """Combine missing counts and percentages for report presentation only."""
    frame = overview_export_tables(result, (OverviewExportTable.COLUMNS,))["Columns"]
    frame["missing_count"] = pd.Series(
        [
            f"{count_format(int(count))} ({fmt_pct(float(fraction), decimals=2)})"
            for count, fraction in zip(frame["missing_count"], frame["missing_fraction"], strict=True)
        ],
        dtype=pd.StringDtype(),
    )
    frame = frame.drop(columns="missing_fraction").rename(
        columns={
            key: translate("OverviewView", label)
            for key, label in (
                ("column", "Column"),
                ("type", "Type"),
                ("storage_type", "Storage type"),
                ("missing_count", "Missing"),
                ("unique_count", "Unique"),
            )
        }
    )
    return _prepare_table("Columns", title, frame)


def _prepare_table(key: str, title: str, frame: pd.DataFrame) -> PreparedReportTable:
    """Convert one fresh localized export DataFrame to immutable table values."""
    return PreparedReportTable(
        key,
        title,
        tuple(str(header) for header in frame.columns),
        tuple(tuple(value for value in row) for row in frame.itertuples(index=False, name=None)),
    )


def _category_title(category: AnalysisCategory) -> str:
    return {
        AnalysisCategory.OVERVIEW: "Overview",
        AnalysisCategory.STATISTICS: "Statistics",
        AnalysisCategory.HYPOTHESIS_TESTS: "Hypothesis Tests",
        AnalysisCategory.CORRELATION: "Correlation",
        AnalysisCategory.REGRESSION: "Regression",
        AnalysisCategory.OUTLIERS: "Outliers",
        AnalysisCategory.CLUSTERING: "Clustering",
        AnalysisCategory.PCA: "PCA",
        AnalysisCategory.TIME_SERIES: "Time Series",
    }[category]


def _component_translation_context(
    category: AnalysisCategory,
    snapshot: ReportSnapshot,
    component_key: str,
) -> str:
    if category is AnalysisCategory.HYPOTHESIS_TESTS and isinstance(snapshot, HypothesisExportSnapshot):
        if component_key == "summary":
            return {
                HypothesisTest.GROUP_COMPARISON: "GroupComparisonView",
                HypothesisTest.CHI_SQUARE: "ChiSquareView",
                HypothesisTest.PAIRED_COMPARISON: "PairedComparisonView",
            }[snapshot.test]
        return "AnalysisExportDialog"
    if category is AnalysisCategory.CORRELATION:
        return "AnalysisExportDialog" if component_key == "strongest_correlations" else "CorrelationView"
    return {
        AnalysisCategory.OVERVIEW: "OverviewView",
        AnalysisCategory.STATISTICS: "StatisticsView",
        AnalysisCategory.HYPOTHESIS_TESTS: "AnalysisExportDialog",
        AnalysisCategory.CORRELATION: "AnalysisExportDialog",
        AnalysisCategory.REGRESSION: "AnalysisExportDialog",
        AnalysisCategory.OUTLIERS: "AnalysisExportDialog",
        AnalysisCategory.CLUSTERING: "AnalysisExportDialog",
        AnalysisCategory.PCA: "AnalysisExportDialog",
        AnalysisCategory.TIME_SERIES: "AnalysisExportDialog",
    }[category]


def _render_entry_charts(
    category: AnalysisCategory,
    snapshot: ReportSnapshot,
    component_keys: tuple[str, ...],
    *,
    translate: Callable[[str, str], str],
    number_format: Callable[[float], str],
    count_format: Callable[[int], str],
    progress_cb: Callable[[int], None] | None,
    cancel_cb: Callable[[], bool] | None,
) -> dict[str, tuple[ExcelChartImage, ...]]:
    """Render only selected chart components and associate their PNGs by key."""
    if not component_keys:
        return {}
    images: tuple[ExcelChartImage, ...]
    if category is AnalysisCategory.STATISTICS and isinstance(snapshot, DescriptiveStatisticsResult):
        statistics_labels = StatisticsChartLabels(
            translate("StatisticsView", "Histogram"),
            translate("StatisticsView", "Boxplot"),
            translate("StatisticsView", "No data"),
        )
        images = render_statistics_charts(
            snapshot.columns, statistics_labels, progress_cb=progress_cb, cancel_cb=cancel_cb
        )
        return {
            "Charts": tuple(
                ExcelChartImage(
                    image.heading,
                    image.image_data,
                    image.width_px,
                    image.height_px,
                    (*image.captions, translate("StatisticsView", "Histogram and boxplot")),
                )
                for image in images
            )
        }
    if category is AnalysisCategory.HYPOTHESIS_TESTS and isinstance(snapshot, HypothesisExportSnapshot):
        context = {
            HypothesisTest.GROUP_COMPARISON: "GroupComparisonView",
            HypothesisTest.CHI_SQUARE: "ChiSquareView",
            HypothesisTest.PAIRED_COMPARISON: "PairedComparisonView",
        }[snapshot.test]
        distribution = (
            "Distribution by group" if snapshot.test is HypothesisTest.GROUP_COMPARISON else "Distribution by occasion"
        )
        residual_annotations: tuple[tuple[str, ...], ...] = ()
        from expo_jbm329.services.analysis.chi_square import ChiSquareResult

        if isinstance(snapshot.result, ChiSquareResult):
            residual_annotations = tuple(
                tuple(number_format(value) for value in row) for row in snapshot.result.adjusted_residuals
            )
        hypothesis_labels = HypothesisChartLabels(
            translate(context, distribution),
            translate("ChiSquareView", "Adjusted standardized residuals"),
            translate("PairedComparisonView", "Subject trajectories"),
            translate("PairedComparisonView", "Value"),
            translate("PairedComparisonView", "Measurement occasion"),
            residual_annotations,
        )
        images = render_hypothesis_charts(snapshot, hypothesis_labels, progress_cb=progress_cb, cancel_cb=cancel_cb)
        return {"charts": images}
    if category is AnalysisCategory.CORRELATION and isinstance(snapshot, CorrelationExportSnapshot):
        chart_keys = tuple(
            {
                "matrix_plot": CorrelationExportComponent.MATRIX_PLOT,
                "scatterplots": CorrelationExportComponent.SCATTERPLOTS,
            }[key]
            for key in component_keys
        )
        method_names = {
            CorrelationMethod.PEARSON: translate("CorrelationView", "Pearson"),
            CorrelationMethod.SPEARMAN: translate("CorrelationView", "Spearman"),
            CorrelationMethod.KENDALL: translate("CorrelationView", "Kendall's tau-b"),
        }
        method = method_names[snapshot.matrix.method]
        annotations = tuple(tuple(number_format(value) for value in row) for row in snapshot.matrix.coefficients)
        correlation_labels = CorrelationChartLabels(
            translate("CorrelationView", "{method} correlation").format(method=method),
            "{x} / {y} (" + method + ")",
            translate("AnalysisExportDialog", "Least-squares line: y = ({slope}) x + ({intercept})"),
            translate(
                "CorrelationView",
                "The line is a linear fit shown for reference. {method} measures monotonic, "
                "not necessarily linear, association.",
            ).format(method=method),
            translate(
                "CorrelationView",
                "Showing a random sample of {shown} of {total} points. Statistics use all points.",
            ),
            translate(
                "CorrelationView",
                "Fewer than {minimum} rows have values in both columns, so no correlation can be computed.",
            ).format(minimum=count_format(MIN_OBSERVATIONS)),
            translate(
                "CorrelationView",
                "At least one of the columns is constant over the rows with values in both, "
                "so no correlation can be computed.",
            ),
            number_format,
            count_format,
            annotations,
        )
        images = render_correlation_charts(
            snapshot,
            chart_keys,
            correlation_labels,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
        )
        output: dict[str, list[ExcelChartImage]] = {key: [] for key in component_keys}
        matrix_heading = correlation_labels.matrix_title
        matrix_selected = "matrix_plot" in component_keys
        scatter_key = "scatterplots"
        for image in images:
            if matrix_selected and image.heading == matrix_heading:
                output["matrix_plot"].append(image)
            elif scatter_key in output:
                output[scatter_key].append(image)
            else:
                message = "The correlation chart renderer returned an unselected chart."
                raise ValueError(message)
        return {key: tuple(value) for key, value in output.items()}
    if category is AnalysisCategory.REGRESSION and isinstance(snapshot, RegressionExportSnapshot):
        images = render_regression_charts(snapshot, progress_cb=progress_cb, cancel_cb=cancel_cb)
        return {"charts": images}
    if category is AnalysisCategory.OUTLIERS and isinstance(snapshot, OutlierExportSnapshot):
        if isinstance(snapshot, UnivariateOutlierExportSnapshot):
            images = render_univariate_outlier_charts(snapshot, progress_cb=progress_cb, cancel_cb=cancel_cb)
        else:
            images = render_multivariate_outlier_charts(snapshot, progress_cb=progress_cb, cancel_cb=cancel_cb)
        return {"charts": images}
    if category is AnalysisCategory.CLUSTERING and isinstance(snapshot, ClusteringExportSnapshot):
        images = render_clustering_charts(snapshot, progress_cb=progress_cb, cancel_cb=cancel_cb)
        return {"charts": images}
    if category is AnalysisCategory.PCA and isinstance(snapshot, PCAExportSnapshot):
        images = render_pca_charts(snapshot, progress_cb=progress_cb, cancel_cb=cancel_cb)
        return {"charts": images}
    if category is AnalysisCategory.TIME_SERIES and isinstance(snapshot, TimeSeriesExportSnapshot):
        images = render_time_series_charts(snapshot, progress_cb=progress_cb, cancel_cb=cancel_cb)
        return {"charts": images}
    message = "The analysis category and applied report snapshot do not match."
    raise TypeError(message)


def render_report_html(
    document: ReportDocument,
    *,
    translate: Callable[[str, str], str] = _identity_translate,
    number_format: Callable[[float], str] = fmt_num,
    count_format: Callable[[int], str] = fmt_int,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
    labels: ReportRenderOptions | None = None,
) -> str:
    """Prepare and render a self-contained, accessible HTML report.

    Args:
        document: Report draft whose ordered entries and metadata are captured.
        translate: Translation callback accepting a context and source text.
        number_format: Locale-aware numeric table-cell and chart formatter.
        count_format: Locale-aware integer table-cell and chart formatter.
        progress_cb: Optional preparation progress callback, receiving 0-100.
        cancel_cb: Optional cooperative cancellation callback.
        labels: Optional translations and locale formatters captured before worker execution.

    Returns:
        Complete HTML5 markup with inline responsive and print styles.

    Raises:
        ExcelChartCancelledError: If chart or report preparation is cancelled.
        TypeError: If a report entry has a mismatched category and snapshot.
        ValueError: If selected report content cannot be prepared.
    """
    if labels is not None:
        translate = labels.translate
        number_format = labels.number_format
        count_format = labels.count_format
    last_progress = 0

    def notify_progress(value: int) -> None:
        nonlocal last_progress
        if progress_cb is not None and value > last_progress:
            last_progress = value
            progress_cb(value)

    def preparation_progress(value: int) -> None:
        notify_progress(value * 85 // _PROGRESS_COMPLETE)

    def serialization_progress(value: int) -> None:
        notify_progress(85 + value * 15 // _PROGRESS_COMPLETE)

    prepared = prepare_report_content(
        document,
        translate=translate,
        number_format=number_format,
        count_format=count_format,
        progress_cb=preparation_progress if progress_cb is not None else None,
        cancel_cb=cancel_cb,
        labels=labels,
    )
    return render_prepared_report_html(
        prepared,
        number_format=number_format,
        count_format=count_format,
        progress_cb=serialization_progress if progress_cb is not None else None,
        cancel_cb=cancel_cb,
    )


def render_prepared_report_html(
    document: PreparedReportDocument,
    *,
    number_format: Callable[[float], str] = fmt_num,
    count_format: Callable[[int], str] = fmt_int,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> str:
    """Serialize prepared report data as escaped, self-contained HTML."""
    total_components = sum(len(entry.components) for entry in document.entries)
    completed_components = 0

    def check_cancel() -> None:
        if cancel_cb is not None and cancel_cb():
            raise ExcelChartCancelledError

    def report_progress() -> None:
        if progress_cb is not None:
            percentage = completed_components * _PROGRESS_COMPLETE // max(total_components, 1)
            progress_cb(min(percentage, _PROGRESS_COMPLETE))

    title = _html_escape(document.title)
    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{title}</title>",
        "<style>",
        _REPORT_CSS,
        "</style>",
        "</head>",
        "<body>",
        '<main class="report">',
        f'<header class="report-header"><h1>{title}</h1>',
    ]
    if document.description:
        parts.append(f'<p class="report-description">{_html_escape(document.description)}</p>')
    parts.append("</header>")
    for entry in document.entries:
        check_cancel()
        dataset_label, rows_label, columns_label, date_label, version_label = document.metadata_labels
        parts.extend([
            '<article class="analysis-entry">',
            f"<h2>{_html_escape(entry.category)}</h2>",
            '<dl class="metadata">',
            f"<div><dt>{_html_escape(dataset_label)}</dt><dd>{_html_escape(entry.dataset_name)}</dd></div>",
            f"<div><dt>{_html_escape(rows_label)}</dt><dd>{_html_escape(count_format(entry.dataset_rows))}</dd></div>",
            f"<div><dt>{_html_escape(columns_label)}</dt><dd>{_html_escape(count_format(entry.dataset_columns))}</dd></div>",
            f"<div><dt>{_html_escape(date_label)}</dt><dd>{_html_escape(entry.analysis_date)}</dd></div>",
            f"<div><dt>{_html_escape(version_label)}</dt><dd>{_html_escape(entry.app_version)}</dd></div>",
            "</dl>",
        ])
        if entry.note:
            parts.append(f'<p class="report-note">{_html_escape(entry.note)}</p>')
        for component in entry.components:
            check_cancel()
            parts.extend([
                '<section class="report-component">',
                f"<h3>{_html_escape(component.label)}</h3>",
            ])
            summary = component.overview_summary
            if summary is not None:
                parts.append('<div class="overview-summary">')
                for heading, facts in ((None, summary.facts), (summary.types_heading, summary.column_types)):
                    if heading is not None:
                        parts.append(f"<h4>{_html_escape(heading)}</h4>")
                    parts.append('<dl class="overview-facts">')
                    parts.extend(
                        f"<div><dt>{_html_escape(label)}</dt><dd><strong>{_html_escape(value)}</strong></dd></div>"
                        for label, value in facts
                    )
                    parts.append("</dl>")
                parts.append(f"<h4>{_html_escape(summary.issues_heading)}</h4>")
                parts.extend(f'<p class="overview-issue">{_html_escape(issue)}</p>' for issue in summary.issues)
                parts.append("</div>")
            for table in component.tables:
                parts.append('<div class="table-scroll">')
                caption_class = ' class="visually-hidden"' if _same_heading(table.title, component.label) else ""
                parts.append(f"<table><caption{caption_class}>{_html_escape(table.title)}</caption><thead><tr>")
                parts.extend(f'<th scope="col">{_html_escape(header)}</th>' for header in table.headers)
                parts.append("</tr></thead><tbody>")
                for row in table.rows:
                    check_cancel()
                    parts.append("<tr>")
                    for value in row:
                        cell = _format_cell(value, document.missing_value_label, number_format, count_format)
                        parts.append(f"<td>{_html_escape(cell)}</td>")
                    parts.append("</tr>")
                parts.append("</tbody></table></div>")
            for chart in component.charts:
                check_cancel()
                encoded = b64encode(chart.image_data).decode("ascii")
                alt = chart.heading
                heading_class = ' class="visually-hidden"' if _same_heading(chart.heading, component.label) else ""
                parts.extend([
                    '<figure class="report-chart">',
                    (
                        f'<img src="data:image/png;base64,{encoded}" alt="{_html_escape(alt)}" '
                        f'width="{chart.width_px}" height="{chart.height_px}">'
                    ),
                    f"<figcaption><strong{heading_class}>{_html_escape(chart.heading)}</strong>",
                ])
                parts.extend(f"<p>{_html_escape(caption)}</p>" for caption in chart.captions)
                parts.extend(["</figcaption>", "</figure>"])
            parts.append("</section>")
            completed_components += 1
            report_progress()
        parts.extend(["</article>"])
    check_cancel()
    if (progress_cb is not None and completed_components < total_components) or (
        progress_cb is not None and total_components == 0
    ):
        progress_cb(_PROGRESS_COMPLETE)
    parts.extend(["</main>", "</body>", "</html>"])
    return "\n".join(parts)


def _same_heading(title: str, component_label: str) -> bool:
    """Compare plain-text titles without insignificant whitespace or case."""
    return " ".join(title.split()).casefold() == " ".join(component_label.split()).casefold()


def _format_cell(
    value: object,
    missing_value_label: str,
    number_format: Callable[[float], str],
    count_format: Callable[[int], str],
) -> str:
    """Format a scalar export value while keeping missingness explicit."""
    if isinstance(value, bool):
        return str(value)
    if value is None or value is pd.NA or value is pd.NaT:
        return missing_value_label
    if isinstance(value, numbers.Integral):
        return count_format(int(value))
    if isinstance(value, numbers.Real):
        numeric_value = float(value)
        if math.isnan(numeric_value):
            return missing_value_label
        return number_format(numeric_value)
    if isinstance(value, datetime | date):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, np.datetime64 | np.timedelta64) and np.isnat(value):
        return missing_value_label
    return str(value)


def _html_escape(value: object) -> str:
    """Escape one plain-text value for safe HTML text or attribute use."""
    return escape(str(value), quote=True)


_REPORT_CSS = """
:root { color-scheme: light; font-family: system-ui, sans-serif; color: #202938; background: #f3f5f8; }
* { box-sizing: border-box; }
.visually-hidden {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0;
}
body { margin: 0; line-height: 1.5; }
.report { max-width: 1100px; margin: 0 auto; padding: 2rem; background: #fff; }
.report-header { border-bottom: 2px solid #d9e0e8; margin-bottom: 2rem; padding-bottom: 1rem; }
h1, h2, h3 { line-height: 1.2; }
h1 { margin-top: 0; }
h2 { border-bottom: 1px solid #d9e0e8; padding-bottom: .4rem; }
.report-description, .report-note { white-space: pre-wrap; }
.report-note { border-left: 4px solid #627d98; margin: 1rem 0; padding: .6rem 1rem; background: #f4f7fa; }
.metadata { display: flex; flex-wrap: wrap; gap: .5rem 1.5rem; margin: .75rem 0 1.25rem; }
.metadata div { display: flex; gap: .4rem; }
.metadata dt { font-weight: 700; }
.metadata dd { margin: 0; }
.report-component { margin: 1.5rem 0; break-inside: avoid; }
.overview-summary h4 { margin: 1rem 0 .4rem; }
.overview-facts { margin: .5rem 0; display: flex; flex-wrap: wrap; gap: .4rem 1.5rem; }
.overview-facts div { display: flex; gap: .4rem; }
.overview-facts dt::after { content: ":"; }
.overview-facts dd { margin: 0; }
.overview-issue { margin: .4rem 0; overflow-wrap: anywhere; }
.table-scroll { overflow-x: auto; margin: .75rem 0 1.25rem; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
caption { text-align: left; font-weight: 700; padding: .5rem 0; }
th, td { border: 1px solid #ccd5df; padding: .4rem .55rem; text-align: left; vertical-align: top; }
td { white-space: pre-wrap; }
th { background: #edf2f7; }
tbody tr:nth-child(even) { background: #f8fafc; }
.report-chart { margin: 1rem auto 1.5rem; text-align: center; break-inside: avoid; }
.report-chart img { display: block; height: auto; max-width: 100%; margin: 0 auto; }
.report-chart figcaption { margin-top: .5rem; }
.report-chart figcaption p { margin: .25rem 0; white-space: pre-wrap; }
@media (max-width: 650px) { .report { padding: 1rem; } .metadata { display: grid; gap: .3rem; } }
@media print {
  :root { background: #fff; color: #000; }
  .report { max-width: none; padding: 0; }
  .table-scroll { overflow: visible; }
  table { font-size: 9pt; }
  th, td { padding: .25rem .35rem; }
  .analysis-entry, .report-component, .report-chart { break-inside: avoid; }
}
"""
