"""Documented product limits and parameter defaults for Advanced Analysis.

These are code defaults, not runtime user settings. Changing a value requires
reviewing its consumers, boundary tests and resource/output implications.
Independent settings intentionally remain separate even when values coincide.
Existing service/chart modules retain legacy names bound to these values for
import compatibility; numeric policy is defined here only.

Other owners:
    chart_config: Renderer pixel budgets, layout passes and label orientation.
    chart_profiles: Figure geometry, typography and preferred rotations.
    services.data_profile.column_data_profile: Shared histogram bin policy,
        top-three text/category frequencies and up to three example values.
    services.data_profile.capabilities: CATEGORY_CARDINALITY_RATIO_LIMIT gates
        the convert-to-category UI action, not analysis eligibility.
    services.data_operations.dtypes: classify_series_dtype inspects the first
        500 non-null object values for booleans; category dtype is not inferred
        from a distinct-value threshold.
    Individual analysis services: Statistical minimums, confidence/significance
        levels, diagnostic heuristics (including Shapiro's large-sample caveat),
        numerical constants and deterministic sampling seeds.
    services.file_writer and app.settings.config_store: Excel format limits.

Reasons marked "Possible reason" are inferred, not benchmark-backed guarantees.
"""

from typing import Final

# Analytical eligibility and resource safeguards.

# Maximum distinct non-null values for categorical analysis eligibility.
# Statistics applies this to text/category/bool and numeric frequency summaries;
# above it the column has no frequency summary (numeric summaries are separate).
# Group comparisons/chi-square also require MIN_GROUPS distinct values.
# Regression (OLS, GLM, Cox) applies the shared grouping classifier only to
# text/category/bool predictors; numeric predictors remain numeric.
# Overview does NOT use this limit: it counts string/category dtypes regardless
# of cardinality and counts booleans separately. This does not infer a dtype.
# Reason: screen ID-like columns and bound cost/detail; 20 is product policy,
# not a universal statistical maximum. MIN_GROUPS remains in group_comparison.
CATEGORICAL_MAX_DISTINCT_VALUES: Final[int] = 50

# Maximum selected input columns, before dummy expansion; regression services
# and RegressionConfigWidget enforce this for OLS, GLM and Cox.
# Possible reason: bound model complexity and configuration size.
REGRESSION_MAX_PREDICTORS: Final[int] = 20

# Maximum non-intercept terms in OLS/GLM/Cox; k category levels need k-1 terms.
# Used by regression, regression_glm and survival validation and error messages.
# Reason: bound design-matrix memory and fitting time, independently of rows.
REGRESSION_MAX_MODEL_TERMS: Final[int] = 50

# Maximum optimizer iterations for logistic fitting in regression_glm.
# Possible reason: bound fitting work; convergence failure is reported, not
# replaced with a successful result. Independent of the count/Cox budgets.
LOGISTIC_MAX_ITERATIONS: Final[int] = 200

# Maximum optimizer iterations for Poisson fitting in regression_glm.
# Possible reason: bound fitting work while allowing convergence.
POISSON_MAX_ITERATIONS: Final[int] = 200

# Maximum optimizer iterations for negative-binomial fitting in regression_glm.
# Possible reason: bound fitting work for coefficient/dispersion estimation.
NEGATIVE_BINOMIAL_MAX_ITERATIONS: Final[int] = 200

# Maximum optimizer iterations for survival.analyze_cox_regression.
# Possible reason: bound Cox fitting work; not a subject-count/sample limit.
COX_MAX_ITERATIONS: Final[int] = 200

# Initial number of numeric columns selected by correlation initialization.
# Used by correlation and its configuration UI; this is not the hard maximum.
# Possible reason: keep the initial matrix readable and affordable.
CORRELATION_DEFAULT_SELECTED_COLUMNS: Final[int] = 20

# Maximum numeric columns in the calculated/exported correlation matrix.
# Used by correlation validation and CorrelationConfigWidget, not just charts.
# Possible reason: bound pairwise computation and matrix size.
CORRELATION_MAX_SELECTED_COLUMNS: Final[int] = 30

# Presentation data and detail; these do not bound statistical sample sizes.

# Maximum diagnostic scatter/Q-Q points in regression._plot_data and
# regression_glm._count_plot_data. Fits/statistics still use all complete rows.
# Reason: keep plotting responsive; the existing deterministic seeds stay local.
REGRESSION_PLOT_SAMPLE_SIZE: Final[int] = 5_000

# Maximum probability bins in regression_glm.prepare_logistic_plot_data.
# All fitted rows contribute; tied probabilities can produce fewer bins.
# Possible reason: readable calibration summaries; ROC/AUC are not sampled.
LOGISTIC_CALIBRATION_MAX_BINS: Final[int] = 10

# Maximum scatter points in correlation pair detail; pair statistics use all
# finite paired rows. Used by correlation's deterministic plot preparation.
# Possible reason: bound rendering cost and visual crowding.
CORRELATION_SCATTER_SAMPLE_SIZE: Final[int] = 5_000

# Largest matrix width with per-cell labels in correlation_charts drawing.
# Larger matrices still exist and render, but without numeric annotations.
# Possible reason: prevent unreadable overlapping cell text.
CORRELATION_MAX_ANNOTATED_COLUMNS: Final[int] = 12

# Maximum cells annotated in hypothesis_charts' chi-square residual heatmap.
# Does not truncate the contingency table or change the chi-square test.
# Possible reason: keep cell labels readable on larger tables.
HYPOTHESIS_MAX_ANNOTATED_CELLS: Final[int] = 100

# Maximum subject trajectories prepared by paired_comparison for its chart.
# All complete subjects still contribute to tests and distribution summaries.
# Possible reason: avoid overplotting; sampling remains deterministic.
PAIRED_MAX_TRAJECTORIES: Final[int] = 200

# Maximum PC1/PC2 scatter rows prepared by pca; the fit uses all complete rows.
# Possible reason: bound point rendering and retained plot-data size.
PCA_SCATTER_SAMPLE_SIZE: Final[int] = 5_000

# Maximum projection points prepared by clustering, not a fit/silhouette cap.
# Silhouette still uses all non-noise rows.
# Possible reason: bound scatter rendering and plot-data size.
CLUSTERING_PLOT_SAMPLE_SIZE: Final[int] = 5_000

# Maximum projection points prepared by multivariate_outliers; detection uses
# all complete rows. Possible reason: bound rendering and retained plot data.
MULTIVARIATE_OUTLIERS_PLOT_SAMPLE_SIZE: Final[int] = 5_000

# Histogram bins in outliers detail, consumed by app/export/report charts.
# All valid observations contribute. Possible reason: consistent plot detail.
OUTLIERS_HISTOGRAM_BINS: Final[int] = 50

# Maximum nonzero ACF lags requested by timeseries, further bounded by row count.
# Does not truncate the analyzed series or seasonal decomposition.
# Possible reason: a readable, bounded diagnostic horizon.
TIME_SERIES_MAX_ACF_LAGS: Final[int] = 40

# Retained observations and previews (also limit dependent exports/reports).

# Maximum ranked extreme rows retained per numeric column by outliers.
# Flagged totals use all valid rows; exported detail is not all flagged rows.
# Possible reason: bound detail-table size and memory.
OUTLIERS_MAX_EXTREME_OBSERVATIONS: Final[int] = 100

# Maximum ranked extreme rows retained by multivariate_outliers; independent
# of the univariate cap. Totals are complete; dependent detail exports are not.
# Possible reason: bound stored row payloads and detail-table size.
MULTIVARIATE_OUTLIERS_MAX_EXTREME_OBSERVATIONS: Final[int] = 100

# Leading rows captured by overview as a raw-data sample, not a full export.
# Reason: inspect parsing/encoding and values without duplicating the data grid.
OVERVIEW_SAMPLE_ROW_LIMIT: Final[int] = 100

# Rows at each end captured by overview's preview/export helpers and reports.
# Separate from the leading sample above; dependent outputs are previews.
# Possible reason: compactly show both the start and end of the dataset.
OVERVIEW_SAMPLE_DISPLAY_ROW_LIMIT: Final[int] = 10

# Algorithm parameter defaults and product bounds (these affect results).

# Initial k in clustering and its configuration widget.
# Possible reason: a small exploratory partition; minimum k=2 remains local.
CLUSTERING_DEFAULT_CLUSTER_COUNT: Final[int] = 3

# Maximum requested k in clustering validation and configuration.
# Possible reason: bound computation and result detail; rows also constrain k.
CLUSTERING_MAX_CLUSTER_COUNT: Final[int] = 100

# Initial DBSCAN neighborhood radius in clustering/configuration, in the units
# of the fitted features. Possible reason: a conventional exploratory start.
CLUSTERING_DEFAULT_DBSCAN_EPSILON: Final[float] = 0.5

# Minimum DBSCAN radius exposed by clustering/configuration, not a mathematical
# universal minimum. Possible reason: a practical positive input range.
CLUSTERING_MIN_DBSCAN_EPSILON: Final[float] = 0.01

# Maximum DBSCAN radius in clustering/configuration; not a statistical bound.
# Possible reason: a bounded UI range; appropriate radii depend on feature scale.
CLUSTERING_MAX_DBSCAN_EPSILON: Final[float] = 100.0

# Initial DBSCAN neighborhood population in clustering/configuration.
# Possible reason: a conventional starting density requirement.
# MIN_DBSCAN_MIN_SAMPLES remains with clustering's algorithm validation.
CLUSTERING_DEFAULT_DBSCAN_MIN_SAMPLES: Final[int] = 5

# Maximum DBSCAN neighborhood population in clustering/configuration.
# Possible reason: bound the selectable density requirement, not row count.
CLUSTERING_MAX_DBSCAN_MIN_SAMPLES: Final[int] = 100

# Initial expected anomaly fraction for multivariate_outliers/configuration.
# Possible reason: a small exploratory anomaly proportion; not a learned rate.
MULTIVARIATE_OUTLIERS_DEFAULT_CONTAMINATION: Final[float] = 0.05

# Minimum selectable anomaly fraction in multivariate_outliers/configuration.
# Stored as a fraction (GUI shows percent). Possible reason: practical UI range.
MULTIVARIATE_OUTLIERS_MIN_CONTAMINATION: Final[float] = 0.01

# Maximum anomaly fraction in multivariate_outliers/configuration (50%).
# Reason: compatible with the underlying estimators' contamination range.
MULTIVARIATE_OUTLIERS_MAX_CONTAMINATION: Final[float] = 0.5

# Initial neighborhood size for LOF in multivariate_outliers/configuration.
# Possible reason: a conventional exploratory local-density neighborhood.
# MIN_LOF_NEIGHBORS remains with the algorithm validation.
MULTIVARIATE_OUTLIERS_DEFAULT_LOF_NEIGHBORS: Final[int] = 20

# Maximum LOF neighbors in multivariate_outliers/configuration; usable row count
# also constrains the effective neighborhood. Possible reason: practical range.
MULTIVARIATE_OUTLIERS_MAX_LOF_NEIGHBORS: Final[int] = 100

# Default IQR fence multiplier used by outliers.DEFAULT_THRESHOLDS and its UI.
# Reason: Tukey's conventional 1.5-IQR exploratory fences.
OUTLIERS_DEFAULT_IQR_THRESHOLD: Final[float] = 1.5

# Default absolute Z-score cutoff in outliers.DEFAULT_THRESHOLDS and its UI.
# Reason: conventional three-standard-deviation screening.
OUTLIERS_DEFAULT_Z_SCORE_THRESHOLD: Final[float] = 3.0

# Default modified-Z cutoff in outliers.DEFAULT_THRESHOLDS and its UI.
# Reason: Iglewicz-Hoaglin's conventional 3.5 screening threshold.
OUTLIERS_DEFAULT_MODIFIED_Z_SCORE_THRESHOLD: Final[float] = 3.5

# Minimum fence multiplier/score cutoff in outliers validation/configuration.
# Possible reason: avoid zero/negative cutoffs and excessively sensitive input.
OUTLIERS_MIN_THRESHOLD: Final[float] = 0.1

# Maximum fence multiplier/score cutoff in outliers validation/configuration.
# Possible reason: bounded UI input, not a statistical maximum.
OUTLIERS_MAX_THRESHOLD: Final[float] = 100.0
