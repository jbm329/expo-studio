"""Controller for the Advanced Analysis workspace dialog."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QT_TR_NOOP, QT_TRANSLATE_NOOP, QTimer
from PyQt6.QtWidgets import QMessageBox

from expo_jbm329.gui.dialogs.analysis.analysis_dialog import AnalysisDialog, build_placeholder_label
from expo_jbm329.gui.dialogs.analysis.chi_square_view import ChiSquareView
from expo_jbm329.gui.dialogs.analysis.clustering_config import ClusteringConfigWidget
from expo_jbm329.gui.dialogs.analysis.clustering_view import ClusteringView
from expo_jbm329.gui.dialogs.analysis.correlation_config import CorrelationConfigWidget
from expo_jbm329.gui.dialogs.analysis.correlation_view import CorrelationView
from expo_jbm329.gui.dialogs.analysis.group_comparison_view import GroupComparisonView
from expo_jbm329.gui.dialogs.analysis.hypothesis_tests_config import HypothesisTestsConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_config import OutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_config import MultivariateOutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_view import MultivariateOutliersView
from expo_jbm329.gui.dialogs.analysis.outliers_view import OutliersView
from expo_jbm329.gui.dialogs.analysis.overview_view import OverviewView
from expo_jbm329.gui.dialogs.analysis.paired_comparison_view import PairedComparisonView
from expo_jbm329.gui.dialogs.analysis.pca_config import PCAConfigWidget
from expo_jbm329.gui.dialogs.analysis.pca_view import PCAView
from expo_jbm329.gui.dialogs.analysis.regression_config import RegressionConfigWidget
from expo_jbm329.gui.dialogs.analysis.regression_glm_view import GeneralizedRegressionView
from expo_jbm329.gui.dialogs.analysis.regression_view import RegressionView
from expo_jbm329.gui.dialogs.analysis.statistics_view import StatisticsView
from expo_jbm329.gui.dialogs.analysis.survival_view import SurvivalRegressionView
from expo_jbm329.gui.dialogs.analysis.timeseries_config import TimeSeriesConfigWidget
from expo_jbm329.gui.dialogs.analysis.timeseries_view import TimeSeriesView
from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.chi_square import analyze_chi_square, initialize_chi_square
from expo_jbm329.services.analysis.clustering import MIN_SELECTED_COLUMNS as CLUSTERING_MIN_SELECTED_COLUMNS
from expo_jbm329.services.analysis.clustering import ClusteringMethod, analyze_clustering, initialize_clustering
from expo_jbm329.services.analysis.clustering_charts import render_clustering_charts
from expo_jbm329.services.analysis.clustering_export import (
    ClusteringExportComponent,
    ClusteringExportRequest,
    ClusteringExportSnapshot,
)
from expo_jbm329.services.analysis.correlation import (
    MAX_SELECTED_COLUMNS,
    MIN_SELECTED_COLUMNS,
    CorrelationMethod,
    analyze_correlation_matrix,
    analyze_correlation_pair,
    default_pair,
    initialize_correlation,
)
from expo_jbm329.services.analysis.correlation_charts import build_correlation_chart_labels, render_correlation_charts
from expo_jbm329.services.analysis.correlation_export import (
    CorrelationExportComponent,
    CorrelationExportRequest,
    CorrelationExportSnapshot,
)
from expo_jbm329.services.analysis.group_comparison import analyze_group_comparison, initialize_group_comparison
from expo_jbm329.services.analysis.hypothesis_charts import (
    build_hypothesis_chart_presentation,
    render_hypothesis_charts,
)
from expo_jbm329.services.analysis.hypothesis_export import (
    HypothesisExportComponent,
    HypothesisExportRequest,
    HypothesisExportSnapshot,
    HypothesisResult,
)
from expo_jbm329.services.analysis.multivariate_outliers import (
    MultivariateOutlierMethod,
    analyze_multivariate_outliers,
    initialize_multivariate_outliers,
)
from expo_jbm329.services.analysis.outliers import (
    OutlierMethod,
    analyze_outlier_column,
    analyze_outlier_summary,
    default_column,
    initialize_outlier_summary,
)
from expo_jbm329.services.analysis.outliers_charts import (
    render_multivariate_outlier_charts,
    render_univariate_outlier_charts,
)
from expo_jbm329.services.analysis.outliers_export import (
    MultivariateOutlierExportSnapshot,
    OutlierExportComponent,
    OutlierExportRequest,
    OutlierExportSnapshot,
    UnivariateOutlierExportSnapshot,
)
from expo_jbm329.services.analysis.overview import (
    DatasetOverviewResult,
    OverviewExportFormat,
    OverviewExportRequest,
    analyze_dataset_overview,
)
from expo_jbm329.services.analysis.paired_comparison import (
    PairedComparisonResult,
    analyze_paired_comparison,
    initialize_paired_comparison,
)
from expo_jbm329.services.analysis.pca import MIN_SELECTED_COLUMNS as PCA_MIN_SELECTED_COLUMNS
from expo_jbm329.services.analysis.pca import analyze_pca, initialize_pca
from expo_jbm329.services.analysis.pca_charts import render_pca_charts
from expo_jbm329.services.analysis.pca_export import (
    PCAExportComponent,
    PCAExportRequest,
    PCAExportSnapshot,
)
from expo_jbm329.services.analysis.presentation import (
    PresentationLabel,
    build_analysis_presentation,
    clustering_component_label,
    hypothesis_component_label,
    outlier_component_label,
    pca_component_label,
    regression_component_label,
    statistics_component_label,
    time_series_component_label,
    translate_presentation_label,
)
from expo_jbm329.services.analysis.regression import RegressionError, analyze_regression, initialize_regression
from expo_jbm329.services.analysis.regression_charts import render_regression_charts
from expo_jbm329.services.analysis.regression_export import (
    RegressionExportComponent,
    RegressionExportRequest,
    RegressionExportSnapshot,
)
from expo_jbm329.services.analysis.regression_glm import (
    GeneralizedRegressionResult,
    GeneralizedTargetColumns,
    RegressionModel,
    analyze_generalized_regression,
    initialize_generalized_targets,
)
from expo_jbm329.services.analysis.report import (
    ReportDocument,
    capture_report_labels,
    localized_report_tables,
    render_report_html,
)
from expo_jbm329.services.analysis.statistics import (
    DescriptiveStatisticsResult,
    StatisticsExportFormat,
    StatisticsExportRequest,
    StatisticsExportTable,
    analyze_descriptive_statistics,
)
from expo_jbm329.services.analysis.statistics_charts import (
    build_statistics_chart_presentations,
    render_statistics_charts,
)
from expo_jbm329.services.analysis.survival import (
    SurvivalColumns,
    SurvivalResult,
    analyze_cox_regression,
    initialize_survival_columns,
)
from expo_jbm329.services.analysis.timeseries import analyze_time_series, initialize_time_series
from expo_jbm329.services.analysis.timeseries_charts import render_time_series_charts
from expo_jbm329.services.analysis.timeseries_export import (
    TimeSeriesAppliedConfiguration,
    TimeSeriesExportComponent,
    TimeSeriesExportRequest,
    TimeSeriesExportSnapshot,
)
from expo_jbm329.services.excel_chart import ExcelChartCancelledError
from expo_jbm329.utils.format_utils import capture_chart_numeric_locale, fmt_int, fmt_num
from expo_jbm329.utils.i18n_utils import tr as translate

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd
    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.services.analysis.chi_square import ChiSquareResult
    from expo_jbm329.services.analysis.clustering import ClusteringResult
    from expo_jbm329.services.analysis.correlation import CorrelationMatrixResult, CorrelationPairDetail
    from expo_jbm329.services.analysis.group_comparison import GroupComparisonResult
    from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierResult
    from expo_jbm329.services.analysis.outliers import OutlierColumnDetail, OutlierSummaryResult
    from expo_jbm329.services.analysis.pca import PCAResult
    from expo_jbm329.services.analysis.regression import RegressionResult
    from expo_jbm329.services.analysis.timeseries import TimeSeriesResult
    from expo_jbm329.services.excel_chart import ExcelChartImage
    from expo_jbm329.utils.dataset_ref import DatasetRef
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )
    from expo_jbm329.workbench.controllers.export_controller import ExportController
    from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import (
        ResultTabManager,
    )


# Matches AsyncOperationController's default overlay watchdog.
_DEFAULT_TIMEOUT_MS = 60_000
_HYPOTHESIS_EXPORT_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Test results"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Test statistic"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "p-value"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Degrees of freedom"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Mean difference"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "95% CI lower"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "95% CI upper"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Effect size"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Effect value"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Numeric column"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Grouping column"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Row column"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Column column"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Sample count"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Yates' continuity correction"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Cochran's rule violated"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Fraction of expected counts below 5"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Minimum expected count"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Odds ratio"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Total subjects"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Excluded subjects"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Notes"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Measurement"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Welch's t-test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Student's t-test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Mann-Whitney U"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "One-way ANOVA"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Kruskal-Wallis"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Pearson's chi-square test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Fisher's exact test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Wilcoxon signed-rank test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Friedman test"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Cohen's d"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Rank-biserial correlation"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Eta²"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Epsilon²"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Cramér's V"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Kendall's W"),
    QT_TRANSLATE_NOOP("ChiSquareView", "Contingency table"),
)
_HYPOTHESIS_PRESENTATION_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Hypothesis Tests"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "{category} — {method}"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Group comparison"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Categorical association"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Paired comparison"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Wilcoxon signed-rank test"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Friedman test"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Numeric variable:"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Grouping variable:"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Row variable:"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Column variable:"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Measurement variables (selected order):"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Tests computed:"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Tests available:"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Welch's t-test"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Student's t-test"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Mann-Whitney U"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "One-way ANOVA"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Kruskal-Wallis"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Pearson's chi-square test"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Fisher's exact test"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Group summary"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Contingency table"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Measurement summary"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Test results"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Group distributions"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Association plots"),
    QT_TRANSLATE_NOOP("HypothesisPresentation", "Paired measurement plots"),
)
_SHARED_PRESENTATION_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("AnalysisConfiguration", "Features"),
    QT_TRANSLATE_NOOP("AnalysisConfiguration", "Standardize features"),
    QT_TRANSLATE_NOOP("ClusteringPresentation", "Clustering"),
    QT_TRANSLATE_NOOP("ClusteringPresentation", "{category} — {method}"),
    QT_TRANSLATE_NOOP("ClusteringPresentation", "K-Means"),
    QT_TRANSLATE_NOOP("ClusteringPresentation", "DBSCAN"),
    QT_TRANSLATE_NOOP("ClusteringPresentation", "Agglomerative"),
    QT_TRANSLATE_NOOP("ClusteringPresentation", "Cluster sizes"),
    QT_TRANSLATE_NOOP("ClusteringPresentation", "Model summary"),
    QT_TRANSLATE_NOOP("ClusteringPresentation", "Cluster projection"),
    QT_TRANSLATE_NOOP("ClusteringPresentation", "Cluster projection (internal PCA)"),
    QT_TRANSLATE_NOOP("ClusteringPresentation", "Number of clusters:"),
    QT_TRANSLATE_NOOP("ClusteringPresentation", "Neighborhood radius (eps):"),
    QT_TRANSLATE_NOOP("ClusteringPresentation", "Minimum samples:"),
    QT_TRANSLATE_NOOP("CorrelationView", "Correlation"),
    QT_TRANSLATE_NOOP("CorrelationView", "{category} — {method}"),
    QT_TRANSLATE_NOOP("CorrelationView", "Columns:"),
    QT_TRANSLATE_NOOP("CorrelationView", "Strongest correlations"),
    QT_TRANSLATE_NOOP("CorrelationView", "Correlation plots"),
    QT_TRANSLATE_NOOP("CorrelationView", "Correlation matrix"),
    QT_TRANSLATE_NOOP("CorrelationView", "Scatterplots"),
    QT_TRANSLATE_NOOP("CorrelationView", "Pearson"),
    QT_TRANSLATE_NOOP("CorrelationView", "Spearman"),
    QT_TRANSLATE_NOOP("CorrelationView", "Kendall's tau-b"),
    QT_TRANSLATE_NOOP("CorrelationView", "{x} vs {y}"),
    QT_TRANSLATE_NOOP(
        "CorrelationView",
        "The line is a linear fit shown for reference. {method} measures monotonic, "
        "not necessarily linear, association.",
    ),
    QT_TRANSLATE_NOOP(
        "CorrelationView", "Showing a random sample of {shown} of {total} points. Statistics use all points."
    ),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Regression"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "{category} — {model}"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Linear regression"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Logistic regression"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Poisson regression"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Negative binomial regression"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Cox proportional-hazards regression"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Outcome:"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Duration:"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Event:"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Predictors:"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Modeled terms:"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Reference levels:"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Coefficients"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Model summary"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Linear diagnostics"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Logistic diagnostics"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Count-model diagnostics"),
    QT_TRANSLATE_NOOP("RegressionPresentation", "Survival charts"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Outliers"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "{category} — {method}"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "IQR (Tukey's fences)"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Z-score"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Modified Z-score"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Isolation Forest"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Local Outlier Factor"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Threshold:"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "IQR multiplier:"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Score threshold:"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Screened columns:"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Selected detail column:"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "None"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Features:"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Standardization:"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Standardized"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Not standardized"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Expected outlier fraction:"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "LOF neighbors:"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Column summary"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Model summary"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Potential outliers"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Column distribution"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Column distributions"),
    QT_TRANSLATE_NOOP("OutliersPresentation", "Outlier projection"),
    QT_TRANSLATE_NOOP("PCAPresentation", "PCA"),
    QT_TRANSLATE_NOOP("PCAPresentation", "Feature loadings"),
    QT_TRANSLATE_NOOP("PCAPresentation", "Explained variance"),
    QT_TRANSLATE_NOOP("PCAPresentation", "Model summary"),
    QT_TRANSLATE_NOOP("PCAPresentation", "PCA plots"),
    QT_TRANSLATE_NOOP("PCAPresentation", "Features:"),
    QT_TRANSLATE_NOOP("PCAPresentation", "Standardization:"),
    QT_TRANSLATE_NOOP("PCAPresentation", "Standardized"),
    QT_TRANSLATE_NOOP("PCAPresentation", "Not standardized"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Time column:"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Value column:"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Resampling:"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Seasonal period:"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Decomposition model:"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Auto-detect seasonal period"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Original frequency"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Automatic"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Automatic (no period detected)"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Automatic (detected: {period})"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Daily"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Weekly"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Monthly"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Quarterly"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Yearly"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Additive"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Multiplicative"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Series"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Autocorrelation"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Model summary"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Charts"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Seasonal decomposition"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Observed"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Trend"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Seasonal"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Residual"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Lag"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Value"),
    QT_TRANSLATE_NOOP("TimeSeriesPresentation", "Timestamp"),
)
_REPORT_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("AnalysisDialog", "Overview"),
    QT_TRANSLATE_NOOP("AnalysisDialog", "Statistics"),
    QT_TRANSLATE_NOOP("AnalysisDialog", "Hypothesis Tests"),
    QT_TRANSLATE_NOOP("AnalysisDialog", "Regression"),
    QT_TRANSLATE_NOOP("AnalysisDialog", "Outliers"),
    QT_TRANSLATE_NOOP("AnalysisDialog", "Clustering"),
    QT_TRANSLATE_NOOP("AnalysisDialog", "PCA"),
    QT_TRANSLATE_NOOP("OverviewView", "Count"),
    QT_TRANSLATE_NOOP("OverviewView", "Fraction"),
    QT_TRANSLATE_NOOP("OverviewView", "Metric"),
    QT_TRANSLATE_NOOP("OverviewView", "Missing fraction"),
    QT_TRANSLATE_NOOP("OverviewView", "Section"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Autocorrelation"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Charts"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Cluster sizes"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Coefficients"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Column details"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Column summary"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Columns"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Contingency table"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Explained variance"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Feature loadings"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Group summary"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Measurement summary"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Model metrics"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Model summary"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Series"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Total"),
    QT_TRANSLATE_NOOP("StatisticsView", "Histogram"),
    QT_TRANSLATE_NOOP("StatisticsView", "Boxplot"),
    QT_TRANSLATE_NOOP("StatisticsView", "No data"),
    QT_TRANSLATE_NOOP("ChiSquareView", "Column"),
    QT_TRANSLATE_NOOP("ChiSquareView", "Group"),
    QT_TRANSLATE_NOOP("ChiSquareView", "Row"),
    QT_TRANSLATE_NOOP("GroupComparisonView", "Group summary"),
    QT_TRANSLATE_NOOP("PairedComparisonView", "Measurement summary"),
)
_CORRELATION_EXPORT_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Least-squares line: y = ({slope}) x + ({intercept})"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Correlation method"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Coefficient"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Significant after Holm"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Ranking and Holm explanation"),
    QT_TRANSLATE_NOOP(
        "AnalysisExportDialog",
        "Pairs are ranked by absolute coefficient. Significance is based on "
        "p < {alpha} after Holm adjustment for {count} tests.",
    ),
)
_REGRESSION_EXPORT_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Rate ratio"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Hazard ratio"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "{name}, 95% CI lower"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "{name}, 95% CI upper"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Term"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Estimate"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Std. error"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "t statistic"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "z statistic"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "VIF"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Significant at p < {alpha}"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "(Intercept)"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Metric"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Value"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Rows used"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Rows dropped because of missing values"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "R²"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Adjusted R²"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "F statistic"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "F-test p-value"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Model degrees of freedom"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Residual degrees of freedom"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "RMSE"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "AIC"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Breusch-Pagan LM"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Breusch-Pagan p-value"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Jarque-Bera JB"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Jarque-Bera p-value"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Durbin-Watson"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Largest VIF"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Log-likelihood"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Null-model log-likelihood"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "McFadden pseudo R²"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "AUC (in-sample)"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Pearson dispersion"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "NB2 alpha"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Events"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Censored"),
)
_OUTLIERS_EXPORT_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Threshold"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Values"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Missing"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Potential outliers"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Potential outlier share"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Low potential outliers"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "High potential outliers"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Lower fence"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Upper fence"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Q1"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Q3"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "IQR"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Mean"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Standard deviation"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Median"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "MAD"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Features"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Expected outlier fraction"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "LOF neighbors"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Total rows"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Rows dropped because of missing or infinite values"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Inliers"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Status"),
)
_CLUSTERING_EXPORT_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Number of clusters"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Neighborhood radius (eps)"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Minimum samples"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Clusters found"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Noise rows"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Silhouette score"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Cluster"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Rows"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Share"),
)
_PCA_EXPORT_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Feature"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Component"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Variance"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Cumulative share"),
)
_TIME_SERIES_EXPORT_TRANSLATIONS = (
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Source rows"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Invalid rows dropped"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Duplicate rows averaged"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Time points"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Seasonal period"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Timestamp"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Trend"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Seasonal"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Residual"),
    QT_TRANSLATE_NOOP("AnalysisExportDialog", "Lag"),
)
# Cancelable jobs report real progress and can be stopped by the user, so
# they get a far longer watchdog before the "taking too long" warning.
_CANCELABLE_TIMEOUT_MS = 600_000


@dataclass(frozen=True, slots=True)
class _JobCallbacks:
    """Cooperative progress/cancellation hooks injected into a background job.

    Attributes:
        progress_cb: Receives the completed percentage (0-100), or `None`.
        cancel_cb: Returns True once the user has asked to cancel, or `None`.
    """

    progress_cb: Callable[[int], None] | None = None
    cancel_cb: Callable[[], bool] | None = None


def _ignore_callbacks(compute: Callable[[pd.DataFrame], object]) -> Callable[[pd.DataFrame, _JobCallbacks], object]:
    """Adapt a computation that neither reports progress nor supports cancellation."""

    def _compute(df: pd.DataFrame, _callbacks: _JobCallbacks) -> object:
        return compute(df)

    return _compute


@dataclass(frozen=True, slots=True)
class _CategoryHandler:
    """Pairs a category's background computation with its GUI rendering.

    Kept as two separate callables because Qt widgets must only ever be
    created on the GUI thread, while `compute` runs on a background pool
    thread via JobManager/AsyncOperationController.

    Attributes:
        compute: Background-safe callable turning a DataFrame (plus the
            job's progress/cancellation hooks) into a plain (non-Qt) result
            object, or `None` if it was cancelled.
        render: GUI-thread callable turning that result object (plus the
            active dialog, so config widgets needing to trigger their own
            recompute - see `AnalysisController._recompute_content` - can
            be wired up here) into ``(content_widget, config_widget)`` -
            the widgets to display in the dialog's result pane and
            configuration pane, respectively. `config_widget` is `None`
            for categories with no configurable input (the configuration
            pane is then hidden).
        cancelable: Whether `compute` reports progress and honors
            cancellation - the busy overlay then shows a progress bar and
            a Cancel button.
        initialize: Optional GUI-thread-cheap callable turning a DataFrame
            into a metadata-only result (column lists and defaults, no
            model fitting). When set, opening the category renders this
            result synchronously - no background job or busy overlay -
            and `compute` is not run; computation then starts only when
            the user applies a configuration.
    """

    compute: Callable[[pd.DataFrame, _JobCallbacks], object]
    render: Callable[[object, AnalysisDialog], tuple[QWidget, QWidget | None]]
    cancelable: bool = False
    initialize: Callable[[pd.DataFrame], object] | None = None


@dataclass(frozen=True, slots=True)
class _HypothesisTestsDefaults:
    """Every hypothesis test's default configuration, without any test computed.

    The Hypothesis Tests category's initial result, so each test's column
    pickers in `HypothesisTestsConfigWidget` can be populated up front.
    """

    group_comparison: GroupComparisonResult
    chi_square: ChiSquareResult
    paired_comparison: PairedComparisonResult


@dataclass(frozen=True, slots=True)
class _RegressionDefaults:
    """Regression defaults and eligible outcome metadata for all model families."""

    linear: RegressionResult
    generalized_targets: GeneralizedTargetColumns
    survival_columns: SurvivalColumns


@dataclass(frozen=True, slots=True)
class _CorrelationOutcome:
    """A correlation matrix plus the detail of its selected pair.

    Attributes:
        matrix: The computed correlation matrix.
        pair_detail: The selected pair's detail, or `None` when the matrix
            has an error (and so no pair to show).
        export_snapshot: Owned selected numeric columns for the successful matrix.
    """

    matrix: CorrelationMatrixResult
    pair_detail: CorrelationPairDetail | None
    export_snapshot: CorrelationExportSnapshot | None = None


@dataclass(frozen=True, slots=True)
class _OutliersOutcome:
    """An outlier summary plus the detail of its selected column.

    Attributes:
        summary: The per-column outlier summary.
        detail: The selected column's detail, or `None` when the summary
            has an error (and so no column to show).
        data: Owned copy of the screened numeric columns for chart
            export, or `None` when the summary has an error.
    """

    summary: OutlierSummaryResult
    detail: OutlierColumnDetail | None
    data: pd.DataFrame | None = None


class AnalysisController:
    """Controller responsible for the Advanced Analysis workspace workflow.

    Each analysis category is backed by a `_CategoryHandler`. Automatic
    categories (Overview, Statistics) compute as soon as they are opened;
    computation always runs as a background job (JobManager, via
    AsyncOperationController) with a busy overlay shown over the dialog's
    result pane, so large datasets never freeze the GUI thread.
    Apply-first categories only build their configuration when opened and
    compute once the user applies it. Categories without a registered
    handler fall back to the not-implemented placeholder.
    """

    TR_NOT_IMPLEMENTED = QT_TR_NOOP("This analysis is not implemented yet.")
    TR_ANALYSIS_ERROR = QT_TR_NOOP("An error occurred while generating this analysis.")
    TR_RUNNING_ANALYSIS = QT_TR_NOOP("Running analysis…")
    TR_ANALYSIS_OPERATION = QT_TR_NOOP("generate analysis")
    TR_ANALYSIS_CANCELLED = QT_TR_NOOP("Analysis cancelled.")
    TR_APPLY_PROMPT = QT_TR_NOOP("Choose settings and click Apply.")
    TR_REPORT_PREPARING = QT_TR_NOOP("Preparing report preview...")
    TR_REPORT_OPERATION = QT_TR_NOOP("prepare report preview")
    TR_REPORT_CANCELLED = QT_TR_NOOP("Report preview cancelled.")
    TR_REPORT_ERROR = QT_TR_NOOP("Could not prepare report preview.\n{error}")
    TR_REPORT_SAVE_UNAVAILABLE = QT_TR_NOOP("HTML report saving is unavailable.")
    TR_REPORT_SAVE_ERROR = QT_TR_NOOP("Could not save HTML report.\n{error}")
    TR_READY_DATASET_REQUIRED = QT_TR_NOOP("Select a ready dataset before opening Advanced Analysis.")
    TR_ANALYSIS_UNAVAILABLE = QT_TR_NOOP("Advanced analysis unavailable")

    @staticmethod
    def _tr(text: str) -> str:
        """Translate a UI string for this controller."""
        return translate("AnalysisController", text)

    def __init__(
        self,
        *,
        results: ResultTabManager,
        async_ops: AsyncOperationController,
        export_controller: ExportController | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the analysis controller.

        Args:
            results: ResultTabManager instance.
            async_ops: Controller running analyses as background jobs.
            export_controller: Shared exporter receiving per-call analysis dialog context.
            logger: Optional logger instance.
        """
        self._results = results
        self._async_ops = async_ops
        self._export_controller = export_controller
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

        self._category_handlers: dict[AnalysisCategory, _CategoryHandler] = {
            AnalysisCategory.OVERVIEW: _CategoryHandler(
                compute=_ignore_callbacks(analyze_dataset_overview),
                render=self._render_overview,
            ),
            AnalysisCategory.STATISTICS: _CategoryHandler(
                compute=_ignore_callbacks(analyze_descriptive_statistics),
                render=self._render_statistics,
            ),
            AnalysisCategory.HYPOTHESIS_TESTS: _CategoryHandler(
                compute=_ignore_callbacks(self._initialize_hypothesis_tests),
                render=self._render_hypothesis_tests,
                initialize=self._initialize_hypothesis_tests,
            ),
            AnalysisCategory.CORRELATION: _CategoryHandler(
                compute=self._compute_correlation,
                render=self._render_correlation,
                cancelable=True,
                initialize=initialize_correlation,
            ),
            AnalysisCategory.REGRESSION: _CategoryHandler(
                compute=_ignore_callbacks(analyze_regression),
                render=self._render_regression,
                initialize=self._initialize_regression,
            ),
            AnalysisCategory.OUTLIERS: _CategoryHandler(
                compute=_ignore_callbacks(self._compute_outliers),
                render=self._render_outliers,
                initialize=initialize_outlier_summary,
            ),
            AnalysisCategory.CLUSTERING: _CategoryHandler(
                compute=_ignore_callbacks(analyze_clustering),
                render=self._render_clustering,
                initialize=initialize_clustering,
            ),
            AnalysisCategory.PCA: _CategoryHandler(
                compute=_ignore_callbacks(analyze_pca),
                render=self._render_pca,
                initialize=initialize_pca,
            ),
            AnalysisCategory.TIME_SERIES: _CategoryHandler(
                compute=_ignore_callbacks(analyze_time_series),
                render=self._render_time_series,
                initialize=initialize_time_series,
            ),
        }

    def open_dialog(self, parent: QWidget) -> None:
        """Open the Advanced Analysis dialog.

        Args:
            parent: Parent widget for the dialog.
        """
        active_tab_id = self._results.active_tab_id()
        source_dataset: DatasetRef | None = next(
            (dataset for dataset in self._results.list_ready_datasets() if dataset.tab_id == active_tab_id),
            None,
        )
        if source_dataset is None:
            self._logger.warning("Advanced Analysis was requested without a ready active dataset.")
            QMessageBox.warning(
                parent,
                self._tr(self.TR_ANALYSIS_UNAVAILABLE),
                self._tr(self.TR_READY_DATASET_REQUIRED),
            )
            return

        dialog = AnalysisDialog(
            parent=parent,
            source_dataset=source_dataset,
        )
        self._connect_report_preview(dialog)
        if self._export_controller is not None:
            exporter = self._export_controller

            def _handle_export(request: object) -> None:
                self._export_overview(dialog, exporter, request)

            def _handle_statistics_export(request: object) -> None:
                self._export_statistics(dialog, exporter, request)

            def _handle_hypothesis_export(request: object) -> None:
                self._export_hypothesis(dialog, exporter, request)

            def _handle_correlation_export(request: object) -> None:
                self._export_correlation(dialog, exporter, request)

            def _handle_regression_export(request: object) -> None:
                self._export_regression(dialog, exporter, request)

            def _handle_outliers_export(request: object) -> None:
                self._export_outliers(dialog, exporter, request)

            dialog.overview_export_requested.connect(_handle_export)
            dialog.statistics_export_requested.connect(_handle_statistics_export)
            dialog.hypothesis_export_requested.connect(_handle_hypothesis_export)
            dialog.correlation_export_requested.connect(_handle_correlation_export)
            dialog.regression_export_requested.connect(_handle_regression_export)

            def _handle_clustering_export(request: object) -> None:
                self._export_clustering(dialog, exporter, request)

            dialog.outliers_export_requested.connect(_handle_outliers_export)
            dialog.clustering_export_requested.connect(_handle_clustering_export)

            def _handle_pca_export(request: object) -> None:
                self._export_pca(dialog, exporter, request)

            dialog.pca_export_requested.connect(_handle_pca_export)

            def _handle_time_series_export(request: object) -> None:
                self._export_time_series(dialog, exporter, request)

            dialog.time_series_export_requested.connect(_handle_time_series_export)

        refresh_started = False

        def _refresh_after_interaction() -> None:
            nonlocal refresh_started
            refresh_started = True
            self._refresh_content(dialog)

        def _handle_category_changed(_category_value: str) -> None:
            _refresh_after_interaction()

        dialog.category_changed.connect(_handle_category_changed)

        # Overview is already selected by the time the dialog is constructed
        # (see AnalysisDialog), but that self-emission happens before the
        # connections above exist. Deferred by one event-loop tick so the
        # dialog is already shown (and correctly sized) once the initial
        # busy overlay is created - showing an overlay on a not-yet-shown
        # widget would compute its geometry against a stale/default size.
        def _refresh_initial_content() -> None:
            if not refresh_started:
                self._refresh_content(dialog)

        QTimer.singleShot(0, _refresh_initial_content)

        dialog.exec()

    def _connect_report_preview(self, dialog: AnalysisDialog) -> None:
        """Share report snapshots and lifecycle guards between preview and HTML saving."""
        generation = 0
        closed = False
        busy = False

        def mark_closed(*_: object) -> None:
            nonlocal closed
            closed = True

        dialog.finished.connect(mark_closed)
        dialog.destroyed.connect(mark_closed)

        def prepare(request: object, *, save: bool = False) -> None:
            nonlocal generation, busy
            if closed or busy:
                return
            if not isinstance(request, ReportDocument) or not request.entries:
                self._logger.warning("Rejected empty or invalid report preview request.")
                return
            exporter = self._export_controller
            if save and exporter is None:
                self._logger.error("Cannot save an analysis report without an export controller.")
                dialog.report_page().set_preview_status(self._tr(self.TR_REPORT_SAVE_UNAVAILABLE))
                return
            generation += 1
            revision = generation
            busy = True
            page = dialog.report_page()
            page.set_preview_status("")
            page.set_preview_busy(True)
            labels = capture_report_labels(translate, fmt_num, fmt_int)

            def stale() -> bool:
                return closed or generation != revision

            def render(
                *,
                progress_cb: Callable[[int], None] | None = None,
                cancel_cb: Callable[[], bool] | None = None,
                **_: object,
            ) -> str:
                def cancelled() -> bool:
                    return closed or (cancel_cb is not None and cancel_cb())

                return render_report_html(
                    request,
                    labels=labels,
                    progress_cb=progress_cb,
                    cancel_cb=cancelled,
                )

            def work(
                *,
                progress_cb: Callable[[int], None] | None = None,
                cancel_cb: Callable[[], bool] | None = None,
                **_: object,
            ) -> str | None:
                try:
                    return render(progress_cb=progress_cb, cancel_cb=cancel_cb)
                except ExcelChartCancelledError:
                    self._logger.info("Report preview preparation cancelled.")
                    return None

            def on_result(html: str | None) -> None:
                if stale():
                    return
                if html is None:
                    page.set_preview_status(self._tr(self.TR_REPORT_CANCELLED))
                else:
                    self._show_report_preview(dialog, html)

            def on_error(error: str) -> None:
                if not stale():
                    message = self.TR_REPORT_SAVE_ERROR if save else self.TR_REPORT_ERROR
                    page.set_preview_status(self._tr(message).format(error=error))

            def on_finished() -> None:
                nonlocal busy
                if not stale():
                    busy = False
                    page.set_preview_busy(False)

            try:
                if save and exporter is not None:
                    started = exporter.export_html_report(
                        html_factory=render,
                        suggested_name=request.title,
                        parent_widget=dialog,
                        operation_target=page,
                        stale_check=stale,
                        on_finished=on_finished,
                    )
                    if not started:
                        on_finished()
                    return
                self._async_ops.run_target_overlay_operation(
                    target=page,
                    runner="pool",
                    work=work,
                    on_result=on_result,
                    on_error=on_error,
                    on_finished=on_finished,
                    busy_message=self._tr(self.TR_REPORT_PREPARING),
                    scope=f"analysis:report-preview:{id(dialog)}",
                    operation_name=self._tr(self.TR_REPORT_OPERATION),
                    stale_check=stale,
                    corr_id=uuid.uuid4().hex,
                    cancelable=True,
                    indeterminate=False,
                    timeout_ms=self._overlay_timeout_ms(cancelable=True),
                )
            except (RuntimeError, ValueError) as error:
                self._logger.exception("Failed to start report operation (save=%s).", save)
                on_error(str(error))
                on_finished()

        dialog.report_preview_requested.connect(prepare)

        def save_report(request: object) -> None:
            prepare(request, save=True)

        dialog.report_save_requested.connect(save_report)

    @staticmethod
    def _show_report_preview(dialog: AnalysisDialog, html: str) -> None:
        """Display prepared HTML without initializing a browser in worker threads."""
        from expo_jbm329.gui.dialogs.analysis.report_preview_dialog import ReportPreviewDialog

        preview = ReportPreviewDialog(html, parent=dialog)
        dialog.finished.connect(preview.close)
        preview.show()

    def _export_overview(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Validate snapshot identity and route owned frames to existing exporters."""
        if not isinstance(request, OverviewExportRequest) or request.result is not dialog.exportable_overview():
            return
        if not any(request.format is format_choice for format_choice in OverviewExportFormat):
            return
        if request.format is not OverviewExportFormat.EXCEL and len(request.tables) != 1:
            return
        try:
            sheets = localized_report_tables(
                AnalysisCategory.OVERVIEW,
                request.result,
                tuple(table.value for table in request.tables),
                translate=translate,
                number_format=fmt_num,
                count_format=fmt_int,
                split_overview_samples=request.format is OverviewExportFormat.EXCEL,
            )
        except (TypeError, ValueError):
            self._logger.warning("Rejected unavailable Overview export selection.")
            return
        # Frames belong to this export only and remain stable for the async job.
        match request.format:
            case OverviewExportFormat.EXCEL:
                exporter.export_excel(
                    sheets=sheets,
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case OverviewExportFormat.CSV:
                exporter.export_csv(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case OverviewExportFormat.BINARY:
                exporter.export_data(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )

    def _export_statistics(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Route validated Statistics snapshots to existing asynchronous exporters."""
        if not isinstance(request, StatisticsExportRequest) or request.result is not dialog.exportable_statistics():
            return
        if request.format not in tuple(StatisticsExportFormat):
            return
        if len(set(request.tables)) != len(request.tables):
            return
        charts_selected = StatisticsExportTable.CHARTS in request.tables
        table_choices = tuple(table for table in request.tables if table is not StatisticsExportTable.CHARTS)
        if not charts_selected and not table_choices:
            return
        if request.format is not StatisticsExportFormat.EXCEL and (charts_selected or len(table_choices) != 1):
            return

        try:
            localized_sheets = localized_report_tables(
                AnalysisCategory.STATISTICS,
                request.result,
                tuple(table.value for table in table_choices),
                translate=translate,
                number_format=fmt_num,
                count_format=fmt_int,
            )
        except (TypeError, ValueError):
            self._logger.warning("Rejected unavailable Statistics export selection.")
            return
        sheet_names = tuple(localized_sheets)
        if len(sheet_names) != len({name.casefold() for name in sheet_names}):
            self._logger.warning("Rejected Statistics export because translated sheet names are not unique.")
            return

        match request.format:
            case StatisticsExportFormat.EXCEL:
                chart_sheet_name = statistics_component_label(StatisticsExportTable.CHARTS, translate)
                chart_factory: (
                    Callable[
                        [Callable[[int], None] | None, Callable[[], bool] | None],
                        tuple[ExcelChartImage, ...],
                    ]
                    | None
                ) = None
                if charts_selected:
                    presentations = build_statistics_chart_presentations(request.result.columns, translate)

                    def make_chart_images(
                        progress_cb: Callable[[int], None] | None,
                        cancel_cb: Callable[[], bool] | None,
                    ) -> tuple[ExcelChartImage, ...]:
                        return render_statistics_charts(
                            request.result.columns,
                            presentations,
                            progress_cb=progress_cb,
                            cancel_cb=cancel_cb,
                        )

                    chart_factory = make_chart_images

                exporter.export_excel(
                    sheets=localized_sheets,
                    chart_factory=chart_factory,
                    chart_sheet_name=chart_sheet_name if charts_selected else None,
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.CSV:
                exporter.export_csv(
                    df=next(iter(localized_sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.BINARY:
                exporter.export_data(
                    df=next(iter(localized_sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )

    def _export_hypothesis(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Localize owned applied-result tables and render worker-owned Excel charts."""
        if not isinstance(request, HypothesisExportRequest) or request.snapshot is not dialog.exportable_hypothesis():
            return
        snapshot = request.snapshot
        charts = HypothesisExportComponent.CHARTS in request.components
        table_choices = tuple(item for item in request.components if item is not HypothesisExportComponent.CHARTS)
        hypothesis_keys = {
            HypothesisExportComponent.SUMMARY: "summary",
            HypothesisExportComponent.TEST_RESULTS: "test_results",
        }
        sheets = localized_report_tables(
            AnalysisCategory.HYPOTHESIS_TESTS,
            snapshot,
            tuple(hypothesis_keys[item] for item in table_choices),
            translate=translate,
            number_format=fmt_num,
            count_format=fmt_int,
        )
        sheet_names = tuple(sheets)
        if len(sheet_names) != len({name.casefold() for name in sheet_names}):
            message = "Translated hypothesis sheet names must be unique."
            raise ValueError(message)
        if request.format is StatisticsExportFormat.EXCEL:
            presentation = build_hypothesis_chart_presentation(snapshot.result, translate)

            def make_images(
                progress_cb: Callable[[int], None] | None, cancel_cb: Callable[[], bool] | None
            ) -> tuple[ExcelChartImage, ...]:
                return render_hypothesis_charts(
                    snapshot,
                    presentation,
                    progress_cb=progress_cb,
                    cancel_cb=cancel_cb,
                )

            exporter.export_excel(
                sheets=sheets,
                chart_factory=make_images if charts else None,
                chart_sheet_name=(
                    hypothesis_component_label(snapshot, HypothesisExportComponent.CHARTS, translate)
                    if charts
                    else None
                ),
                parent_widget=dialog,
                operation_target=dialog.content_panel(),
                show_success_dialog=True,
            )
        elif request.format is StatisticsExportFormat.CSV:
            exporter.export_csv(
                df=next(iter(sheets.values())),
                parent_widget=dialog,
                operation_target=dialog.content_panel(),
                show_success_dialog=True,
            )
        else:
            exporter.export_data(
                df=next(iter(sheets.values())),
                parent_widget=dialog,
                operation_target=dialog.content_panel(),
                show_success_dialog=True,
            )

    def _localized_correlation_table(self, snapshot: CorrelationExportSnapshot) -> pd.DataFrame:
        """Localize the ranked table while preserving numeric statistics."""
        sheets = localized_report_tables(
            AnalysisCategory.CORRELATION,
            snapshot,
            (CorrelationExportComponent.STRONGEST_CORRELATIONS.value,),
            translate=translate,
            number_format=fmt_num,
            count_format=fmt_int,
        )
        return next(iter(sheets.values()))

    def _export_correlation(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Export applied tables and worker-owned chart images from one snapshot."""
        if not isinstance(request, CorrelationExportRequest) or request.snapshot is not dialog.exportable_correlation():
            return
        snapshot = request.snapshot
        sheet_name = translate_presentation_label(PresentationLabel.STRONGEST_CORRELATIONS, translate)
        sheets = (
            {sheet_name: self._localized_correlation_table(snapshot)}
            if CorrelationExportComponent.STRONGEST_CORRELATIONS in request.components
            else {}
        )
        charts = tuple(
            component
            for component in request.components
            if component is not CorrelationExportComponent.STRONGEST_CORRELATIONS
        )
        labels = build_correlation_chart_labels(snapshot.matrix, translate, capture_chart_numeric_locale())

        def make_images(
            progress_cb: Callable[[int], None] | None, cancel_cb: Callable[[], bool] | None
        ) -> tuple[ExcelChartImage, ...]:
            return render_correlation_charts(snapshot, charts, labels, progress_cb=progress_cb, cancel_cb=cancel_cb)

        match request.format:
            case StatisticsExportFormat.EXCEL:
                exporter.export_excel(
                    sheets=sheets,
                    chart_factory=make_images if charts else None,
                    chart_sheet_name=(
                        translate_presentation_label(PresentationLabel.CORRELATION_PLOTS, translate) if charts else None
                    ),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.CSV:
                exporter.export_csv(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.BINARY:
                exporter.export_data(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )

    def _localized_regression_tables(
        self,
        snapshot: RegressionExportSnapshot,
        components: tuple[RegressionExportComponent, ...],
    ) -> dict[str, pd.DataFrame]:
        """Build regression sheets with translated names, headers and metric labels."""
        return localized_report_tables(
            AnalysisCategory.REGRESSION,
            snapshot,
            tuple(component.value for component in components),
            translate=translate,
            number_format=fmt_num,
            count_format=fmt_int,
        )

    def _export_regression(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Export the displayed model's localized tables and worker-rendered charts."""
        if not isinstance(request, RegressionExportRequest) or request.snapshot is not dialog.exportable_regression():
            return
        snapshot = request.snapshot
        charts = RegressionExportComponent.CHARTS in request.components
        sheets = self._localized_regression_tables(snapshot, request.components)

        def make_images(
            progress_cb: Callable[[int], None] | None, cancel_cb: Callable[[], bool] | None
        ) -> tuple[ExcelChartImage, ...]:
            return render_regression_charts(snapshot, progress_cb=progress_cb, cancel_cb=cancel_cb)

        match request.format:
            case StatisticsExportFormat.EXCEL:
                exporter.export_excel(
                    sheets=sheets,
                    chart_factory=make_images if charts else None,
                    chart_sheet_name=(
                        regression_component_label(
                            snapshot.model,
                            RegressionExportComponent.CHARTS,
                            translate,
                        )
                        if charts
                        else None
                    ),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.CSV:
                exporter.export_csv(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.BINARY:
                exporter.export_data(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )

    @staticmethod
    def _outlier_score_label(snapshot: OutlierExportSnapshot) -> str:
        """Return the displayed score header of the snapshot's potential outliers."""
        if isinstance(snapshot, MultivariateOutlierExportSnapshot):
            return translate("MultivariateOutliersView", "Anomaly score")
        score_headers = {
            OutlierMethod.IQR: translate("OutliersView", "Distance past fence"),
            OutlierMethod.Z_SCORE: translate("OutliersView", "z"),
            OutlierMethod.MODIFIED_Z_SCORE: translate("OutliersView", "Modified z"),
        }
        return score_headers[snapshot.summary.method]

    def _localized_outlier_tables(
        self,
        snapshot: OutlierExportSnapshot,
        components: tuple[OutlierExportComponent, ...],
    ) -> dict[str, pd.DataFrame]:
        """Build outlier sheets with translated names, headers, statuses and metric labels."""
        return localized_report_tables(
            AnalysisCategory.OUTLIERS,
            snapshot,
            tuple(component.value for component in components),
            translate=translate,
            number_format=fmt_num,
            count_format=fmt_int,
        )

    def _export_outliers(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Export the displayed screening's localized tables and worker-rendered charts."""
        if not isinstance(request, OutlierExportRequest) or request.snapshot is not dialog.exportable_outliers():
            return
        snapshot = request.snapshot
        charts = OutlierExportComponent.CHARTS in request.components
        sheets = self._localized_outlier_tables(snapshot, request.components)

        def make_images(
            progress_cb: Callable[[int], None] | None, cancel_cb: Callable[[], bool] | None
        ) -> tuple[ExcelChartImage, ...]:
            if isinstance(snapshot, UnivariateOutlierExportSnapshot):
                return render_univariate_outlier_charts(snapshot, progress_cb=progress_cb, cancel_cb=cancel_cb)
            return render_multivariate_outlier_charts(snapshot, progress_cb=progress_cb, cancel_cb=cancel_cb)

        match request.format:
            case StatisticsExportFormat.EXCEL:
                exporter.export_excel(
                    sheets=sheets,
                    chart_factory=make_images if charts else None,
                    chart_sheet_name=(
                        outlier_component_label(
                            OutlierExportComponent.CHARTS,
                            translate,
                            multivariate=isinstance(snapshot, MultivariateOutlierExportSnapshot),
                        )
                        if charts
                        else None
                    ),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.CSV:
                exporter.export_csv(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.BINARY:
                exporter.export_data(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )

    @staticmethod
    def _localized_clustering_tables(
        components: tuple[ClusteringExportComponent, ...],
        snapshot: ClusteringExportSnapshot,
    ) -> dict[str, pd.DataFrame]:
        """Build clustering sheets with translated names, headers and metric labels.

        Cluster names are already translated by the snapshot's chart labels.
        """
        return localized_report_tables(
            AnalysisCategory.CLUSTERING,
            snapshot,
            tuple(component.value for component in components),
            translate=translate,
            number_format=fmt_num,
            count_format=fmt_int,
        )

    def _export_clustering(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Export the displayed clustering's localized tables and worker-rendered projection."""
        if not isinstance(request, ClusteringExportRequest) or request.snapshot is not dialog.exportable_clustering():
            return
        snapshot = request.snapshot
        charts = ClusteringExportComponent.CHARTS in request.components
        sheets = self._localized_clustering_tables(request.components, snapshot)

        def make_images(
            progress_cb: Callable[[int], None] | None, cancel_cb: Callable[[], bool] | None
        ) -> tuple[ExcelChartImage, ...]:
            return render_clustering_charts(snapshot, progress_cb=progress_cb, cancel_cb=cancel_cb)

        match request.format:
            case StatisticsExportFormat.EXCEL:
                exporter.export_excel(
                    sheets=sheets,
                    chart_factory=make_images if charts else None,
                    chart_sheet_name=clustering_component_label(ClusteringExportComponent.CHARTS, translate)
                    if charts
                    else None,
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.CSV:
                exporter.export_csv(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.BINARY:
                exporter.export_data(
                    df=next(iter(sheets.values())),
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )

    @staticmethod
    def _localized_pca_tables(
        components: tuple[PCAExportComponent, ...],
        snapshot: PCAExportSnapshot,
    ) -> dict[str, pd.DataFrame]:
        """Build PCA sheets with translated names, headers and metric labels.

        Component names such as ``PC1`` are displayed untranslated, as in the view.
        """
        return localized_report_tables(
            AnalysisCategory.PCA,
            snapshot,
            tuple(component.value for component in components),
            translate=translate,
            number_format=fmt_num,
            count_format=fmt_int,
        )

    def _export_pca(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Export the displayed PCA's localized tables and worker-rendered plots."""
        if not isinstance(request, PCAExportRequest) or request.snapshot is not dialog.exportable_pca():
            return
        snapshot = request.snapshot
        presentation = build_analysis_presentation(AnalysisCategory.PCA, snapshot, translate)
        charts = PCAExportComponent.CHARTS in request.components
        sheets = self._localized_pca_tables(request.components, snapshot)

        def make_images(
            progress_cb: Callable[[int], None] | None, cancel_cb: Callable[[], bool] | None
        ) -> tuple[ExcelChartImage, ...]:
            return render_pca_charts(snapshot, progress_cb=progress_cb, cancel_cb=cancel_cb)

        match request.format:
            case StatisticsExportFormat.EXCEL:
                exporter.export_excel(
                    sheets=sheets,
                    chart_factory=make_images if charts else None,
                    chart_sheet_name=(pca_component_label(PCAExportComponent.CHARTS, translate) if charts else None),
                    suggested_name=presentation.title,
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.CSV:
                exporter.export_csv(
                    df=next(iter(sheets.values())),
                    suggested_name=presentation.title,
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.BINARY:
                exporter.export_data(
                    df=next(iter(sheets.values())),
                    suggested_name=presentation.title,
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )

    @staticmethod
    def _localized_time_series_tables(
        components: tuple[TimeSeriesExportComponent, ...],
        snapshot: TimeSeriesExportSnapshot,
    ) -> dict[str, pd.DataFrame]:
        """Build time-series sheets with translated names, headers and metric labels."""
        return localized_report_tables(
            AnalysisCategory.TIME_SERIES,
            snapshot,
            tuple(component.value for component in components),
            translate=translate,
            number_format=fmt_num,
            count_format=fmt_int,
        )

    def _export_time_series(self, dialog: AnalysisDialog, exporter: ExportController, request: object) -> None:
        """Export the displayed time series' localized tables and worker-rendered plots."""
        if not isinstance(request, TimeSeriesExportRequest) or request.snapshot is not dialog.exportable_time_series():
            return
        snapshot = request.snapshot
        presentation = build_analysis_presentation(AnalysisCategory.TIME_SERIES, snapshot, translate)
        charts = TimeSeriesExportComponent.CHARTS in request.components
        sheets = self._localized_time_series_tables(request.components, snapshot)

        def make_images(
            progress_cb: Callable[[int], None] | None, cancel_cb: Callable[[], bool] | None
        ) -> tuple[ExcelChartImage, ...]:
            return render_time_series_charts(snapshot, progress_cb=progress_cb, cancel_cb=cancel_cb)

        match request.format:
            case StatisticsExportFormat.EXCEL:
                exporter.export_excel(
                    sheets=sheets,
                    chart_factory=make_images if charts else None,
                    chart_sheet_name=(
                        time_series_component_label(TimeSeriesExportComponent.CHARTS, translate) if charts else None
                    ),
                    suggested_name=presentation.title,
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.CSV:
                exporter.export_csv(
                    df=next(iter(sheets.values())),
                    suggested_name=presentation.title,
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )
            case StatisticsExportFormat.BINARY:
                exporter.export_data(
                    df=next(iter(sheets.values())),
                    suggested_name=presentation.title,
                    parent_widget=dialog,
                    operation_target=dialog.content_panel(),
                    show_success_dialog=True,
                )

    # ------------------------------------------------------------------
    # Renderers (GUI thread only)
    # ------------------------------------------------------------------

    def _render_overview(self, result: object, _dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Dataset Overview view. Must run on the GUI thread."""
        return OverviewView(cast("DatasetOverviewResult", result)), None

    def _render_statistics(self, result: object, _dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render full-width Statistics with column selection owned by its table.

        Must run on the GUI thread.
        """
        stats_result = cast("DescriptiveStatisticsResult", result)
        content = StatisticsView(stats_result)

        return content, None

    def _render_hypothesis_tests(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Hypothesis Tests Apply prompt and its test/column-picker config.

        Must run on the GUI thread. Nothing is computed until the user
        clicks Apply; the configuration widget's `apply_requested` signal is
        wired to `_recompute_content`, which dispatches a background job and
        replaces only the content pane, leaving this exact configuration
        widget instance (and the user's picks) in place. Switching test or
        editing columns replaces the previous result with the prompt again.
        """
        defaults = cast("_HypothesisTestsDefaults", result)
        config = HypothesisTestsConfigWidget(
            defaults.group_comparison,
            defaults.chi_square,
            defaults.paired_comparison,
        )

        def _unapplied_content() -> QWidget:
            test = config.selected_test()
            initial_by_test: dict[HypothesisTest, GroupComparisonResult | ChiSquareResult | PairedComparisonResult] = {
                HypothesisTest.GROUP_COMPARISON: defaults.group_comparison,
                HypothesisTest.CHI_SQUARE: defaults.chi_square,
                HypothesisTest.PAIRED_COMPARISON: defaults.paired_comparison,
            }
            initial = initial_by_test[test]
            if initial.error is None:
                return self._apply_prompt()
            return self._render_hypothesis_test_content(test, initial)

        def _handle_apply_requested() -> None:
            configuration = config.applied_configuration()
            if configuration is None:
                return
            test, selection = configuration
            revision = config.configuration_revision()

            def apply_displayed_result(value: object) -> None:
                """Register a snapshot only after the accepted result is displayed."""
                content = self._render_hypothesis_test_content(test, value)
                dialog.set_content_widget(content)
                typed_result: HypothesisResult
                columns: tuple[str, ...]
                if isinstance(content, GroupComparisonView):
                    typed_result = cast("GroupComparisonResult", value)
                    columns = (typed_result.numeric_column, typed_result.grouping_column)
                    notes = content.export_notes(typed_result)
                elif isinstance(content, ChiSquareView):
                    chi_result = cast("ChiSquareResult", value)
                    columns = (chi_result.row_column, chi_result.column_column)
                    notes = content.export_notes(chi_result)
                    typed_result = chi_result
                else:
                    paired_result = cast("PairedComparisonResult", value)
                    columns = paired_result.columns
                    notes = cast("PairedComparisonView", content).export_notes(paired_result)
                    typed_result = paired_result
                if typed_result.error is not None:
                    return
                snapshot = HypothesisExportSnapshot(
                    test,
                    typed_result,
                    selection if selection is not None else columns,
                    notes,
                )
                dialog.set_exportable_hypothesis(snapshot)
                dialog.set_analysis_presentation(
                    build_analysis_presentation(AnalysisCategory.HYPOTHESIS_TESTS, snapshot, translate)
                )

            self._recompute_content(
                dialog,
                category=AnalysisCategory.HYPOTHESIS_TESTS,
                scope_suffix=":".join((test.value, *(selection or ()))),
                compute=lambda df, _callbacks: self._compute_hypothesis_test(df, test, selection),
                apply_result=apply_displayed_result,
                is_stale=lambda: (
                    config.applied_configuration() is not configuration
                    or config.selected_test() is not test
                    or config.configuration_revision() != revision
                ),
            )

        config.test_changed.connect(lambda: dialog.set_content_widget(_unapplied_content()))
        config.configuration_changed.connect(lambda: dialog.set_content_widget(_unapplied_content()))
        config.apply_requested.connect(_handle_apply_requested)
        return _unapplied_content(), config

    @staticmethod
    def _initialize_hypothesis_tests(df: pd.DataFrame) -> _HypothesisTestsDefaults:
        """Return every hypothesis test's default configuration without computing a test."""
        return _HypothesisTestsDefaults(
            group_comparison=initialize_group_comparison(df),
            chi_square=initialize_chi_square(df),
            paired_comparison=initialize_paired_comparison(df),
        )

    @staticmethod
    def _compute_hypothesis_test(
        df: pd.DataFrame,
        test: HypothesisTest,
        selection: tuple[str, ...] | None,
    ) -> object:
        """Compute one hypothesis test for `selection`, or its defaults when `None`."""
        match test:
            case HypothesisTest.GROUP_COMPARISON:
                return (
                    analyze_group_comparison(df)
                    if selection is None
                    else analyze_group_comparison(df, selection[0], selection[1])
                )
            case HypothesisTest.CHI_SQUARE:
                return (
                    analyze_chi_square(df) if selection is None else analyze_chi_square(df, selection[0], selection[1])
                )
            case HypothesisTest.PAIRED_COMPARISON:
                return analyze_paired_comparison(df, selection or ())

    @staticmethod
    def _render_hypothesis_test_content(test: HypothesisTest, result: object) -> QWidget:
        """Build the content view for one computed hypothesis test (GUI thread only)."""
        match test:
            case HypothesisTest.GROUP_COMPARISON:
                return GroupComparisonView(cast("GroupComparisonResult", result))
            case HypothesisTest.CHI_SQUARE:
                return ChiSquareView(cast("ChiSquareResult", result))
            case HypothesisTest.PAIRED_COMPARISON:
                return PairedComparisonView(cast("PairedComparisonResult", result))

    @staticmethod
    def _compute_correlation(
        df: pd.DataFrame,
        callbacks: _JobCallbacks,
        *,
        method: CorrelationMethod = CorrelationMethod.PEARSON,
        columns: tuple[str, ...] | None = None,
        pair: tuple[str, str] | None = None,
    ) -> _CorrelationOutcome | None:
        """Compute a correlation matrix and its pair detail (background-safe).

        Args:
            df: The DataFrame to analyze.
            callbacks: The job's progress/cancellation hooks.
            method: The correlation coefficient to compute.
            columns: Matrix columns, or `None` for the service's default.
            pair: The pair to detail, or `None` for the matrix's strongest.

        Returns:
            The outcome, or `None` if cancelled.
        """
        configuration = initialize_correlation(df)
        selected = configuration.columns if columns is None else tuple(columns)
        selection_is_valid = (
            len(selected) <= MAX_SELECTED_COLUMNS
            and len(selected) >= MIN_SELECTED_COLUMNS
            and len(set(selected)) == len(selected)
            and all(column in configuration.available_columns for column in selected)
        )
        if not selection_is_valid:
            # The public analyzer returns a structured selection error without
            # indexing the frame; retain that behavior for invalid requests.
            matrix = analyze_correlation_matrix(
                df,
                columns,
                method,
                progress_cb=callbacks.progress_cb,
                cancel_cb=callbacks.cancel_cb,
            )
            if matrix is None:
                return None
            return _CorrelationOutcome(matrix=matrix, pair_detail=None)

        matrix_data = df.loc[:, list(selected)].copy(deep=True)
        matrix = analyze_correlation_matrix(
            matrix_data,
            selected,
            method,
            progress_cb=callbacks.progress_cb,
            cancel_cb=callbacks.cancel_cb,
        )
        if matrix is None:
            return None
        if matrix.error is not None:
            return _CorrelationOutcome(matrix=matrix, pair_detail=None)
        matrix = replace(matrix, available_columns=configuration.available_columns)

        detail_pair = (
            pair
            if pair is not None and pair[0] != pair[1] and all(column in matrix.columns for column in pair)
            else default_pair(matrix)
        )
        pair_detail = analyze_correlation_pair(matrix_data, *detail_pair, method) if detail_pair is not None else None
        snapshot = CorrelationExportSnapshot(matrix=matrix, matrix_data=matrix_data)
        return _CorrelationOutcome(matrix=matrix, pair_detail=pair_detail, export_snapshot=snapshot)

    def _render_correlation(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Correlation Explorer's initial state: the Apply prompt and its config.

        Must run on the GUI thread. `result` is the configuration-only
        `initialize_correlation` matrix; nothing is computed until the user
        applies a method and column selection, which recomputes the whole
        matrix (a cancelable job replacing the view). Once a matrix is
        shown, a pair change recomputes only the pair detail (a quick job
        updating the current view's pair panel in place).
        """
        matrix = cast("CorrelationMatrixResult", result)
        if len(matrix.available_columns) < MIN_SELECTED_COLUMNS:
            return CorrelationView(matrix, None), None

        config = CorrelationConfigWidget(matrix)

        def _handle_matrix_requested() -> None:
            self._recompute_correlation_matrix(dialog, config)

        config.matrix_requested.connect(_handle_matrix_requested)
        config.configuration_changed.connect(lambda: dialog.set_content_widget(self._apply_prompt()))
        return self._apply_prompt(), config

    def _build_correlation_view(self, outcome: _CorrelationOutcome, dialog: AnalysisDialog) -> CorrelationView:
        """Build a Correlation Explorer view whose table rows request pair details."""
        view = CorrelationView(outcome.matrix, outcome.pair_detail)

        def _handle_pair_activated(x_column: str, y_column: str) -> None:
            if dialog.content_widget() is view:
                self._recompute_correlation_pair(dialog, x_column, y_column)

        view.pair_activated.connect(_handle_pair_activated)
        return view

    def _recompute_correlation_matrix(self, dialog: AnalysisDialog, config: CorrelationConfigWidget) -> None:
        """Recompute the whole correlation matrix for the config's applied method and columns.

        Preserve the table-selected pair when it remains in the applied
        columns; otherwise detail the new matrix's strongest pair.
        """
        dialog.invalidate_correlation_export()
        request_revision = dialog.correlation_export_revision()
        configuration = config.matrix_configuration()
        method, columns = configuration
        view = dialog.content_widget()
        pair = view.selected_pair() if isinstance(view, CorrelationView) else None

        def _apply(result: object) -> None:
            outcome = cast("_CorrelationOutcome", result)
            current_view = dialog.content_widget()
            latest_pair = current_view.selected_pair() if isinstance(current_view, CorrelationView) else None
            new_view = self._build_correlation_view(outcome, dialog)
            dialog.set_content_widget(new_view)
            if outcome.matrix.error is not None:
                return
            if outcome.export_snapshot is None:
                message = "A successful correlation matrix must retain its worker-owned export snapshot."
                raise ValueError(message)
            dialog.set_exportable_correlation(outcome.export_snapshot)
            if (
                latest_pair is not None
                and latest_pair != new_view.selected_pair()
                and all(column in outcome.matrix.columns for column in latest_pair)
            ):
                # A table selection made during the matrix job still takes precedence.
                new_view.select_pair(*latest_pair)

        self._recompute_content(
            dialog,
            category=AnalysisCategory.CORRELATION,
            scope_suffix=f"matrix:{method.value}",
            compute=lambda df, callbacks: self._compute_correlation(
                df, callbacks, method=method, columns=columns, pair=pair
            ),
            apply_result=_apply,
            is_stale=lambda: (
                config.matrix_configuration() != configuration
                or dialog.correlation_export_revision() != request_revision
            ),
            cancelable=True,
        )

    def _recompute_correlation_pair(
        self,
        dialog: AnalysisDialog,
        x_column: str,
        y_column: str,
    ) -> None:
        """Recompute only the pair detail, updating the current view's pair panel in place."""
        view = dialog.content_widget()
        if (
            not isinstance(view, CorrelationView)
            or view.table() is None
            or x_column == y_column
            or x_column not in view.columns()
            or y_column not in view.columns()
        ):
            # Pair selection is only available in a successful displayed matrix.
            return

        # The displayed matrix's method, not the config's: a pending method
        # change will bring its own pair detail with the new matrix.
        method = view.method()
        selection_revision = view.pair_selection_revision()

        def _apply(result: object) -> None:
            view.set_pair_detail(cast("CorrelationPairDetail", result))

        self._recompute_content(
            dialog,
            category=AnalysisCategory.CORRELATION,
            scope_suffix=f"pair:{method.value}:{x_column}:{y_column}",
            compute=lambda df, _callbacks: analyze_correlation_pair(df, x_column, y_column, method),
            apply_result=_apply,
            is_stale=lambda: (
                dialog.content_widget() is not view
                or view.selected_pair() != (x_column, y_column)
                or view.pair_selection_revision() != selection_revision
            ),
            target=view.pair_panel(),
        )

    def _render_regression(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render regression model results and the shared target/predictor config.

        Must run on the GUI thread. Linear regression remains the default;
        all configuration edits wait for Apply before refitting in a
        background job without recreating the configuration widget.
        """
        defaults = cast("_RegressionDefaults", result)
        regression = defaults.linear
        content = RegressionView(regression)
        if (
            regression.error is RegressionError.NO_NUMERIC_COLUMN
            and not defaults.generalized_targets.binary
            and not defaults.generalized_targets.count
        ):
            return content, None

        config = RegressionConfigWidget(regression, defaults.generalized_targets, defaults.survival_columns)

        def _handle_model_requested() -> None:
            configuration = config.model_configuration()
            model, target, predictors = configuration
            event = config.applied_event()
            revision = config.configuration_revision()
            if model is RegressionModel.LINEAR:
                scope_parts = (target, *predictors)
            elif model is RegressionModel.COX:
                scope_parts = (model.value, target, event, *predictors)
            else:
                scope_parts = (model.value, target, *predictors)

            def _compute(df: pd.DataFrame, _callbacks: _JobCallbacks) -> object:
                if model is RegressionModel.LINEAR:
                    return analyze_regression(df, target, predictors)
                if model is RegressionModel.COX:
                    return analyze_cox_regression(df, target, event, predictors)
                return analyze_generalized_regression(df, model, target, predictors)

            def _apply_result(computed: object) -> None:
                view: RegressionView | SurvivalRegressionView | GeneralizedRegressionView
                if model is RegressionModel.LINEAR:
                    view = RegressionView(cast("RegressionResult", computed))
                elif model is RegressionModel.COX:
                    view = SurvivalRegressionView(cast("SurvivalResult", computed))
                else:
                    view = GeneralizedRegressionView(cast("GeneralizedRegressionResult", computed))
                dialog.set_content_widget(view)
                # Register only after display so the snapshot matches what the user sees.
                if view.result().error is None:
                    dialog.set_exportable_regression(
                        RegressionExportSnapshot(view.result(), view.chart_labels(), view.export_notes())
                    )

            self._recompute_content(
                dialog,
                category=AnalysisCategory.REGRESSION,
                scope_suffix=":".join(scope_parts),
                compute=_compute,
                apply_result=_apply_result,
                is_stale=lambda: (
                    dialog.config_widget() is not config
                    or config.configuration_revision() != revision
                    or config.model_configuration() != configuration
                    or config.applied_event() != event
                ),
            )

        config.configuration_changed.connect(lambda: dialog.set_content_widget(self._apply_prompt()))
        config.model_requested.connect(_handle_model_requested)
        return content, config

    @staticmethod
    def _initialize_regression(df: pd.DataFrame) -> _RegressionDefaults:
        """Build configuration defaults for linear, binary and count regression."""
        return _RegressionDefaults(
            linear=initialize_regression(df),
            generalized_targets=initialize_generalized_targets(df),
            survival_columns=initialize_survival_columns(df),
        )

    @staticmethod
    def _compute_outliers(
        df: pd.DataFrame,
        method: OutlierMethod = OutlierMethod.IQR,
        threshold: float | None = None,
        column: str | None = None,
    ) -> _OutliersOutcome:
        """Compute an outlier summary and one column's detail (background-safe).

        Args:
            df: The DataFrame to analyze.
            method: The detection method.
            threshold: The method's threshold, or `None` for its default.
            column: The column to detail, or `None` for the summary's
                top-ranked one.

        Returns:
            The outcome.
        """
        summary = analyze_outlier_summary(df, method, threshold)
        if summary.error is not None:
            return _OutliersOutcome(summary=summary, detail=None)

        detail_column = column if column is not None else default_column(summary)
        detail = (
            analyze_outlier_column(df, detail_column, method, summary.threshold) if detail_column is not None else None
        )
        # The export renders every column's histogram later, so it needs data
        # that later edits of the dataset tab cannot change.
        data = df.loc[:, list(summary.available_columns)].copy(deep=True)
        return _OutliersOutcome(summary=summary, detail=detail, data=data)

    def _render_outliers(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Outlier Explorer's initial state: the Apply prompt and its config.

        Must run on the GUI thread. `result` is the configuration-only
        `initialize_outlier_summary` result; nothing is computed until the
        user applies a method and threshold, which recomputes the whole
        summary (a job replacing the view). Once a summary is shown, a
        column change recomputes only the column detail (a job updating the
        current view's detail panel in place).
        """
        summary = cast("OutlierSummaryResult", result)
        if not summary.available_columns:
            return OutliersView(summary, None), None

        config = OutliersConfigWidget(summary)

        def _handle_summary_requested() -> None:
            self._recompute_outlier_summary(dialog, config)

        config.summary_requested.connect(_handle_summary_requested)
        config.configuration_changed.connect(lambda: dialog.set_content_widget(self._apply_prompt()))
        config.multivariate_requested.connect(lambda: self._switch_to_multivariate_outliers(dialog))
        return self._apply_prompt(), config

    def _build_outliers_view(self, outcome: _OutliersOutcome, dialog: AnalysisDialog) -> OutliersView:
        """Build an Outlier Explorer view whose table rows request column details."""
        view = OutliersView(outcome.summary, outcome.detail)

        def _handle_column_activated(column: str) -> None:
            if dialog.content_widget() is view:
                self._recompute_outlier_column(dialog, column)

        view.column_activated.connect(_handle_column_activated)
        return view

    def _recompute_outlier_summary(self, dialog: AnalysisDialog, config: OutliersConfigWidget) -> None:
        """Recompute the whole outlier summary for the config's applied method and threshold.

        Preserve the table-selected column, or detail the summary's
        top-ranked column before a table selection exists.
        """
        configuration = config.summary_configuration()
        revision = config.configuration_revision()
        method, threshold = configuration
        view = dialog.content_widget()
        column = view.selected_column() if isinstance(view, OutliersView) else None

        def _apply(result: object) -> None:
            outcome = cast("_OutliersOutcome", result)
            current_view = dialog.content_widget()
            latest_column = current_view.selected_column() if isinstance(current_view, OutliersView) else None
            new_view = self._build_outliers_view(outcome, dialog)
            dialog.set_content_widget(new_view)
            if outcome.data is not None and outcome.summary.error is None and outcome.summary.columns:
                detail = new_view.column_detail()
                displayed_detail = detail if detail is not None and detail.error is None else None
                snapshot = UnivariateOutlierExportSnapshot(
                    summary=outcome.summary,
                    data=outcome.data,
                    chart_labels=new_view.histogram_labels(),
                    summary_notes=new_view.summary_notes(),
                    detail=displayed_detail,
                    detail_notes=new_view.detail_notes(),
                )
                dialog.set_exportable_outliers(snapshot)
                dialog.set_analysis_presentation(
                    build_analysis_presentation(AnalysisCategory.OUTLIERS, snapshot, translate)
                )
            if outcome.detail is None:
                return
            if (
                latest_column is not None
                and latest_column != new_view.selected_column()
                and any(summary.column == latest_column for summary in outcome.summary.columns)
            ):
                new_view.select_column(latest_column)

        self._recompute_content(
            dialog,
            category=AnalysisCategory.OUTLIERS,
            scope_suffix=f"summary:{method.value}:{threshold}",
            compute=lambda df, _callbacks: self._compute_outliers(df, method, threshold, column),
            apply_result=_apply,
            is_stale=lambda: (
                dialog.config_widget() is not config
                or config.configuration_revision() != revision
                or config.summary_configuration() != configuration
            ),
        )

    def _recompute_outlier_column(self, dialog: AnalysisDialog, column: str) -> None:
        """Recompute only the column detail, updating the current view's detail panel in place."""
        view = dialog.content_widget()
        if not isinstance(view, OutliersView) or view.table() is None or view.selected_column() != column:
            # Column selection is only available in a displayed summary.
            return

        # The displayed summary's configuration, not the config's: a pending
        # method/threshold change will bring its own detail with the new summary.
        method, threshold = view.configuration()
        selection_revision = view.column_selection_revision()

        def _apply(result: object) -> None:
            detail = cast("OutlierColumnDetail", result)
            view.set_column_detail(detail)
            snapshot = dialog.exportable_outliers()
            if isinstance(snapshot, UnivariateOutlierExportSnapshot) and snapshot.summary is view.result():
                displayed_detail = detail if detail.error is None else None
                updated_snapshot = snapshot.with_detail(displayed_detail, view.detail_notes())
                dialog.set_exportable_outliers(updated_snapshot)
                dialog.set_analysis_presentation(
                    build_analysis_presentation(AnalysisCategory.OUTLIERS, updated_snapshot, translate)
                )

        self._recompute_content(
            dialog,
            category=AnalysisCategory.OUTLIERS,
            scope_suffix=f"column:{method.value}:{threshold}:{column}",
            compute=lambda df, _callbacks: analyze_outlier_column(df, column, method, threshold),
            apply_result=_apply,
            is_stale=lambda: (
                dialog.content_widget() is not view
                or view.selected_column() != column
                or view.column_selection_revision() != selection_revision
            ),
            target=view.detail_panel(),
        )

    def _switch_to_multivariate_outliers(self, dialog: AnalysisDialog) -> None:
        """Show the multivariate configuration after the mode switch, without fitting.

        Like every apply-first category, the model is only fitted once the
        user applies a configuration. When the dataset cannot support
        multivariate screening, its explanatory error view is shown instead
        of the Apply prompt, but the configuration is kept so the user can
        switch back to univariate mode.
        """
        df = self._load_source_dataset(dialog, AnalysisCategory.OUTLIERS)
        if df is None:
            self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_ERROR))
            return

        multivariate_result = initialize_multivariate_outliers(df)
        multivariate_config = MultivariateOutliersConfigWidget(multivariate_result)
        multivariate_config.analysis_requested.connect(
            lambda: self._recompute_multivariate_outliers(dialog, multivariate_config)
        )
        multivariate_config.configuration_changed.connect(lambda: dialog.set_content_widget(self._apply_prompt()))
        multivariate_config.univariate_requested.connect(lambda: self._refresh_content(dialog))
        content = (
            self._apply_prompt() if multivariate_result.error is None else MultivariateOutliersView(multivariate_result)
        )
        dialog.set_content_widget(content)
        dialog.set_config_widget(multivariate_config)

    def _recompute_multivariate_outliers(
        self,
        dialog: AnalysisDialog,
        config: MultivariateOutliersConfigWidget,
    ) -> None:
        """Refit multivariate screening while preserving its configuration widget."""
        configuration = config.analysis_configuration()
        revision = config.configuration_revision()
        columns, method, standardize, contamination, lof_neighbors = configuration
        scope_parts = [
            "multivariate",
            method.value,
            "standardized" if standardize else "raw",
            f"contamination:{contamination}",
        ]
        if method is MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR:
            scope_parts.append(f"neighbors:{lof_neighbors}")
        scope_parts.extend(columns)

        def _apply_result(result: object) -> None:
            view = MultivariateOutliersView(cast("MultivariateOutlierResult", result))
            dialog.set_content_widget(view)
            if view.result().error is None:
                snapshot = MultivariateOutlierExportSnapshot(view.result(), view.chart_labels(), view.export_notes())
                dialog.set_exportable_outliers(snapshot)
                dialog.set_analysis_presentation(
                    build_analysis_presentation(AnalysisCategory.OUTLIERS, snapshot, translate)
                )

        self._recompute_content(
            dialog,
            category=AnalysisCategory.OUTLIERS,
            scope_suffix=":".join(scope_parts),
            compute=lambda df, _callbacks: analyze_multivariate_outliers(
                df,
                columns=columns,
                method=method,
                standardize=standardize,
                contamination=contamination,
                lof_neighbors=lof_neighbors,
            ),
            apply_result=_apply_result,
            is_stale=lambda: (
                dialog.config_widget() is not config
                or config.configuration_revision() != revision
                or config.analysis_configuration() != configuration
            ),
        )

    def _render_pca(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render PCA's initial state: the Apply prompt and its feature/scaling config.

        `result` is the configuration-only `initialize_pca` result; the fit
        only runs once the user applies a configuration. When the dataset
        cannot support PCA, its explanatory error view is shown instead.
        """
        pca_result = cast("PCAResult", result)
        if len(pca_result.available_columns) < PCA_MIN_SELECTED_COLUMNS:
            return PCAView(pca_result), None

        config = PCAConfigWidget(pca_result)
        config.analysis_requested.connect(lambda: self._recompute_pca(dialog, config))

        def _on_configuration_changed() -> None:
            dialog.invalidate_pca_export()
            dialog.set_content_widget(self._apply_prompt())

        config.configuration_changed.connect(_on_configuration_changed)
        return self._apply_prompt(), config

    def _recompute_pca(self, dialog: AnalysisDialog, config: PCAConfigWidget) -> None:
        """Run PCA for an applied feature/scaling configuration."""
        dialog.invalidate_pca_export()
        configuration = config.analysis_configuration()
        revision = config.configuration_revision()
        columns, standardize = configuration

        def _apply_result(result: object) -> None:
            view = PCAView(cast("PCAResult", result))
            dialog.set_content_widget(view)
            if view.result().error is None:
                snapshot = PCAExportSnapshot(view.result(), view.chart_labels(), view.export_notes())
                dialog.set_exportable_pca(snapshot)
                dialog.set_analysis_presentation(build_analysis_presentation(AnalysisCategory.PCA, snapshot, translate))

        self._recompute_content(
            dialog,
            category=AnalysisCategory.PCA,
            scope_suffix=f"fit:{'standardized' if standardize else 'raw'}:{':'.join(columns)}",
            compute=lambda df, _callbacks: analyze_pca(df, columns, standardize=standardize),
            apply_result=_apply_result,
            is_stale=lambda: (
                dialog.config_widget() is not config
                or config.configuration_revision() != revision
                or config.analysis_configuration() != configuration
            ),
        )

    def _render_clustering(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render clustering's initial state: the Apply prompt and its config.

        `result` is the configuration-only `initialize_clustering` result;
        the fit only runs once the user applies a configuration. When the
        dataset cannot support clustering, its explanatory error view is
        shown instead.
        """
        clustering_result = cast("ClusteringResult", result)
        if len(clustering_result.available_columns) < CLUSTERING_MIN_SELECTED_COLUMNS:
            return ClusteringView(clustering_result), None

        config = ClusteringConfigWidget(clustering_result)
        config.analysis_requested.connect(lambda: self._recompute_clustering(dialog, config))
        config.configuration_changed.connect(lambda: dialog.set_content_widget(self._apply_prompt()))
        return self._apply_prompt(), config

    def _recompute_clustering(self, dialog: AnalysisDialog, config: ClusteringConfigWidget) -> None:
        """Run clustering for the latest applied config."""
        configuration = config.analysis_configuration()
        revision = config.configuration_revision()
        columns, method, standardize, cluster_count, dbscan_epsilon, dbscan_min_samples = configuration
        parameters = (
            f"eps:{dbscan_epsilon}:min_samples:{dbscan_min_samples}"
            if method is ClusteringMethod.DBSCAN
            else f"clusters:{cluster_count}"
        )
        scale = "standardized" if standardize else "raw"
        scope_suffix = f"fit:{method.value}:{scale}:{parameters}:{':'.join(columns)}"

        def _apply_result(result: object) -> None:
            view = ClusteringView(cast("ClusteringResult", result))
            dialog.set_content_widget(view)
            if view.result().error is None:
                snapshot = ClusteringExportSnapshot(view.result(), view.chart_labels(), view.export_notes())
                dialog.set_exportable_clustering(snapshot)
                dialog.set_analysis_presentation(
                    build_analysis_presentation(AnalysisCategory.CLUSTERING, snapshot, translate)
                )

        self._recompute_content(
            dialog,
            category=AnalysisCategory.CLUSTERING,
            scope_suffix=scope_suffix,
            compute=lambda df, _callbacks: analyze_clustering(
                df,
                columns,
                method=method,
                standardize=standardize,
                cluster_count=cluster_count,
                dbscan_epsilon=dbscan_epsilon,
                dbscan_min_samples=dbscan_min_samples,
            ),
            apply_result=_apply_result,
            is_stale=lambda: (
                dialog.config_widget() is not config
                or config.configuration_revision() != revision
                or config.analysis_configuration() != configuration
            ),
        )

    def _render_time_series(self, result: object, dialog: AnalysisDialog) -> tuple[QWidget, QWidget | None]:
        """Render the Time Series Explorer's initial state: the Apply prompt and its config.

        `result` is the configuration-only `initialize_time_series` result;
        the series is only analyzed once the user applies a configuration.
        When the dataset lacks a datetime or numeric column, the explanatory
        error view is shown instead.
        """
        series_result = cast("TimeSeriesResult", result)
        if not series_result.available_datetime_columns or not series_result.available_value_columns:
            return TimeSeriesView(series_result), None

        config = TimeSeriesConfigWidget(series_result)
        config.analysis_requested.connect(lambda: self._recompute_time_series(dialog, config))
        config.configuration_changed.connect(lambda: dialog.set_content_widget(self._apply_prompt()))
        return self._apply_prompt(), config

    def _recompute_time_series(self, dialog: AnalysisDialog, config: TimeSeriesConfigWidget) -> None:
        """Analyze one applied Time Series Explorer configuration."""
        dialog.invalidate_time_series_export()
        configuration = config.analysis_configuration()
        revision = config.configuration_revision()
        datetime_column, value_column, frequency, period, model = configuration
        frequency_scope = frequency or "original"
        period_scope = str(period) if period is not None else "auto"

        def _apply_result(result: object) -> None:
            view = TimeSeriesView(cast("TimeSeriesResult", result))
            dialog.set_content_widget(view)
            if view.result().error is None:
                snapshot = TimeSeriesExportSnapshot(
                    view.result(),
                    view.chart_labels(),
                    view.export_notes(),
                    view.autocorrelation_note(),
                    applied_configuration=TimeSeriesAppliedConfiguration(
                        datetime_column,
                        value_column,
                        frequency,
                        period,
                        model,
                    ),
                )
                dialog.set_exportable_time_series(snapshot)
                dialog.set_analysis_presentation(
                    build_analysis_presentation(AnalysisCategory.TIME_SERIES, snapshot, translate)
                )

        self._recompute_content(
            dialog,
            category=AnalysisCategory.TIME_SERIES,
            scope_suffix=f"fit:{datetime_column}:{value_column}:{frequency_scope}:{period_scope}:{model.value}",
            compute=lambda df, _callbacks: analyze_time_series(
                df,
                datetime_column,
                value_column,
                resample_frequency=frequency,
                seasonal_period=period,
                decomposition_model=model,
            ),
            apply_result=_apply_result,
            is_stale=lambda: (
                dialog.config_widget() is not config
                or config.configuration_revision() != revision
                or config.analysis_configuration() != configuration
            ),
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _refresh_content(self, dialog: AnalysisDialog) -> None:
        """Rebuild the content panel for the currently selected category/dataset.

        Apply-first categories (with an `initialize` callable) only render
        their configuration here, synchronously. Every other category's
        computation runs as a background job with a busy overlay shown over
        the dialog's result pane, so large datasets or heavier analyses
        never freeze the GUI thread.

        Args:
            dialog: Active Advanced Analysis dialog.
        """
        category = dialog.selected_category()
        if category is None:
            return

        handler = self._category_handlers.get(category)
        if handler is None:
            self._show_placeholder(dialog, self._tr(self.TR_NOT_IMPLEMENTED))
            return

        tab_id = dialog.source_tab_id()
        if not tab_id:
            # Defensive only: open_dialog() requires a nonempty stable tab ID.
            self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_ERROR))
            return

        df = self._load_dataset(category, tab_id)
        if df is None:
            self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_ERROR))
            return

        if handler.initialize is not None:
            self._initialize_category(dialog, category, handler.initialize, handler.render, df)
            return

        self._run_analysis(dialog, category, handler, tab_id, df)

    def _initialize_category(
        self,
        dialog: AnalysisDialog,
        category: AnalysisCategory,
        initialize: Callable[[pd.DataFrame], object],
        render: Callable[[object, AnalysisDialog], tuple[QWidget, QWidget | None]],
        df: pd.DataFrame,
    ) -> None:
        """Render an apply-first category's configuration synchronously.

        Initializers only inspect column metadata, so they are cheap enough
        for the GUI thread and need neither a background job nor a busy
        overlay; the actual computation starts when the user clicks Apply.

        Args:
            dialog: Active Advanced Analysis dialog.
            category: The category being opened (for logging).
            initialize: Metadata-only initializer for the category.
            render: The category's renderer.
            df: The DataFrame to analyze.
        """
        try:
            result = initialize(df)
        except (KeyError, TypeError, ValueError):
            self._logger.exception("AnalysisController: failed to initialize category '%s'.", category)
            self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_ERROR))
            return

        content_widget, config_widget = render(result, dialog)
        dialog.set_content_widget(content_widget)
        dialog.set_config_widget(config_widget)

    def _apply_prompt(self) -> QWidget:
        """Build the content shown by an apply-first category before its first Apply."""
        return build_placeholder_label(self._tr(self.TR_APPLY_PROMPT))

    def _load_dataset(self, category: AnalysisCategory, tab_id: str) -> pd.DataFrame | None:
        """Return the dataset of `tab_id`, or `None` (logged) if it cannot be loaded.

        Args:
            category: The category needing the dataset (for logging).
            tab_id: The dataset's result tab ID.
        """
        try:
            return self._results.get_df_by_tab_id(tab_id)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self._logger.exception(
                "AnalysisController: failed to load dataset for category '%s' (tab_id=%s).",
                category,
                tab_id,
            )
            return None

    def _load_source_dataset(self, dialog: AnalysisDialog, category: AnalysisCategory) -> pd.DataFrame | None:
        """Load the dialog's fixed source dataset, or return `None` if unavailable.

        Args:
            dialog: Active Advanced Analysis dialog.
            category: The category needing the dataset (for logging).
        """
        tab_id = dialog.source_tab_id()
        if not tab_id:
            return None
        return self._load_dataset(category, tab_id)

    def _show_placeholder(self, dialog: AnalysisDialog, text: str) -> None:
        """Show a placeholder message and hide any stale configuration widget.

        Args:
            dialog: Active Advanced Analysis dialog.
            text: Message to show instead of analysis results.
        """
        dialog.show_placeholder(text)
        dialog.set_config_widget(None)

    def _run_analysis(
        self,
        dialog: AnalysisDialog,
        category: AnalysisCategory,
        handler: _CategoryHandler,
        tab_id: str,
        df: pd.DataFrame,
    ) -> None:
        """Run a category's computation in the background with a busy overlay."""
        corr_id = uuid.uuid4().hex
        dialog.invalidate_overview_export()
        revision = dialog.analysis_revision()

        # Hide any configuration widget left over from the previous category
        # immediately - it isn't covered by the busy overlay (which only
        # covers the result pane), so it would otherwise stay visible and
        # irrelevant while this job runs.
        dialog.set_config_widget(None)

        def _is_stale() -> bool:
            """Discard results once the user has moved on to something else."""
            return (
                dialog.selected_category() != category
                or dialog.source_tab_id() != tab_id
                or dialog.analysis_revision() != revision
            )

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> object:
            if cancel_cb is not None and cancel_cb():
                return None
            return handler.compute(df, _JobCallbacks(progress_cb=progress_cb, cancel_cb=cancel_cb))

        def _on_result(result: object) -> None:
            if _is_stale():
                return
            if result is None:
                if handler.cancelable:
                    self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_CANCELLED))
                return
            content_widget, config_widget = handler.render(result, dialog)
            dialog.set_content_widget(content_widget)
            dialog.set_config_widget(config_widget)
            if category is AnalysisCategory.OVERVIEW and isinstance(result, DatasetOverviewResult):
                dialog.set_exportable_overview(result)
            elif category is AnalysisCategory.STATISTICS and isinstance(result, DescriptiveStatisticsResult):
                dialog.set_exportable_statistics(result)

        def _on_error(_traceback: str) -> None:
            if _is_stale():
                return
            self._show_placeholder(dialog, self._tr(self.TR_ANALYSIS_ERROR))

        self._async_ops.run_target_overlay_operation(
            target=dialog.content_panel(),
            runner="pool",
            work=_work,
            on_result=_on_result,
            on_error=_on_error,
            busy_message=self._tr(self.TR_RUNNING_ANALYSIS),
            scope=f"analysis:{category.value}",
            operation_name=self._tr(self.TR_ANALYSIS_OPERATION),
            stale_check=_is_stale,
            corr_id=corr_id,
            cancelable=handler.cancelable,
            indeterminate=not handler.cancelable,
            timeout_ms=self._overlay_timeout_ms(cancelable=handler.cancelable),
        )

    @staticmethod
    def _overlay_timeout_ms(*, cancelable: bool) -> int:
        """Return the busy overlay's watchdog timeout for a job.

        Cancelable jobs report real progress and show a Cancel button
        (their overlay is determinate), so they get a longer timeout.
        """
        return _CANCELABLE_TIMEOUT_MS if cancelable else _DEFAULT_TIMEOUT_MS

    def _recompute_content(
        self,
        dialog: AnalysisDialog,
        *,
        category: AnalysisCategory,
        scope_suffix: str,
        compute: Callable[[pd.DataFrame, _JobCallbacks], object],
        apply_result: Callable[[object], None],
        is_stale: Callable[[], bool],
        target: QWidget | None = None,
        cancelable: bool = False,
    ) -> None:
        """Recompute and redraw only the content pane for a config-driven category.

        Used by categories whose configuration widget selects *what* to
        compute (e.g. which columns to compare) rather than merely *how*
        to redraw already-computed data (contrast the Statistics table,
        which only switches which precomputed column is shown). A
        configuration change therefore needs a new background computation,
        but the configuration widget itself - and the user's current picks
        - must be left alone, unlike `_run_analysis`, which always
        replaces both the content and configuration widgets.

        Args:
            dialog: Active Advanced Analysis dialog.
            category: The category this recompute belongs to - checked
                (alongside the dataset) to detect that the user has since
                navigated away entirely, not just changed the
                configuration again.
            scope_suffix: Appended to the async job's scope, so each
                distinct configuration gets its own job identity for
                cancellation/logging purposes.
            compute: Background-safe callable turning the DataFrame (plus
                the job's progress/cancellation hooks) into a plain (non-Qt)
                result object for the current configuration, or `None` if
                cancelled.
            apply_result: GUI-thread callable displaying that result -
                typically by replacing the content widget. Must not build
                a configuration widget - the existing one is left in place.
            is_stale: Checked (in addition to category/dataset staleness)
                before applying a result or error - typically compares the
                configuration widget's *current* selection against the one
                this recompute was triggered for.
            target: Widget covered by the busy overlay. Defaults to the
                dialog's whole content panel.
            cancelable: Whether `compute` reports progress and honors
                cancellation (see `_CategoryHandler.cancelable`).
        """
        tab_id = dialog.source_tab_id()
        if not tab_id:
            return

        df = self._load_dataset(category, tab_id)
        if df is None:
            dialog.show_placeholder(self._tr(self.TR_ANALYSIS_ERROR))
            return

        corr_id = uuid.uuid4().hex
        if category is AnalysisCategory.HYPOTHESIS_TESTS:
            dialog.invalidate_overview_export()
        revision = dialog.analysis_revision()

        def _combined_is_stale() -> bool:
            """Discard results once the user has moved on from this exact configuration."""
            return (
                dialog.selected_category() != category
                or dialog.source_tab_id() != tab_id
                or (
                    category in {AnalysisCategory.HYPOTHESIS_TESTS, AnalysisCategory.REGRESSION}
                    and dialog.analysis_revision() != revision
                )
                or is_stale()
            )

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> object:
            if cancel_cb is not None and cancel_cb():
                return None
            return compute(df, _JobCallbacks(progress_cb=progress_cb, cancel_cb=cancel_cb))

        def _on_result(result: object) -> None:
            if _combined_is_stale():
                return
            if result is None:
                if cancelable:
                    dialog.show_placeholder(self._tr(self.TR_ANALYSIS_CANCELLED))
                return
            apply_result(result)

        def _on_error(_traceback: str) -> None:
            if _combined_is_stale():
                return
            dialog.show_placeholder(self._tr(self.TR_ANALYSIS_ERROR))

        self._async_ops.run_target_overlay_operation(
            target=target if target is not None else dialog.content_panel(),
            runner="pool",
            work=_work,
            on_result=_on_result,
            on_error=_on_error,
            busy_message=self._tr(self.TR_RUNNING_ANALYSIS),
            scope=f"analysis:{category.value}:{scope_suffix}",
            operation_name=self._tr(self.TR_ANALYSIS_OPERATION),
            stale_check=_combined_is_stale,
            corr_id=corr_id,
            cancelable=cancelable,
            indeterminate=not cancelable,
            timeout_ms=self._overlay_timeout_ms(cancelable=cancelable),
        )
