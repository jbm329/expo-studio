# Dataset Overview

Use **Overview** for a structural check of the selected dataset. It reports
the number of rows and columns, missing cells, duplicate rows and a breakdown
of columns by semantic type. It does not identify relationships or perform
outlier screening; use [Statistics](statistics.md), [Correlation](correlation.md)
or [Outliers](outliers.md) for those analyses.

## Review the dataset summary {#review-the-summary}

1. Open [Advanced analysis](index.md#open-advanced-analysis) for a ready
   result dataset.
2. Select **Overview**. It calculates automatically.
3. Read **Dataset statistics**, **Column types** and **Potential issues**.
4. Review the **Columns metadata** table for each column's semantic type,
   storage type, missing count and percentage, and distinct non-missing count.
5. Use the **Sample** tabs to inspect the first and last rows.

The semantic type groups columns as Integer, Float, Boolean, Datetime, Text,
Category or Other. The storage type shows the underlying dtype. The unique
count does not include missing values.

## Interpret the potential-issues notice {#potential-issues}

Overview flags a column when at least 20% of its values are missing. This is
a data-quality prompt, not a judgment that the column should be removed.
Review the column and decide whether its missingness is expected for your
analysis.

The duplicate-row count is for fully duplicated rows; repeated values in an
individual column do not by themselves make a row duplicate.

## Sample and export limits {#sample-limits}

Overview captures up to the first 100 source rows for its bounded sample
snapshot. The on-screen sample previews up to 10 rows from the beginning and
up to 10 from the end. Small datasets can appear in both previews. These
limits do not reduce the row, missing-cell, duplicate or per-column counts.

Select **Export** for the available **Summary**, **Columns** and **Sample**
tables. Sample exports contain captured first/last rows, not a full data
export. Depending on the selection, samples can be combined or split into
separate tables. For shared export steps and report workflows, see
[Export data](../export-and-report/index.md).

## Empty datasets {#empty-datasets}

Overview can describe datasets with no rows or no columns. When no columns
exist, there is no column table to export; when there are no rows, the sample
is empty while dataset metadata remains available.

## Inspect column properties {#column-properties}

Use **Properties** for a closer look at one column without changing the
dataset. This is a separate dialog opened from a result tab, not from the
**Columns metadata** table in Advanced analysis.

### Open Properties {#open-column-properties}

1. Select a ready result tab.
2. Right-click the header of the column you want to inspect and select
   **Properties**. The action is unavailable when multiple columns are selected.
3. If profiling is needed, wait for **Profiling column: …** to finish.
4. Review **Properties - column name**, then select **Close** when finished.

Profiling runs in the background. Opening or closing Properties does not
convert types, clean values or modify the source file or database.

### Read the summary {#column-properties-summary}

The header shows **Type** and the underlying storage dtype in parentheses.
The type is a simplified classification such as `int`, `float`, `bool`,
`datetime`, `string`, `category` or `other`. A type/storage warning, if shown,
is a prompt to review conversion; opening Properties does not perform it.
Do not rely on this dialog to recognize numbers or dates stored as text.
See [Clean values](../prepare-data/clean-values.md) for conversion workflows.

| Property | Meaning |
|---|---|
| Rows / Count (n) | All rows in the column, including missing values. |
| Missing | Missing count and percentage of all rows. |
| Unique | Distinct non-missing values and their count divided by the number of non-missing rows. This is not the percentage of values occurring only once. |
| Memory (bytes) | The column's in-memory usage, including its index; the value may be displayed in KB or larger units. It is not the source file size. |
| Constant | `True` when there is at most one distinct non-missing value, including an empty or all-missing column. |
| Sample values | Up to three distinct non-missing examples in source order, not a random sample. |

### Interpret properties and charts {#column-properties-details}

The read-only **Property / Value** table and chart depend on the column type.

| Column type | Available detail |
|---|---|
| Numeric | Minimum, Q1, median, Q3, maximum, mean, sample standard deviation, unscaled median absolute deviation (MAD), skewness, kurtosis, and zero/negative/positive counts and percentages; **Histogram**. |
| Boolean | True and false counts and percentages; **Distribution**. |
| Datetime | Minimum and maximum datetime, **Span (seconds)** between them; **Weekday distribution**. |
| Text | **Top 3** values with counts, minimum/median/maximum/mean text length, and **Empty strings (n)** when nonzero; **Top values** chart. |
| Category | Common summary properties plus the number of defined categories, whether they are ordered, and storage metadata. Category columns do not currently receive Top 3, text-length statistics or a chart in this dialog. |
| Other | Common summary properties where profiling is supported; no type-specific chart. |

Numeric statistics and histograms exclude missing and infinite values.
Zero, negative and positive percentages use the remaining numeric values
as their denominator. Boolean percentages use non-missing rows. Numeric
standard deviation is zero for a single usable value; statistics that cannot
be calculated can be blank.

**Empty strings (n)** currently counts missing text values as well as
zero-length strings. It does not count whitespace-only strings. Text lengths
exclude missing values; **Length median** is displayed as an integer.

The histogram uses the integer part of the square root of the usable numeric
count, bounded to 5–30 bins. Text previews show only the three most frequent
values, with chart labels shortened after 18 characters. These presentation
limits do not restrict the rows used to calculate statistics. The 50-value
eligibility limit in [Statistics](statistics.md#category-frequencies) does not
limit this dialog's Top 3 text preview.

Empty or all-missing columns have no distribution chart or type-specific
statistics. If binary values are detected, the dialog warns that the column
cannot be profiled; only the row count and binary-data notice are supplied.
The header's missing and unique zeros in that case are not a completed
missingness or uniqueness analysis. If Matplotlib is unavailable, the dialog
shows **Plot not available (matplotlib missing).**

### Try a numeric example {#column-properties-example}

Save this as a CSV file and [open it](../get-data/local-files.md). The final
row has a missing **Amount**, not a zero.

```csv
Record,Amount
1,0
2,2
3,2
4,4
5,8
6,
```

Open **Properties** for **Amount**. Expect 6 rows, 1 missing value (16.67%)
and 4 distinct non-missing values (80.00% of the 5 non-missing rows).
The minimum is 0, Q1 is 2, median is 2, Q3 is 4, maximum is 8 and mean is
3.2. **Zeros (n)** is 1 (20.00%), **Negatives (n)** is 0 (0.00%) and
**Positives (n)** is 4 (80.00%). The histogram contains five observations
in five bins. Decimal separators and displayed precision follow the local
number formatting.

### Copy the property table {#copy-column-properties}

Select **Copy as Markdown** to place the formatted **Property / Value**
table on the clipboard, then paste it into a Markdown document. The copy
does not include the column name, type header, sample-values line or chart.
It is not a full-precision data export or an Advanced analysis report item.
For those workflows, see [Export data](../export-and-report/index.md).
