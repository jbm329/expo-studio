"""Shared presentation descriptors for applied analysis results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.chi_square import ChiSquareResult
from expo_jbm329.services.analysis.clustering import ClusteringMethod
from expo_jbm329.services.analysis.clustering_export import ClusteringExportComponent, ClusteringExportSnapshot
from expo_jbm329.services.analysis.correlation import CorrelationMethod
from expo_jbm329.services.analysis.correlation_export import CorrelationExportSnapshot
from expo_jbm329.services.analysis.group_comparison import GroupComparisonResult
from expo_jbm329.services.analysis.hypothesis_export import HypothesisExportComponent, HypothesisExportSnapshot
from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierMethod
from expo_jbm329.services.analysis.outliers import OutlierMethod
from expo_jbm329.services.analysis.outliers_export import (
    MultivariateOutlierExportSnapshot,
    OutlierExportComponent,
    OutlierExportSnapshot,
    UnivariateOutlierExportSnapshot,
)
from expo_jbm329.services.analysis.paired_comparison import PairedComparisonMethod, PairedComparisonResult
from expo_jbm329.services.analysis.pca_export import PCAExportComponent, PCAExportSnapshot
from expo_jbm329.services.analysis.regression import RegressionResult, TermKind, term_name
from expo_jbm329.services.analysis.regression_export import (
    RegressionExportComponent,
    RegressionExportSnapshot,
    regression_model,
)
from expo_jbm329.services.analysis.regression_glm import (
    GeneralizedRegressionResult,
    RegressionModel,
    generalized_term_name,
)
from expo_jbm329.services.analysis.statistics import StatisticsExportTable
from expo_jbm329.services.analysis.survival import SurvivalResult, survival_term_name
from expo_jbm329.services.analysis.timeseries import DecompositionModel
from expo_jbm329.services.analysis.timeseries_export import (
    TimeSeriesAppliedConfiguration,
    TimeSeriesExportComponent,
    TimeSeriesExportSnapshot,
)
from expo_jbm329.utils.format_utils import fmt_num, fmt_pct

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.services.analysis.pca import PCAResult
    from expo_jbm329.services.analysis.report import ReportSnapshot


class PresentationLabel(StrEnum):
    """Stable semantic labels shared by analysis presentation surfaces."""

    CORRELATION = "correlation"
    CONFIGURED_TITLE = "configured_title"
    COLUMNS = "columns"
    OVERVIEW_COLUMNS_METADATA = "overview_columns_metadata"
    STATISTICS_DISTRIBUTION = "statistics_distribution"
    STATISTICS_CONTINUOUS = "statistics_continuous"
    STATISTICS_CATEGORICAL = "statistics_categorical"
    STRONGEST_CORRELATIONS = "strongest_correlations"
    CORRELATION_PLOTS = "correlation_plots"
    CORRELATION_MATRIX = "correlation_matrix"
    SCATTERPLOTS = "scatterplots"
    PEARSON = "pearson"
    SPEARMAN = "spearman"
    KENDALL = "kendall"
    SCATTERPLOT_TITLE = "scatterplot_title"
    HYPOTHESIS_TESTS = "hypothesis_tests"
    GROUP_COMPARISON = "group_comparison"
    CATEGORICAL_ASSOCIATION = "categorical_association"
    WILCOXON_SIGNED_RANK = "wilcoxon_signed_rank"
    FRIEDMAN = "friedman"
    NUMERIC_VARIABLE = "numeric_variable"
    GROUPING_VARIABLE = "grouping_variable"
    ROW_VARIABLE = "row_variable"
    COLUMN_VARIABLE = "column_variable"
    MEASUREMENT_VARIABLES = "measurement_variables"
    TESTS_COMPUTED = "tests_computed"
    TESTS_AVAILABLE = "tests_available"
    WELCH_T_TEST = "welch_t_test"
    STUDENT_T_TEST = "student_t_test"
    MANN_WHITNEY_U = "mann_whitney_u"
    ONE_WAY_ANOVA = "one_way_anova"
    KRUSKAL_WALLIS = "kruskal_wallis"
    PEARSON_CHI_SQUARE = "pearson_chi_square"
    FISHER_EXACT = "fisher_exact"
    GROUP_SUMMARY = "group_summary"
    CONTINGENCY_TABLE = "contingency_table"
    MEASUREMENT_SUMMARY = "measurement_summary"
    TEST_RESULTS = "test_results"
    GROUP_DISTRIBUTIONS = "group_distributions"
    ASSOCIATION_PLOTS = "association_plots"
    PAIRED_MEASUREMENT_PLOTS = "paired_measurement_plots"
    HYPOTHESIS_CONFIGURED_TITLE = "hypothesis_configured_title"
    REGRESSION = "regression"
    REGRESSION_CONFIGURED_TITLE = "regression_configured_title"
    LINEAR_REGRESSION = "linear_regression"
    LOGISTIC_REGRESSION = "logistic_regression"
    POISSON_REGRESSION = "poisson_regression"
    NEGATIVE_BINOMIAL_REGRESSION = "negative_binomial_regression"
    COX_REGRESSION = "cox_regression"
    OUTCOME = "outcome"
    DURATION = "duration"
    EVENT = "event"
    PREDICTORS = "predictors"
    MODEL_TERMS = "model_terms"
    REFERENCE_LEVELS = "reference_levels"
    COEFFICIENTS = "coefficients"
    REGRESSION_MODEL_SUMMARY = "regression_model_summary"
    LINEAR_DIAGNOSTICS = "linear_diagnostics"
    LOGISTIC_DIAGNOSTICS = "logistic_diagnostics"
    COUNT_DIAGNOSTICS = "count_diagnostics"
    SURVIVAL_CHARTS = "survival_charts"
    INTERCEPT = "intercept"
    OUTLIERS = "outliers"
    OUTLIERS_CONFIGURED_TITLE = "outliers_configured_title"
    IQR_OUTLIERS = "iqr_outliers"
    Z_SCORE_OUTLIERS = "z_score_outliers"
    MODIFIED_Z_SCORE_OUTLIERS = "modified_z_score_outliers"
    ISOLATION_FOREST = "isolation_forest"
    LOCAL_OUTLIER_FACTOR = "local_outlier_factor"
    THRESHOLD = "threshold"
    IQR_MULTIPLIER = "iqr_multiplier"
    SCORE_THRESHOLD = "score_threshold"
    SCREENED_COLUMNS = "screened_columns"
    SELECTED_DETAIL_COLUMN = "selected_detail_column"
    NO_COLUMN_SELECTED = "no_column_selected"
    FEATURES = "features"
    STANDARDIZATION = "standardization"
    STANDARDIZED = "standardized"
    NOT_STANDARDIZED = "not_standardized"
    EXPECTED_OUTLIER_FRACTION = "expected_outlier_fraction"
    LOF_NEIGHBORS = "lof_neighbors"
    COLUMN_SUMMARY = "column_summary"
    MODEL_SUMMARY = "model_summary"
    POTENTIAL_OUTLIERS = "potential_outliers"
    COLUMN_DISTRIBUTION = "column_distribution"
    COLUMN_DISTRIBUTIONS = "column_distributions"
    OUTLIER_PROJECTION = "outlier_projection"
    CLUSTERING = "clustering"
    CLUSTERING_CONFIGURED_TITLE = "clustering_configured_title"
    K_MEANS = "k_means"
    DBSCAN = "dbscan"
    AGGLOMERATIVE = "agglomerative"
    CLUSTER_SIZES = "cluster_sizes"
    CLUSTER_MODEL_SUMMARY = "cluster_model_summary"
    CLUSTER_PROJECTION = "cluster_projection"
    CLUSTER_PCA_TITLE = "cluster_pca_title"
    CLUSTER_COUNT = "cluster_count"
    DBSCAN_EPSILON = "dbscan_epsilon"
    DBSCAN_MIN_SAMPLES = "dbscan_min_samples"
    FEATURES_SELECTOR = "features_selector"
    STANDARDIZE_FEATURES_SELECTOR = "standardize_features_selector"
    PCA = "pca"
    PCA_FEATURE_LOADINGS = "pca_feature_loadings"
    PCA_EXPLAINED_VARIANCE = "pca_explained_variance"
    PCA_MODEL_SUMMARY = "pca_model_summary"
    PCA_PLOTS = "pca_plots"
    PCA_FEATURES = "pca_features"
    PCA_STANDARDIZATION = "pca_standardization"
    PCA_STANDARDIZED = "pca_standardized"
    PCA_NOT_STANDARDIZED = "pca_not_standardized"
    TIME_SERIES_TIME_COLUMN = "time_series_time_column"
    TIME_SERIES_VALUE_COLUMN = "time_series_value_column"
    TIME_SERIES_RESAMPLING = "time_series_resampling"
    TIME_SERIES_SEASONAL_PERIOD = "time_series_seasonal_period"
    TIME_SERIES_DECOMPOSITION_MODEL = "time_series_decomposition_model"
    TIME_SERIES_AUTO_DETECT_PERIOD = "time_series_auto_detect_period"
    TIME_SERIES_ORIGINAL_FREQUENCY = "time_series_original_frequency"
    TIME_SERIES_AUTOMATIC_PERIOD = "time_series_automatic_period"
    TIME_SERIES_NO_DETECTED_PERIOD = "time_series_no_detected_period"
    TIME_SERIES_DETECTED_PERIOD = "time_series_detected_period"
    TIME_SERIES_DAILY = "time_series_daily"
    TIME_SERIES_WEEKLY = "time_series_weekly"
    TIME_SERIES_MONTHLY = "time_series_monthly"
    TIME_SERIES_QUARTERLY = "time_series_quarterly"
    TIME_SERIES_YEARLY = "time_series_yearly"
    TIME_SERIES_ADDITIVE = "time_series_additive"
    TIME_SERIES_MULTIPLICATIVE = "time_series_multiplicative"
    TIME_SERIES_SERIES = "time_series_series"
    TIME_SERIES_AUTOCORRELATION = "time_series_autocorrelation"
    TIME_SERIES_MODEL_SUMMARY = "time_series_model_summary"
    TIME_SERIES_CHARTS = "time_series_charts"
    TIME_SERIES_SEASONAL_DECOMPOSITION = "time_series_seasonal_decomposition"
    TIME_SERIES_OBSERVED = "time_series_observed"
    TIME_SERIES_TREND = "time_series_trend"
    TIME_SERIES_SEASONAL = "time_series_seasonal"
    TIME_SERIES_RESIDUAL = "time_series_residual"
    TIME_SERIES_LAG = "time_series_lag"
    TIME_SERIES_VALUE = "time_series_value"
    TIME_SERIES_TIMESTAMP = "time_series_timestamp"


@dataclass(frozen=True, slots=True)
class PresentationLabelDefinition:
    """Translation source and context for one semantic presentation label."""

    context: str
    source: str


_CORRELATION_CONTEXT = "CorrelationView"
_HYPOTHESIS_CONTEXT = "HypothesisPresentation"
_REGRESSION_CONTEXT = "RegressionPresentation"
_OUTLIERS_CONTEXT = "OutliersPresentation"
_CLUSTERING_CONTEXT = "ClusteringPresentation"
_ANALYSIS_CONFIGURATION_CONTEXT = "AnalysisConfiguration"
_PCA_CONTEXT = "PCAPresentation"
_TIME_SERIES_CONTEXT = "TimeSeriesPresentation"
_LABEL_DEFINITIONS: dict[PresentationLabel, PresentationLabelDefinition] = {
    PresentationLabel.OVERVIEW_COLUMNS_METADATA: PresentationLabelDefinition("OverviewView", "Columns metadata"),
    PresentationLabel.STATISTICS_DISTRIBUTION: PresentationLabelDefinition("StatisticsView", "Distribution"),
    PresentationLabel.STATISTICS_CONTINUOUS: PresentationLabelDefinition("StatisticsView", "Continuous"),
    PresentationLabel.STATISTICS_CATEGORICAL: PresentationLabelDefinition("StatisticsView", "Categorical"),
    PresentationLabel.CLUSTERING: PresentationLabelDefinition(_CLUSTERING_CONTEXT, "Clustering"),
    PresentationLabel.CLUSTERING_CONFIGURED_TITLE: PresentationLabelDefinition(
        _CLUSTERING_CONTEXT, "{category} — {method}"
    ),
    PresentationLabel.K_MEANS: PresentationLabelDefinition(_CLUSTERING_CONTEXT, "K-Means"),
    PresentationLabel.DBSCAN: PresentationLabelDefinition(_CLUSTERING_CONTEXT, "DBSCAN"),
    PresentationLabel.AGGLOMERATIVE: PresentationLabelDefinition(_CLUSTERING_CONTEXT, "Agglomerative"),
    PresentationLabel.CLUSTER_SIZES: PresentationLabelDefinition(_CLUSTERING_CONTEXT, "Cluster sizes"),
    PresentationLabel.CLUSTER_MODEL_SUMMARY: PresentationLabelDefinition(_CLUSTERING_CONTEXT, "Model summary"),
    PresentationLabel.CLUSTER_PROJECTION: PresentationLabelDefinition(_CLUSTERING_CONTEXT, "Cluster projection"),
    PresentationLabel.CLUSTER_PCA_TITLE: PresentationLabelDefinition(
        _CLUSTERING_CONTEXT, "Cluster projection (internal PCA)"
    ),
    PresentationLabel.CLUSTER_COUNT: PresentationLabelDefinition(_CLUSTERING_CONTEXT, "Number of clusters:"),
    PresentationLabel.DBSCAN_EPSILON: PresentationLabelDefinition(_CLUSTERING_CONTEXT, "Neighborhood radius (eps):"),
    PresentationLabel.DBSCAN_MIN_SAMPLES: PresentationLabelDefinition(_CLUSTERING_CONTEXT, "Minimum samples:"),
    PresentationLabel.FEATURES_SELECTOR: PresentationLabelDefinition(_ANALYSIS_CONFIGURATION_CONTEXT, "Features"),
    PresentationLabel.STANDARDIZE_FEATURES_SELECTOR: PresentationLabelDefinition(
        _ANALYSIS_CONFIGURATION_CONTEXT, "Standardize features"
    ),
    PresentationLabel.PCA: PresentationLabelDefinition(_PCA_CONTEXT, "PCA"),
    PresentationLabel.PCA_FEATURE_LOADINGS: PresentationLabelDefinition(_PCA_CONTEXT, "Feature loadings"),
    PresentationLabel.PCA_EXPLAINED_VARIANCE: PresentationLabelDefinition(_PCA_CONTEXT, "Explained variance"),
    PresentationLabel.PCA_MODEL_SUMMARY: PresentationLabelDefinition(_PCA_CONTEXT, "Model summary"),
    PresentationLabel.PCA_PLOTS: PresentationLabelDefinition(_PCA_CONTEXT, "PCA plots"),
    PresentationLabel.PCA_FEATURES: PresentationLabelDefinition(_PCA_CONTEXT, "Features:"),
    PresentationLabel.PCA_STANDARDIZATION: PresentationLabelDefinition(_PCA_CONTEXT, "Standardization:"),
    PresentationLabel.PCA_STANDARDIZED: PresentationLabelDefinition(_PCA_CONTEXT, "Standardized"),
    PresentationLabel.PCA_NOT_STANDARDIZED: PresentationLabelDefinition(_PCA_CONTEXT, "Not standardized"),
    PresentationLabel.TIME_SERIES_TIME_COLUMN: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Time column:"),
    PresentationLabel.TIME_SERIES_VALUE_COLUMN: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Value column:"),
    PresentationLabel.TIME_SERIES_RESAMPLING: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Resampling:"),
    PresentationLabel.TIME_SERIES_SEASONAL_PERIOD: PresentationLabelDefinition(
        _TIME_SERIES_CONTEXT, "Seasonal period:"
    ),
    PresentationLabel.TIME_SERIES_DECOMPOSITION_MODEL: PresentationLabelDefinition(
        _TIME_SERIES_CONTEXT, "Decomposition model:"
    ),
    PresentationLabel.TIME_SERIES_AUTO_DETECT_PERIOD: PresentationLabelDefinition(
        _TIME_SERIES_CONTEXT, "Auto-detect seasonal period"
    ),
    PresentationLabel.TIME_SERIES_ORIGINAL_FREQUENCY: PresentationLabelDefinition(
        _TIME_SERIES_CONTEXT, "Original frequency"
    ),
    PresentationLabel.TIME_SERIES_AUTOMATIC_PERIOD: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Automatic"),
    PresentationLabel.TIME_SERIES_NO_DETECTED_PERIOD: PresentationLabelDefinition(
        _TIME_SERIES_CONTEXT, "Automatic (no period detected)"
    ),
    PresentationLabel.TIME_SERIES_DETECTED_PERIOD: PresentationLabelDefinition(
        _TIME_SERIES_CONTEXT, "Automatic (detected: {period})"
    ),
    PresentationLabel.TIME_SERIES_DAILY: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Daily"),
    PresentationLabel.TIME_SERIES_WEEKLY: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Weekly"),
    PresentationLabel.TIME_SERIES_MONTHLY: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Monthly"),
    PresentationLabel.TIME_SERIES_QUARTERLY: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Quarterly"),
    PresentationLabel.TIME_SERIES_YEARLY: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Yearly"),
    PresentationLabel.TIME_SERIES_ADDITIVE: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Additive"),
    PresentationLabel.TIME_SERIES_MULTIPLICATIVE: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Multiplicative"),
    PresentationLabel.TIME_SERIES_SERIES: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Series"),
    PresentationLabel.TIME_SERIES_AUTOCORRELATION: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Autocorrelation"),
    PresentationLabel.TIME_SERIES_MODEL_SUMMARY: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Model summary"),
    PresentationLabel.TIME_SERIES_CHARTS: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Charts"),
    PresentationLabel.TIME_SERIES_SEASONAL_DECOMPOSITION: PresentationLabelDefinition(
        _TIME_SERIES_CONTEXT, "Seasonal decomposition"
    ),
    PresentationLabel.TIME_SERIES_OBSERVED: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Observed"),
    PresentationLabel.TIME_SERIES_TREND: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Trend"),
    PresentationLabel.TIME_SERIES_SEASONAL: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Seasonal"),
    PresentationLabel.TIME_SERIES_RESIDUAL: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Residual"),
    PresentationLabel.TIME_SERIES_LAG: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Lag"),
    PresentationLabel.TIME_SERIES_VALUE: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Value"),
    PresentationLabel.TIME_SERIES_TIMESTAMP: PresentationLabelDefinition(_TIME_SERIES_CONTEXT, "Timestamp"),
    PresentationLabel.CORRELATION: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Correlation"),
    PresentationLabel.CONFIGURED_TITLE: PresentationLabelDefinition(_CORRELATION_CONTEXT, "{category} — {method}"),
    PresentationLabel.COLUMNS: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Columns:"),
    PresentationLabel.STRONGEST_CORRELATIONS: PresentationLabelDefinition(
        _CORRELATION_CONTEXT, "Strongest correlations"
    ),
    PresentationLabel.CORRELATION_PLOTS: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Correlation plots"),
    PresentationLabel.CORRELATION_MATRIX: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Correlation matrix"),
    PresentationLabel.SCATTERPLOTS: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Scatterplots"),
    PresentationLabel.PEARSON: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Pearson"),
    PresentationLabel.SPEARMAN: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Spearman"),
    PresentationLabel.KENDALL: PresentationLabelDefinition(_CORRELATION_CONTEXT, "Kendall's tau-b"),
    PresentationLabel.SCATTERPLOT_TITLE: PresentationLabelDefinition(_CORRELATION_CONTEXT, "{x} vs {y}"),
    PresentationLabel.HYPOTHESIS_TESTS: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Hypothesis Tests"),
    PresentationLabel.GROUP_COMPARISON: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Group comparison"),
    PresentationLabel.CATEGORICAL_ASSOCIATION: PresentationLabelDefinition(
        _HYPOTHESIS_CONTEXT, "Categorical association"
    ),
    PresentationLabel.WILCOXON_SIGNED_RANK: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Wilcoxon signed-rank"),
    PresentationLabel.FRIEDMAN: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Friedman"),
    PresentationLabel.NUMERIC_VARIABLE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Numeric variable:"),
    PresentationLabel.GROUPING_VARIABLE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Grouping variable:"),
    PresentationLabel.ROW_VARIABLE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Row variable:"),
    PresentationLabel.COLUMN_VARIABLE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Column variable:"),
    PresentationLabel.MEASUREMENT_VARIABLES: PresentationLabelDefinition(
        _HYPOTHESIS_CONTEXT, "Measurement variables (selected order):"
    ),
    PresentationLabel.TESTS_COMPUTED: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Tests computed:"),
    PresentationLabel.TESTS_AVAILABLE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Tests available:"),
    PresentationLabel.WELCH_T_TEST: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Welch's t-test"),
    PresentationLabel.STUDENT_T_TEST: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Student's t-test"),
    PresentationLabel.MANN_WHITNEY_U: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Mann-Whitney U"),
    PresentationLabel.ONE_WAY_ANOVA: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "One-way ANOVA"),
    PresentationLabel.KRUSKAL_WALLIS: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Kruskal-Wallis"),
    PresentationLabel.PEARSON_CHI_SQUARE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Pearson's chi-square test"),
    PresentationLabel.FISHER_EXACT: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Fisher's exact test"),
    PresentationLabel.GROUP_SUMMARY: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Group summary"),
    PresentationLabel.CONTINGENCY_TABLE: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Contingency table"),
    PresentationLabel.MEASUREMENT_SUMMARY: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Measurement summary"),
    PresentationLabel.TEST_RESULTS: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Test results"),
    PresentationLabel.GROUP_DISTRIBUTIONS: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Group distributions"),
    PresentationLabel.ASSOCIATION_PLOTS: PresentationLabelDefinition(_HYPOTHESIS_CONTEXT, "Association plots"),
    PresentationLabel.PAIRED_MEASUREMENT_PLOTS: PresentationLabelDefinition(
        _HYPOTHESIS_CONTEXT, "Paired measurement plots"
    ),
    PresentationLabel.HYPOTHESIS_CONFIGURED_TITLE: PresentationLabelDefinition(
        _HYPOTHESIS_CONTEXT, "{category} — {method}"
    ),
    PresentationLabel.REGRESSION: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Regression"),
    PresentationLabel.REGRESSION_CONFIGURED_TITLE: PresentationLabelDefinition(
        _REGRESSION_CONTEXT, "{category} — {model}"
    ),
    PresentationLabel.LINEAR_REGRESSION: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Linear regression"),
    PresentationLabel.LOGISTIC_REGRESSION: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Logistic regression"),
    PresentationLabel.POISSON_REGRESSION: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Poisson regression"),
    PresentationLabel.NEGATIVE_BINOMIAL_REGRESSION: PresentationLabelDefinition(
        _REGRESSION_CONTEXT, "Negative binomial regression"
    ),
    PresentationLabel.COX_REGRESSION: PresentationLabelDefinition(
        _REGRESSION_CONTEXT, "Cox proportional-hazards regression"
    ),
    PresentationLabel.OUTCOME: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Outcome:"),
    PresentationLabel.DURATION: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Duration:"),
    PresentationLabel.EVENT: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Event:"),
    PresentationLabel.PREDICTORS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Predictors:"),
    PresentationLabel.MODEL_TERMS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Modeled terms:"),
    PresentationLabel.REFERENCE_LEVELS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Reference levels:"),
    PresentationLabel.COEFFICIENTS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Coefficients"),
    PresentationLabel.REGRESSION_MODEL_SUMMARY: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Model summary"),
    PresentationLabel.LINEAR_DIAGNOSTICS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Linear diagnostics"),
    PresentationLabel.LOGISTIC_DIAGNOSTICS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Logistic diagnostics"),
    PresentationLabel.COUNT_DIAGNOSTICS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Count-model diagnostics"),
    PresentationLabel.SURVIVAL_CHARTS: PresentationLabelDefinition(_REGRESSION_CONTEXT, "Survival charts"),
    PresentationLabel.INTERCEPT: PresentationLabelDefinition(_REGRESSION_CONTEXT, "(Intercept)"),
    PresentationLabel.OUTLIERS: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Outliers"),
    PresentationLabel.OUTLIERS_CONFIGURED_TITLE: PresentationLabelDefinition(
        _OUTLIERS_CONTEXT, "{category} — {method}"
    ),
    PresentationLabel.IQR_OUTLIERS: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "IQR (Tukey's fences)"),
    PresentationLabel.Z_SCORE_OUTLIERS: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Z-score"),
    PresentationLabel.MODIFIED_Z_SCORE_OUTLIERS: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Modified Z-score"),
    PresentationLabel.ISOLATION_FOREST: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Isolation Forest"),
    PresentationLabel.LOCAL_OUTLIER_FACTOR: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Local Outlier Factor"),
    PresentationLabel.THRESHOLD: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Threshold:"),
    PresentationLabel.IQR_MULTIPLIER: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "IQR multiplier:"),
    PresentationLabel.SCORE_THRESHOLD: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Score threshold:"),
    PresentationLabel.SCREENED_COLUMNS: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Screened columns:"),
    PresentationLabel.SELECTED_DETAIL_COLUMN: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Selected detail column:"),
    PresentationLabel.NO_COLUMN_SELECTED: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "None"),
    PresentationLabel.FEATURES: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Features:"),
    PresentationLabel.STANDARDIZATION: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Standardization:"),
    PresentationLabel.STANDARDIZED: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Standardized"),
    PresentationLabel.NOT_STANDARDIZED: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Not standardized"),
    PresentationLabel.EXPECTED_OUTLIER_FRACTION: PresentationLabelDefinition(
        _OUTLIERS_CONTEXT, "Expected outlier fraction:"
    ),
    PresentationLabel.LOF_NEIGHBORS: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "LOF neighbors:"),
    PresentationLabel.COLUMN_SUMMARY: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Column summary"),
    PresentationLabel.MODEL_SUMMARY: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Model summary"),
    PresentationLabel.POTENTIAL_OUTLIERS: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Potential outliers"),
    PresentationLabel.COLUMN_DISTRIBUTION: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Column distribution"),
    PresentationLabel.COLUMN_DISTRIBUTIONS: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Column distributions"),
    PresentationLabel.OUTLIER_PROJECTION: PresentationLabelDefinition(_OUTLIERS_CONTEXT, "Outlier projection"),
}

_CATEGORY_FALLBACKS: dict[AnalysisCategory, str] = {
    AnalysisCategory.OVERVIEW: "Overview",
    AnalysisCategory.STATISTICS: "Statistics",
    AnalysisCategory.HYPOTHESIS_TESTS: "Hypothesis Tests",
    AnalysisCategory.CORRELATION: _LABEL_DEFINITIONS[PresentationLabel.CORRELATION].source,
    AnalysisCategory.REGRESSION: "Regression",
    AnalysisCategory.OUTLIERS: _LABEL_DEFINITIONS[PresentationLabel.OUTLIERS].source,
    AnalysisCategory.CLUSTERING: "Clustering",
    AnalysisCategory.PCA: "PCA",
    AnalysisCategory.TIME_SERIES: "Time Series",
}
_CORRELATION_METHOD_LABELS = {
    CorrelationMethod.PEARSON: PresentationLabel.PEARSON,
    CorrelationMethod.SPEARMAN: PresentationLabel.SPEARMAN,
    CorrelationMethod.KENDALL: PresentationLabel.KENDALL,
}
_HYPOTHESIS_COMPONENT_LABELS = {
    HypothesisTest.GROUP_COMPARISON: {
        HypothesisExportComponent.SUMMARY: PresentationLabel.GROUP_SUMMARY,
        HypothesisExportComponent.TEST_RESULTS: PresentationLabel.TEST_RESULTS,
        HypothesisExportComponent.CHARTS: PresentationLabel.GROUP_DISTRIBUTIONS,
    },
    HypothesisTest.CHI_SQUARE: {
        HypothesisExportComponent.SUMMARY: PresentationLabel.CONTINGENCY_TABLE,
        HypothesisExportComponent.TEST_RESULTS: PresentationLabel.TEST_RESULTS,
        HypothesisExportComponent.CHARTS: PresentationLabel.ASSOCIATION_PLOTS,
    },
    HypothesisTest.PAIRED_COMPARISON: {
        HypothesisExportComponent.SUMMARY: PresentationLabel.MEASUREMENT_SUMMARY,
        HypothesisExportComponent.TEST_RESULTS: PresentationLabel.TEST_RESULTS,
        HypothesisExportComponent.CHARTS: PresentationLabel.PAIRED_MEASUREMENT_PLOTS,
    },
}


@dataclass(frozen=True, slots=True)
class ConfigurationField:
    """One ordered applied setting represented by a label and values."""

    label: str
    items: tuple[str, ...]

    def __post_init__(self) -> None:
        """Require a visible label and at least one applied value."""
        if not self.label or not self.items:
            message = "A configuration field requires a label and at least one value."
            raise ValueError(message)

    @property
    def display_value(self) -> str:
        """Return values in their captured order for a plain-text surface."""
        return ", ".join(self.items)


@dataclass(frozen=True, slots=True)
class AnalysisPresentation:
    """Configured analysis title and structured applied configuration."""

    category: str
    title: str
    configuration: tuple[ConfigurationField, ...] = ()

    def __post_init__(self) -> None:
        """Require visible category and title labels."""
        if not self.category or not self.title:
            message = "An analysis presentation requires a category and title."
            raise ValueError(message)

    @property
    def summary_lines(self) -> tuple[str, ...]:
        """Return configuration fields as plain-text lines."""
        return tuple(f"{field.label} {field.display_value}" for field in self.configuration)


def presentation_label_source(label: PresentationLabel) -> tuple[str, str]:
    """Return the canonical translation context and source for a semantic label."""
    definition = _LABEL_DEFINITIONS[label]
    return definition.context, definition.source


def presentation_label_sources() -> tuple[tuple[str, str], ...]:
    """Return unique translation context/source pairs for worker label capture."""
    return tuple(dict.fromkeys((item.context, item.source) for item in _LABEL_DEFINITIONS.values()))


def translate_presentation_label(
    label: PresentationLabel,
    translate: Callable[[str, str], str],
) -> str:
    """Resolve one shared semantic label using the supplied translation source."""
    context, source = presentation_label_source(label)
    return translate(context, source)


def statistics_component_label(
    component: StatisticsExportTable,
    translate: Callable[[str, str], str],
) -> str:
    """Return the shared Statistics component label across presentation surfaces."""
    labels = {
        StatisticsExportTable.CONTINUOUS: PresentationLabel.STATISTICS_CONTINUOUS,
        StatisticsExportTable.CATEGORICAL: PresentationLabel.STATISTICS_CATEGORICAL,
        StatisticsExportTable.CHARTS: PresentationLabel.STATISTICS_DISTRIBUTION,
    }
    return translate_presentation_label(labels[component], translate)


def correlation_method_label(
    method: CorrelationMethod,
    translate: Callable[[str, str], str],
) -> str:
    """Return the localized display name of an applied correlation method."""
    return translate_presentation_label(_CORRELATION_METHOD_LABELS[method], translate)


def analysis_category_source(category: AnalysisCategory) -> str:
    """Return the legacy category source label used by non-Correlation surfaces."""
    return _CATEGORY_FALLBACKS[category]


def build_analysis_presentation(
    category: AnalysisCategory,
    snapshot: ReportSnapshot,
    translate: Callable[[str, str], str],
    *,
    number_format: Callable[[float], str] = fmt_num,
) -> AnalysisPresentation:
    """Build a presentation descriptor from a captured applied result.

    Correlation, Hypothesis Tests, Regression, Outliers, Clustering, PCA and
    Time Series receive configured titles and ordered settings.
    Other categories deliberately retain their existing category-only title.

    Args:
        category: Category that owns the successful applied result.
        snapshot: Captured result, never live configuration controls.
        translate: Translation callback accepting a context and source label.
        number_format: Locale-aware formatter for displayed numeric settings.

    Returns:
        Category title, configured analysis title, and typed settings.

    Raises:
        TypeError: If a Correlation category is paired with another snapshot type.
    """
    if category is AnalysisCategory.CORRELATION:
        if not isinstance(snapshot, CorrelationExportSnapshot):
            message = "Correlation presentation requires a correlation result snapshot."
            raise TypeError(message)
        return build_correlation_presentation(
            snapshot.matrix.method,
            snapshot.matrix.columns,
            translate,
        )
    if category is AnalysisCategory.HYPOTHESIS_TESTS:
        if not isinstance(snapshot, HypothesisExportSnapshot):
            message = "Hypothesis Tests presentation requires a hypothesis result snapshot."
            raise TypeError(message)
        return build_hypothesis_presentation(snapshot, translate)
    if category is AnalysisCategory.REGRESSION:
        if not isinstance(snapshot, RegressionExportSnapshot):
            message = "Regression presentation requires a regression result snapshot."
            raise TypeError(message)
        return build_regression_presentation(snapshot, translate)
    if category is AnalysisCategory.OUTLIERS:
        if not isinstance(snapshot, (UnivariateOutlierExportSnapshot, MultivariateOutlierExportSnapshot)):
            message = "Outliers presentation requires an outlier result snapshot."
            raise TypeError(message)
        return build_outliers_presentation(snapshot, translate, number_format=number_format)
    if category is AnalysisCategory.CLUSTERING:
        if not isinstance(snapshot, ClusteringExportSnapshot):
            message = "Clustering presentation requires a clustering result snapshot."
            raise TypeError(message)
        return build_clustering_presentation(snapshot, translate, number_format=number_format)
    if category is AnalysisCategory.PCA:
        if not isinstance(snapshot, PCAExportSnapshot):
            message = "PCA presentation requires a PCA result snapshot."
            raise TypeError(message)
        return build_pca_presentation(snapshot, translate)
    if category is AnalysisCategory.TIME_SERIES:
        if not isinstance(snapshot, TimeSeriesExportSnapshot):
            message = "Time Series presentation requires a time-series result snapshot."
            raise TypeError(message)
        configuration = (
            snapshot.applied_configuration
            if snapshot.applied_configuration is not None
            else TimeSeriesAppliedConfiguration.from_result(snapshot.result)
        )
        return build_time_series_presentation(
            configuration,
            snapshot.result.seasonal_period,
            translate,
            number_format=number_format,
        )
    category_source = analysis_category_source(category)
    category_title = translate("AnalysisDialog", category_source)
    return AnalysisPresentation(category_title, category_title)


def clustering_method_label(method: ClusteringMethod, translate: Callable[[str, str], str]) -> str:
    """Return the canonical translated clustering method name."""
    labels = {
        ClusteringMethod.K_MEANS: PresentationLabel.K_MEANS,
        ClusteringMethod.DBSCAN: PresentationLabel.DBSCAN,
        ClusteringMethod.AGGLOMERATIVE: PresentationLabel.AGGLOMERATIVE,
    }
    return translate_presentation_label(labels[method], translate)


def pca_component_label(
    component: PCAExportComponent,
    translate: Callable[[str, str], str],
) -> str:
    """Return the shared content-specific heading for an applied PCA component."""
    labels = {
        PCAExportComponent.FEATURE_LOADINGS: PresentationLabel.PCA_FEATURE_LOADINGS,
        PCAExportComponent.EXPLAINED_VARIANCE: PresentationLabel.PCA_EXPLAINED_VARIANCE,
        PCAExportComponent.MODEL_SUMMARY: PresentationLabel.PCA_MODEL_SUMMARY,
        PCAExportComponent.CHARTS: PresentationLabel.PCA_PLOTS,
    }
    return translate_presentation_label(labels[component], translate)


def time_series_component_label(
    component: TimeSeriesExportComponent,
    translate: Callable[[str, str], str],
) -> str:
    """Return the shared display heading for a time-series component."""
    labels = {
        TimeSeriesExportComponent.SERIES: PresentationLabel.TIME_SERIES_SERIES,
        TimeSeriesExportComponent.AUTOCORRELATION: PresentationLabel.TIME_SERIES_AUTOCORRELATION,
        TimeSeriesExportComponent.MODEL_SUMMARY: PresentationLabel.TIME_SERIES_MODEL_SUMMARY,
        TimeSeriesExportComponent.CHARTS: PresentationLabel.TIME_SERIES_CHARTS,
    }
    return translate_presentation_label(labels[component], translate)


def build_time_series_presentation(
    configuration: TimeSeriesAppliedConfiguration,
    detected_period: int | None,
    translate: Callable[[str, str], str],
    *,
    number_format: Callable[[float], str] = fmt_num,
) -> AnalysisPresentation:
    """Describe the applied time-series roles and settings, not pending controls."""
    category = translate("AnalysisDialog", "Time Series")
    frequency_labels = {
        "D": PresentationLabel.TIME_SERIES_DAILY,
        "W": PresentationLabel.TIME_SERIES_WEEKLY,
        "MS": PresentationLabel.TIME_SERIES_MONTHLY,
        "QS": PresentationLabel.TIME_SERIES_QUARTERLY,
        "YS": PresentationLabel.TIME_SERIES_YEARLY,
    }
    frequency = (
        translate_presentation_label(PresentationLabel.TIME_SERIES_ORIGINAL_FREQUENCY, translate)
        if configuration.resample_frequency is None
        else translate_presentation_label(frequency_labels[configuration.resample_frequency], translate)
        if configuration.resample_frequency in frequency_labels
        else configuration.resample_frequency
    )
    if configuration.seasonal_period is not None:
        period = number_format(float(configuration.seasonal_period))
    elif detected_period is None:
        period = translate_presentation_label(PresentationLabel.TIME_SERIES_NO_DETECTED_PERIOD, translate)
    else:
        period = translate_presentation_label(PresentationLabel.TIME_SERIES_DETECTED_PERIOD, translate).format(
            period=number_format(float(detected_period))
        )
    model_label = (
        PresentationLabel.TIME_SERIES_ADDITIVE
        if configuration.decomposition_model is DecompositionModel.ADDITIVE
        else PresentationLabel.TIME_SERIES_MULTIPLICATIVE
    )
    return AnalysisPresentation(
        category,
        category,
        (
            ConfigurationField(
                translate_presentation_label(PresentationLabel.TIME_SERIES_TIME_COLUMN, translate),
                (configuration.datetime_column,),
            ),
            ConfigurationField(
                translate_presentation_label(PresentationLabel.TIME_SERIES_VALUE_COLUMN, translate),
                (configuration.value_column,),
            ),
            ConfigurationField(
                translate_presentation_label(PresentationLabel.TIME_SERIES_RESAMPLING, translate),
                (frequency,),
            ),
            ConfigurationField(
                translate_presentation_label(PresentationLabel.TIME_SERIES_SEASONAL_PERIOD, translate),
                (period,),
            ),
            ConfigurationField(
                translate_presentation_label(PresentationLabel.TIME_SERIES_DECOMPOSITION_MODEL, translate),
                (translate_presentation_label(model_label, translate),),
            ),
        ),
    )


def build_pca_presentation(
    snapshot: PCAExportSnapshot,
    translate: Callable[[str, str], str],
) -> AnalysisPresentation:
    """Describe a successful PCA using its applied ordered features and standardization."""
    return build_pca_result_presentation(snapshot.result, translate)


def build_pca_result_presentation(
    result: PCAResult,
    translate: Callable[[str, str], str],
) -> AnalysisPresentation:
    """Describe an applied PCA result without requiring export-only chart metadata."""
    category = translate_presentation_label(PresentationLabel.PCA, translate)
    standardization = (
        PresentationLabel.PCA_STANDARDIZED if result.standardize else PresentationLabel.PCA_NOT_STANDARDIZED
    )
    return AnalysisPresentation(
        category,
        category,
        (
            ConfigurationField(
                translate_presentation_label(PresentationLabel.PCA_FEATURES, translate),
                result.columns,
            ),
            ConfigurationField(
                translate_presentation_label(PresentationLabel.PCA_STANDARDIZATION, translate),
                (translate_presentation_label(standardization, translate),),
            ),
        ),
    )


def clustering_component_label(component: ClusteringExportComponent, translate: Callable[[str, str], str]) -> str:
    """Return the shared content-specific clustering component label."""
    labels = {
        ClusteringExportComponent.CLUSTER_SIZES: PresentationLabel.CLUSTER_SIZES,
        ClusteringExportComponent.MODEL_SUMMARY: PresentationLabel.CLUSTER_MODEL_SUMMARY,
        ClusteringExportComponent.CHARTS: PresentationLabel.CLUSTER_PROJECTION,
    }
    return translate_presentation_label(labels[component], translate)


def build_clustering_presentation(
    snapshot: ClusteringExportSnapshot,
    translate: Callable[[str, str], str],
    *,
    number_format: Callable[[float], str] = fmt_num,
) -> AnalysisPresentation:
    """Describe the successful fit using only its applicable applied settings."""
    result = snapshot.result
    category = translate_presentation_label(PresentationLabel.CLUSTERING, translate)
    title = translate_presentation_label(PresentationLabel.CLUSTERING_CONFIGURED_TITLE, translate).format(
        category=category, method=clustering_method_label(result.method, translate)
    )
    fields = [
        ConfigurationField(translate_presentation_label(PresentationLabel.FEATURES, translate), result.columns),
        ConfigurationField(
            translate_presentation_label(PresentationLabel.STANDARDIZATION, translate),
            (
                translate_presentation_label(
                    PresentationLabel.STANDARDIZED if result.standardize else PresentationLabel.NOT_STANDARDIZED,
                    translate,
                ),
            ),
        ),
    ]
    parameters = (
        (
            (PresentationLabel.DBSCAN_EPSILON, number_format(result.dbscan_epsilon)),
            (PresentationLabel.DBSCAN_MIN_SAMPLES, str(result.dbscan_min_samples)),
        )
        if result.method is ClusteringMethod.DBSCAN
        else ((PresentationLabel.CLUSTER_COUNT, str(result.cluster_count)),)
    )
    fields.extend(
        ConfigurationField(translate_presentation_label(label, translate), (value,)) for label, value in parameters
    )
    return AnalysisPresentation(category, title, tuple(fields))


def outlier_method_label(method: OutlierMethod, translate: Callable[[str, str], str]) -> str:
    """Return the canonical translated name of a univariate outlier method."""
    labels = {
        OutlierMethod.IQR: PresentationLabel.IQR_OUTLIERS,
        OutlierMethod.Z_SCORE: PresentationLabel.Z_SCORE_OUTLIERS,
        OutlierMethod.MODIFIED_Z_SCORE: PresentationLabel.MODIFIED_Z_SCORE_OUTLIERS,
    }
    return translate_presentation_label(labels[method], translate)


def multivariate_outlier_method_label(
    method: MultivariateOutlierMethod,
    translate: Callable[[str, str], str],
) -> str:
    """Return the canonical translated name of a multivariate outlier method."""
    labels = {
        MultivariateOutlierMethod.ISOLATION_FOREST: PresentationLabel.ISOLATION_FOREST,
        MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR: PresentationLabel.LOCAL_OUTLIER_FACTOR,
    }
    return translate_presentation_label(labels[method], translate)


def outlier_component_label(
    component: OutlierExportComponent,
    translate: Callable[[str, str], str],
    *,
    multivariate: bool,
) -> str:
    """Return the shared, content-specific label for an outlier component."""
    labels = {
        OutlierExportComponent.COLUMN_SUMMARY: PresentationLabel.COLUMN_SUMMARY,
        OutlierExportComponent.COLUMN_DETAILS: PresentationLabel.MODEL_SUMMARY,
        OutlierExportComponent.MODEL_SUMMARY: PresentationLabel.MODEL_SUMMARY,
        OutlierExportComponent.POTENTIAL_OUTLIERS: PresentationLabel.POTENTIAL_OUTLIERS,
    }
    if component is OutlierExportComponent.CHARTS:
        if multivariate:
            return translate_presentation_label(PresentationLabel.OUTLIER_PROJECTION, translate)
        return translate_presentation_label(PresentationLabel.COLUMN_DISTRIBUTIONS, translate)
    return translate_presentation_label(labels[component], translate)


def build_outliers_presentation(
    snapshot: OutlierExportSnapshot,
    translate: Callable[[str, str], str],
    *,
    number_format: Callable[[float], str] = fmt_num,
) -> AnalysisPresentation:
    """Build the configured title and all semantically relevant applied settings."""
    category = translate_presentation_label(PresentationLabel.OUTLIERS, translate)
    if isinstance(snapshot, UnivariateOutlierExportSnapshot):
        summary = snapshot.summary
        method = outlier_method_label(summary.method, translate)
        title = translate_presentation_label(PresentationLabel.OUTLIERS_CONFIGURED_TITLE, translate).format(
            category=category, method=method
        )
        threshold_role = (
            PresentationLabel.IQR_MULTIPLIER
            if summary.method is OutlierMethod.IQR
            else PresentationLabel.SCORE_THRESHOLD
        )
        detail_column = (
            snapshot.detail.summary.column
            if snapshot.detail is not None
            else translate_presentation_label(PresentationLabel.NO_COLUMN_SELECTED, translate)
        )
        return AnalysisPresentation(
            category,
            title,
            (
                ConfigurationField(
                    translate_presentation_label(threshold_role, translate),
                    (number_format(summary.threshold),),
                ),
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.SCREENED_COLUMNS, translate),
                    summary.available_columns,
                ),
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.SELECTED_DETAIL_COLUMN, translate),
                    (detail_column,),
                ),
            ),
        )
    result = snapshot.result
    method = multivariate_outlier_method_label(result.method, translate)
    title = translate_presentation_label(PresentationLabel.OUTLIERS_CONFIGURED_TITLE, translate).format(
        category=category, method=method
    )
    configuration = [
        ConfigurationField(
            translate_presentation_label(PresentationLabel.FEATURES, translate),
            result.columns,
        ),
        ConfigurationField(
            translate_presentation_label(PresentationLabel.STANDARDIZATION, translate),
            (
                translate_presentation_label(
                    PresentationLabel.STANDARDIZED if result.standardize else PresentationLabel.NOT_STANDARDIZED,
                    translate,
                ),
            ),
        ),
        ConfigurationField(
            translate_presentation_label(PresentationLabel.EXPECTED_OUTLIER_FRACTION, translate),
            (fmt_pct(result.contamination, decimals=1),),
        ),
    ]
    if result.method is MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR:
        configuration.append(
            ConfigurationField(
                translate_presentation_label(PresentationLabel.LOF_NEIGHBORS, translate),
                (str(result.lof_neighbors),),
            )
        )
    return AnalysisPresentation(category, title, tuple(configuration))


def regression_model_label(model: RegressionModel, translate: Callable[[str, str], str]) -> str:
    """Return the canonical translated name of a regression model family."""
    labels = {
        RegressionModel.LINEAR: PresentationLabel.LINEAR_REGRESSION,
        RegressionModel.LOGISTIC: PresentationLabel.LOGISTIC_REGRESSION,
        RegressionModel.POISSON: PresentationLabel.POISSON_REGRESSION,
        RegressionModel.NEGATIVE_BINOMIAL: PresentationLabel.NEGATIVE_BINOMIAL_REGRESSION,
        RegressionModel.COX: PresentationLabel.COX_REGRESSION,
    }
    return translate_presentation_label(labels[model], translate)


def regression_component_label(
    model: RegressionModel,
    component: RegressionExportComponent,
    translate: Callable[[str, str], str],
) -> str:
    """Return a truthful shared heading for a regression result component."""
    if component is RegressionExportComponent.COEFFICIENTS:
        label = PresentationLabel.COEFFICIENTS
    elif component is RegressionExportComponent.MODEL_METRICS:
        label = PresentationLabel.REGRESSION_MODEL_SUMMARY
    else:
        labels = {
            RegressionModel.LINEAR: PresentationLabel.LINEAR_DIAGNOSTICS,
            RegressionModel.LOGISTIC: PresentationLabel.LOGISTIC_DIAGNOSTICS,
            RegressionModel.POISSON: PresentationLabel.COUNT_DIAGNOSTICS,
            RegressionModel.NEGATIVE_BINOMIAL: PresentationLabel.COUNT_DIAGNOSTICS,
            RegressionModel.COX: PresentationLabel.SURVIVAL_CHARTS,
        }
        label = labels[model]
    return translate_presentation_label(label, translate)


def regression_intercept_label(translate: Callable[[str, str], str]) -> str:
    """Return the canonical translated name of a regression intercept term."""
    return translate_presentation_label(PresentationLabel.INTERCEPT, translate)


def build_regression_presentation(
    snapshot: RegressionExportSnapshot,
    translate: Callable[[str, str], str],
) -> AnalysisPresentation:
    """Build the configured title and role-ordered settings from a fitted model."""
    return build_regression_result_presentation(snapshot.result, translate)


def build_regression_result_presentation(
    result: RegressionResult | GeneralizedRegressionResult | SurvivalResult,
    translate: Callable[[str, str], str],
) -> AnalysisPresentation:
    """Build the applied configuration directly from a fitted result."""
    model_name = regression_model_label(regression_model(result), translate)
    category = translate_presentation_label(PresentationLabel.REGRESSION, translate)
    title = translate_presentation_label(PresentationLabel.REGRESSION_CONFIGURED_TITLE, translate).format(
        category=category,
        model=model_name,
    )
    outcome_role = (
        (
            (PresentationLabel.DURATION, result.duration),
            (PresentationLabel.EVENT, result.event),
        )
        if isinstance(result, SurvivalResult)
        else ((PresentationLabel.OUTCOME, result.target),)
    )
    configuration = [
        ConfigurationField(translate_presentation_label(role, translate), (value,)) for role, value in outcome_role
    ]
    configuration.append(
        ConfigurationField(
            translate_presentation_label(PresentationLabel.PREDICTORS, translate),
            result.predictors,
        )
    )
    references = result.references
    if references:
        configuration.append(
            ConfigurationField(
                translate_presentation_label(PresentationLabel.REFERENCE_LEVELS, translate),
                tuple(f"{reference.column} = {reference.reference_level}" for reference in references),
            )
        )
    terms = _regression_term_names(result, translate)
    configuration.append(
        ConfigurationField(
            translate_presentation_label(PresentationLabel.MODEL_TERMS, translate),
            terms,
        )
    )
    return AnalysisPresentation(category, title, tuple(configuration))


def _regression_term_names(
    result: RegressionResult | GeneralizedRegressionResult | SurvivalResult,
    translate: Callable[[str, str], str],
) -> tuple[str, ...]:
    """Return fitted terms in model order, including dummy levels and intercept."""
    if isinstance(result, RegressionResult):
        return tuple(
            translate("RegressionPresentation", "(Intercept)") if term.kind is TermKind.INTERCEPT else term_name(term)
            for term in result.terms
        )
    if isinstance(result, GeneralizedRegressionResult):
        return tuple(
            translate("RegressionPresentation", "(Intercept)")
            if term.kind is TermKind.INTERCEPT
            else generalized_term_name(term)
            for term in result.terms
        )
    return tuple(
        translate("RegressionPresentation", "(Intercept)")
        if term.kind is TermKind.INTERCEPT
        else survival_term_name(term)
        for term in result.terms
    )


def build_hypothesis_presentation(
    snapshot: HypothesisExportSnapshot,
    translate: Callable[[str, str], str],
) -> AnalysisPresentation:
    """Build the configured title and role-ordered settings from a fitted result."""
    category_title = translate_presentation_label(PresentationLabel.HYPOTHESIS_TESTS, translate)
    result = snapshot.result
    configuration: tuple[ConfigurationField, ...]
    match result:
        case GroupComparisonResult():
            tests = (
                (PresentationLabel.WELCH_T_TEST, PresentationLabel.STUDENT_T_TEST, PresentationLabel.MANN_WHITNEY_U)
                if result.pairwise is not None
                else (PresentationLabel.ONE_WAY_ANOVA, PresentationLabel.KRUSKAL_WALLIS)
            )
            method = translate_presentation_label(PresentationLabel.GROUP_COMPARISON, translate)
            configuration = (
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.NUMERIC_VARIABLE, translate),
                    (result.numeric_column,),
                ),
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.GROUPING_VARIABLE, translate),
                    (result.grouping_column,),
                ),
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.TESTS_COMPUTED, translate),
                    tuple(translate_presentation_label(test, translate) for test in tests),
                ),
            )
        case ChiSquareResult():
            method = translate_presentation_label(PresentationLabel.CATEGORICAL_ASSOCIATION, translate)
            tests_available = [translate_presentation_label(PresentationLabel.PEARSON_CHI_SQUARE, translate)]
            if result.fisher_p_value is not None and result.fisher_odds_ratio is not None:
                tests_available.append(translate_presentation_label(PresentationLabel.FISHER_EXACT, translate))
            configuration = (
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.ROW_VARIABLE, translate),
                    (result.row_column,),
                ),
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.COLUMN_VARIABLE, translate),
                    (result.column_column,),
                ),
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.TESTS_AVAILABLE, translate),
                    tuple(tests_available),
                ),
            )
        case PairedComparisonResult():
            method_label = (
                PresentationLabel.WILCOXON_SIGNED_RANK
                if result.method is PairedComparisonMethod.WILCOXON
                else PresentationLabel.FRIEDMAN
            )
            method = translate_presentation_label(method_label, translate)
            configuration = (
                ConfigurationField(
                    translate_presentation_label(PresentationLabel.MEASUREMENT_VARIABLES, translate),
                    result.columns,
                ),
            )
        case _:
            message = "Hypothesis Tests presentation requires a supported fitted result."
            raise TypeError(message)
    title_template = translate_presentation_label(PresentationLabel.HYPOTHESIS_CONFIGURED_TITLE, translate)
    return AnalysisPresentation(
        category_title, title_template.format(category=category_title, method=method), configuration
    )


def hypothesis_component_label(
    snapshot: HypothesisExportSnapshot,
    component: HypothesisExportComponent,
    translate: Callable[[str, str], str],
) -> str:
    """Return the shared family-specific heading for an applied report/export component."""
    labels = _HYPOTHESIS_COMPONENT_LABELS.get(snapshot.test)
    if labels is None or component not in labels:
        message = "The hypothesis component does not match its applied test family."
        raise ValueError(message)
    return translate_presentation_label(labels[component], translate)


def build_correlation_presentation(
    method: CorrelationMethod,
    columns: tuple[str, ...],
    translate: Callable[[str, str], str],
) -> AnalysisPresentation:
    """Build the configured title and ordered columns for an applied matrix."""
    if not columns:
        message = "A correlation presentation requires applied columns."
        raise ValueError(message)
    category_title = translate_presentation_label(PresentationLabel.CORRELATION, translate)
    method_name = correlation_method_label(method, translate)
    title_template = translate_presentation_label(PresentationLabel.CONFIGURED_TITLE, translate)
    return AnalysisPresentation(
        category_title,
        title_template.format(category=category_title, method=method_name),
        (
            ConfigurationField(
                translate_presentation_label(PresentationLabel.COLUMNS, translate),
                columns,
            ),
        ),
    )
