# Open a local file

Use **Open** on the toolbar or **File → Open**, or double-click a supported data
file in the workbench's **Files** panel. Opening a data file creates a result
tab. The Files panel shows the configured documents directory; change it in
[General settings](../settings/general-settings.md#basic-settings).

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
see [CSV settings](../settings/general-settings.md#csv-settings). For supported
outputs, see [Export a dataset](../export-and-report/export-data.md).

## CSV datatypes

CSV loading infers datatypes from the parsed values. Integer columns containing
missing values use pandas nullable `Int64`; boolean columns use nullable
`boolean`. Complete integer and boolean columns retain native storage. These
rules apply to the final dataset, including files read in chunks.

For example, `1`, a blank entry and `2` load as `Int64`; `True`, a blank entry
and `False` load as `boolean`. A numeric `0`/`1` column remains integer, not
boolean. Decimal values such as `1.0` and `2.0` remain floating-point, even
when they have no fractional part. Columns with only missing entries remain
`float64` because there is no evidence of an integer or boolean type.

Integer values are preserved without an intermediate floating-point conversion.
Nonnegative integers above the signed 64-bit range, up to
`18446744073709551615`, use `UInt64` when missing values require it and native
`uint64` when complete. The unsigned-only recovery also recognizes the usual
CSV missing tokens, such as blank entries, `NA` and `NULL`. Mixed or
out-of-range values are not silently converted to missing values.

Text remains object-backed and floating-point columns remain `float64`.
This CSV policy does not change the loading rules for other file formats.

## Excel datatypes and limitations

For `.xlsx` files, integer cells mixed with missing cells load as nullable
`Int64` (or `UInt64` for nonnegative values above the signed range). Boolean
cells mixed with missing cells load as nullable `boolean`. Complete columns
retain native integer/boolean storage. Text, dates, mixed-value columns and
columns containing only missing cells retain their existing inference.

Inference uses the stored cell values returned by the workbook reader, not
the displayed number format. Text such as `001` or `NA` remains text.
Floating-point cell values are not reclassified merely because they have
no fractional part; however, a workbook may store `1.0` as an integer token.
Integer precision is preserved during loading, but precision already lost
when a spreadsheet application saved the workbook cannot be recovered.

**Legacy `.xls` limitation:** although `.xls` is listed by the file workflow,
the current openpyxl reader cannot load this format. Save the workbook as
`.xlsx` before opening it. This change does not add legacy `.xls` support.

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
