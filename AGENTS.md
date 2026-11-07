# Expo Studio AI Agent Guide

## Project overview

Expo Studio is a PyQt6 desktop data analysis and data-prep workbench for SQL, file-based datasets, REST APIs, and statistical analysis.

Primary entry points:

- `src/expo_jbm329/gui_main.py` — launches the desktop app, boots the application, and shows the splash screen.
- `src/expo_jbm329/cli_main.py` — minimal CLI entry point used for `--help` and `--version`.

The package is organized around the app shell and feature modules under `src/expo_jbm329/`:

- `app/` — bootstrap, config, metadata, and application lifecycle
- `gui/` — Qt dialogs, panels, and view code
- `workbench/` — workbench UI and theme/resource plumbing
- `services/` — file loading, data processing, schema/profile logic, job orchestration, and related business behavior
- `db/` — DB connection and SQL-related logic
- `analysis/` — statistical analysis pages and chart/report outputs
- `result_tabs/` — dataset result tab management and display contracts
- `utils/` — reusable helpers, localization, path utilities, and other shared logic
- `tests/` — pytest suite and Qt-aware fixture setup

Follow the existing architecture: keep UI widgets thin, place business rules in services/controllers, and keep result-tab and async job lifecycle behavior intact.

## Working conventions

- Python target: 3.13
- Framework: PyQt6 only; do not introduce PyQt5 patterns
- Prefer `pathlib.Path`, dataclasses where useful, and explicit type hints on public APIs
- Use Google-style docstrings and English-only comments/logs
- Prefer small, readable functions over clever abstractions
- Keep None-handling and failure paths explicit; avoid silent fallbacks
- Favor dependency injection and existing shared services over ad hoc instantiation
- Implement all work in in small steps, halt and ask for review after each step.
- Do not ever commit to git. Always wait for code review.

The codebase emphasizes maintainability and clean boundaries over quick hacks. When in doubt, follow the pattern already used in the module you are editing and reuse existing services/helpers before adding new ones.

## Architecture notes

### UI and business logic separation

Keep dialogs and widgets focused on input/dispatch. Heavy logic belongs in controllers/services, not in Qt widgets.

Examples:

- `src/expo_jbm329/gui_main.py` is a thin app launcher and bootstrap entry point
- `tests/conftest.py` isolates user config directories and installs Qt translators; it is intentionally test-focused, not app logic

### Async jobs and result tabs

Long-running work should not block the GUI thread. Preserve the established job manager/result-tab lifecycle and keep background progress/cancellation patterns aligned with existing services.

When changing result tab or job-related behavior, follow the module's existing ownership and completion flow instead of introducing a new UI/job model.

### Data flow

The app is centered on tabular data flows: file loads, SQL result sets, REST-normalized data, and analysis outputs. Shared services handle IO, schema metadata, data profiling, and export behavior before data reaches the UI or report layer.

## Development workflow

### User manual authoring and maintenance

The English-only online user manual uses Zensical (`docs/`, `zensical.toml`).
It is authored incrementally; do not generate a comprehensive manual or empty
navigation sections. Home currently describes coverage, and planned guides
must not be presented as available until they exist.

For changes to user-facing features, workflows, formulas, validation, or error
behavior, review the documentation impact. Update affected existing guides in
the same PR. If an affected area has no guide, explicitly note that gap in the
PR and propose a focused follow-up rather than silently ignoring it or writing
unrequested broad documentation. Internal-only changes need no manual update
unless they change observable behavior.

Verify instructions and examples against the implementation and relevant tests;
do not infer supported syntax or behavior from UI labels alone. Use the app's
English terminology, task-oriented instructions, and small reproducible examples.
Reuse shared explanations where behavior genuinely matches, but document editor
differences explicitly. Screenshots are optional and should explain a task;
keep them free of personal data and secrets.

Organize guides by task in `docs/<section>/`, with screenshots in the matching
`docs/assets/<section>/`: `workbench` (app shell, settings, connections),
`get-data`, `prepare-data` (same columns and meaning: filter, sort, rename,
remove, reorder, data types, missing values, cleansing), `transform-data`
(new columns or granularity, or combined datasets: derived columns, reshape,
split/merge columns, join, concatenate), `analyze-data` and `export-and-report`.
Folders may exist before their guides; `.gitkeep` files are placeholders.

Add navigation entries only for useful pages that exist. Preserve established
page paths and explicit anchors used as help targets; review links before
renaming them. Keep Home's coverage notice accurate as sections are added.
Use local preview and PR artifacts to review changes, and run
`uv run --frozen --extra docs zensical build --clean --strict`.
Do not generate or commit `site/` output or generated `publication.json`.

The public manual represents the latest stable application release. Document
new behavior alongside its feature change for preview and release together;
do not publish unreleased instructions through a stable documentation correction.
Documentation-only corrections must describe behavior available in their stable
baseline. Site configuration changes are outside that correction route and
must wait for an eligible application release, not weaken publication policy.

Follow `DOCUMENTATION.md` for detailed documentation builds and publication
policy, and `RELEASING.md` for manual and automatic publication recovery. Manual
publication defaults to preview; deployment requires explicit operator
selection from `main`.
Stable application releases invoke the shared pipeline after successful
application publication; prereleases do not. Preserve caller verification,
release eligibility, source-progress checks, and shared publication concurrency.
Do not publish, rerun publication jobs, delete deployment records, or change
Pages settings without explicit approval. Do not create a release to test
documentation automation or rerun a release solely to retry documentation.
The Help menu opens the manual home page. General Settings, Log settings,
Database connections and REST API connections have a Help button and contextual
F1 link. The SCB query builder also links to its manual section through Help/F1.
The Join datasets dialog provides Help/F1 for its guide; Join preview links
to the preview section.
Concatenate datasets also provides Help/F1 for its guide.
The Derived column dialog provides Help/F1 for the Derived columns guide.
The Reshape dialog provides Help/F1 for its guide.
Build condition provides Help/F1 for the Reshape guide's visual condition builder.
Register manual destinations in
`app/help_topics.py`; its pytest contract checks pages and explicit anchors.

Use `uv` from the repository root.

### Install dependencies

```sh
uv sync
uv sync --extra profiling
uv sync --extra dev
uv sync --extra dev --extra build
```

The project defines the main development and packaging commands in `pyproject.toml`.

### Run tests

```sh
uv run pytest
```

The test suite depends on `tests/conftest.py` for:

- a session-scoped `QApplication`
- temporary, isolated config directories instead of real user directories
- Qt translation catalog setup for language-aware UI tests

### Build and package

```sh
uv run build-resources
uv run build-i18n
uv run build-i18n-clean
uv run build-locales
uv run build-exe
uv run stage-release
uv run build-release
```

Important project-specific details:

- `build-resources` recompiles Qt resource files (`*.qrc`) into adjacent `*_rc.py` modules.
- `build-i18n` extracts strings for translation from Python sources and updates `src/expo_jbm329/i18n/locales`.
- `build-locales` compiles Qt `.ts` catalogs to `.qm` bundles.
- `build-exe` produces a PyInstaller `dist/expo/` build; `stage-release` packages an existing build into `release/staging/`.
- `build-release` runs the build + staging + packaging flow as a single release step.

## i18n and UI text conventions

This project keeps user-facing strings in Qt translation catalogs and follows a very specific translation workflow.

Relevant files:

- `src/expo_jbm329/i18n/locales/`
- `src/expo_jbm329/utils/i18n_utils.py` (shared translation helper)
- `README.md` sections covering i18n and build steps

Important patterns:

- Prefer the shared translation helper, `translate(...)` and `translate_fmt(...)`, for explicit-context messages instead of bypassing the extraction system.
- Keep literal `QT_TRANSLATE_NOOP` / `QT_TR_NOOP` markers in the canonical context when strings are dynamically selected or formatted.
- For ordinary widget messages, `self.tr("Text")` remains appropriate.
- Do not format before translation; pass descriptive named arguments into translated templates.

When editing user-visible strings, update the source text and run the i18n extraction/build flow rather than hand-editing an ad hoc translation pattern.

## Code quality and linting

`pyproject.toml` configures strict tooling:

- Ruff for lint/format rules with a 120-character line length
- Mypy with `strict = true`
- Pyright configuration in the project config
- Google-style docstrings

Follow the repo's existing code quality rules instead of improvising new ones.

## Project-specific examples

When adding or modifying code, use the patterns already present in the repo:

- `src/expo_jbm329/gui_main.py` is the canonical thin launcher pattern
- `tests/conftest.py` provides the project-specific `QApplication` and isolated runtime directories pattern
- `README.md` and `pyproject.toml` are the authoritative project workflow and command references

## Before making changes

- Check the relevant feature module and nearby service/controller patterns before adding new code
- Reuse existing services rather than creating parallel implementations
- Keep changes narrow and compatible with the current architecture
- Prefer a patch that matches how this app already structures Qt, jobs, and data-processing flows

## Do not do

- Do not add PyQt5 code or Qt patterns outside the PyQt6 API
- Do not move business logic into widgets or dialogs without a clear architectural reason
- Do not bypass the project’s async job/result-tab lifecycle
- Do not ever commit to git. Always wait for code review. 
- Do not invent a new translation scheme or build workflow outside the existing commands in `pyproject.toml` and `README.md`
