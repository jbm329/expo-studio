# Export a dataset

Export the rows and columns in a ready result tab when you want to keep a query
result, a cleaned dataset, or the output of a transformation.

## Save a result dataset

1. Select the ready result tab containing the dataset to save. Check the tab
   before exporting if you have several datasets open; the selected result is
   the one being exported.
2. Select **Export to CSV**, **Export to Excel** or **Export to data file** on
   the toolbar. You can also use **File → Export…** and choose the matching
   format.
3. Choose a destination and filename in the save dialog, then confirm the
   export. The file is written in a background operation.

The suggested filename is based on the active result tab. The save dialog lets
you choose where to save it. If you cancel the dialog, no export starts.

## Choose an output format

| Action | Output | Use it when |
|---|---|---|
| **Export to CSV** | Comma-separated UTF-8 text (`.csv`) | You need a broadly readable text table. |
| **Export to Excel** | Excel workbook (`.xlsx`) | You want to open the result as a spreadsheet. |
| **Export to data file** | Pickle (`.df`), Feather (`.feather`, `.ft`) or Parquet (`.parquet`) | You need a binary tabular format for another compatible tool or a later workflow. |

The binary format is chosen by the selected filename suffix. The export dialog
offers `.df`, `.feather`, `.ft` and `.parquet`; `.df` is the application's
Pickle-based DataFrame format. These output choices are not the same as the
formats available for opening files. For example, an input format being
supported does not mean Expo Studio can export it.

CSV exports use comma separators and UTF-8 encoding. The CSV reading settings
do not change these output defaults. To read CSV files with other delimiters or
encodings, see [CSV settings](../workbench/settings.md#csv-settings).

Excel writing follows the Excel settings. In streaming mode, a large dataset
can continue onto additional worksheets when it reaches the configured
per-sheet row limit; that limit includes each worksheet's header row. See
[Excel settings](../workbench/settings.md#excel-settings) for the row-batch,
streaming and worksheet-limit options. These settings affect future exports,
not datasets already open.

## Example: save a prepared summary

After you create a grouped summary in a new result tab, select that tab and
choose **Export to CSV** or **Export to Excel**. The saved file contains the
summary dataset. To save the individual analysis tables or charts instead, use
the analysis export workflow described in
[Export analysis results and reports](analysis-results-and-reports.md).
