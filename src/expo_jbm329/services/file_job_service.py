"""Service for managing file-related background jobs and operations.

This module provides the FileJobService class, which coordinates importing, exporting,
profiling, and classification of files within the application.
"""

from __future__ import annotations

import contextlib
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
from PyQt6.QtCore import QT_TR_NOOP

from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.gui_utils import ui_invoke
from expo_jbm329.utils.format_utils import fmt_path, fmt_shape, fmt_time
from expo_jbm329.utils.i18n_utils import tr, tr_fmt

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )
    from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager


class FileJobService:
    """Service for data file I/O background jobs.

    Responsibilities:
      • Execute file-related background jobs (import/export/profiling)
      • Provide correct progress forwarding to both loader progress callbacks
        and BlockingProgressDialog (worker.progress)
      • Provide consistent filename sanitizing and uniqueness logic
      • Provide safe renaming operations with status feedback

    Notes:
      - All heavy I/O is executed through AsyncOperationController, which delegates execution to JobManager.
    """

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_OPENED_SQL_FILE = QT_TR_NOOP("Opened SQL file: {file_name}")
    TR_SAVED_SQL_FILE = QT_TR_NOOP("Saved SQL file: {file_name}")

    TR_FAILURE = QT_TR_NOOP("Failure")
    TR_OPEN_SQL_FILE_FAILED = QT_TR_NOOP("Open SQL file failed")
    TR_SAVE_SQL_FILE_FAILED = QT_TR_NOOP("Save SQL file failed")
    TR_OPEN_SQL_FILE_FAILED_ERROR = QT_TR_NOOP("Open SQL file failed:\n{error}")
    TR_SAVE_SQL_FILE_FAILED_ERROR = QT_TR_NOOP("Save SQL file failed:\n{error}")
    TR_OPEN_HTML_FILE_FAILED_ERROR = QT_TR_NOOP("Open HTML file failed:\n{error}")
    TR_LOADING_DATA_CANCELLED = QT_TR_NOOP("Loading data from file cancelled")

    TR_LOADING_DATA_FILE = QT_TR_NOOP("Loading data from file: {file_name} …")
    TR_LOADING_DATA_FAILED = QT_TR_NOOP("Loading data from file failed")
    TR_LOADING_DATA_FAILED_ERROR = QT_TR_NOOP("Loading data from file failed:\n{error}")

    TR_OPENED_DATA_FILE_ELAPSED = QT_TR_NOOP(
        "Completed: Opened file {file_name} - {rows} rows, {columns} columns ({elapsed_time})"
    )
    TR_OPENED_DATA_FILE = QT_TR_NOOP("Completed: Opened file {file_name} - {rows} rows, {columns} columns")
    TR_PROCESSING = QT_TR_NOOP("Processing…")

    TR_MISSING = QT_TR_NOOP("(missing)")
    TR_FILE_EXT_ADJUSTED = QT_TR_NOOP("File extension adjusted: '{old_ext}' → '{new_ext}'")
    TR_RENAMED_FILE_NAME = QT_TR_NOOP("Renamed file to: {new_file_name}")
    TR_RENAME_FILE_FAILED = QT_TR_NOOP("Rename file failed")
    TR_RENAME_FILE_FAILED_ERROR = QT_TR_NOOP("Rename file failed:\n{error}")

    TR_NO_SQL = QT_TR_NOOP("No SQL")
    TR_NO_ACTIVE_TAB = QT_TR_NOOP("There is no active tab to save.")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("FileJobService", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("FileJobService", text, **kwargs)

    __slots__ = (
        "_async_ops",
        "_dialogs",
        "_display_dataframe",
        "_get_active_tab_title",
        "_is_shutting_down_cb",
        "_logger",
        "_operation_target",
        "_parent",
        "_resolve_and_load_df",
        "_results",
        "_set_status",
    )

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def __init__(
        self,
        *,
        parent_widget: QWidget,
        async_ops: AsyncOperationController,
        results: ResultTabManager,
        set_status: Callable[[str, int | None], None],
        get_active_tab_title: Callable[[], str],
        resolve_and_load_df: Callable[..., Any],
        display_dataframe: Callable[..., None],
        dialogs: DialogService,
        is_shutting_down: Callable[[], bool] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize FileJobService.

        Args:
            parent_widget: The parent QWidget for dialogs.
            async_ops: AsyncOperationController instance.
            results: ResultTabManager instance.
            set_status: Callback to set status messages.
            get_active_tab_title: Callback to get the active tab title.
            resolve_and_load_df: Callback to resolve and load a DataFrame.
            display_dataframe: Callback to display a DataFrame.
            dialogs: Dialog service.
            is_shutting_down: Callback to check if the application is shutting down.
            logger: Optional logger instance.
        """
        self._parent = parent_widget
        self._async_ops = async_ops
        self._results = results
        self._set_status = set_status
        self._get_active_tab_title = get_active_tab_title
        self._display_dataframe = display_dataframe
        self._resolve_and_load_df = resolve_and_load_df
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._is_shutting_down_cb = is_shutting_down
        self._logger = logger if logger is not None else logging.getLogger("applogger.service")

    # ==================================================================
    # Public facade: open data file
    # ==================================================================

    def open_data_file(self, *, path: str | Path) -> None:
        """Open a data file into a pending result tab using AsyncOperationController.

        Args:
            path: The path to the data file.
        """
        import uuid

        p = Path(path)
        suffix = p.suffix.lower()
        file_name = p.name

        indeterminate = suffix in {
            ".qvd",
            ".parquet",
            ".pkl",
            ".pickle",
            ".feather",
            ".ft",
            ".dta",
            ".sav",
        }

        corr = uuid.uuid4().hex
        scope = f"load:{suffix.lstrip('.') or 'file'}"
        started_msg = self._tr_fmt(
            self.TR_LOADING_DATA_FILE,
            file_name=file_name,
        )

        self._logger.info(
            "FileJobService: loading data file requested (path=%s, suffix=%s, indeterminate=%s, corr=%s)",
            fmt_path(p),
            suffix,
            indeterminate,
            corr,
        )

        pending_handle = self._results.create_pending_tab(
            title=file_name,
            origin_type="file",
            remove_on_cancel=True,
            remove_on_error=True,
            close_cancels_job=True,
        )

        pending_tab_id = pending_handle.tab_id
        pending_view = pending_handle.view

        def _work(*, progress_cb=None, cancel_cb=None, job_id=None, job_scope=None, **_):
            self._logger.debug(
                "FileJobService: data file job started (corr=%s, job_id=%s, scope=%s, path=%s, tab_id=%s)",
                corr,
                job_id,
                job_scope,
                fmt_path(p),
                pending_tab_id,
            )

            return self._resolve_and_load_df(
                str(p),
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
                job_id=job_id,
                job_scope=job_scope,
                corr_id=corr,
            )

        def _on_result(payload: Any) -> None:
            """Handle file load result for the pending result tab."""
            self._on_data_loaded(
                payload,
                fmt_path(p),
                corr=corr,
                pending_tab_id=pending_tab_id,
            )

        def _on_error(err: str) -> None:
            """Handle file load error for the pending result tab."""
            self._on_data_load_error(
                err,
                fmt_path(p),
                corr=corr,
                pending_tab_id=pending_tab_id,
            )

        job = self._async_ops.run_target_overlay_operation(
            target=pending_view,
            runner="thread",
            work=_work,
            on_result=_on_result,
            on_error=_on_error,
            busy_message=started_msg,
            scope=scope,
            operation_name=self._tr(self.TR_LOADING_DATA_FAILED),
            timeout_ms=0,
            indeterminate=indeterminate,
            cancelable=True,
            show_status_progress=False,
            show_started_in_status=False,
            suppress_error_dialog=True,
            stale_check=self._is_shutting_down,
            corr_id=corr,
        )

        jobid = self._async_ops.job_mgr.get_job_id(job)
        if jobid is not None:
            self._results.bind_job_to_tab(pending_tab_id, jobid)
        else:
            self._logger.warning(
                "FileJobService: could not bind file load job to pending tab (corr=%s, tab_id=%s, path=%s).",
                corr,
                pending_tab_id,
                fmt_path(p),
            )

    # ------------------------------------------------------------------
    # Internal result handlers (UI logic stays inside the service)
    # ------------------------------------------------------------------

    def _on_data_loaded(
        self,
        payload: Any,
        path: str,
        *,
        corr: str | None = None,
        pending_tab_id: str | None = None,
    ) -> None:
        """Handle data load completion.

        Args:
            payload: The loaded data payload (JobResult).
            path: The path of the loaded file.
            corr: Optional correlation identifier.
            pending_tab_id: The ID of the pending result tab.
        """
        from pathlib import Path as _Path

        from expo_jbm329.services.job_result import JobResult

        corr_eff = (getattr(payload, "corr_id", None) if isinstance(payload, JobResult) else None) or corr

        if self._is_shutting_down():
            self._logger.info(
                "FileJobService: data load result ignored during shutdown (corr=%s, path=%s)",
                corr_eff,
                fmt_path(path),
            )
            return

        if not isinstance(payload, JobResult):
            self._logger.error(
                "FileJobService: unexpected non-JobResult payload received (corr=%s, path=%s, type=%s).",
                corr_eff,
                fmt_path(path),
                type(payload).__name__,
            )
            msg = "FileJobService expected JobResult"
            raise TypeError(msg)

        if payload.cancelled:
            self._logger.info(
                "FileJobService: data load cancelled (corr=%s, path=%s, tab_id=%s)",
                corr_eff,
                fmt_path(path),
                pending_tab_id,
            )

            if pending_tab_id is not None:
                self._results.remove_pending_tab(pending_tab_id)

            if not self._is_shutting_down():
                self._set_status(self._tr(self.TR_LOADING_DATA_CANCELLED), 6000)
            return

        if not payload.ok or payload.data is None:
            self._logger.error(
                "FileJobService: data load result not ok (corr=%s, path=%s, tab_id=%s, error=%s)",
                corr_eff,
                fmt_path(path),
                pending_tab_id,
                payload.error,
            )

            if pending_tab_id is not None:
                self._results.remove_pending_tab(pending_tab_id)

            if not self._is_shutting_down():
                status = self._tr(self.TR_LOADING_DATA_FAILED)
                self._set_status(status, 6000)
                self._dialogs.critical(
                    parent=self._parent,
                    title=self._tr(self.TR_FAILURE),
                    text=payload.error or self._tr(self.TR_LOADING_DATA_FAILED),
                )
            return

        self._logger.debug(
            "FileJobService: processing successful data load result (corr=%s, path=%s)",
            corr_eff,
            fmt_path(path),
        )

        df_obj = payload.data
        if not isinstance(df_obj, pd.DataFrame):
            self._logger.error(
                "FileJobService: expected DataFrame in successful job result (corr=%s, path=%s, tab_id=%s, type=%s)",
                corr_eff,
                fmt_path(path),
                pending_tab_id,
                type(df_obj).__name__,
            )

            if pending_tab_id is not None:
                self._results.remove_pending_tab(pending_tab_id)

            if not self._is_shutting_down():
                status = self._tr(self.TR_LOADING_DATA_FAILED)
                self._set_status(status, 6000)
                self._dialogs.critical(
                    parent=self._parent,
                    title=self._tr(self.TR_FAILURE),
                    text=self._tr(self.TR_LOADING_DATA_FAILED),
                )
            return

        df = df_obj
        elapsed_s = payload.elapsed

        title = _Path(path).name

        if pending_tab_id is not None:
            self._results.fulfill_pending_tab(pending_tab_id, df)
        else:
            self._display_dataframe(df, title=title)

        rows, columns = fmt_shape(df)
        if elapsed_s:
            elapsed_time = fmt_time(elapsed_s)
            txt = self._tr_fmt(
                self.TR_OPENED_DATA_FILE_ELAPSED,
                file_name=title,
                rows=rows,
                columns=columns,
                elapsed_time=elapsed_time,
            )
        else:
            txt = self._tr_fmt(
                self.TR_OPENED_DATA_FILE,
                file_name=title,
                rows=rows,
                columns=columns,
            )

        ui_invoke(self._set_status, txt, 10000)

        self._logger.info(
            "FileJobService: displayed DataFrame (corr=%s, path=%s, rows=%s, cols=%s, elapsed=%s)",
            corr_eff,
            fmt_path(path),
            rows,
            columns,
            (fmt_time(elapsed_s) if elapsed_s else None),
        )

    def _on_data_load_error(
        self,
        err: str,
        path: str,
        *,
        corr: str | None = None,
        pending_tab_id: str | None = None,
    ) -> None:
        """Handle data load error.

        Args:
            err: The error message.
            path: The path of the file that failed to load.
            corr: Optional correlation identifier.
            pending_tab_id: Optional pending tab identifier to remove on failure.
        """
        if self._is_shutting_down():
            self._logger.info(
                "FileJobService: data load error ignored during shutdown (corr=%s, path=%s, tab_id=%s)",
                corr,
                fmt_path(path),
                pending_tab_id,
            )
            return

        if pending_tab_id is not None:
            self._results.remove_pending_tab(pending_tab_id)

        self._logger.error(
            "Data load error (corr=%s, path=%s, tab_id=%s): %s",
            corr,
            fmt_path(path),
            pending_tab_id,
            err,
        )

        status = self._tr(self.TR_LOADING_DATA_FAILED)
        self._set_status(status, 6000)
        self._dialogs.critical(
            parent=self._parent,
            title=self._tr(self.TR_FAILURE),
            text=self._tr_fmt(self.TR_LOADING_DATA_FAILED_ERROR, error=str(err)),
        )

    # ==================================================================
    # Filename building & sanitizing
    # ==================================================================
    _SUFFIX_PAT = re.compile(r"\*\.[A-Za-z0-9_-]+")

    def _suffixes_from_qt_filter(self, selected_filter: str) -> list[str]:
        """Extract allowed suffixes from a Qt filter string.

        Args:
            selected_filter: The Qt filter string (e.g., "CSV-filer (*.csv)").

        Returns:
            A list of allowed suffixes.
        """
        if not selected_filter:
            return []
        return [m.group(0)[1:].lower() for m in self._SUFFIX_PAT.finditer(selected_filter)]
        # m.group(0) = "*.csv" → [1:] = ".csv"

    def coerce_save_suffix(self, path: str, selected_filter: str, fallback: str | None = None) -> str:
        """Ensure the path has an allowed suffix according to the selected filter.

        Args:
            path: The original path.
            selected_filter: The selected Qt filter.
            fallback: Optional fallback suffix if no filter is matched.

        Returns:
            The potentially corrected path string.
        """
        p = Path(path)
        allowed_list = self._suffixes_from_qt_filter(selected_filter)

        if not allowed_list and fallback:
            fb = fallback if fallback.startswith(".") else f".{fallback}"
            allowed_list = [fb.lower()]

        if not allowed_list:
            return str(p)

        old = p.suffix.lower()
        allowed = set(allowed_list)

        # Nothing to do
        if old in allowed:
            return str(p)

        # Build new name with first allowed suffix
        base_name = p.name
        for s in p.suffixes:
            base_name = base_name[: -len(s)]
        new_ext = allowed_list[0]
        fixed = p.with_name(base_name + new_ext)

        # “Toast” via statusbar (non-modal, 5s)
        with contextlib.suppress(Exception):
            old_ext = old or self._tr(self.TR_MISSING)
            status = self._tr_fmt(self.TR_FILE_EXT_ADJUSTED, old_ext=old_ext, new_ext=new_ext)
            self._set_status(status, 5000)

        return str(fixed)

    # noinspection PyMethodMayBeStatic
    def sanitize_filename(self, name: str) -> str:
        """Remove prohibited characters and normalize whitespace in a filename.

        Args:
            name: The filename to sanitize.

        Returns:
            The sanitized filename.
        """
        forbidden = '<>:"/\\|?*'
        cleaned = name.translate(str.maketrans("", "", forbidden))
        cleaned = cleaned.replace("*", "").replace("?", "").strip().rstrip(".")
        return cleaned or "export"

    # noinspection PyMethodMayBeStatic
    def strip_suffix(self, name: str) -> str:
        """Remove the file extension from a filename.

        Args:
            name: The filename.

        Returns:
            The stem of the filename.
        """
        return Path(name).stem

    def build_export_filename(self, suffix: str, base_dir: str) -> str:
        """Build a unique export filename based on the active tab title.

        Args:
            suffix: The desired file suffix.
            base_dir: The base directory for exports.

        Returns:
            A unique filename.
        """
        title = self._get_active_tab_title()
        stem = self.sanitize_filename(self.strip_suffix(title))

        max_len = 255 - len(suffix)
        stem = stem[:max_len] if len(stem) > max_len else stem

        candidate = f"{stem}{suffix}"
        base_path = Path(base_dir)

        counter = 1
        while (base_path / candidate).exists():
            candidate = f"{stem}({counter}){suffix}"
            counter += 1

        return candidate

    def build_safe_filename(self, name: str, suffix: str, base_dir: Path) -> Path:
        """Build a safe, unique filename for rename operations.

        Args:
            name: The desired base name.
            suffix: The file suffix.
            base_dir: The directory where the file resides.

        Returns:
            A unique Path object.
        """
        stem = self.sanitize_filename(self.strip_suffix(name)) or "rename"

        max_len = 255 - len(suffix)
        stem = stem[:max_len] if len(stem) > max_len else stem

        candidate = f"{stem}{suffix}"
        path = base_dir / candidate

        counter = 1
        while path.exists():
            candidate = f"{stem}({counter}){suffix}"
            path = base_dir / candidate
            counter += 1

        return path

    # ==================================================================
    # File rename
    # ==================================================================
    def rename_file(self, old_path: Path, new_name: str) -> tuple[bool, str | None]:
        """Perform a safe rename operation with status feedback.

        Args:
            old_path: The current path of the file.
            new_name: The new desired name.

        Returns:
            A tuple of (success_boolean, error_message_or_none).
        """
        parent_dir = old_path.parent
        suffix = old_path.suffix.lower()

        new_path = self.build_safe_filename(new_name, suffix, parent_dir)

        try:
            old_path.rename(new_path)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as e:
            msg = self._tr_fmt(self.TR_RENAME_FILE_FAILED_ERROR, error=str(e))
            self._set_status(self._tr(self.TR_RENAME_FILE_FAILED), 6000)
            return False, msg

        self._set_status(self._tr_fmt(self.TR_RENAMED_FILE_NAME, new_file_name=new_path.name), 10000)
        return True, None

    # ==================================================================
    # Shutdown check
    # ==================================================================

    def _is_shutting_down(self) -> bool:
        """Return True if the application is shutting down."""
        cb = self._is_shutting_down_cb
        if cb is None:
            return False

        try:
            return bool(cb())
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self._logger.debug(
                "FileJobService: shutdown state callback failed.",
                exc_info=True,
            )
            return False
