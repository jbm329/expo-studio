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
