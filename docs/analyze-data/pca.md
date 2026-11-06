# PCA

Principal component analysis (**PCA**) combines numeric features into
components that summarize variation in the selected columns. It does not
use a target column or assign class labels.

## Configure PCA {#configure}

Select at least two numeric features. By default, every numeric column is
selected and **Standardize features** is enabled. Standardization centers
and scales each selected feature before fitting; leave it off only when
using the original feature scales is intentional.

Select **Apply** to calculate PCA. At least two complete finite rows are
required. A row missing or containing an infinite value in any selected
feature is excluded from the fit.

## Read variance, loadings and the plot {#interpret}

Review the explained-variance and cumulative-variance results to see how
much of the selected data's variation each component accounts for. The
feature loadings describe how the original selected columns contribute to
the components. A loading is not a causal effect.

The PC1-versus-PC2 scatterplot displays at most 5,000 complete rows. PCA
is fitted using all complete selected rows; only the scatterplot is sampled.
The explained variance and loadings are calculated from the full fit.

## Export {#export}

After a successful fit, select **Export** for the available explained
variance, feature-loading and chart outputs. For shared export steps and
report workflows, see [Export data](../export-and-report/index.md).
