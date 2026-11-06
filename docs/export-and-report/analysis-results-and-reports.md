# Export analysis results and reports

Analysis exports and HTML reports save results from Advanced analysis. They
are separate from [dataset exports](export-data.md), which save the rows and
columns in a result tab.

## Export an analysis result

1. Select a ready result tab and open **Analyze data**.
2. Configure the analysis and select **Apply** when required. Overview and
   Statistics calculate when opened.
3. After the analysis has a successful result, select **Export** and choose
   from the available tables, charts and file formats.

The choices depend on the analysis. Exports use the applied result, not edits
to settings that have not been applied. See the relevant
[analysis guide](../analyze-data/index.md#choose-an-analysis) for the outputs
available in that section. A selected table can be saved as CSV or a binary
data file; an Excel workbook can contain selected tables and available charts.
The [dataset export guide](export-data.md) describes the output formats.

For example, an Overview sample export contains the captured first and last
rows, not a full dataset export; see
[Overview sample and export limits](../analyze-data/overview.md#sample-limits).

## Build an HTML analysis report

Add a successfully calculated result to a report, then choose which parts to
include:

1. Select **Add to report** for a successful analysis result.
2. Open **Reports**. Select the content to include, arrange or remove entries,
   and add notes as needed.
3. Edit the report title or description, then preview the report.
4. Select **Generate HTML report** and choose where to save the HTML file.

Only successful analysis results can be added. The report is assembled from
the results you select; it does not replace the source dataset or include
every analysis automatically.

## Data profiling reports {#data-profiling-reports}

**External tools → Data profiling…** generates an HTML profile for the active
ready dataset. When multiple ready datasets are open, choose whether to profile
the active dataset or compare all open datasets. This tool requires the
optional profiling dependency.

Data profiling is separate from the HTML report assembled in **Reports**:
profiling describes dataset characteristics, while an analysis report contains
selected analysis results and notes.
