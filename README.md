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
- **SQL Editor**: Syntax highlighting and basic SQL-aware auto-completion
- **Schema Browser**: Navigate through database structures, including tables, views, and schemas.
- **File Explorer**: Integrated file system browser for quick access to local SQL scripts and data files.
- **REST Data Loader**: Experimental support for loading and exploring datasets from REST APIs.
- **Result Tabs**: Multi-dataset result viewer with support for large datasets using efficient table views.
- **Theme Support**: System-aware UI and icons, with configurable SQL highlighter themes.

### 📊 Data Operations
- **Data Preparation**: Built-in tools for joining and concatenating datasets within the workbench.
- **Data Transformation**: Apply transformations to datasets using a visual interface.
- **Export Capabilities**: Export query results to multiple formats including **CSV**, **feather**, **parquet**, and more.
- **Dataset Analysis**: Integrated data profiling (via `ydata-profiling`) for in-depth dataset statistics.
- **Column Analysis**: Analyze column types and distributions to understand data quality and structure.
- **Persistence**: Supports management of database connections, application settings, and logs.

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

Expo Studio has primarily been developed and tested against **Microsoft SQL Server**, which is currently the most stable and well-supported database backend.

Basic testing has been performed with **MariaDB** on Linux (Fedora 43).

Support for other databases is experimental and largely unverified.  
They may work partially or require additional configuration.

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
The REST loader currently works best with APIs that return:

- **JSON-stat v2**  
  (e.g. statistical APIs such as SCB Statistikdatabasen, Eurostat, OECD)
- **List-of-objects JSON**  
  (common REST APIs returning records)
- **Dictionary-of-lists JSON**  
  (e.g. time series or metric-based APIs)

Responses are automatically normalized into a “long” tabular format when possible.

#### Configuration
REST connections are configured interactively in the UI and allow:
- HTTP method selection (GET / POST)
- Query parameters and headers
- Optional JSON request bodies
- Optional response path extraction for nested payloads

Authentication mechanisms such as **Bearer tokens** can be supplied via HTTP headers.

#### Limitations
REST support is still evolving and comes with several limitations:

- No support for streaming or incremental loading
- No built-in pagination handling
- No authentication flows (OAuth, refresh tokens, etc.)
- Limited validation of API schemas
- Error handling is basic and may surface raw API errors

The REST feature should be considered **experimental** and subject to change.

It is primarily intended for:
- public data APIs
- internal APIs with stable response formats
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

```powershell
# Create virtual environment
uv venv

# Sync dependencies
uv sync
```

## 🖥️ Usage

### Launching the GUI
After installation, you can launch the main application using:

```powershell
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
The project uses `uv` for dependency management.

```powershell
# Sync dependencies
uv sync

# Sync dependencies ydata-profiling
uv sync --extra profiling

# Sync dev dependencies (ruff, pytest, mypy etc.)
uv sync --extra dev
```

### Running Tests
The project uses `pytest` for automated unit testing.

```powershell
# Run all tests
uv run pytest

```

### 🌍 Internationalization (i18n)

Expo Studio uses Qt's translation system for internationalization, with all user-facing UI strings explicitly marked for translation in the source code.

The i18n workflow consists of three main steps:

#### 1️⃣ Extract translatable strings
All strings tagged for translation are collected using the following command:

```powershell
uv run build-i18n
```

#### 2️⃣ Edit translations
The extracted strings are then manually edited in the `src/expo_jbm329/i18n/locales` directory using Qt Linguist (e.g. `app_sv.ts`).


#### 3️⃣ Compile translations
After editing, the translations are compiled into binary format using the following command:
```powershell
uv run build-locales
```

### Building

```powershell
# Compile resources (icons & splash)
uv run build-resources

# Build project (requires PyInstaller)
uv run build-exe

# Build onedir release zip (requires PyInstaller) or onedir setup wizard (requires Inno Setup)
uv run build-release
```

## 📝 License

This project is licensed under the **GNU General Public License v3.0 or later** - see the [LICENSE.txt](LICENSE.txt) file for details.

## 👤 Author

**Jonas Brännström** - [jonas.brannstrom@gmail.com](mailto:jonas.brannstrom@gmail.com)


## 🎨 Icon Credits

This project uses icons from Icons8 (https://icons8.com).

Icons are used under the free license and require attribution.

---
*Built with ❤️ using PyQt6 and Python.*
