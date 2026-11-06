# Statistics

Use **Statistics** to summarize numeric columns, inspect distributions and
review category frequencies. It runs automatically when selected.

## Review numeric summaries {#numeric-summaries}

The **Continuous** table reports the non-missing count, missing count, mean,
median, sample standard deviation and variance, minimum, maximum, range,
quartiles, interquartile range, skewness and kurtosis for each numeric
column. Select a numeric row to inspect its histogram, boxplot and
Shapiro-Wilk normality result.

When Shapiro-Wilk provides a usable result, **Mean ± SD** is suggested if
the p-value is at least 0.05; **Median (Q1 to Q3)** is suggested if it is
below 0.05. If the test cannot provide a usable recommendation, neither
summary is starred. This is a presentation suggestion, not proof that a
distribution is normal or a replacement for choosing a method appropriate
to your question.

Shapiro-Wilk needs at least three non-missing values and cannot provide a
useful recommendation for a constant column. Above 5,000 observations, its
p-value may be inaccurate; the application displays this caveat. The other
descriptive statistics are not limited to 5,000 rows.

## Review category frequencies {#category-frequencies}

The **Categorical** table shows each eligible value's count and percentage
among non-missing values, plus the missing count. Text, category and Boolean
columns are eligible, as are numeric columns with at most 50 distinct
non-missing values. Columns with more than 50 distinct values are omitted
from the frequency summaries; their numeric descriptive statistics remain
available when they are numeric.

An empty result can mean there are no numeric columns and no eligible
categorical columns, or that the dataset has no non-missing values to
summarize.

## Export {#export}

Select **Export** to choose available continuous or categorical tables and
charts. Exports reflect the displayed Statistics result. The frequency
eligibility limit is 50 distinct values; it does not cap numeric summary
calculations. For shared export steps and report workflows, see
[Export data](../export-and-report/index.md).
