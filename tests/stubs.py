# tests/stubs.py
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from PyQt6.QtCore import QObject, pyqtSignal

from expo_jbm329.gui.dialogs.service.dialog_service import ProfileChoice
from expo_jbm329.gui.dialogs.service.null_dialog_service import NullDialogService
from expo_jbm329.gui.dialogs.workflows.file.file_dialog_service import NullFileDialogService
from expo_jbm329.services.job_result import JobResult


class DummyResult:
    """Mock for SqlResult from execute_sql_safe."""
    def __init__(self, data=None, ok=True, rows=0, elapsed_s=0.0, error=None):
        self.data = data
        self.ok = ok
        self.rows = rows
        self.elapsed_s = elapsed_s
        self.error = error

class DummyWorker:
    """Simulates the Worker object returned by JobManager.run."""
    def __init__(self):
        self.result = DummySignal()
        self.error = DummySignal()

class DummySignal:
    """Simple signal replacement collecting callbacks."""
    def __init__(self):
        self.callbacks = []
    def connect(self, cb):
        self.callbacks.append(cb)
    def emit(self, value):
        for cb in self.callbacks:
            cb(value)

class DummyJobManager:
    """Captures run() calls and returns a DummyWorker."""
    def __init__(self):
        self.last_run = None
        self.worker = DummyWorker()
    def run(self, parent, fn, *args, **kwargs):
        self.last_run = {"parent": parent, "fn": fn, "args": args, "kwargs": kwargs}
        return self.worker
    def get_job_id(self):
        return "job_123"

class DummyAsyncOps:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def run_target_overlay_operation(self, **kwargs):
        self.calls.append(kwargs)
        work = kwargs["work"]
        result = work(progress_cb=None, cancel_cb=None, job_id="job_123", job_scope=kwargs.get("scope"))
        on_result = kwargs.get("on_result")
        if callable(on_result):
            on_result(result if isinstance(result, JobResult) else JobResult(ok=True, elapsed=0.1, path=None))
        return result

class DummyResults:
    """
    results: has current_df(), tabs.count(), collect_all_tabs_data(), display_dataframe().
    """
    def __init__(self, df: pd.DataFrame | None = None, tabs_count: int = 1,
                 data_all: list[tuple[pd.DataFrame, str]] | None = None):
        self._df = df
        self.tabs = SimpleNamespace(count=lambda: tabs_count)
        self._data_all = data_all or []
        self.closed_titles = []
        self.display_calls = []

    def current_df(self):
        return self._df

    def collect_all_tabs_data(self):
        return list(self._data_all)

    def ready_dataset_count(self):
        return len(self._data_all) if self._data_all else 1 if self._df is not None else 0

    def close_tabs_by_title(self, title: str):
        self.closed_titles.append(title)

    def display_dataframe(self, df: pd.DataFrame):
        self.display_calls.append(df)

class DummyFileJobs:
    """
    Minimal service: build_export_filename, coerce_save_suffix, format_to_behaviour, run,
    classify_file, open_data_file, open_sql_file, open_html_file, rename_file
    Capture: last_run (args/kwargs)
    """
    def __init__(self, behaviour_map: dict[str, str] | None = None):
        self.behaviour_map = behaviour_map or {
            ".csv": "nonblocking",
            ".xlsx": "nonblocking",
            ".df": "nonblocking",
            ".feather": "nonblocking",
            ".ft": "nonblocking",
            ".parquet": "nonblocking",
            "html": "nonblocking",
        }
        self.last_run = None
        self.run_calls = 0
        self.open_data_calls = []
        self.open_sql_calls = []
        self.open_html_calls = []
        self.rename_calls = []
        self.open_html_return = (True, None)
        self.rename_return = (True, None)

    def classify_file(self, path: Path | str) -> str:
        suf = Path(path).suffix.lower()
        if suf in (".csv", ".xlsx", ".feather", ".ft", ".parquet", ".df", ""):
            return "data"
        if suf == ".sql":
            return "sql"
        if suf == ".html":
            return "html"
        return "unknown"

    def open_data_file(self, path: str):
        self.open_data_calls.append(path)

    def open_sql_file(self, path: Path | str):
        self.open_sql_calls.append(Path(path))

    def open_html_file(self, path: Path | str):
        self.open_html_calls.append(Path(path))
        return self.open_html_return

    def rename_file(self, old_path: Path | str, new_name: str):
        self.rename_calls.append((Path(old_path), new_name))
        return self.rename_return

    def build_export_filename(self, ext: str, base: str) -> str:
        return f"default{ext}"

    def coerce_save_suffix(self, path: str, selected_filter: str, fallback: str) -> str:
        return path

    def format_to_behaviour(self, suffix_or_key: str) -> str:
        return self.behaviour_map.get(suffix_or_key, "nonblocking")

    def run(self, **kwargs):
        self.last_run = kwargs
        self.run_calls += 1

class DummyDataIO:
    """
    Minimal data_io with methods called by ExportController.
    """
    def export_df_csv(self, *a, **k): return JobResult(ok=True, elapsed=0.1, path=k.get("path") or (a[1] if len(a) > 1 else None))
    def export_df_excel(self, *a, **k): return JobResult(ok=True, elapsed=0.1, path=k.get("path") or (a[1] if len(a) > 1 else None))
    def export_df_datafile(self, *a, **k): return JobResult(ok=True, elapsed=0.1, path=k.get("path") or (a[1] if len(a) > 1 else None))
    def export_df_profile(self, *a, **k): return JobResult(ok=True, elapsed=0.1, path=k.get("path") or (a[1] if len(a) > 1 else None))
    def export_dfs_profile(self, *a, **k): return JobResult(ok=True, elapsed=0.1, path=k.get("path") or (a[1] if len(a) > 1 else None))

class DummyStatusLogger:
    """Captures set_status calls."""
    def __init__(self):
        self.messages: list[tuple[str, int | None]] = []
    
    def set_status(self, text: str, timeout: int | None = None):
        self.messages.append((text, timeout))

class DummyIconService:
    def __init__(self):
        self.icons = {}

    def get(self, name: str):
        if name not in self.icons:
            from PyQt6.QtGui import QIcon
            self.icons[name] = QIcon()
        return self.icons[name]

class DummyDialogState:
    def __init__(self, directory: str = "C:/tmp") -> None:
        self.directory = directory
        self.calls: list[tuple[str, str, str | None]] = []

    def get_dir(self, key: str, fallback: str | None = None) -> str:
        self.calls.append(("get_dir", key, fallback))
        return self.directory

    def set_dir(self, key: str, value: str) -> None:
        self.calls.append(("set_dir", key, value))
        self.directory = value

def make_dialog_services(profile_choice=ProfileChoice.ACTIVE):
    return NullDialogService(default_profile_choice=profile_choice), NullFileDialogService()

class DummyThemeService(QObject):
    theme_changed = pyqtSignal(str)

    def __init__(self, theme="light"):
        super().__init__()
        self.theme = theme

    def resolve_theme(self):
        return self.theme

    def set_theme(self, theme):
        self.theme = theme
        self.theme_changed.emit(theme)
