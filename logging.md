
# Logging Policy (logging.md)

> Applies to the Expo project (`expo_jbm329`).  
> Version: **1.2**

This policy defines **namespaces**, **levels**, **handlers**, the **smart wildcard** for third‑party logs, and **best practices** for logging across UI, services, background jobs, and data pipelines. Goals: **high signal‑to‑noise**, predictable behavior in production, and reliable traceability (via corr‑ID).

---

## 1) Logger namespaces

Use a small, stable set of namespaces:

- `applogger.ui` — UI/controllers (e.g., `ExportController`, `ResultTabManager`)
- `applogger.service` — services/data logic (e.g., `DataIOService`, `FileWriter`, `FileLoader`)
- `applogger.jobs` — background jobs (e.g., `JobManager`, `FileJobService`)
- `applogger.db` — database interfaces/drivers (if/when relevant)

> Sub‑loggers (e.g., `applogger.ui.export`) are allowed only when they add clear value.

**Rule:** every new module picks one of the four above.

---

## 2) Root logger & handlers

- The **root logger** owns *all handlers* (file + stdout).  
- Named loggers **do not** have handlers; they **propagate** to root.  
- Prevents duplicates and centralizes formatting/filtering.

### Handlers
The following describes the intended roles of the handlers. The shipped defaults
are **file INFO**, **stdout WARNING**, **UI INFO**, **service WARNING**,
**jobs INFO**, and **DB WARNING**. The JSON examples below are illustrative
diagnostic configurations, not the shipped defaults. Stdout is disabled in frozen
builds.

- **File (RotatingFileHandler)** — deeper diagnostics
  - Level: `DEBUG` (dev), `INFO` (prod)
  - Formatter: verbose (timestamp, level, file, line, function, message)
  - Rotation configured in `logconfig.json`
- **Stdout (StreamHandler)** — clean console for the UI
  - Level: `INFO`
  - Formatter: default (compact)

---

## 3) Per‑namespace levels

Configured in `logconfig.json`, for example:

```json
"loggers": {
  "applogger.ui":      { "level": "INFO",    "propagate": true },
  "applogger.service": { "level": "DEBUG",   "propagate": true },
  "applogger.jobs":    { "level": "INFO",    "propagate": true },
  "applogger.db":      { "level": "WARNING", "propagate": true }
}
```

**Recommendations**
- Raise `applogger.service` to `DEBUG` during data/export troubleshooting.
- Also set the **file handler** level to `DEBUG`; changing only the namespace
  does not enable DEBUG file output. Set `applogger.ui` to `DEBUG` when investigating
  ignored stale results. Keep stdout and third-party filtering at `WARNING`.
- Keep `applogger.db` at `WARNING` unless debugging DB logic.
- Keep `applogger.ui` at `INFO` (UI should not be too chatty).

---

## 4) Smart wildcard for third‑party logs

All loggers **not** starting with `applogger` are treated as third‑party. A single setting controls the **minimum allowed level** for them:

```json
"third_party_log_level": "WARNING"
```

- `WARNING` (default): only warnings/errors from libraries are shown.  
- `INFO`/`DEBUG`: allow more third‑party logs *if* those libraries actually emit them.  
- This **does not force** libraries to produce DEBUG output.  
- TQDM progress is globally disabled for profiling (removes the long `100%|████` lines).

**Goal:** one simple lever for everything outside `applogger.*`.

---

## 5) Corr‑ID (correlation ID)

Long‑running operations (load, export, profiling) must carry a **corr_id** generated at the UI entry.

- Create with `uuid.uuid4()`.
- Pass through UI → JobManager → DataIOService → FileWriter → JobResult.
- Log the corr‑ID in every layer.

Example:
```python
corr = str(uuid.uuid4())
logger.info("ExportController: export requested (corr=%s, kind=excel, path=%s)", corr, path)
```

---

## 6) Levels & message style

- **DEBUG** — entries, parameters, branching, dataset shape, chosen engine, timings (ms)
- **INFO** — successful outcomes (files written, reports generated), notable state changes
- **WARNING** — recoverable problems (fallbacks, limitations)
- **ERROR** — exceptions; include `exc_info=True`
- **CRITICAL** — startup failure only

**Don’ts**
- No raw data dumps (privacy/volume). Prefer metadata (rows/cols, target path, key parameters).
- No personal or sensitive data in logs.

**Formatting**
- Use `%s` placeholders with separate args.
- Avoid f‑strings in logging calls.

**Message naming**

Every message follows `Component: event (key=value, ...)`:

- `Component` is the owning class or service name in PascalCase, e.g.
  `JobManager`, `FileWriter`, `ExportController`, `AnalysisService`.
  Interactive analysis requests and computation completions use the
  section-qualified prefix `Advanced analysis (Section)` described in section 15.
- `event` is a short lower‑case phrase in past tense or present state, e.g.
  `job started`, `HTML report written`, `settings reloaded`.
- Metadata goes in one parenthesized list of comma‑separated `key=value` pairs.
  Put `corr=` first when the operation has a correlation ID. Use `corr`, not
  `corr_id`, as the key.
- Omit fields that do not apply instead of logging `none` placeholders.
- Report durations as `ms=` with one decimal.

Examples:
```text
JobManager: job finalized (job_id=6341…, runner=thread, scope=load:csv, ms=26.2, corr=6551…)
FileWriter: HTML report written (corr=fde5…, path=…)
Advanced analysis (Overview): computation requested (corr=50813..., scope=analysis:overview, rows=624, cols=10)
Advanced analysis (Overview): computation finished (corr=50813..., scope=analysis:overview, outcome=success, rows=624, cols=10, items=10, ms=6.9)
```

---

## 7) Patterns by layer

### UI (`applogger.ui`)
- Log user intent, choices, and `corr_id`.
- Log job scheduling (blocking vs non‑blocking).
- Use INFO for completion/cancellation.

### Services (`applogger.service`)
- Log entry (rows/cols, path, scope, engine) and `corr_id`.
- Log duration (ms) on success.
- Log errors with `exc_info=True`.
- Validate early (e.g., Excel sheet name) and provide clear messages.

### Jobs (`applogger.jobs`)
- Log start/finish/cancel; include total runtime (ms).

### DB (`applogger.db`)
- Keep WARNING by default; raise during DB investigations only.

---

## 8) Progress (0→100)

- `JobManager` injects `progress_cb` **only if** the callable signature includes `progress_cb`.
- Readers/writers should call `progress_cb` roughly once per 1% and at 0/100.
- Chunked operations: update after batches/rows.
- Check cancellation regularly.

**Why only 0→100 happens**
- Signature missing `progress_cb` on some call path.
- Chunk size > dataset size (fast path).
- Underlying library has no granular progress.

---

## 9) Excel export robustness

- Sheet names: max 31 chars; no `: \\ / ? * [ ]`; not empty; no leading/trailing `'`; no control chars.
- Missing values (`pd.NA`, `NaN`, `NaT`) → normalize to `None` (or `na_rep`).
- tz‑aware timestamps → tz‑naive.
- bytes → UTF‑8 strings.
- Write‑only streaming with autosplit across sheets if row limit is exceeded.

---

## 10) Third‑party progress & spam

- TQDM progress disabled globally (`TQDM_DISABLE=1`).
- ydata‑profiling progress disabled (`progress_bar=False`).
- Wildcard filter governs all logs outside `applogger.*`.
- `third_party_log_level=DEBUG` enables displaying DEBUG *if* libraries emit it (it does **not** force them to).

---

## 11) `logconfig.json` example

```json
{
  "logger_level": "INFO",
  "handlers": {
    "file":   { "level": "DEBUG",   "formatter": "verbose", "maxBytes": 10000000, "backupCount": 5 },
    "stdout": { "level": "INFO",    "formatter": "default" }
  },
  "loggers": {
    "applogger.ui":      { "level": "INFO",    "propagate": true },
    "applogger.service": { "level": "DEBUG",   "propagate": true },
    "applogger.jobs":    { "level": "INFO",    "propagate": true },
    "applogger.db":      { "level": "WARNING", "propagate": true }
  },
  "third_party_log_level": "WARNING"
}
```

---

## 12) Code snippets

**Module logger**
```python
logger = logging.getLogger("applogger.service")
```

**Corr‑ID usage**
```python
corr = str(uuid.uuid4())
logger.info("ExportController: export started (corr=%s, path=%s)", corr, path)
```

**Exception with traceback**
```python
try:
    ...
except Exception as e:
    logger.error("FileWriter: Excel write failed (corr=%s, path=%s): %s", corr, path, e, exc_info=True)
    raise
```

---

## 13) FAQ

**"I set `third_party_log_level = DEBUG` but output is still quiet."**  
Wildcard filtering *allows* DEBUG from libraries; it does **not** force them to produce DEBUG. Also, TQDM is disabled and Matplotlib font caching may have completed already.

**"Why do I only see 0→100 progress?"**  
Usually missing `progress_cb` in the signature along the job path, chunk sizes too large for the data, or no granular progress from the underlying library.

---

## 14) Changelog

- Restored DEBUG interactive analysis request events and section-qualified
  `Advanced analysis (Section)` request/completion prefixes across all categories.
- **1.2** — `Component: event (corr=..., key=value)` naming convention; Advanced
  Analysis diagnostics emit one summary line per computation, chart batch, and
  report instead of nested start/finish pairs.
- **1.1** — Advanced Analysis diagnostic ownership, explicit correlation, metadata
  exclusions, and clarification of shipped defaults.
- **1.0** — Initial release: namespaces, wildcard for third‑party, corr‑ID policy, Excel robustness, progress guidelines, recommended levels.

---

## 15) Advanced Analysis diagnostics

Advanced Analysis uses the existing namespaces and logging configuration. It does
not require new settings, handlers, or third-party DEBUG output.

| Owner | Diagnostic responsibility |
| --- | --- |
| UI/controller | DEBUG `Advanced analysis (Section): computation requested` before scheduling, operation correlation, stale-result handling, and presentation failures |
| JobManager | Worker lifecycle, cancellation requests, unexpected exceptions, and total job duration |
| Analysis services (`Advanced analysis (Section)`) | DEBUG `computation finished` with duration, typed success/unavailable/cancelled outcome, and safe cohort/feature counts |
| GLM/Cox services (`AnalysisService`) | WARNING `model fit failed` when fitting fails recoverably: exception class, non-convergence, or non-finite estimates |
| Chart services (`AnalysisChartService`) | DEBUG `chart batch finished` per export batch; raster lines only for standalone rasters or cancelled/failed rasters |
| Report service (`AnalysisReportService`) | DEBUG `report stage finished` once per report; nested stages only when cancelled or failed |
| Export services/writer | Existing file-write, cancellation, and export success/failure records |

**Job finalization is not analytical success.** A job may finish normally with an
unavailable analysis, a recovered fit failure, cancellation, or a failed export
result. Consult the typed service outcome or export result alongside job records.

Each computation, export, or preview has its own `corr_id`. Controllers pass that
ID explicitly through service calls. Analysis chart factories capture the export
ID and pass it to renderers; report rendering passes it through entry preparation
and rasterization. Existing callers can omit the optional ID. Correlation is
never taken from mutable dialog-wide or thread-local context.

**Interactive request and computation completion.** Before scheduling an initial
analysis or configuration-driven recomputation, the controller logs
`Advanced analysis (Section): computation requested (corr=..., scope=..., rows=..., cols=...)`.
The computation's existing completion line uses the same section prefix and
correlation identifier, retaining its outcome and timing metadata.
Both events use the exact `scope` supplied to JobManager instead of separate
`operation` and `method` fields. The controller defines this scope once and
exposes it to diagnostics only while its worker computation runs, using a
context variable restored in `finally` to isolate concurrent and reused workers.
Correlation identifiers remain explicitly passed arguments. Standalone service
calls without a controller job retain operation/method metadata rather than
inventing a JobManager scope.
Section labels are stable English: Overview, Statistics, Hypothesis Tests,
Correlation, Regression, Outliers, Clustering, PCA and Time Series.
Hypothesis subtests, regression variants and outlier variants retain their
distinct job scopes under their parent section.
Completion means the calculation returned, not that its result was displayed.
JobManager retains worker lifecycle and unexpected-exception ownership.

**Exports and reports remain summarized.**
A chart batch or report stage opens a summary scope (`summary_scope()` in
`services/analysis/diagnostics.py`, backed by a per-thread context variable).
Inside it, successful nested computations (for example per-chart outlier or
correlation-pair recomputation), rasters, batches, and stages stay silent, so an
Excel export logs one batch line and an HTML report logs one `stage=render_html`
line. Cancellations and failures are always logged with their stage, entry
ordinal, and category so the stopping point remains visible.

Normal input limitations (for example, too few observations or no eligible
columns), statistical caveats, sampling, cancellation, and stale results are not
operational errors. They must not generate new WARNING/ERROR records. Recovered
GLM/Cox fitting failures use WARNING without dumping exception messages or data.
Unexpected exceptions still propagate to the existing worker/export boundary;
services must not add repeated tracebacks at each layer.

New diagnostics contain only metadata: stable operation/method/reason codes,
counts, booleans, elapsed milliseconds, chart dimensions, and layout-pass counts.
Analysis job scopes use bounded category/action/method identifiers, not selected
column names. Do not log dataset labels, column/group names, row identifiers,
values, model coefficients, p-values, report titles/descriptions/notes, complete
results, HTML, or image payloads. This rule does not imply that legacy general
exception/path logging elsewhere in the application has been sanitized.

Keep diagnostics bounded to operations, report entries/stages, and chart batches
or rasters. Do not log individual rows, correlation pairs, optimizer iterations,
progress ticks, repaint/resize events, or lock retries. Preserve the live canvas's
existing one-shot layout-limit warnings.
