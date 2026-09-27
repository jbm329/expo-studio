# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Advanced Analysis workspace: the "Overview" category now shows a
  structural summary of the selected dataset (row/column counts, missing
  values, duplicate rows, and a breakdown of column counts by type), with
  columns above a missing-value threshold flagged as potential issues.
- Advanced Analysis workspace: the "Statistics" category now shows a
  dataset-wide descriptive statistics table (count, missing, mean, median,
  standard deviation, variance, min, max, range, quartiles, IQR, skewness,
  kurtosis) for every numeric column, plus a histogram/boxplot pair and a
  Shapiro-Wilk normality test for one column at a time, selectable via a
  new configuration pane.
- Advanced Analysis workspace: new "Hypothesis Tests" category with a
  Group Comparison analysis - compares a numeric column across the groups
  of another column using Welch's t-test and Mann-Whitney U (exactly two
  groups) or one-way ANOVA and Kruskal-Wallis (more than two groups).
  Shows both the parametric and non-parametric result side by side, with
  confidence intervals, effect sizes (Cohen's d, rank-biserial correlation,
  eta-squared, epsilon-squared), a per-group boxplot, and each group's own
  Shapiro-Wilk normality check used as explicit guidance for which result
  to trust.
- Advanced Analysis workspace: chi-square test of independence in the
  "Hypothesis Tests" category, selected via a new "Test" dropdown in the
  configuration pane. Shows the observed contingency table with totals,
  chi-square/df/p (Yates-corrected for 2x2 tables), Cramér's V, Fisher's
  exact test for 2x2 tables, a heatmap of adjusted standardized residuals
  showing which cells drive the association, and a warning when Cochran's
  rule for expected counts is violated. Columns that can't be used as a
  categorical variable (fewer than 2 or more than 20 distinct values) are
  still listed in the column pickers - also Group Comparison's grouping
  column - but disabled, with a tooltip explaining why.
- Advanced Analysis workspace: new "Correlation" category (Correlation
  Explorer). Computes Pearson, Spearman or Kendall's tau-b correlations
  between numeric columns (the first 20 by default, up to 30 selectable)
  with pairwise deletion of missing values. Shows a heatmap of the matrix,
  a table of every pair ranked by strength with its 95% confidence
  interval, p-value, Holm-adjusted p-value and n, and a scatterplot with a
  least-squares line and statistics for a selected pair (chosen via X/Y
  pickers or by clicking a table row; large datasets are plotted as a
  5,000-point sample while statistics use every row). The matrix job
  reports its progress and can be cancelled from the busy overlay.
- Advanced Analysis workspace: new "Regression" category with multiple
  linear regression (ordinary least squares). Choose a numeric target and
  up to 20 numeric or categorical predictors; categorical predictors are
  dummy-coded against their most frequent level, which is shown as the
  reference. Shows the model summary (rows used/dropped, R-squared,
  adjusted R-squared, F test, RMSE, AIC), a coefficient table with standard
  errors, t, p, 95% confidence intervals and VIF, diagnostics with verdicts
  (Breusch-Pagan, Jarque-Bera, Durbin-Watson, largest VIF), warnings for
  likely problems, and residuals-vs-fitted, actual-vs-predicted and normal
  Q-Q plots (sampled to 5,000 points on large datasets). Models are fitted
  in a background job with a busy overlay.
- New dependency: `statsmodels` (used for linear regression).

### Changed
- Advanced Analysis workspace: added a dedicated configuration pane
  (right-hand side) for analysis categories that need user input, such as
  the Statistics category's column picker.
- Advanced Analysis workspace: analyses now always run as background jobs
  with a busy overlay shown over the result pane, so large datasets no
  longer freeze the application while an analysis is computed. For
  analyses whose configuration selects *what* to compute (e.g. Group
  Comparison's column pickers), changing the configuration now also
  triggers a fresh background computation instead of only redrawing
  already-computed data.

### Fixed
- Standard dialog buttons using the "Close" role (Advanced Analysis
  workspace, Column properties) now correctly localize with the
  application's active language instead of always showing English text.
- Advanced Analysis workspace: removed a leftover "Select an analysis from
  the list on the left" message that could never be reached now that an
  analysis category (Overview) is always selected by default.

### Removed
- Removed the legacy "Visualize data" dialog and its chart-configuration
  workflow, in preparation for a new Advanced Analysis workspace.

## [1.0.0] - 2026-09-13

### Added
- Initial release.
