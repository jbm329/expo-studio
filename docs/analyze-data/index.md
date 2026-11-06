# Advanced analysis

Advanced analysis calculates summaries and statistical models from a ready
result dataset. It keeps the selected source dataset fixed while you switch
between analysis sections.

## Open Advanced analysis {#open-advanced-analysis}

1. Select the result tab containing the dataset you want to analyze.
2. Wait until the dataset has finished loading.
3. Select **Analyze data** on the toolbar.

The dialog title shows the source dataset name, row count and column count.
Advanced analysis is unavailable until a ready result dataset is active.
To load or prepare data first, see [Get data](../get-data/index.md),
[Prepare data](../prepare-data/index.md) or
[Transform data](../transform-data/index.md).

## Choose an analysis {#choose-an-analysis}

The category row at the top of the workspace contains these analyses:

| Analysis | Use it to |
|---|---|
| [Dataset Overview](overview.md) | Check dataset size, column types, missing values, duplicates and sample rows. |
| [Statistics](statistics.md) | Summarize numeric columns and review eligible category frequencies. |
| [Hypothesis Tests](hypothesis-tests.md) | Compare numeric groups, categorical associations or repeated measurements. |
| [Correlation](correlation.md) | Measure pairwise relationships among numeric columns. |
| [Regression](regression.md) | Model a numeric, binary, count or survival outcome from predictors. |
| [Outliers](outliers.md) | Screen individual numeric columns or multivariate rows for potential outliers. |
| [Clustering](clustering.md) | Assign complete numeric rows to groups without a target column. |
| [PCA](pca.md) | Summarize variation across numeric features as principal components. |
| [Time Series](time-series.md) | Prepare a dated numeric series and inspect its temporal patterns. |

Overview and Statistics calculate when opened. The other sections have
configuration controls; choose the inputs and select **Apply** to calculate.
An edit to an applied configuration makes the displayed result out of date
until you apply the new settings. A section can be unavailable for a dataset
that does not have the required column types or values.

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
The available tables and charts are specific to each analysis; the section
guides below describe those outputs.

## Section guides {#section-guides}

- [Dataset Overview](overview.md)
- [Statistics](statistics.md)
- [Hypothesis Tests](hypothesis-tests.md)
- [Correlation](correlation.md)
- [Regression](regression.md)
- [Outliers](outliers.md)
- [Clustering](clustering.md)
- [PCA](pca.md)
- [Time Series](time-series.md)
