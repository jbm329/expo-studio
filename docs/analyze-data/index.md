# Overview

Use Advanced analysis to inspect a ready result dataset, compare groups,
measure relationships or fit statistical models. Choose a task below to find
the analysis guide for it.

## Choose a task {#choose-an-analysis}

<a id="section-guides"></a>

| Task | Guide |
|---|---|
| Inspect dataset structure, missingness, duplicates and sample rows | [Dataset Overview](overview.md) |
| Inspect one column's properties and distribution from its result header | [Column properties](overview.md#column-properties) |
| Summarize numeric columns and eligible category frequencies | [Statistics](statistics.md) |
| Compare groups, categorical associations or repeated measurements | [Hypothesis Tests](hypothesis-tests.md) |
| Measure pairwise relationships among numeric columns | [Correlation](correlation.md) |
| Model a numeric, binary, count or survival outcome from predictors | [Regression](regression.md) |
| Screen numeric columns or multivariate rows for potential outliers | [Outliers](outliers.md) |
| Group complete numeric rows without a target column | [Clustering](clustering.md) |
| Summarize variation across numeric features as principal components | [PCA](pca.md) |
| Explore the temporal patterns in a dated numeric series | [Time Series](time-series.md) |

## Use Advanced analysis {#open-advanced-analysis}

Column properties is a separate result-header workflow; it does not require
opening Advanced analysis.

Select the ready result tab you want to analyze, then choose **Analyze data** on
the toolbar. The dialog title identifies the source dataset. The selected
source remains fixed while you switch between analysis sections.

Select **Help** at the bottom left or press **F1** to open the guide for the
currently selected analysis. In **Hypothesis Tests**, Help opens the section
for the selected test, even before you select **Apply**. In **Reports**, it
opens the analysis exports and reports guide. **Export**, **Add to report**
and **Close** remain on the right. Help does not change configuration or run
an analysis. If the browser cannot be opened, a warning includes the manual URL.

Overview and Statistics calculate when opened. The other sections have
configuration controls; choose the inputs and select **Apply** to calculate.
An edit to an applied configuration makes the displayed result out of date
until you apply the new settings. A section can be unavailable for a dataset
that does not have the required column types or values.

To load or prepare data first, see [Get data](../get-data/index.md),
[Prepare data](../prepare-data/index.md) or
[Transform data](../transform-data/index.md).

## Understand limits before interpreting results {#analysis-limits}

Limits are specific to an analysis. Some determine which columns or settings
are accepted; others bound a preview, chart or retained detail without
truncating the underlying calculation. The section guides distinguish these
cases and list their numeric limits and defaults.

| Shared rule | Effect |
|---|---|
| Categorical eligibility is capped at 50 distinct non-missing values. | Group Comparison and Chi-square require 2–50 values in a grouping column; Regression excludes text, category and Boolean predictors above 50 levels. Statistics omits frequency summaries above 50 levels. Numeric summaries and Dataset Overview's type/count reporting are separate. |
| Regression accepts at most 20 selected predictors and 50 expanded non-intercept model terms. | A categorical predictor with *k* levels contributes *k − 1* terms, so the term cap may be reached before the predictor-count cap. |
| Several charts and detail tables use bounded samples. | Read the section guide to see whether the bound affects only presentation or also the analyzed data. |

These are application limits, not recommended statistical sample sizes or
guarantees that a model is appropriate for a dataset.

## Export results and prepare a report {#export-and-report}

For shared steps to export analysis outputs, assemble an HTML report or create
a data-profiling report, see
[Export analysis results and reports](../export-and-report/analysis-results-and-reports.md).
Each guide above describes its own available tables and charts.

## Continue your workflow

- [Prepare data](../prepare-data/index.md) or
  [Transform data](../transform-data/index.md) before analysis.
- [Export data](../export-and-report/index.md) to save datasets, analysis
  outputs or reports.
- See [Workbench window](../workbench/index.md) to orient yourself in the
  application.
