# Open a local file

Use **Open** on the toolbar or **File → Open**, or double-click a supported data
file in the workbench's **Files** panel. Opening a data file creates a result
tab. The Files panel shows the configured documents directory; change it in
[Settings](../workbench/settings.md#basic-settings).

## Supported data-file formats

| File type | Supported suffixes |
|---|---|
| CSV | `.csv` |
| Excel | `.xls`, `.xlsx` |
| Parquet | `.parquet` |
| Feather | `.feather`, `.ft` |
| Pickle/dataframe | `.df`, `.pkl` |
| Qlik QVD | `.qvd` |
| SPSS | `.sav` |
| Stata | `.dta` |

Importing is not the same as exporting: the supported output formats are
different. For CSV reading options such as delimiter detection and encoding,
see [CSV settings](../workbench/settings.md#csv-settings). For supported
outputs, see [Export a dataset](../export-and-report/export-data.md).

## Other file types

The **Open** command also accepts other file types with different behavior:

- A `.sql` file opens its text in an editor tab. It does not execute the query;
  associate the tab with a database connection before running it. See
  [Load data with SQL](sql-queries.md).
- An `.html` or `.htm` file opens in your default browser, not as a dataset.
- A local `.json` file is not supported by this Open workflow. JSON returned by
  a configured REST request is a separate workflow; see
  [Load a REST response](rest-api.md).

## Continue your workflow

- [Get data overview](index.md) for database and REST loading.
- [Prepare data](../prepare-data/index.md) or
  [Transform data](../transform-data/index.md) to work with the loaded dataset.
- [Analyze data](../analyze-data/index.md) or
  [Export data](../export-and-report/index.md) when it is ready.
