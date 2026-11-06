# Clustering

Use **Clustering** to group rows using numeric features when you do not have
a known target label. Select the method, feature columns and settings, then
select **Apply**.

## Configure a clustering {#configure}

At least two numeric features and two complete finite rows are required.
Initially, all available numeric columns are selected. Choose whether to
standardize each feature to zero mean and unit variance before fitting.
Standardization changes feature scales and is important when columns use
different units.

| Method | Settings |
|---|---|
| K-means | Number of clusters, default 3; accepted range 2–100. |
| Agglomerative | Number of clusters, default 3; accepted range 2–100. |
| DBSCAN | Neighborhood radius (**eps**), default 0.5 and range 0.01–100; minimum samples, default 5 and range 2–100. |

For K-means and Agglomerative, the requested number of clusters must also
be compatible with the usable row count. DBSCAN's radius is measured in the
selected feature space; its useful value depends on feature scaling and
data density. DBSCAN can label rows as noise rather than assigning every
row to a cluster.

## Interpret results and limits {#results}

Review cluster sizes, the silhouette score when it is defined, and the
projection plot together. The projection uses principal components to show
the selected features in two dimensions; it is a visual aid, not the
clustering space itself.

Missing or infinite values in any selected feature exclude that row. The
fit and silhouette calculation use the eligible data; the projection
displays at most 5,000 points. This plot limit does not cap the fit or
silhouette calculation. Silhouette is unavailable when the fitted labels
do not define a valid multi-cluster comparison.

## Export {#export}

After a successful fit, select **Export** for the available cluster-size,
model-summary and chart outputs. The projection may show a bounded sample
even when the exported model summaries cover the complete fit. For shared
export steps and report workflows, see
[Export data](../export-and-report/index.md).
