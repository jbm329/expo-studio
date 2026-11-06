# Outliers

Use **Outliers** to flag potential outliers in individual numeric columns or
to detect unusual rows across several numeric features. A flagged value is a
prompt to investigate, not proof that the value is wrong.

## Screen columns individually {#univariate}

Keep **Mode** set to **Univariate (by column)**. Choose **IQR**,
**Z-score** or **Modified Z-score**, adjust the threshold if needed, and
select **Apply**.

| Method | Default | What is flagged |
|---|---:|---|
| IQR | 1.5 | Values strictly beyond Q1 − threshold × IQR or Q3 + threshold × IQR. |
| Z-score | 3.0 | Values whose absolute z-score is greater than the threshold. |
| Modified Z-score | 3.5 | Values whose absolute modified z-score is greater than the threshold. |

The threshold control accepts values from 0.1 to 100. Missing and infinite
values are ignored. A column needs at least three finite observations to be
screened; zero-spread data cannot produce a meaningful outlier screen.

The summary counts all flagged values. A column's detail retains at most
the 100 most extreme flagged rows, and its distribution chart uses 50
histogram bins. These limits do not reduce the screening counts.

## Screen rows across features {#multivariate}

Choose **Multivariate (by row)** to open the multivariate screen. Select
**Isolation Forest** or **Local Outlier Factor (LOF)**, choose at least two
numeric features and select **Apply**. You can choose whether to standardize
the features before fitting.

**Expected outliers** is the contamination setting: it ranges from 1% to
50% and defaults to 5%. It is an estimator setting, not a guarantee that
the data contains that exact proportion of errors. LOF's neighbor count
ranges from 2 to 100 and defaults to 20; the number of usable rows also
constrains the fit.

Rows with missing or infinite values in any selected feature are excluded.
At least three complete rows are required. The model screens all complete
rows, but the projection chart displays at most 5,000 points and the detail
table retains at most 100 of the most anomalous rows.

## Review results carefully {#review}

Investigate flagged rows in context before changing or removing data.
Univariate methods screen each numeric column independently; multivariate
methods consider feature combinations and can flag a row that is not
extreme in any one column.

After a successful screen, use **Export** to see the available summary,
detail and chart outputs. For shared export steps and report workflows, see
[Export data](../export-and-report/index.md).
