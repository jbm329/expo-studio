# Correlation

Use **Correlation** to calculate pairwise associations among numeric
columns. Choose a method and the columns for the matrix, then select
**Apply**.

## Configure a correlation matrix {#configure}

Select **Pearson**, **Spearman** or **Kendall**. The initial selection is
the first 20 numeric columns in dataset order. Select at least 2 and at
most 30 numeric columns; use **Select all** or **Clear** to adjust the
selection.

The matrix lists each pair's coefficient, p-value, 95% confidence interval
when defined, and Holm-adjusted p-value. Pairs are ranked by absolute
coefficient. Select a pair to inspect its details and scatterplot.

Pearson measures linear association; Spearman uses ranks, and Kendall
measures rank association. Correlation does not establish causation.

## Missing values and undefined results {#missing-values}

Each pair uses rows where both values are finite and reports its own
observation count. Fewer than three usable values or a constant input makes
the coefficient undefined for that pair. The matrix can still display
other defined pairs.

## Display limits {#display-limits}

Pair statistics use all finite paired rows. The pair scatterplot displays
at most 5,000 points; larger pairs use a deterministic sample. The matrix
can contain up to 30 columns, but cell-value annotations are shown only
when the matrix has at most 12 columns. These are chart readability limits,
not calculation limits.

## Export {#export}

After a successful matrix calculation, select **Export** to review available
correlation tables and charts. The export corresponds to the applied
method and matrix selection. For shared export steps and report workflows, see
[Export data](../export-and-report/index.md).
