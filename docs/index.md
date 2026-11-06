# Expo Studio User Manual

<figure style="text-align: left; margin-left: 0;">
  <img src="assets/splash.png" alt="Expo Studio" width="600">
</figure>

Practical guidance for working with your data in Expo Studio.

Start with [What you can do with Expo Studio](application-overview.md) for an
overview of data sources, reviewing and preparing datasets, analysis, reports
and exports. Read [Workbench window](workbench/index.md) to find your way around
the menus, toolbar, source panels and editor/result areas.

## About this manual

This manual is being written a section at a time. The application overview
introduces the main capabilities; the guides below explain selected workflows
in detail. It is not yet a complete guide to the application.

## Available guides

- [Workbench window](workbench/index.md) — locate the main controls, understand
  editor and result tabs, and adjust the layout.
- [Get data](get-data/index.md) — load data with database queries, supported
  local files, or configured REST requests.
- [Settings](workbench/settings.md) — configure application preferences, CSV and
  Excel processing, undo limits and schema caching.
- [Log settings](workbench/log-settings.md) — configure diagnostic log levels,
  output destinations and file rotation.
- [Database connections](workbench/database-connections.md) — configure and test
  named database connections, choose drivers and authentication, and connect
  to local SQLite or read-only DuckDB files.
- [REST API connections](workbench/rest-api-connections.md) — configure JSON
  requests, authentication and pagination, and generate SCB request syntax
  with the query builder.
- [Advanced analysis](analyze-data/index.md) — choose an analysis for a ready
  result dataset, work with its settings and results, and build an HTML report.
- [Dataset Overview](analyze-data/overview.md) — inspect dataset structure,
  missing values, duplicate rows and bounded first/last samples.
- [Statistics](analyze-data/statistics.md) — review numeric summaries,
  categorical frequencies, distributions and normality results.
- [Hypothesis Tests](analyze-data/hypothesis-tests.md) — compare groups,
  categorical associations and repeated measurements.
- [Correlation](analyze-data/correlation.md) — calculate and interpret
  Pearson, Spearman or Kendall correlations.
- [Regression](analyze-data/regression.md) — fit linear, logistic, count or
  Cox regression models and review their diagnostics.
- [Outliers](analyze-data/outliers.md) — screen numeric columns or rows for
  potential univariate and multivariate outliers.
- [Clustering](analyze-data/clustering.md) — group numeric rows with K-means,
  DBSCAN or agglomerative clustering.
- [PCA](analyze-data/pca.md) — reduce numeric features to principal
  components and inspect explained variance and loadings.
- [Time Series](analyze-data/time-series.md) — prepare one dated numeric
  series, inspect autocorrelation and optionally decompose seasonality.
- [Derived columns](transform-data/derived-columns.md) — create your first
  calculated column, write conditional formulas, work with dates and missing
  values, and troubleshoot formula errors.
- [Reshape](transform-data/reshape.md) — group rows, calculate metrics, build
  conditions, and preview a new summary dataset.

Detailed file-format setup, general cleaning, dataset-combination and
dataset-export guides are not yet available. Navigation will grow as more
guides are added.