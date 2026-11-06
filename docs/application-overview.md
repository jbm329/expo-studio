# What you can do with Expo Studio

Use Expo Studio to bring tabular data from different sources into one desktop
workbench, review its quality, prepare it for analysis and share the results.
You can work with database query results, local data files and REST API
responses as result datasets.

For a tour of the menus, toolbar and panels, see
[Workbench window](workbench/index.md).

A typical workflow is **get data → review → clean and transform → analyze →
export and share**. Use only the steps you need: you can export a query result
directly, prepare a file without fitting a model, or analyze an already prepared
dataset.

## Get data from different sources {#get-data}

| Source | What you can work with |
|---|---|
| Databases | SQL Server, PostgreSQL, MySQL/MariaDB, SQLite and DuckDB. Browse the schema and run SQL against a configured connection to load query results. |
| Text and spreadsheet files | CSV (`.csv`) and Excel (`.xls`, `.xlsx`). |
| Binary data files | Parquet (`.parquet`), Feather (`.feather`, `.ft`) and Pickle/dataframe files (`.df`, `.pkl`). |
| Other analytical formats | Qlik QVD (`.qvd`), SPSS (`.sav`) and Stata (`.dta`). |
| REST APIs | Configured GET or POST requests whose supported JSON responses can be converted into tabular data. |
| Statistics Sweden (SCB) | Use the **SCB query builder…** in REST connection settings to browse tables and select variable values, then load the data through the REST connection. |

For step-by-step source workflows, see [Get data](get-data/index.md).

Database connections need the appropriate access and drivers. DuckDB connections
open an existing database file read-only. Opening a `.sql` file opens query text;
run the query against a connection to obtain a result dataset.

REST connections support authentication and page-number pagination when these
match the API's requirements. A response can contain records directly or inside
a configured response path. This does not mean that every API or response
structure is supported. JSON API responses are distinct from local JSON files,
which the normal **Open** workflow does not offer.

Use **Open** to load a supported data file. Loaded data and query results appear
in result tabs, so you can keep several datasets available while you work.
Import and export formats differ; opening a format does not mean you can write
that format back.

## Review and understand your data {#review-data}

Start by checking what the dataset contains before changing or analyzing it.
Sort rows, filter a column and open its **Properties** from the column-header
menu to inspect it more closely.

Select **Analyze data** on the toolbar for a ready result dataset:

- [Dataset Overview](analyze-data/overview.md) shows dataset size, column types,
  missing values, duplicate-row counts and bounded first/last row samples.
- [Statistics](analyze-data/statistics.md) provides numeric summaries,
  eligible categorical frequencies and distribution charts.

These checks help you identify missing information, unexpected types or values
and repeated records. Counting duplicate rows does not remove them.

## Clean and transform data {#clean-and-transform}

Right-click a column header to find preparation actions. Depending on the column
type and contents, you can:

- Trim or normalize whitespace, change text case, and replace or remove text.
- Fill missing values with a custom value or an available statistical fill.
- Convert data types, such as text to numbers or datetimes, and manage categories.
- Rename, reorder or remove columns, and split or merge text columns.

Use [Derived columns](transform-data/derived-columns.md) to create calculated
values from existing columns. For example, multiply a price by a quantity or
assign labels with a conditional formula.

Use [Reshape](transform-data/reshape.md) to group rows and calculate metrics such
as sums, averages or counts in a **new result dataset**. It summarizes data;
it is not a general pivot/unpivot or wide-to-long tool.

Preparation actions can change the dataset in the current result tab; not every
action creates a separate tab. Review the result and export the prepared dataset
when you want to keep it. The available actions depend on data types, selections
and whether the dataset has finished loading.

## Combine datasets {#combine-datasets}

Load the datasets you need into result tabs, then choose the operation that
matches your task:

| Action | Use it to |
|---|---|
| **Join datasets** | Match rows using one or more key columns and bring related columns together, such as sales and customer details. |
| **Concatenate datasets** | Append one dataset's rows to another, such as two monthly extracts. Columns align by name; unmatched columns have missing values. You can optionally remove duplicate rows. |

These operations create a new combined result dataset. A join matches keys;
concatenation stacks rows. Neither requires the original datasets to have come
from the same source.

## Analyze data and share findings {#analyze-and-share}

Select a ready result tab, then **Analyze data** to open
[Advanced analysis](analyze-data/index.md).

| Question | Analysis |
|---|---|
| What does the dataset contain, and how are values distributed? | Dataset Overview and Statistics |
| Do groups or repeated measurements differ, or are categories associated? | Hypothesis Tests |
| How are numeric variables related? | Correlation |
| How does an outcome relate to predictors? | Regression |
| Which values or rows might be unusual? | Outliers |
| Can numeric rows be grouped, or features reduced? | Clustering and PCA |
| How does a dated numeric series vary over time? | Time Series |

The analyses include their own tables, diagnostics and, where available, charts.
Required column types, settings and limits vary by analysis. The
[section guides](analyze-data/index.md#choose-an-analysis) explain how to
configure and interpret each one.

### Export analysis results

After a successful calculation, select **Export** in Advanced analysis.
Depending on the section and your selection, you can export result tables to
CSV or a binary data file, or put selected tables and available charts in an
Excel workbook. Exports use the applied result, not settings you have edited
but not yet applied.

### Build an HTML analysis report

Select **Add to report** for a successful analysis result. In **Reports**, choose
the content to include, arrange entries and add notes. You can edit the report
title and description, preview it and select **Generate HTML report** to save a
shareable report. See
[Export results and prepare a report](analyze-data/index.md#export-and-report).

There is also a separate **External tools → Data profiling…** workflow for
generating an HTML profile of one dataset or comparing ready datasets. This
optional tool requires the profiling dependency; it is distinct from the report
you assemble in Advanced analysis.

## Export prepared data {#export-data}

To save the data itself rather than an analysis, select the result tab you want
to export and use a toolbar export action:

| Action | Output |
|---|---|
| **Export to CSV** | CSV (`.csv`) |
| **Export to Excel** | Excel workbook (`.xlsx`) |
| **Export to data file** | Pickle (`.df`), Feather (`.feather`, `.ft`) or Parquet (`.parquet`) |

For example, export a cleaned file, a query result, joined data or a grouped
summary. Saving SQL text is not the same as exporting the dataset. Likewise,
an HTML analysis report shares selected findings rather than serving as a
replacement for a data export.

## Try a small sales workflow {#try-a-workflow}

This example turns three sales lines into totals by region. Save the following
text as `sales.csv`, then select **Open** to load it:

```csv
Region,Price,Quantity
North,12.50,2
North,8.00,3
South,20.00,1
```

1. Select the loaded result tab and wait for loading to finish. Use
   **Analyze data** to inspect Dataset Overview, then close Advanced analysis
   to return to the result table. Check that **Price** and **Quantity** have
   numeric types.
2. Right-click the **Quantity** column header and select **Derived column…**.
   Enter `Line total` as the **Column name** and `[Price] * [Quantity]` in
   **f(x)**, then select **OK**. The calculated values are **25**, **24** and
   **20**, in source-row order. See
   [Create your first derived column](transform-data/derived-columns.md#create-your-first-derived-column).
3. Select **Reshape**. Under **Dimensions**, check **Region**. Configure one
   metric with function **SUM**, source column **Line total** and
   **Metric name** `Total sales`. Leave its condition empty.
4. Select **Preview**, then **OK** to create the full summary in a new
   **Reshaped data** result tab. See
   [Create your first summary](transform-data/reshape.md#create-your-first-summary).

The summary contains:

| Region | Total sales |
|---|---|
| North | 49 |
| South | 20 |

Displayed number formatting may differ. The line-level dataset remains in its
own tab, including the derived column.

Select the summary tab and **Export to CSV** or **Export to Excel** to save it.
To explore the individual sales lines instead, select the original tab and
open **Analyze data → Statistics**. After it calculates successfully, use
**Add to report** and **Reports** to prepare an HTML report. This tiny example
demonstrates the workflow, not a basis for statistical conclusions.

## Continue with the guides {#continue}

For detailed steps, start with [Derived columns](transform-data/derived-columns.md),
[Reshape](transform-data/reshape.md) or
[Advanced analysis](analyze-data/index.md). [Home](index.md#available-guides)
lists all currently available guides.

This page is a capability overview, not a complete manual. Detailed source setup,
general cleaning, joining and dataset-export guides are not yet available.
