
# Logging Policy (logging.md)

> Applies to the Expo project (`expo_jbm329`).  
> Version: **1.0**

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
logger.info("Export requested (corr=%s, kind=Excel, path=%s)", corr, path)
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
logger.info("Start export (corr=%s, path=%s)", corr, path)
```

**Exception with traceback**
```python
try:
    ...
except Exception as e:
    logger.error("Excel write failed (corr=%s, path=%s): %s", corr, path, e, exc_info=True)
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

- **1.0** — Initial release: namespaces, wildcard for third‑party, corr‑ID policy, Excel robustness, progress guidelines, recommended levels.
