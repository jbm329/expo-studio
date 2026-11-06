# Hypothesis Tests

**Hypothesis Tests** contains **Group Comparison**, **Chi-square** and
**Paired Comparison**. Choose a test in the **Test** selector, configure its
columns and select **Apply**. A test is unavailable when the dataset lacks
the required eligible columns.

## Group Comparison {#group-comparison}

Choose a numeric **Numeric column** and a **Grouping column** whose values
define the groups. The grouping column must contain 2–50 distinct
non-missing values. Numeric and nonnumeric columns can be grouping columns
when they meet that distinct-value limit.

For two groups, results include Welch's t-test, Student's equal-variance
t-test and Mann–Whitney U. For more than two groups, results include
one-way ANOVA and Kruskal–Wallis. The view also reports group summaries and
normality checks; it does not choose one test for you. Numeric missing or
infinite values are excluded from the comparison, and group counts show how
many observations contribute.

Some summaries need at least two observations in a group to calculate a
sample standard deviation and at least three to calculate Shapiro-Wilk.
The normality p-value may be inaccurate above 5,000 observations.

## Chi-square {#chi-square}

Choose two categorical columns as the **Row variable** and **Column
variable**. Each must have 2–50 distinct non-missing values. Rows missing
either selected value are excluded.

The result includes the observed and expected contingency tables, Pearson's
chi-square test and Cramér's V. For a 2-by-2 table, it also reports Fisher's
exact test and applies Yates' continuity correction to Pearson's test. The
view warns when Cochran's rule of thumb is violated: more than 20% of
expected counts are below 5, or any expected count is below 1. Treat this
as a caveat about the chi-square approximation.

Adjusted residuals help identify cells that depart from independence; an
absolute adjusted residual greater than 1.96 marks a cell as different at
the 5% level. The heatmap annotates at most 100 cells; this display limit
does not truncate the contingency table or change the test.

## Paired Comparison {#paired-comparison}

Use this test when each row represents one subject and each selected numeric
column represents a repeated measurement occasion. Select at least two
columns. Their order in the checklist is the occasion order; chronological
order is not inferred.

With exactly two columns the application runs a Wilcoxon signed-rank test.
With three or more it runs a Friedman test, which requires at least three
complete subjects. A subject missing any selected value is excluded from
the paired test and summaries.

Boxplots and test summaries use all complete subjects. The trajectory chart
shows at most 200 complete subjects; when there are more, it uses a
deterministic sample and indicates that it is sampled.

## Review and export {#review-and-export}

Read the complete-case counts, test statistics, p-values, effect sizes and
any warnings together. Group Comparison uses a 0.05 significance level for
its group normality verdicts and reports 95% confidence intervals for
two-group mean differences. Statistical significance does not establish
practical importance or prove a causal relationship.

After a successful **Apply**, select **Export** for the available result
tables and charts. The chi-square heatmap's 100-cell annotation limit and
the paired chart's 200-trajectory limit apply to presentation, not to the
test calculations. For shared export steps and report workflows, see
[Export data](../export-and-report/index.md).
