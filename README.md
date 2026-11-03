# Expo Studio

Expo Studio is a PyQt6-based data exploration and analysis tool built primarily for my own workflows and learning.  
It is shared publicly in case others find it useful.

Connect to databases, load files, and retrieve data from REST APIs. Inspect and
prepare datasets, then analyze them with a range of statistical methods.


![Expo Studio Splash](src/expo_jbm329/workbench/splash/splash.png)


## 📌 Project Status & Philosophy

This is a personal side project developed and maintained in my spare time.

- Development is driven by my own use cases and interests
- There is no fixed roadmap or release schedule
- Features may change, break, or be removed over time
- Issues and pull requests are welcome, but may not receive a response

If development stops, the code will remain available as-is.


## 🚀 Features
The feature list reflects current functionality, not guarantees.
The project is still in its infancy and may change significantly.

### 🛠️ Core Workbench
- **SQL Editor**: Syntax highlighting, SQL-aware auto-completion and linting.
- **Schema Browser**: Navigate through database structures, including tables, views, and schemas.
- **File Explorer**: Integrated file system browser for quick access to local SQL scripts and data files.
- **REST Data Loader**: Experimental support for loading and exploring datasets from REST APIs.
- **Result Tabs**: Multi-dataset result viewer with support for large datasets using efficient table views.
- **Theme Support**: System-aware UI and icons, with configurable SQL highlighter themes.

### 📊 Data Operations
- **Data Preparation**: Built-in tools for joining and concatenating datasets within the workbench.
- **Column Order**: Right-click a result-tab column header and choose **Order** → **Move right**, **Move left**, **Move to first**, or **Move to last**. This changes the dataset's column order for subsequent operations and exports, and supports **Undo**. Moves apply to one column at a time; unavailable moves are disabled.
- **Data Transformations**: Transform and reshape datasets using a visual interface, including grouping by dimensions and calculating named metrics (including median and ordered FIRST/LAST values) with optional per-metric conditions editable as syntax or in a visual builder, and a five-row preview.
- **Export Capabilities**: Export query results to multiple formats including **CSV**, **feather**, **parquet**, and more.
- **Dataset Analysis**: Integrated data profiling (via `fg-data-profiling`) for in-depth dataset statistics.
- **Advanced Analysis**: Explore the active ready result dataset in an interactive analysis workspace.
- **Persistence**: Supports management of database connections, application settings, and logs.

### 📈 Advanced Analysis

The **Advanced Analysis** workspace provides statistical and machine-learning
tools for datasets in result tabs. Select a ready result tab before opening
**Analyze data**. Each analysis window stays bound to the dataset it opened with;
close and reopen it to analyze another dataset.

- **Overview** profiles dataset structure, missing values, duplicates, and columns, with sample-row previews.
- **Statistics** summarizes numeric and categorical data, distributions, and normality.
- **Hypothesis Tests** compares groups, tests categorical associations, and analyzes paired measurements.
- **Correlation** explores Pearson, Spearman, or Kendall relationships with matrix and pairwise plots.
- **Regression** fits linear, logistic, Poisson, Negative Binomial, and Cox models with diagnostics.
- **Outliers** detects univariate and multivariate anomalies.
- **Clustering** groups observations using K-means, DBSCAN, or agglomerative clustering.
- **PCA** reduces numeric data to principal components and shows loadings and explained variance.
- **Time Series** prepares and analyzes series with optional resampling, autocorrelation, and seasonal decomposition.

Analysis pages show applied settings alongside results and explanatory notes.
Charts adapt to long labels, with scrolling when more space is needed.
Long-running analyses run in the background where needed.

**Export** selected analysis results to Excel, CSV, or supported binary formats.
Excel workbooks can combine tables and charts; CSV and binary exports contain
one selected table. Exports use the latest successful analysis result.

Use **Add to report** to collect applied analyses, choose their components, and
add notes. The **Reports** page lets you edit and reorder entries, add a title
and description, and preview the report before saving a self-contained HTML file.
Updating or replacing an existing report result requires confirmation.

### 📂 Supported Data File Formats

Expo Studio supports loading a range of common tabular data formats into pandas DataFrames for interactive exploration and transformation within the workbench.

#### 📊 Supported Formats
- **CSV / Text files** (`.csv`, `.txt`, `.tsv`)  
  Standard delimited formats with optional delimiter detection

- **Excel** (`.xlsx`, `.xls`)  
  Streaming support for large files where possible

- **Columnar & Binary formats**
  - **Parquet** (`.parquet`)
  - **Feather** (`.feather`, `.ft`)
  - **Pickle** (`.pkl`, `.pickle`, `.df`)

- **Statistical data formats**
  - **Stata** (`.dta`)
  - **SPSS** (`.sav`)

- **Qlik format**
  - **QVD** (`.qvd`)

#### ⚙️ Performance & Behaviour
- Text-based formats (e.g. CSV) support streaming and progress reporting
- Binary formats (e.g. Parquet, Feather, Pickle, QVD, Stata, SPSS) are loaded in a single operation and use an indeterminate progress indicator
- Very large datasets may incur additional processing time during rendering in the UI

#### ⚠️ Limitations
- Limited support for advanced metadata (e.g. value labels in SPSS/Stata)
- No streaming or incremental loading for binary formats
- Corrupted or partially downloaded files may result in empty datasets or load errors

This functionality is still evolving and will be extended as new use cases emerge.

### 🗄️ Database Support

Database support has been tested on Windows and Linux (Fedora 44). The tested
platform and database combinations are:

- **Windows**: Microsoft SQL Server (MSSQL) and SQLite
- **Linux (Fedora 44)**: MariaDB/MySQL, PostgreSQL, SQLite and DuckDB (read-only local files)

On Linux, MariaDB and MySQL connections are supported through the bundled
PyMySQL and MySQL Connector/Python drivers. PostgreSQL connections are supported
through the bundled `psycopg` driver and DuckDB connections are supported through the bundled `duckdb-engine` and `duckdb` drivers. Users of the packaged application do not
need to install these drivers separately.

Windows is expected to support MariaDB/MySQL, PostgreSQL and SQLite through the same
drivers, but those combinations have not yet been tested. Support for other
databases is experimental and may require additional configuration.

- **Microsoft SQL Server (MSSQL)**
- **MySQL**
- **MariaDB**
- **PostgreSQL**
- **SQLite**
- **DuckDB** (existing local files, read-only)

Database connections use SQLAlchemy with standard DBAPI drivers.

Recommended drivers:
- MSSQL: pyodbc (ODBC Driver 17 or 18 required)
- SQLite: sqlite3 (built-in)
- MySQL / MariaDB: PyMySQL or MySQL Connector/Python (bundled)
- PostgreSQL: psycopg (bundled)
- DuckDB: duckdb-engine and duckdb (bundled)

### 🌐 REST API Support

Expo Studio includes experimental support for loading datasets from REST APIs.

The REST functionality is designed for **read-only data access** and focuses on:
- fetching structured data from public or internal APIs
- normalizing API responses into tabular datasets
- inspecting and transforming the resulting data alongside SQL-based datasets

REST support is intentionally **generic** and not tied to specific vendors or services.

#### Supported API patterns

The REST loader supports APIs that return:

- **JSON-stat v2**
Commonly used by statistical APIs such as SCB Statistikdatabasen
- **List-of-objects JSON**
Common REST responses containing records
- **Dictionary-of-lists JSON**
Common for time series and metric-based APIs

Responses are normalized into a tabular format when possible. Response
schemas can be validated against required columns before data is loaded.

#### Configuration

REST connections are configured interactively in the UI and support:

- HTTP method selection (GET / POST)
- Query parameters, headers, and optional JSON request bodies
- Response path extraction for nested payloads
- Bearer, Basic, API key, and OAuth2 authentication
- Page-number pagination with configurable page and page-size parameters
- Retry and backoff handling for transient failures and rate limiting
- Response validation and preview before saving a connection

The connection test displays normalized columns, row and column totals,
and a sample record preview.

#### SCB integration

Expo Studio includes a guided connection wizard for
**SCB Statistikdatabasen**. It allows users to search and browse available
tables, select variables and values, and generate a valid REST connection
without manually constructing the PxWeb request.

The generated URL and query parameters are transferred to the generic
REST connection editor, where they can be reviewed and adjusted before
the connection is saved.

#### Limitations

REST support is still evolving and currently has some limitations:

- No support for streaming or incremental loading
- Pagination is limited to page-number based APIs
- No next-link or cursor-based pagination
- API-specific response formats may require manual configuration
- The SCB wizard currently targets SCB Statistikdatabasen and its PxWeb API

The REST feature is intended primarily for:

- public data APIs
- internal APIs with stable response formats
- statistical APIs, including SCB Statistikdatabasen
- exploratory and analytical workflows

### Derived columns

Right-click a column header and choose **Derived column…** beside Split/Merge.
The new column is inserted immediately to the right of that header (or at the
end when you right-click the last column). This action is available when no
more than one column is selected; it is no longer in the result-tab context
menu. The clicked column determines placement only: formulas can reference
any column in the dataset.

Derived columns support numeric arithmetic (`+`, `-`, `*`, `/`) and nested
`IF(condition; then; else)` expressions. Reference columns with `[Column Name]`,
quote text with single quotes, separate IF arguments with semicolons, and
separate IN-list values with commas. Keywords are case-insensitive.

```text
IF([Age] BETWEEN 0 AND 20; 'Youth'; IF([Age] BETWEEN 21 AND 40; 'Midlife'; 'Oldies'))
IF([Vehicle] IN('BMW', 'Volvo'); 'Cars'; 'Other')
IF([Column1] IS NULL; 'Empty'; [Column1])
IF([Age] IS NULL; 0; [Age])
```

Conditions support `=`, `!=`, `<`, `<=`, `>`, `>=`, `BETWEEN`, `NOT BETWEEN`,
`IN`, `NOT IN`, `IS NULL`, and `IS NOT NULL`. Combine them with `NOT`, `AND`,
`OR`, and parentheses. Arithmetic and column-to-column comparisons work too:
`IF([Age] + 1 > [Limit]; [Age]; 0)`. Precedence is arithmetic, comparisons,
NOT, AND, then OR. Parentheses override precedence. IN lists contain literals.
Escape an apostrophe by doubling it (`'O''Brien'`) and a closing bracket in a
column name by doubling it (`[a]]b]` references `a]b`).

BETWEEN includes both bounds. The age-group example leaves decimal ages
between 20 and 21, values outside the listed ranges, and missing ages in
`Oldies`. For continuous ages with an explicit missing group, use:

```text
IF([Age] IS NULL; 'Unknown'; IF([Age] < 21; 'Youth'; IF([Age] <= 40; 'Midlife'; 'Oldies')))
```

Comparisons and membership tests on missing cells produce an unknown condition.
NOT, AND, and OR preserve SQL-style three-valued logic; IF selects else for
unknown. Use IS NULL to handle missing values explicitly. Empty text is not
missing. Both result branches must be text or both numeric; `NULL` is allowed
in either. Text results use nullable string storage, and numeric results use
nullable Float64. The Column1 replacement example requires a text column; the
Age replacement requires a numeric column. Nonmissing values pass through
without automatic text/numeric conversion. Both branches are validated even
when only one is selected. Division by zero produces missing output by default.

Text-only datasets are supported. Type `[` in the multiline formula editor to
complete an available column name. Suggestions filter without case sensitivity;
press Enter or Tab to insert a name, or Escape to dismiss suggestions. Closing
brackets in names are escaped automatically. No column dropdown or Insert button
is needed. Syntax, column references, and compatible types are checked without
evaluating source values; errors are underlined with a tooltip explaining the
problem. Output-column name errors appear separately below the editor.

#### Time hierarchies and groups

Time functions take one datetime column, for example `YEAR([Created])`.
Function names are case-insensitive; columns containing text dates must be
converted to datetime first. Missing dates produce missing results. Components
are read in the column's stored timezone, without converting to UTC or the
computer's timezone. `TIME` uses 24-hour `HH:mm`, ignoring seconds without rounding.

| Function | Example output | Meaning |
|---|---|---|
| `TIME([Created])` | `14:33` | Hour and minute |
| `WEEK([Created])` | `W01` | Zero-padded ISO week |
| `WEEK#([Created])` | `1` | Numeric ISO week, 1–53 |
| `MONTH([Created])` | `January` | Full month name in the app language |
| `MONTHSHORT([Created])` | `Jan` | Abbreviated month name in the app language |
| `MONTH#([Created])` | `1` | Numeric month, 1–12 |
| `TERTIAL([Created])` | `T1` | Four-month period: Jan–Apr, May–Aug, Sep–Dec |
| `TERTIAL#([Created])` | `1` | Numeric tertial, 1–3 |
| `QUARTER([Created])` | `Q1` | Calendar quarter: Jan–Mar, Apr–Jun, Jul–Sep, Oct–Dec |
| `QUARTER#([Created])` | `1` | Numeric quarter, 1–4 |
| `YEAR([Created])` | `2026` | Calendar year |
| `ISOYEAR([Created])` | `2026` | ISO week-numbering year |
| `YEARWEEK([Created])` | `2026-W01` | ISO year and week |
| `YEARMONTH([Created])` | `2026-01` | Calendar year and month |
| `YEARQUARTER([Created])` | `2026-Q1` | Calendar year and quarter |
| `YEARTERTIAL([Created])` | `2026-T1` | Calendar year and tertial |

ISO weeks start on Monday; week 1 contains January 4. ISO years can differ from
calendar years: January 1, 2021 has `YEAR` = 2021, `ISOYEAR` = 2020, and
`YEARWEEK` = `2020-W53`. Use `YEARWEEK` rather than calendar year plus week number
to group weeks correctly across New Year.

Text outputs use nullable string storage, and numeric outputs use nullable
Float64, including whole-number years and period numbers. Month labels are
captured from the app language when you accept the dialog, before background
execution. Changing the language afterward does not relabel an existing column.
Abbreviations retain their language-specific spelling, punctuation and casing.
`W`, `Q`, `T` and year-qualified formats stay fixed in every language. Labels do
not add categorical sorting: use numeric month/period functions for chronological
ordering within a year, or year-qualified labels to distinguish multiple years.

Time functions compose with arithmetic and conditional formulas:

```text
IF([Created] IS NULL; 'Unknown'; MONTH([Created]))
IF(MONTH#([Created]) <= 6; 'H1'; 'H2')
YEAR([Created]) + 1
```

Use numeric month conditions when a formula should be language-independent.
Direct datetime results, datetime-valued IF branches, date comparisons, implicit
date parsing, fiscal calendars and timezone conversion are not supported here.
For service callers, `DerivedColumnSpec.month_labels` accepts an immutable
`MonthLabels` snapshot shared by creation and preview; the default is English,
independent of the UI or operating-system locale.

### 🌍 Internationalization
- **Multilingual UI**: Built-in i18n support using Qt translations.
- **Languages**: English, Swedish, German, French, Italian, Spanish, and Polish.


## 🛠️ Installation

> Note: Expo Studio is primarily developed for my own environment and workflow.
> Installation instructions are provided on a best-effort basis.

Expo Studio requires **Python 3.13**.

### Using `uv` (Recommended)
If you have `uv` installed, you can run or install it directly:

```sh
# Create virtual environment
uv venv

# Sync dependencies
uv sync
```

## 🖥️ Usage

### Launching the GUI
After installation, you can launch the main application using:

```sh
uv run expo-gui
```

### CLI Access
The `expo` entry point currently provides help and version output only; it does not yet support data-processing operations.

```sh
# Show CLI help
uv run expo --help

# Print the CLI version
uv run expo --version
```

### Configuration
- **Settings**: Accessible via `Settings` in the menu.
- **Connections**: Manage database connections through the `Connections` dialog.
- **Logs**: Configure logging levels and destinations via `Logsettings`.


### 🎨 Themes & Appearance

Expo Studio follows the operating system's appearance settings and automatically adapts to light or dark mode.

#### Application Theme
- The application UI automatically detects whether the OS is using a light or dark theme.
- There is currently no custom application theme that overrides the system appearance.
- Icons automatically adapt to match the active OS theme.

#### SQL Highlighter Themes
The SQL editor uses a dedicated syntax highlighting theme system that can be configured independently of the application UI.

- **Default behavior**:  
  The default setting is **System**, which automatically applies:
  - a light SQL highlighter theme when the OS is in light mode
  - a dark SQL highlighter theme when the OS is in dark mode

- **Explicit selection**:  
  Users can manually select a specific SQL highlighter theme, regardless of OS appearance.

- **Available themes**:  
  In addition to the built-in light and dark themes, several additional predefined SQL highlighter themes are available.

#### Custom SQL Highlighter Themes
Custom SQL highlighter themes can be created by defining theme files in JSON format.

- Each theme is defined in a separate `.json` file.
- A new theme can be created by copying an existing theme file, renaming it, and adjusting the color definitions.
- Custom theme files are located in:

```text
src/expo_jbm329/workbench/theme/themes/custom
```


## 🧑‍💻 Development
Development notes below are provided mainly for contributors and for my own reference.

### Setup
The project uses `uv` for dependency management. Development, testing, and release builds are supported on both Windows and Linux. Local development and testing have been verified on Windows and Fedora 44; pull-request CI currently runs on Ubuntu, while tagged release workflows build for both Windows and Linux.

```sh
# Sync dependencies
uv sync

# Sync dependencies for fg-data-profiling
uv sync --extra profiling

# Sync dev dependencies (ruff, pytest, mypy etc.)
uv sync --extra dev

# Sync development and build dependencies together
uv sync --extra dev --extra build
```

Run the commands below from the repository root. The `dev` extra includes the Qt tools used by `build-resources` and `build-locales` (`pyside6-rcc` and `pyside6-lrelease`). String extraction uses `pylupdate6`, supplied by PyQt6. The `build` extra supplies build dependencies such as Pillow and PyInstaller.

### Running Tests
The project uses `pytest` for automated unit testing.

```sh
# Run all tests
uv run pytest

```

### 🌍 Internationalization (i18n)

Expo Studio uses Qt's translation system for internationalization, with all user-facing UI strings explicitly marked for translation in the source code.

The i18n workflow consists of three main steps:

#### 1️⃣ Extract translatable strings
`build-i18n` collects strings tagged for translation from the Python sources and
updates every supported language catalog in `src/expo_jbm329/i18n/locales`.
The `Language` enum defines extraction targets and the language options in
Settings. Existing translations are retained, and messages no longer used by
the sources are kept as vanished entries.

| Language | Settings label | Catalog | Translation locale |
|---|---|---|---|
| English (source) | English | `app_en.ts` | English source fallback |
| Swedish | Svenska | `app_sv.ts` | `sv_SE` |
| German | Deutsch | `app_de.ts` | `de_DE` |
| French | Français | `app_fr.ts` | `fr_FR` |
| Italian | Italiano | `app_it.ts` | `it_IT` |
| Spanish | Español | `app_es.ts` | `es_ES` |
| Polish | Polski | `app_pl.ts` | `pl_PL` |

Select a language by its native name in Settings. Settings and runtime loading
use the short codes (`en`, `sv`, `de`, `fr`, `it`, `es`, `pl`). UI language
selection does not change the system locale used for number/date formatting.

```sh
uv run build-i18n
```

To extract strings **and remove obsolete/unused entries**, use `build-i18n-clean` instead:

```sh
uv run build-i18n-clean
```

This runs the same extraction with `pylupdate6 --no-obsolete`. It deletes translations for messages no longer present in the sources; review the changes before committing. It is an alternative to `build-i18n`, not a required additional step.

#### 2️⃣ Edit translations
The extracted strings are then manually edited in the `src/expo_jbm329/i18n/locales` directory using Qt Linguist (e.g. `app_sv.ts`).

English is the source language: edit English wording in the Python sources, not
in `app_en.ts`. Keep its translation elements empty and marked unfinished
(`<translation type="unfinished" />`) so Qt uses the source text. Do not copy
English source strings into translation elements or mark them finished.
`app_en.ts` remains a source-language catalog, and `app_en.qm` must still be
compiled and shipped because the language loader expects it. If numerus
messages are introduced, review their English plural forms separately rather
than applying the empty-translation convention blindly.

All user-facing strings must support every language listed above. After adding
or changing strings, run `uv run build-i18n`, review and finish translations in
each non-English catalog, then run `uv run build-locales`. Non-English catalogs
use nonempty, finished translations, following the Swedish catalog's pattern.
Preserve named placeholders such as `{component}` (including format specs),
markup, links, and significant whitespace. Verify compiled translations in the
affected UI or report. New translations are authored translations, not a
substitute for native-speaker review of terminology and phrasing.

Separate complete sentences with periods and capitalize
the following sentence. Use commas between short labels, values, or parenthetical
phrases instead of semicolons, and apply the same convention to English sources
and all translations, including chart captions and report text. Separate
chart titles in accessible names with periods. Preserve technical semicolons in
HTML entities and styles, and never rewrite punctuation in user-provided data.

For explicit contexts, import the shared helper with
`from expo_jbm329.utils.i18n_utils import translate` rather than calling Qt's
translation API directly. Use `translate(context, "Text")` for plain messages.
For marker-based messages with substitutions, import `translate_fmt` from the
same module. It translates the template **before** substituting descriptive
named values, so translators can reorder values without changing their meaning.
Names such as `{file}` and `{count}` explain each value's role and avoid fragile
chains of positional replacements such as `.replace("%1", ...)`.

For ordinary widget messages, retain `self.tr` and format the translated
literal directly:

```python
message = self.tr("Could not find {document}.").format(document=document_name)
```

Keep the template literal inside `self.tr` so Qt can extract it and retain the
widget's translation context. Do not format the source before translation
(including with an f-string). Use descriptive named fields instead of `%1`, `%2`,
or positional `{}` fields so translators can identify and reorder values.
Literal braces in a format template must be doubled (`{{` and `}}`); braces
inside inserted values need no special treatment. Formatting does not escape
HTML or localize values, so preserve any required escaping and locale formatting.
No shared helper or local wrapper is needed for this widget pattern.

Choose the call style by the translation contexts used across the **whole
module** for explicit-context messages. For a single-context module, reuse or
create a local `_tr` wrapper for plain messages and `_tr_fmt` for formatted
messages, as needed. Bind both to that context and retain literal extraction
markers:

```python
from PyQt6.QtCore import QT_TRANSLATE_NOOP

from expo_jbm329.utils.i18n_utils import translate, translate_fmt

TR_READY = QT_TRANSLATE_NOOP("FilePanelController", "Ready")
TR_LOADING = QT_TRANSLATE_NOOP("FilePanelController", "Loading {file}")


def _tr(text: str) -> str:
    return translate("FilePanelController", text)


def _tr_fmt(text: str, **kwargs: object) -> str:
    return translate_fmt("FilePanelController", text, **kwargs)


status = _tr(TR_READY)
message = _tr_fmt(TR_LOADING, file=filename)
```

For class-local markers in their matching Qt context, the same pattern can use
`QT_TR_NOOP` and static wrappers:

```python
from PyQt6.QtCore import QT_TR_NOOP

from expo_jbm329.utils.i18n_utils import translate_fmt


class FilePanelController:
    TR_LOADING = QT_TR_NOOP("Loading {file}")

    @staticmethod
    def _tr_fmt(text: str, **kwargs: object) -> str:
        return translate_fmt("FilePanelController", text, **kwargs)

    def loading_message(self, filename: str) -> str:
        return self._tr_fmt(self.TR_LOADING, file=filename)
```

For a module using multiple contexts, call `translate` and `translate_fmt`
directly instead of adding fixed-context wrappers:

```python
from PyQt6.QtCore import QT_TRANSLATE_NOOP

from expo_jbm329.utils.i18n_utils import translate_fmt

TR_FAILURE = QT_TRANSLATE_NOOP("QueryController", "Failed to run SQL.\n\n{traceback_str}")

message = translate_fmt("QueryController", TR_FAILURE, traceback_str=error_details)
```

Use these examples for explicit-context, marker-based messages, not as a reason
to replace ordinary widget `self.tr("Text")` calls. Keep injected translation
callbacks and captured-template formatting in Qt-free chart/report services:
calling the shared helper there would bypass the caller's translation source.
At the UI boundary, pass the shared `translate` helper instead of Qt's method
when a service needs a two-argument `(context, source) -> str` callback:

```python
labels = build_outlier_histogram_labels(translate)
```

The service still uses the injected callback and can request different contexts.
Do not pass a single-context `_tr(text)` wrapper in its place.

`translate_fmt` leaves the translated template unchanged if formatting fails.
It does not localize numbers or paths, escape HTML, or validate placeholders:
preserve the appropriate formatters and escaping before passing values, and
check placeholder consistency in translations. Braces or positional-looking
tokens inside inserted values are preserved, not formatted again.

`pylupdate6` recognizes literal `translate(context, "Text")` calls, but
`translate_fmt` and calls with variable source text still require literal
`QT_TRANSLATE_NOOP` markers (or class-local `QT_TR_NOOP` markers in the matching
context). Do not alias the two-argument helper to `tr`: the extractor interprets
that spelling as Qt's `tr(source, comment)` instead.
Widget calls such as `self.tr("Text")` are unaffected and remain appropriate.
Local wrappers do not make strings extractable: retain the markers for both
plain and formatted messages. Keep existing markers for dynamically selected
sources in their canonical context.

Shared labels resolved dynamically need literal `QT_TRANSLATE_NOOP` extraction
markers in their canonical context. Advanced Analysis keeps these alongside its
views and controller; extraction tests compare them with the shared presentation
and report label registries. Repeated source text in different contexts is valid,
while vanished entries are retained translation history, not active duplicates.
Remove obsolete entries only after checking their runtime replacements; avoid a
global clean when performing a targeted translation cleanup.


#### 3️⃣ Compile translations
`build-locales` compiles all `app_*.ts` files in the locales directory into `.qm` binaries alongside their source files. It uses `pyside6-lrelease` from the `dev` extra:
```sh
uv run build-locales
```

### Building

Install development and build dependencies with `uv sync --extra dev --extra build` before running these commands.

#### Compile UI resources

`build-resources` compiles the icon and splash `.qrc` files into adjacent `*_rc.py` modules using `pyside6-rcc`, then adjusts their imports for PyQt6. Run it after changing the bundled resources.

```sh
# Compile resources (icons & splash)
uv run build-resources
```

#### Build the executable

`build-exe` builds the GUI application with PyInstaller in **onedir** mode, writing the application and its dependencies to `dist/expo/`. PyInstaller's intermediate files are written to `build/expo/`. This command does not stage or package a release.

```sh
uv run build-exe
```

`expo.spec` includes DuckDB's SQLAlchemy entry-point metadata and collects its
native `_duckdb` extension through PyInstaller's dependency analysis, using the
installed platform's `.pyd` on Windows or `.so` on Linux. Build on each target
OS with that OS's dependencies; a Linux build does not verify Windows DLL
loading. Third-party notices include the bundled `duckdb` and `duckdb-engine`
distributions and their license files.

#### Stage an existing build

`stage-release` prepares `release/staging/` from an existing `build-exe` output. It copies the application and release documentation, writes `BUILD-INFO.txt`, and generates third-party notices from that build's PyInstaller metadata. Both `dist/expo/` and the corresponding metadata in `build/expo/` must be present. Existing staging contents are replaced.

```sh
uv run stage-release
```

#### Build and package a release

`build-release` runs the executable build, staging, and platform-specific packaging in sequence; there is no need to run `build-exe` or `stage-release` separately beforehand. Windows installer packaging additionally requires Inno Setup.

```sh
uv run build-release
```

The release artifacts are written to `release/artifacts/`: a `.tar.gz` archive and SHA-256 checksum on Linux, or a ZIP archive, installer, and their checksums on Windows. To publish a release, update the version in `pyproject.toml`, run `uv lock`, commit both files, and push the matching `v<version>` tag (for example, `v1.0.0`). The tag workflow builds both platforms, verifies the files, and publishes them as GitHub Release assets with GitHub-generated release notes. The generated `BUILD-INFO.txt` is bundled with each release and records build metadata rather than release changes; its platform label matches the artifact suffix (`win64`, `linux`, or `macos`). The Windows installer does not display this file automatically. Its finish page offers an unchecked option to view the installed `THIRD-PARTY-NOTICES.txt`, which also remains accessible from the application's About dialog. Build outputs are also available as separate `release-windows` and `release-linux` workflow artifacts. Rerunning a tag after its release is published will not overwrite its assets.

For prereleases, use a normalized Python version such as `version = "1.0.0rc1"` in `pyproject.toml`, run `uv lock`, and commit both files before pushing the hyphenated tag `v1.0.0-rc1`. The same convention supports `-aN` and `-bN`; release asset filenames retain the hyphen (for example, `ExpoStudio-1.0.0-rc1-linux.tar.gz`). The workflow rejects tags that disagree with the project version or lockfile.

## 📝 License

Copyright © 2026 Jonas Brännström.

Expo Studio is free software: you can redistribute it and/or modify
it under the terms of the **GNU General Public License** as published
by the Free Software Foundation, version 3.

Expo Studio is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

See the [LICENSE.txt](LICENSE.txt) file for details.

## 👤 Author

**Jonas Brännström** - [expostudio.contact@gmail.com](mailto:expostudio.contact@gmail.com)


## 🎨 Icon Credits

This project uses icons from Icons8 (https://icons8.com).

Icons are used under the free license and require attribution.

---
*Built with ❤️ using PyQt6 and Python.*
