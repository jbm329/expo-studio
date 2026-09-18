"""Export controller for exporting DataFrames and generating reports.

This module provides the ExportController class, which orchestrates exporting
DataFrames to various formats (CSV, Excel, data files) and generating ydata-profiling
reports. It handles file dialogs, format validation, job scheduling, and progress
tracking for export operations.
"""

from __future__ import annotations

import logging
import uuid
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Final

from PyQt6.QtCore import QT_TR_NOOP

from expo_jbm329.gui.dialogs.service.dialog_service import DialogService, ProfileChoice
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.dialogs.workflows.file.file_dialog_service import (
    FileDialogService,
    QtFileDialogService,
    SaveFileRequest,
)
from expo_jbm329.services.job_result import JobResult
from expo_jbm329.utils.format_utils import fmt_path, fmt_shape, fmt_time
from expo_jbm329.utils.i18n_utils import tr, tr_fmt
from expo_jbm329.utils.path_manager import get_documents_dir

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import pandas as pd
    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.utils.dialog_state import DialogState
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )


class ExportKind(Enum):
    """Enumeration of export kinds."""

    CSV = auto()
    EXCEL = auto()
    DATAFILE = auto()
    PROFILE = auto()
    PROFILE_COMPARE = auto()


class ExportController:
    """Controller for exporting DataFrames and generating profiling reports.

    This class handles all export operations including CSV, Excel, and binary
    data formats, as well as ydata-profiling report generation for single or
    multiple datasets. It manages file dialogs, coordinates with FileJobService
    for background processing, and provides comprehensive logging and error handling.
    """

    # --- i18n markers (pylupdate6-visible) -----------------------------
    # No dataset
    TR_NO_DATASET_TITLE = QT_TR_NOOP("No dataset")
    TR_NO_DATASET_TEXT = QT_TR_NOOP("There is no dataset to export.")
    TR_NO_DATASET_PROFILE_TEXT = QT_TR_NOOP("There is no dataset to profile.")

    # CSV export
    TR_KIND_CSV = QT_TR_NOOP("Export data to CSV")
    TR_EXPORT_CSV_DIALOG_FILTER = QT_TR_NOOP("CSV files (*.csv)")

    # Excel export
    TR_KIND_EXCEL = QT_TR_NOOP("Export data to Excel")
    TR_EXPORT_EXCEL_DIALOG_FILTER = QT_TR_NOOP("Excel files (*.xlsx)")

    # Datafile Export
    TR_KIND_DATAFILE = QT_TR_NOOP("Export data to binary data file")
    TR_EXPORT_DATAFILE_DIALOG_FILTER = QT_TR_NOOP(
        "All data files (*.df *.feather *.ft *.parquet);;Pickle (*.df);;Feather (*.feather *.ft);;Parquet (*.parquet)"
    )

    # Profile report
    TR_KIND_PROFILE = QT_TR_NOOP("Generate data profile report")
    TR_EXPORT_PROFILE_DIALOG_FILTER = QT_TR_NOOP("HTML files (*.html)")
    TR_EXPORT_PROFILE_STARTED_MSG = QT_TR_NOOP("Generating data profile report {title}…")

    # Multiple tabs
    TR_EXPORT_DATA_MULTIPLE_TABS_DIALOG_TITLE = QT_TR_NOOP("Multiple datasets open")
    TR_EXPORT_DATA_MULTIPLE_TABS_DIALOG_TEXT = QT_TR_NOOP("Multiple datasets are open. What do you want to profile?")
    TR_EXPORT_DATA_MULTIPLE_ACTIVE_TAB = QT_TR_NOOP("Active tab: {profile_kind}")
    TR_EXPORT_DATA_MULTIPLE_ALL_TABS = QT_TR_NOOP("All tabs: {comparison_kind}")

    # Comparison profile report
    TR_KIND_COMPARISON_PROFILE = QT_TR_NOOP("Generate data profile comparison report")
    TR_EXPORT_COMPARISON_PROFILE_FILE_EXT = QT_TR_NOOP("_comparison.html")
    TR_EXPORT_COMPARISON_PROFILE_DIALOG_FILTER = QT_TR_NOOP("HTML files (*.html)")
    TR_EXPORT_COMPARISON_PROFILE_STARTED_MSG = QT_TR_NOOP(
        "Generating data profile comparison report with {datasets_cnt} datasets…"
    )

    # General messages
    TR_EXPORT_STARTED_MSG = QT_TR_NOOP("Exporting data to {file_name}…")
    TR_DONE_STATUS_FILE = QT_TR_NOOP("{kind_label} completed: {file_name}")
    TR_DONE_STATUS_TIME_FILE = QT_TR_NOOP("{kind_label} completed: {time_str}: {file_name}")

    # Exceptions
    TR_EXCEPT_UNKNOWN_RESULT = QT_TR_NOOP("Unknown job result")
    TR_EXCEPT_UNKNOWN_ERROR = QT_TR_NOOP("Unknown error")
    TR_DONE_STATUS_FAIL = QT_TR_NOOP("{kind_label} failed")
    TR_DONE_STATUS_CANCEL = QT_TR_NOOP("{kind_label} cancelled")
    TR_DONE_CANCEL_DIALOG_TEXT = QT_TR_NOOP("Operation was cancelled.")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("ExportController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("ExportController", text, **kwargs)

    _EXPORT_LABELS: Final[dict[ExportKind, str]] = {
        ExportKind.CSV: TR_KIND_CSV,
        ExportKind.EXCEL: TR_KIND_EXCEL,
        ExportKind.DATAFILE: TR_KIND_DATAFILE,
        ExportKind.PROFILE: TR_KIND_PROFILE,
        ExportKind.PROFILE_COMPARE: TR_KIND_COMPARISON_PROFILE,
    }

    __slots__ = (
        "__weakref__",
        "_async_ops",
        "_data_io",
        "_dialog_state",
        "_dialogs",
        "_documents_dir",
        "_file_dialogs",
        "_file_jobs",
        "_get_tab_title",
        "_logger",
        "_open_url",
        "_operation_target",
        "_parent",
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
        operation_target: QWidget,
        results,
        set_status: Callable[[str, int | None], None],
        file_jobs,
        get_tab_title: Callable[[], str],
        open_url: Callable[[str], bool],
        data_io,
        dialogs: DialogService | None = None,
        file_dialogs: FileDialogService | None = None,
        dialog_state: DialogState,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the ExportController.

        Args:
            parent_widget: The parent widget.
            async_ops: AsyncOperationController for managing asynchronous operations.
            operation_target: The widget that will be used as the target for busy overlay.
            results: ResultTabManager for accessing DataFrames.
            set_status: Callback to set status messages.
            file_jobs: FileJobService for scheduling export jobs.
            get_tab_title: Callback to get the current tab title.
            open_url: Callback to open URLs.
            data_io: DataIO service for export operations.
            dialogs: Optional dialog service.
            file_dialogs: Optional file dialog service.
            dialog_state: DialogState instance for managing dialog state.
            logger: Optional logger instance.
        """
        self._parent = parent_widget
        self._async_ops = async_ops
        self._operation_target = operation_target
        self._results = results
        self._set_status = set_status
        self._file_jobs = file_jobs
        self._get_tab_title = get_tab_title
        self._open_url = open_url
        self._data_io = data_io
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._file_dialogs = file_dialogs if file_dialogs is not None else QtFileDialogService()
        self._dialog_state = dialog_state
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._documents_dir: Path | None = None

    # ==================================================================
    # Properties read-only
    # ==================================================================
    @property
    def file_jobs(self):
        """Return the FileJobService instance."""
        return self._file_jobs

    # ==================================================================
    # Settings
    # ==================================================================
    def reload_settings(self, settings: dict) -> None:
        """Synchronize ExportController with updated global settings.

        Things controlled by settings:
            • get_documents_dir
        """
        try:
            self._documents_dir = get_documents_dir(settings)
            self._logger.debug(
                "ExportController: settings reloaded (documents_dir=%s).", fmt_path(self._get_documents_dir())
            )
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
            self._logger.exception("ExportController: failed to reload settings: %s", e)

    # ==================================================================
    # Logging helpers (corr-id & safe shape)
    # ==================================================================
    def _new_corr(self) -> str:
        """Create a correlation id for this export flow."""
        _ = self._logger
        return uuid.uuid4().hex

    def _log_start_export(
        self, *, corr_id: str, kind: ExportKind, suggested_path: str, rows: str, cols: str, scope: str | None = None
    ) -> None:
        """Unified start log for exports.

        kind   : Export kind e.g., "ExportKind.CSV", "ExportKind.EXCEL"
        scope  : optional job scope key
        """
        self._logger.info(
            "ExportController: export requested (corr=%s, kind=%s, scope=%s, rows=%s, cols=%s, suggested_path=%s)",
            corr_id,
            kind,
            scope or "-",
            rows,
            cols,
            fmt_path(suggested_path),
        )

    # ==================================================================
    # Internal helpers (DRY)
    # ==================================================================
    def _get_active_df(self) -> pd.DataFrame | None:
        """Get the current active DataFrame from the results manager.

        Returns:
            pd.DataFrame | None: The current DataFrame or None if unavailable.
        """
        return self._results.current_df()

    def _choose_export_path(self, title: str, base_dir: str, default_name: str, filter_str: str) -> tuple[str, str]:
        """Display a save file dialog to choose export path.

        Args:
            title: The dialog window title.
            base_dir: The default directory path.
            default_name: The default filename.
            filter_str: The file filter string (e.g., "CSV-filer (*.csv)").

        Returns:
            tuple[str, str]: The (chosen_path, selected_filter) or ("", "") if cancelled.
        """
        initial = str(Path(base_dir) / default_name)
        req = SaveFileRequest(title=title, initial_path=initial, filter_str=filter_str)
        return self._file_dialogs.get_save_filename(parent=self._parent, req=req)

    def _run_export_job(
        self,
        *,
        job_fn,
        job_args,
        started_msg: str,
        scope: str,
        suffix: str,
        out_path: str,
        kind: ExportKind,
        indeterminate: bool,
        cancelable: bool,
        corr_id: str,
    ) -> None:
        """Schedule an export job via AsyncOperationController.

        Args:
            job_fn: The job function to execute.
            job_args: Arguments to pass to the job function.
            started_msg: Status message to display when job starts.
            scope: Job scope identifier for logging.
            suffix: File suffix.
            out_path: Output file path.
            kind: Export kind.
            indeterminate: Whether progress is indeterminate.
            cancelable: Whether the job can be canceled.
            corr_id: Correlation ID for logging.
        """
        self._logger.debug(
            "ExportController: scheduling async export job (corr=%s, kind=%s, scope=%s, suffix=%s, indeterminate=%s)",
            corr_id,
            kind,
            scope,
            suffix,
            indeterminate,
        )

        def _work(*, progress_cb=None, cancel_cb=None, job_id=None, job_scope=None, **_):
            return job_fn(
                *job_args,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
                job_id=job_id,
                job_scope=job_scope,
            )

        self._async_ops.run_target_overlay_operation(
            target=self._operation_target,
            runner="thread",
            work=_work,
            on_result=lambda payload: self._on_export_done(payload, kind, out_path),
            on_error=lambda err: self._on_export_error(err, kind),
            busy_message=started_msg,
            scope=scope,
            operation_name=self._tr(self._EXPORT_LABELS[kind]),
            timeout_ms=0,
            indeterminate=indeterminate,
            cancelable=cancelable,
            show_status_progress=False,
            show_started_in_status=False,
            suppress_error_dialog=True,
            corr_id=corr_id,
        )

    def _df_is_empty(self, df: pd.DataFrame | None) -> bool:
        """Check if a DataFrame is empty."""
        empty = False
        if df is None or df.empty:
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_NO_DATASET_TITLE),
                text=self._tr(self.TR_NO_DATASET_TEXT),
            )
            empty = True
        return empty

    def _get_documents_dir(self) -> Path:
        """Return documents directory, guaranteed to be initialized."""
        if self._documents_dir is None:
            msg = "ExportController: documents_dir not initialized. reload_settings() must be called before export."
            raise RuntimeError(msg)
        return self._documents_dir

    # ==================================================================
    # Export CSV
    # ==================================================================
    def export_csv(self):
        """Export the current DataFrame to CSV format.

        Displays a file dialog for the user to choose the export path,
        then schedules an export job via FileJobService.
        """
        df = self._get_active_df()
        if self._df_is_empty(df):
            return

        corr = self._new_corr()

        start_dir = self._dialog_state.get_dir(
            "dialogs/export_csv_dir",
            fallback=self._get_documents_dir(),
        )

        default_name = self._file_jobs.build_export_filename(".csv", start_dir)
        suggested = str(Path(start_dir) / default_name)
        kind = ExportKind.CSV
        scope = "export:csv"

        rows, columns = fmt_shape(df)
        self._log_start_export(
            corr_id=corr,
            kind=kind,
            suggested_path=suggested,
            rows=rows,
            cols=columns,
            scope=scope,
        )

        path, selected_filter = self._choose_export_path(
            title=self._tr(self._EXPORT_LABELS[kind]),
            base_dir=str(start_dir),
            default_name=default_name,
            filter_str=self._tr(self.TR_EXPORT_CSV_DIALOG_FILTER),
        )
        if not path:
            self._logger.debug("ExportController: export canceled by user (corr=%s, kind=%s)", corr, kind)
            return

        self._logger.debug(
            "ExportController: save dialog result (corr=%s, kind=%s, selected_filter=%r, chosen=%s)",
            corr,
            kind,
            selected_filter,
            fmt_path(path),
        )

        path = self._file_jobs.coerce_save_suffix(path, selected_filter, fallback=".csv")

        self._dialog_state.set_dir(
            "dialogs/export_csv_dir",
            Path(path).parent,
        )

        self._logger.debug("ExportController: coerced path (corr=%s, kind=%s, out=%s)", corr, kind, fmt_path(path))

        def job(df_in, dest, progress_cb=None, cancel_cb=None, job_id=None, job_scope=None):
            return self._data_io.export_df_csv(
                df_in,
                dest,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
                job_id=job_id,
                job_scope=job_scope,
                corr_id=corr,
            )

        started_msg = self._tr_fmt(self.TR_EXPORT_STARTED_MSG, file_name=Path(path).name)

        self._run_export_job(
            job_fn=job,
            job_args=(df, path),
            started_msg=started_msg,
            scope=scope,
            suffix=".csv",
            out_path=path,
            kind=kind,
            indeterminate=False,
            cancelable=True,
            corr_id=corr,
        )

    # ==================================================================
    # Export Excel
    # ==================================================================
    def export_excel(self):
        """Export the current DataFrame to Excel format."""
        df = self._get_active_df()
        if self._df_is_empty(df):
            return

        corr = self._new_corr()

        start_dir = self._dialog_state.get_dir(
            "dialogs/export_excel_dir",
            fallback=self._get_documents_dir(),
        )

        default_name = self._file_jobs.build_export_filename(".xlsx", start_dir)
        suggested = str(Path(start_dir) / default_name)
        kind = ExportKind.EXCEL
        scope = "export:excel"

        rows, columns = fmt_shape(df)
        self._log_start_export(
            corr_id=corr,
            kind=kind,
            suggested_path=suggested,
            rows=rows,
            cols=columns,
            scope=scope,
        )

        path, selected_filter = self._choose_export_path(
            title=self._tr(self._EXPORT_LABELS[kind]),
            base_dir=str(start_dir),
            default_name=default_name,
            filter_str=self._tr(self.TR_EXPORT_EXCEL_DIALOG_FILTER),
        )

        if not path:
            self._logger.debug("ExportController: export canceled by user (corr=%s, kind=%s)", corr, kind)
            return

        self._logger.debug(
            "ExportController: save dialog result (corr=%s, kind=%s, selected_filter=%r, chosen=%s)",
            corr,
            kind,
            selected_filter,
            fmt_path(path),
        )

        path = self._file_jobs.coerce_save_suffix(path, selected_filter, fallback=".xlsx")

        self._dialog_state.set_dir(
            "dialogs/export_excel_dir",
            Path(path).parent,
        )

        self._logger.debug("ExportController: coerced path (corr=%s, kind=%s, out=%s)", corr, kind, fmt_path(path))

        def job(df_in, dest, progress_cb=None, cancel_cb=None, job_id=None, job_scope=None):
            return self._data_io.export_df_excel(
                df_in,
                dest,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
                job_id=job_id,
                job_scope=job_scope,
                corr_id=corr,
            )

        self._run_export_job(
            job_fn=job,
            job_args=(df, path),
            started_msg=self._tr_fmt(self.TR_EXPORT_STARTED_MSG, file_name=Path(path).name),
            scope=scope,
            suffix=".xlsx",
            out_path=path,
            kind=kind,
            indeterminate=False,
            cancelable=True,
            corr_id=corr,
        )

    # ==================================================================
    # EXPORT: Data file (pickle/feather/parquet/df)
    # ==================================================================
    def export_data(self):
        """Export the current DataFrame to a data file format."""
        df = self._get_active_df()
        if self._df_is_empty(df):
            return

        corr = self._new_corr()

        start_dir = self._dialog_state.get_dir(
            "dialogs/export_data_dir",
            fallback=self._get_documents_dir(),
        )

        default_name = self._file_jobs.build_export_filename(".df", start_dir)
        suggested = str(Path(start_dir) / default_name)
        kind = ExportKind.DATAFILE
        scope = "export:data"

        rows, columns = fmt_shape(df)
        self._log_start_export(
            corr_id=corr,
            kind=kind,
            suggested_path=suggested,
            rows=rows,
            cols=columns,
            scope=scope,
        )

        path, selected_filter = self._choose_export_path(
            title=self._tr(self._EXPORT_LABELS[kind]),
            base_dir=str(start_dir),
            default_name=default_name,
            filter_str=self._tr(self.TR_EXPORT_DATAFILE_DIALOG_FILTER),
        )
        if not path:
            self._logger.debug("ExportController: export canceled by user (corr=%s, kind=%s)", corr, kind)
            return

        self._logger.debug(
            "ExportController: save dialog result (corr=%s, kind=%s, selected_filter=%r, chosen=%s)",
            corr,
            kind,
            selected_filter,
            fmt_path(path),
        )

        path = self._file_jobs.coerce_save_suffix(path, selected_filter, fallback=".df")

        self._dialog_state.set_dir(
            "dialogs/export_data_dir",
            Path(path).parent,
        )

        suffix = Path(path).suffix.lower()
        self._logger.debug(
            "ExportController: coerced path (corr=%s, kind=%s, out=%s, suffix=%s)", corr, kind, fmt_path(path), suffix
        )

        def job(df_in, dest, progress_cb=None, cancel_cb=None, job_id=None, job_scope=None):
            return self._data_io.export_df_datafile(
                df_in,
                dest,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
                job_id=job_id,
                job_scope=job_scope,
                corr_id=corr,
            )

        self._run_export_job(
            job_fn=job,
            job_args=(df, path),
            started_msg=self._tr_fmt(self.TR_EXPORT_STARTED_MSG, file_name=Path(path).name),
            scope=f"export:{suffix.lstrip('.')}",
            suffix=suffix,
            out_path=path,
            kind=kind,
            indeterminate=True,
            cancelable=False,
            corr_id=corr,
        )

    # ==================================================================
    # PROFILING ydata (single-tab / multi-tab)
    # ==================================================================
    def profile_report(self) -> None:
        """Generate a profile report for the active dataset or compare multiple ready datasets."""
        df = self._get_active_df()
        if self._df_is_empty(df):
            return

        ready_dataset_count = self._results.ready_dataset_count()

        if ready_dataset_count <= 1:
            self._profile_single(df)
        else:
            self._profile_multi(df)

    # ------------------------------------------------------------------
    # Internal: profile single tab
    # ------------------------------------------------------------------
    def _profile_single(self, df):
        corr = self._new_corr()

        start_dir = self._dialog_state.get_dir(
            "dialogs/save_report_dir",
            fallback=self._get_documents_dir(),
        )

        default_name = self._file_jobs.build_export_filename(".html", start_dir)
        suggested = str(Path(start_dir) / default_name)

        kind = ExportKind.PROFILE
        scope = "processdata:y-data-single"

        rows, columns = fmt_shape(df)
        self._log_start_export(
            corr_id=corr,
            kind=kind,
            suggested_path=suggested,
            rows=rows,
            cols=columns,
            scope=scope,
        )

        path, selected_filter = self._choose_export_path(
            title=self._tr(self._EXPORT_LABELS[kind]),
            base_dir=str(start_dir),
            default_name=default_name,
            filter_str=self._tr(self.TR_EXPORT_PROFILE_DIALOG_FILTER),
        )

        if not path:
            self._logger.debug("ExportController: export canceled by user (corr=%s, kind=%s)", corr, kind)
            return

        self._logger.debug(
            "ExportController: save dialog result (corr=%s, kind=%s, selected_filter=%r, chosen=%s)",
            corr,
            kind,
            selected_filter,
            fmt_path(path),
        )

        path = self._file_jobs.coerce_save_suffix(path, selected_filter, fallback=".html")

        self._dialog_state.set_dir(
            "dialogs/save_report_dir",
            Path(path).parent,
        )

        suffix = Path(path).suffix.lower()

        self._logger.debug(
            "ExportController: coerced path (corr=%s, kind=%s, out=%s, suffix=%s)", corr, kind, fmt_path(path), suffix
        )

        title = self._get_tab_title() or "Dataset"

        def job(df_in, dest, title_x, progress_cb=None, cancel_cb=None, job_id=None, job_scope=None):
            return self._data_io.export_df_profile(
                df_in,
                dest,
                title_x,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
                job_id=job_id,
                job_scope=job_scope,
                corr_id=corr,
            )

        started_msg = self._tr_fmt(self.TR_EXPORT_PROFILE_STARTED_MSG, title=title)
        self._run_export_job(
            job_fn=job,
            job_args=(df, path, title),
            started_msg=started_msg,
            scope=scope,
            suffix=".html",
            out_path=path,
            kind=kind,
            indeterminate=True,
            cancelable=False,
            corr_id=corr,
        )

    # ------------------------------------------------------------------
    # Internal: profile multi-tab
    # ------------------------------------------------------------------
    def _profile_multi(self, df):
        profile_kind = self._tr(self.TR_KIND_PROFILE)
        comparison_kind = self._tr(self.TR_KIND_COMPARISON_PROFILE)
        choice = self._dialogs.confirm_profile_scope(
            parent=self._parent,
            title=self._tr(self.TR_KIND_PROFILE),
            text=self._tr(self.TR_EXPORT_DATA_MULTIPLE_TABS_DIALOG_TEXT),
            active_tab_text=self._tr_fmt(self.TR_EXPORT_DATA_MULTIPLE_ACTIVE_TAB, profile_kind=profile_kind),
            all_tabs_text=self._tr_fmt(self.TR_EXPORT_DATA_MULTIPLE_ALL_TABS, comparison_kind=comparison_kind),
        )
        if choice is ProfileChoice.CANCEL:
            return
        if choice is ProfileChoice.ACTIVE:
            self._profile_single(df)
        elif choice is ProfileChoice.ALL:
            self._profile_all_tabs()

    # ------------------------------------------------------------------
    # Internal: profile all tabs
    # ------------------------------------------------------------------
    def _profile_all_tabs(self):
        data_all = self._results.collect_all_tabs_data()
        if not data_all:
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_NO_DATASET_TITLE),
                text=self._tr(self.TR_NO_DATASET_PROFILE_TEXT),
            )
            return

        corr = self._new_corr()

        start_dir = self._dialog_state.get_dir(
            "dialogs/save_report_dir",
            fallback=self._get_documents_dir(),
        )

        default_ext = self._tr(self.TR_EXPORT_COMPARISON_PROFILE_FILE_EXT)
        default_name = self._file_jobs.build_export_filename(default_ext, start_dir)
        suggested = str(Path(start_dir) / default_name)
        kind = ExportKind.PROFILE_COMPARE
        scope = "processdata:y-data-comparison"

        self._logger.info(
            "ExportController: export requested (corr=%s, kind=%s, scope=%s, datasets=%s, suggested_path=%s)",
            corr,
            kind,
            scope or "-",
            len(data_all),
            fmt_path(suggested),
        )

        path, selected_filter = self._choose_export_path(
            title=self._tr(self._EXPORT_LABELS[kind]),
            base_dir=str(start_dir),
            default_name=default_name,
            filter_str=self._tr(self.TR_EXPORT_COMPARISON_PROFILE_DIALOG_FILTER),
        )
        if not path:
            self._logger.debug("ExportController: export canceled by user (corr=%s, kind=%s)", corr, kind)
            return

        self._logger.debug(
            "ExportController: save dialog result (corr=%s, kind=%s, selected_filter=%r, chosen=%s)",
            corr,
            kind,
            selected_filter,
            fmt_path(path),
        )

        path = self._file_jobs.coerce_save_suffix(path, selected_filter, fallback=".html")

        suffix = Path(path).suffix.lower()
        self._logger.debug(
            "ExportController: coerced path (corr=%s, kind=%s, out=%s, suffix=%s)", corr, kind, fmt_path(path), suffix
        )

        datasets_cnt = len(data_all)
        started_msg = self._tr_fmt(self.TR_EXPORT_COMPARISON_PROFILE_STARTED_MSG, datasets_cnt=str(datasets_cnt))

        data_copied: Sequence[tuple[pd.DataFrame, str]] = list(data_all)

        def job(data, dest, progress_cb=None, cancel_cb=None, job_id=None, job_scope=None):
            return self._data_io.export_dfs_profile(
                data,
                dest,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
                job_id=job_id,
                job_scope=job_scope,
                corr_id=corr,
            )

        self._run_export_job(
            job_fn=job,
            job_args=(data_copied, path),
            started_msg=started_msg,
            scope=scope,
            suffix=".html",
            out_path=path,
            kind=kind,
            indeterminate=True,
            cancelable=False,
            corr_id=corr,
        )

    # ==================================================================
    # Callbacks
    # ==================================================================

    def _on_export_done(self, payload, kind: ExportKind, out_path):
        # Build JobResult robustly
        try:
            if isinstance(payload, JobResult):
                res = payload
            elif isinstance(payload, dict):
                res = JobResult(
                    ok=bool(payload.get("ok", False)),
                    elapsed=payload.get("elapsed"),
                    path=out_path,
                    cancelled=bool(payload.get("cancelled", False)),
                    error=payload.get("error"),
                    corr_id=payload.get("corr_id"),
                )
            else:
                res = JobResult(
                    ok=False,
                    elapsed=None,
                    path=out_path,
                    cancelled=False,
                    error=self._tr(self.TR_EXCEPT_UNKNOWN_RESULT),
                )
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
            res = JobResult(
                ok=False, elapsed=None, path=out_path, cancelled=False, error=self._tr(self.TR_EXCEPT_UNKNOWN_RESULT)
            )

        corr = res.corr_id or "-"
        kind_label = self._tr(self._EXPORT_LABELS[kind])
        if res.ok:
            # Successful export
            file_name = Path(out_path).name

            self._logger.info(
                "ExportController: export done (corr=%s, kind=%s, out=%s)", corr, kind, fmt_path(out_path)
            )

            if res.elapsed:
                time_str = fmt_time(res.elapsed)
                msg_str = self._tr_fmt(
                    self.TR_DONE_STATUS_TIME_FILE, kind_label=kind_label, time_str=time_str, file_name=file_name
                )
            else:
                msg_str = self._tr_fmt(self.TR_DONE_STATUS_FILE, kind_label=kind_label, file_name=file_name)

            self._set_status(msg_str, 10000)

            if kind in (ExportKind.PROFILE, ExportKind.PROFILE_COMPARE) and not self._open_url(str(out_path)):
                self._logger.warning("ExportController: open URL failed (corr=%s, path=%s)", corr, out_path)
            return

        if res.cancelled:
            self._logger.info("ExportController: export cancelled (corr=%s, kind=%s)", corr, kind)
            self._set_status(self._tr_fmt(self.TR_DONE_STATUS_CANCEL, kind_label=kind_label), 8000)
            self._dialogs.info(parent=self._parent, title=kind_label, text=self._tr(self.TR_DONE_CANCEL_DIALOG_TEXT))
            return

        # Failed export
        fail_status = self._tr_fmt(self.TR_DONE_STATUS_FAIL, kind_label=kind_label)
        self._logger.error(
            "ExportController: export failed (corr=%s, kind=%s): %s",
            corr,
            kind,
            res.error or self._tr(self.TR_EXCEPT_UNKNOWN_ERROR),
        )
        self._set_status(fail_status, 8000)
        self._dialogs.warn(parent=self._parent, title=kind_label, text=res.error or fail_status)

    def _on_export_error(self, err: str, kind: ExportKind):
        corr = "-"
        kind_label = self._tr(self._EXPORT_LABELS[kind])
        if isinstance(err, JobResult):
            corr = getattr(err, "corr_id", "-")
            msg = err.error or self._tr(self.TR_EXCEPT_UNKNOWN_ERROR)
        else:
            msg = str(err)

        self._logger.error("ExportController: export failed (corr=%s, kind=%s): %s", corr, kind, msg)
        self._set_status(self._tr_fmt(self.TR_DONE_STATUS_FAIL, kind_label=kind_label), 8000)

        self._dialogs.critical(parent=self._parent, title=kind_label, text=msg)
