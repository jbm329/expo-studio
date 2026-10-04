# Expo Studio

Expo Studio is a PyQt6-based SQL editor and data exploration tool built primarily for my own workflows and learning.  
It is shared publicly in case others find it useful.

The application focuses on interactive SQL development, dataset inspection, and lightweight data preparation in a desktop environment.


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
- **SQL Editor**: Syntax highlighting, SQL-aware auto-completion and linting
- **Schema Browser**: Navigate through database structures, including tables, views, and schemas.
- **File Explorer**: Integrated file system browser for quick access to local SQL scripts and data files.
- **REST Data Loader**: Experimental support for loading and exploring datasets from REST APIs.
- **Result Tabs**: Multi-dataset result viewer with support for large datasets using efficient table views.
- **Theme Support**: System-aware UI and icons, with configurable SQL highlighter themes.

### 📊 Data Operations
- **Data Preparation**: Built-in tools for joining and concatenating datasets within the workbench.
- **Data Transformation**: Apply transformations to datasets using a visual interface.
- **Export Capabilities**: Export query results to multiple formats including **CSV**, **feather**, **parquet**, and more.
- **Dataset Analysis**: Integrated data profiling (via `fg-data-profiling`) for in-depth dataset statistics.
- **Advanced Analysis**: Explore active datasets through an interactive statistical-analysis workspace.
- **Persistence**: Supports management of database connections, application settings, and logs.

### 📈 Advanced Analysis

The **Advanced Analysis** workspace provides interactive statistical tools for datasets loaded in result tabs. Open it with **Analyze data** in the toolbar, then choose a dataset and analysis category.

Available analyses include:

- **Overview**: Dataset dimensions, missing values, duplicate rows, column types, per-column statistics, and a sample of up to 100 rows.
- **Statistics**: Descriptive statistics, histograms, boxplots, and Shapiro-Wilk normality tests for numeric columns.
- **Hypothesis Tests**: Group comparisons for numeric and categorical variables, plus chi-square tests of independence with adjusted residuals.
- **Correlation**: Pearson, Spearman, and Kendall correlation matrices, strongest-pair summaries, significance tests, heatmaps, and pairwise scatterplots.
- **Regression**: Multiple linear regression with numeric and categorical predictors, coefficient estimates, confidence intervals, model summaries, diagnostic tests, and residual plots.
- **Outliers**: Univariate screening using IQR, z-score, or modified z-score, and multivariate detection using Isolation Forest or Local Outlier Factor.
- **Clustering**: K-means, DBSCAN, and agglomerative clustering with cluster summaries and PCA-based projections.
- **PCA**: Principal component analysis with optional standardization, explained variance, score plots, and feature loadings.
- **Time Series**: Series preparation, optional resampling, autocorrelation, and additive or multiplicative seasonal decomposition.

The workspace uses adjustable result sections and configurable column selections. Long-running calculations are performed in the background to keep the interface responsive, and supported analyses provide progress or cancellation where appropriate.

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

Expo Studio has been developed and tested on both Windows and Linux. The tested database combinations are:

- **Windows**: Microsoft SQL Server (MSSQL) and SQLite
- **Linux (Fedora 44)**: MariaDB and SQLite

Support for other databases is experimental and largely unverified. They may work partially or require additional configuration.

- **Microsoft SQL Server (MSSQL)**
- **MySQL**
- **MariaDB**
- **SQLite**

Database drivers are provided via SQLAlchemy and standard DBAPI backends.

Recommended drivers:
- MSSQL: pyodbc (ODBC Driver 17 or 18 required)
- SQLite: sqlite3 (built-in)
- MySQL / MariaDB: mysqlclient (preferred) or PyMySQL

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

### 🌍 Internationalization
- **Multilingual UI**: Built-in i18n support using Qt translations.
- **Languages**: Swedish and English.


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
Some day, I may implement a CLI interface for certain operations, but currently the focus is on the GUI.

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
```

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
All strings tagged for translation are collected using the following command:

```sh
uv run build-i18n
```

#### 2️⃣ Edit translations
The extracted strings are then manually edited in the `src/expo_jbm329/i18n/locales` directory using Qt Linguist (e.g. `app_sv.ts`).


#### 3️⃣ Compile translations
After editing, the translations are compiled into binary format using the following command:
```sh
uv run build-locales
```

### Building

```sh
# Compile resources (icons & splash)
uv run build-resources

# Build project (requires PyInstaller)
uv run build-exe

# Build a platform-specific onedir release (requires PyInstaller; Windows installer also requires Inno Setup)
uv run build-release
```

The release artifacts are written to `release/artifacts/`: a `.tar.gz` archive and SHA-256 checksum on Linux, or a ZIP archive, installer, and their checksums on Windows. To publish a release, update the version in `pyproject.toml`, run `uv lock`, commit both files, and push the matching `v<version>` tag (for example, `v1.0.0`). The tag workflow builds both platforms, verifies the files, and publishes them as GitHub Release assets with GitHub-generated release notes. The generated `BUILD-INFO.txt` is bundled with each release and records build metadata rather than release changes; its platform label matches the artifact suffix (`win64`, `linux`, or `macos`). The Windows installer does not display this file automatically. Its finish page offers an unchecked option to view the installed `THIRD-PARTY-NOTICES.txt`, which also remains accessible from the application's About dialog. Build outputs are also available as separate `release-windows` and `release-linux` workflow artifacts. Rerunning a tag after its release is published will not overwrite its assets.

For prereleases, use a normalized Python version such as `version = "1.0.0rc1"` in `pyproject.toml`, run `uv lock`, and commit both files before pushing the hyphenated tag `v1.0.0-rc1`. The same convention supports `-aN` and `-bN`; release asset filenames retain the hyphen (for example, `ExpoStudio-1.0.0-rc1-linux.tar.gz`). The workflow rejects tags that disagree with the project version or lockfile.

## 📝 License

Expo Studio is free software: you can redistribute it and/or modify
it under the terms of the **GNU General Public License** as published
by the Free Software Foundation, version 3.

Expo Studio is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

See the [LICENSE.txt](LICENSE.txt) file for details.

## 👤 Author

**Jonas Brännström** - [jonas.brannstrom@gmail.com](mailto:jonas.brannstrom@gmail.com)


## 🎨 Icon Credits

This project uses icons from Icons8 (https://icons8.com).

Icons are used under the free license and require attribution.

---
*Built with ❤️ using PyQt6 and Python.*
