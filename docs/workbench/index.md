# Workbench window

The workbench is Expo Studio's main window. Source panels are on the left,
SQL editor tabs are in the upper-right area, and result tabs are below them.
Use this page to orient yourself; task-specific instructions live in the
[Get data](../get-data/index.md), [Prepare data](../prepare-data/index.md),
[Transform data](../transform-data/index.md) and
[Export data](../export-and-report/index.md) guides.

## Find your way around {#window-layout}

![Expo Studio workbench with menus and toolbar at the top, three source panels on the left, empty editor and result areas on the right, and a status bar at the bottom.](../assets/workbench/main_window.png)

*The workbench before any editor or result tabs are open. The upper blank area
is for SQL editor tabs; the lower blank area is for result datasets. Connection
names and files depend on your configuration.*

| Area | Where to find it | Purpose |
|---|---|---|
| Menu bar | Across the top | Open files, access tools and configure the application. |
| Toolbar | Below the menu bar | Access common query, dataset, preparation and analysis actions. |
| Source panels | Left side | Browse database connections, files and REST requests. |
| SQL editor area | Upper right | Work with SQL editor tabs. |
| Result area | Lower right | View datasets loaded or created in the workbench. |
| Status bar | Along the bottom | Read operation status and selected-dataset dimensions. |

## Use the menu bar {#menu-bar}

The menu bar groups file actions, editor actions, application tools and help.
Use the links below for details on the task behind each command:

| Menu | Where to find task guidance |
|---|---|
| **File** | [Open local data](../get-data/local-files.md), [export a dataset](../export-and-report/export-data.md), or save SQL text in an editor tab. |
| **Edit** | Editor actions such as clearing SQL text. |
| **Tools** | [Settings](../settings/index.md), including [general settings](../settings/general-settings.md), [log settings](../settings/log-settings.md), [database connections](../settings/database-connections.md) and [REST API connections](../settings/rest-api-connections.md). |
| **External tools** | [Data profiling reports](../export-and-report/analysis-results-and-reports.md#data-profiling-reports). |
| **Help** | Application information. |

## Change application settings {#settings}

Use **Tools → Settings…** for application preferences and file-processing
options. See [General settings](../settings/general-settings.md) for field
descriptions.

Use **Tools → Log settings…** to configure diagnostic logging. See
[Log settings](../settings/log-settings.md) for details.

## Use the toolbar {#toolbar}

The toolbar provides shortcuts for common workbench actions:

| Action group | Examples |
|---|---|
| Files and queries | Open files, edit SQL and run queries. |
| Dataset export | Save the selected result dataset in a supported output format. |
| Dataset operations | Prepare, combine, reshape or analyze result datasets. |
| Display and history | Change table presentation, refresh schema metadata or undo an available dataset change. |

Which actions are available depends on the active editor or result tab and
whether its data or connection is ready. For complete workflows, see
[Get data](../get-data/index.md),
[Prepare data](../prepare-data/index.md),
[Transform data](../transform-data/index.md),
[Analyze data](../analyze-data/index.md) and [Export data](../export-and-report/index.md).

## Browse the source panels {#source-panels}

The left side contains panels for database connections, local files and REST
request presets. Use the corresponding guides for configuration and loading:

### Database connections

Configure named connections in
[Database connections](../settings/database-connections.md),
then follow [Load data with SQL](../get-data/sql-queries.md) to load
query results.

### Files

Use the **Files** panel to browse the configured documents directory. For
supported formats and opening behavior, see [Open a local file](../get-data/local-files.md).

### REST connections

Configure requests in
[REST API connections](../settings/rest-api-connections.md), then
follow [Load a REST response](../get-data/rest-api.md) to load its data.

## Work with SQL editor tabs {#sql-editor}

The upper area contains SQL editor tabs. Each tab holds query text and its
connection association. For opening, associating and running a query, see
[Load data with SQL](../get-data/sql-queries.md).

## Work with result tabs {#result-tabs}

The lower area contains datasets loaded from files, database queries or REST
requests, along with datasets produced by transformations. Select a ready
result tab to work with its data.

- [Prepare data](../prepare-data/index.md) to clean, filter or organize columns.
- [Transform data](../transform-data/index.md) to create columns, reshape or
  combine datasets.
- [Analyze data](../analyze-data/index.md) to inspect data or calculate results.
- [Export data](../export-and-report/index.md) to save a dataset, analysis
  outputs or reports.

## Read the status bar {#status-bar}

The bottom-left area shows operation status. The **Rows** and **Columns**
indicators show dimensions for the selected result dataset when available.

## Adjust the layout {#adjust-layout}

Resize the editor and result areas or rearrange the source panels to suit your
workspace.

Return to [Home](../index.md#available-guides) for the available task guides.
