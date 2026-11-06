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

This manual is organized around common tasks: getting data, preparing and
transforming it, analyzing results, and exporting datasets or reports. Start
with a section overview to choose a workflow, then follow its task guides for
step-by-step instructions. The manual covers the workflows documented here;
it does not describe every feature, file format or service-specific behavior.

## Available guides

- [Workbench window](workbench/index.md) — locate the main controls, understand
  editor and result tabs, and adjust the layout.
- [Get data](get-data/index.md) — load data with database queries, supported
  local files, or configured REST requests.
- [Prepare data](prepare-data/index.md) — prepare a ready result dataset before
  analysis or export.
  - [Organize columns](prepare-data/organize-columns.md) — sort rows, rename or
    remove columns, and change column order.
  - [Clean values](prepare-data/clean-values.md) — clean text, replace values,
    fill missing entries, and convert data types.
  - [Filter rows](prepare-data/filter-rows.md) — keep or remove rows using a
    column filter or a selected cell's value.
- [Transform data](transform-data/index.md) — create calculated columns and
  summary datasets, or combine datasets.
  - [Derived columns](transform-data/derived-columns.md) — calculate new values
    with formulas, conditions and date/time functions.
  - [Reshape](transform-data/reshape.md) — group rows and calculate summary
    metrics.
  - [Join datasets](transform-data/join.md) — match rows using key columns.
  - [Concatenate datasets](transform-data/concatenate.md) — append rows from
    two result datasets.
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
- [Analyze data overview](analyze-data/index.md) — choose an analysis for a
  ready result dataset and find the guide for its inputs and results.
- [Export data](export-and-report/index.md) — save datasets, analysis results
  and HTML reports.
  - [Export a dataset](export-and-report/export-data.md) — save a result tab as
    CSV, Excel or a binary data file.
  - [Export analysis results and reports](export-and-report/analysis-results-and-reports.md)
    — save analysis outputs or create HTML reports.
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
Detailed guides for additional workflows and individual file formats are not
yet available. Navigation will grow as more guides are added.