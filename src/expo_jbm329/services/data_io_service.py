"""Data I/O service providing a facade for loading and exporting data.

This module contains the DataIOService class which handles high-level data operations
using FileLoader and FileWriter.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from expo_jbm329.services.data_processing import (
    generate_comparison_profile_report,
    generate_profile_report,
)
from expo_jbm329.services.file_loader import FileLoader, OperationCancelledError
from expo_jbm329.services.file_writer import ExportCancelledError, FileWriter
from expo_jbm329.services.job_result import JobResult
from expo_jbm329.utils.format_utils import fmt_path, fmt_shape

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pandas as pd


class DataIOService:
    """Enterprise DI facade for data I/O (always returns JobResult).

    Responsibilities:
      • Resolve & load DataFrames using FileLoader
      • Export DataFrames to CSV/Excel/datafile using FileWriter
      • Generate ydata-profiling reports (single/compare) and write to HTML

    Notes:
      - Logs & docstrings are English. UI strings live in controllers.
      - Progress emits integers in [0..100].
      - Cancellation returns JobResult(cancelled=True, ok=False, elapsed=None).
      - Load returns JobResult with `data` (the DataFrame payload).
    """

    def __init__(
            self,
            loader: FileLoader,
            writer: FileWriter,
            logger: logging.Logger | None = None
    ):
        """Initialize the DataIOService.

        Args:
            loader: The FileLoader to use for loading data.
            writer: The FileWriter to use for exporting data.
            logger: An optional logger. Defaults to 'applogger.service'.
        """
        self._loader = loader
        self._writer = writer
        self._logger = logger or logging.getLogger("applogger.service")

    # ==================================================================
    # Settings (propagate to loader/writer)
    # ==================================================================
    def reload_settings(self, settings: dict) -> None:
        """Propagate new settings into FileLoader and FileWriter.

        Args:
            settings: A dictionary of new settings.
        """
        try:
            if self._loader:
                self._loader.reload_settings(settings)
            if self._writer:
                self._writer.reload_settings(settings)
            self._logger.debug("DataIOService: settings reloaded into loader & writer.")
        except Exception:
            self._logger.exception("DataIOService: failed to reload settings")

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def resolve_and_load_df(
        self,
        path_or_name: str,
        *,
        progress_cb: Callable[[int], None] | None = None,
        cancel_cb: Callable[[], bool] | None = None,
        job_id: str | None = None,
        job_scope: str | None = None,
        corr_id: str | None = None,
    ) -> JobResult:
        """Resolve and load a DataFrame from a path or name.

        Args:
            path_or_name: The path or logical name of the file to load.
            progress_cb: Optional callback for progress updates.
            cancel_cb: Optional callback returning True if cancellation was requested.
            job_id: Optional job identifier for tracing.
            job_scope: Optional job scope for tracing.
            corr_id: Optional correlation identifier.

        Returns:
            A JobResult describing success, cancellation, or failure.
        """
        _ = job_id
        _ = job_scope

        resolved_path_str: str | None = None
        t0 = time.perf_counter()

        try:
            path = self._loader.resolve(path_or_name)
            if path is None:
                dt = time.perf_counter() - t0
                return JobResult(
                    ok=False,
                    elapsed=dt,
                    path=None,
                    cancelled=False,
                    error="File not found",
                    data=None,
                    corr_id=corr_id,
                )

            resolved_path_str = str(path)

            if cancel_cb is not None and cancel_cb():
                dt = time.perf_counter() - t0
                return JobResult(
                    ok=False,
                    elapsed=dt,
                    path=resolved_path_str,
                    cancelled=True,
                    error=None,
                    data=None,
                    corr_id=corr_id,
                )

            df = self._loader.load_df_auto(
                resolved_path_str,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
                corr_id=corr_id,
            )
            dt = time.perf_counter() - t0

            if cancel_cb is not None and cancel_cb():
                return JobResult(
                    ok=False,
                    elapsed=dt,
                    path=resolved_path_str,
                    cancelled=True,
                    error=None,
                    data=None,
                    corr_id=corr_id,
                )

            return JobResult(
                ok=True,
                elapsed=dt,
                path=resolved_path_str,
                cancelled=False,
                error=None,
                data=df,
                corr_id=corr_id,
            )

        except OperationCancelledError:
            dt = time.perf_counter() - t0
            return JobResult(
                ok=False,
                elapsed=dt,
                path=resolved_path_str,
                cancelled=True,
                error=None,
                data=None,
                corr_id=corr_id,
            )

        except Exception as e:
            dt = time.perf_counter() - t0
            return JobResult(
                ok=False,
                elapsed=dt,
                path=resolved_path_str,
                cancelled=False,
                error=str(e),
                data=None,
                corr_id=corr_id,
            )

    # ------------------------------------------------------------------
    # Export: CSV
    # ------------------------------------------------------------------
    def export_df_csv(
            self,
            df: pd.DataFrame,
            dest: str | Path,
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            job_id: str | None = None,
            job_scope: str | None = None,
            corr_id: str | None = None,
    ) -> JobResult:
        """Exports a DataFrame to CSV and returns JobResult.

        Args:
            df: The DataFrame to export.
            dest: Destination path.
            progress_cb: Optional callback for progress updates.
            cancel_cb: Optional callback to check for cancellation.
            job_id: Optional job identifier.
            job_scope: Optional job scope.
            corr_id: Optional correlation identifier.

        Returns:
            A JobResult containing the export status.
        """
        dest_str = str(dest)
        rows, columns = fmt_shape(df)

        self._logger.debug(
            "DataIOService: export CSV start (corr=%s, path=%s, rows=%s, cols=%s, job_id=%s, scope=%s)",
            corr_id, fmt_path(dest_str), rows, columns, job_id, job_scope
        )

        if cancel_cb and cancel_cb():
            self._logger.debug(
                "DataIOService: export CSV cancelled early (corr=%s, path=%s)", corr_id, fmt_path(dest_str))
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=True, error=None, corr_id=corr_id)

        t0 = time.perf_counter()
        try:
            self._writer.save_csv(
                df, dest_str,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
                corr_id=corr_id
            )
            dt = time.perf_counter() - t0
            self._logger.info(
                "DataIOService: CSV written (corr=%s, path=%s, ms=%.1f, rows=%s, cols=%s)",
                corr_id, fmt_path(dest_str), dt * 1000, rows, columns
            )
            return JobResult(ok=True, elapsed=dt, path=dest_str, corr_id=corr_id)

        except ExportCancelledError as ce:
            dt = time.perf_counter() - t0
            self._logger.info(
                "DataIOService: export CSV cancelled (corr=%s, path=%s, ms=%.1f, rows_written=%s of %s)",
                corr_id, fmt_path(dest_str), dt * 1000, getattr(ce, "rows_written", None), rows
            )
            return JobResult(
                ok=False, elapsed=dt, path=dest_str, cancelled=True, error=None, corr_id=corr_id
            )

        except Exception as e:
            self._logger.exception(
                "DataIOService: export CSV failed (corr=%s, path=%s): %s", corr_id, fmt_path(dest_str), e)
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=False, error=str(e), corr_id=corr_id)

    # ------------------------------------------------------------------
    # Export: Excel
    # ------------------------------------------------------------------
    def export_df_excel(
            self,
            df: pd.DataFrame,
            dest: str | Path,
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            job_id: str | None = None,
            job_scope: str | None = None,
            corr_id: str | None = None,
    ) -> JobResult:
        """Exports a DataFrame to Excel and returns JobResult.

        Args:
            df: The DataFrame to export.
            dest: Destination path.
            progress_cb: Optional callback for progress updates.
            cancel_cb: Optional callback to check for cancellation.
            job_id: Optional job identifier.
            job_scope: Optional job scope.
            corr_id: Optional correlation identifier.

        Returns:
            A JobResult containing the export status.

        Semantics:
            - Success → ok=True, cancelled=False, elapsed populated, path set.
            - Cancellation (raised by FileWriter) → ok=False, cancelled=True, elapsed populated.
            - Failure (unexpected exception) → ok=False, cancelled=False, error populated.

        Notes:
            - When using pandas fallback in FileWriter, cancellation is honored only before write.
            - When using streaming (openpyxl write_only), mid-write cancellation is supported.
        """
        dest_str = str(dest)
        rows, columns = fmt_shape(df)

        self._logger.debug(
            "DataIOService: export excel start (corr=%s, path=%s, rows=%s, cols=%s, job_id=%s, scope=%s)",
            corr_id, fmt_path(dest_str), rows, columns, job_id, job_scope
        )

        # Early cancellation before any I/O
        if cancel_cb and cancel_cb():
            self._logger.debug(
                "DataIOService: export excel cancelled early (corr=%s, path=%s)", corr_id, fmt_path(dest_str))
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=True, error=None, corr_id=corr_id)

        t0 = time.perf_counter()
        try:
            # Delegate to FileWriter; it will raise ExportCancelledError on user cancellation.
            self._writer.save_excel(
                df,
                dest_str,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
                corr_id=corr_id,
                na_rep="",  # keep explicit empty string for NA in Excel
            )

            dt = time.perf_counter() - t0
            self._logger.info(
                "DataIOService: excel written (corr=%s, path=%s, ms=%.1f, rows=%s, cols=%s)",
                corr_id, fmt_path(dest_str), dt * 1000, rows, columns
            )
            return JobResult(ok=True, elapsed=dt, path=dest_str, corr_id=corr_id)

        except ExportCancelledError as ce:
            # Cancellation path: provide informative logging including partial counters if available.
            dt = time.perf_counter() - t0
            rows_written = getattr(ce, "rows_written", None)
            sheets_written = getattr(ce, "sheets_written", None)

            if rows_written is not None and sheets_written is not None:
                self._logger.info(
                    "DataIOService: export excel cancelled "
                    "(corr=%s, path=%s, ms=%.1f, rows_written=%s of %s, sheets_written=%s)",
                    corr_id, fmt_path(dest_str), dt * 1000, rows_written, rows, sheets_written
                )
            elif rows_written is not None:
                self._logger.info(
                    "DataIOService: export excel cancelled (corr=%s, path=%s, ms=%.1f, rows_written=%s of %s)",
                    corr_id, fmt_path(dest_str), dt * 1000, rows_written, rows
                )
            else:
                self._logger.info(
                    "DataIOService: export excel cancelled (corr=%s, path=%s, ms=%.1f)",
                    corr_id, fmt_path(dest_str), dt * 1000
                )

            return JobResult(
                ok=False,
                elapsed=dt,
                path=dest_str,
                cancelled=True,
                error=None,
                corr_id=corr_id,
            )

        except Exception as e:
            # Unexpected failure path
            self._logger.exception(
                "DataIOService: export excel failed (corr=%s, path=%s): %s",
                corr_id, fmt_path(dest_str), e
            )
            return JobResult(
                ok=False,
                elapsed=None,
                path=dest_str,
                cancelled=False,
                error=str(e),
                corr_id=corr_id,
            )

    # ------------------------------------------------------------------
    # Export: Datafile (suffix-routed)
    # ------------------------------------------------------------------
    def export_df_datafile(
            self,
            df: pd.DataFrame,
            dest: str | Path,
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            job_id: str | None = None,
            job_scope: str | None = None,
            corr_id: str | None = None,
    ) -> JobResult:
        """Exports a DataFrame to a data file based on suffix and returns JobResult.

        Args:
            df: The DataFrame to export.
            dest: Destination path.
            progress_cb: Optional callback for progress updates.
            cancel_cb: Optional callback to check for cancellation.
            job_id: Optional job identifier.
            job_scope: Optional job scope.
            corr_id: Optional correlation identifier.

        Returns:
            A JobResult containing the export status.
        """
        dest_str = str(dest)
        rows, columns = fmt_shape(df)

        self._logger.debug(
            "DataIOService: export data file start (corr=%s, path=%s, rows=%s, cols=%s, job_id=%s, scope=%s)",
            corr_id, fmt_path(dest_str), rows, columns, job_id, job_scope
        )

        if progress_cb:
            progress_cb(0)
        if cancel_cb and cancel_cb():
            self._logger.debug(
                "DataIOService: export data file cancelled early (corr=%s, path=%s)", corr_id, fmt_path(dest_str))
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=True, error=None, corr_id=corr_id)

        t0 = time.perf_counter()
        try:
            self._writer.save_datafile(df, dest_str, corr_id=corr_id)
            dt = time.perf_counter() - t0
            if progress_cb:
                progress_cb(100)
            self._logger.info(
                "DataIOService: data file written (corr=%s, path=%s, ms=%.1f, rows=%s, cols=%s)",
                corr_id, fmt_path(dest_str), dt * 1000, rows, columns)
            return JobResult(ok=True, elapsed=dt, path=dest_str, corr_id=corr_id)
        except Exception as e:
            if progress_cb:
                progress_cb(100)
            self._logger.exception(
                "DataIOService: export data file failed (corr=%s, path=%s): %s",
                corr_id,
                fmt_path(dest_str),
                e,
                )
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=False, error=str(e), corr_id=corr_id)

    # ------------------------------------------------------------------
    # Export: Profiling (single)
    # ------------------------------------------------------------------
    def export_df_profile(
            self,
            df: pd.DataFrame,
            dest: str | Path,
            title: str,
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            job_id: str | None = None,
            job_scope: str | None = None,
            corr_id: str | None = None,
    ) -> JobResult:
        """Generates a ydata-profiling report for one DataFrame and returns JobResult.

        Args:
            df: The DataFrame to profile.
            dest: Destination path for the HTML report.
            title: Title for the report.
            progress_cb: Optional callback for progress updates.
            cancel_cb: Optional callback to check for cancellation.
            job_id: Optional job identifier.
            job_scope: Optional job scope.
            corr_id: Optional correlation identifier.

        Returns:
            A JobResult containing the export status.
        """
        _ = progress_cb
        dest_str = str(dest)
        rows, columns = fmt_shape(df)

        self._logger.debug(
            "DataIOService: export profile report (corr=%s, path=%s, title=%r, rows=%s, cols=%s, job_id=%s, scope=%s)",
            corr_id, fmt_path(dest_str), title, rows, columns, job_id, job_scope
        )

        if cancel_cb and cancel_cb():
            self._logger.debug(
                "DataIOService: export profile report cancelled early (corr=%s, path=%s)", corr_id, fmt_path(dest_str))
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=True, error=None, corr_id=corr_id)

        t0 = time.perf_counter()
        try:
            report = generate_profile_report(df, title, corr_id=corr_id if corr_id is not None else "-")

            self._writer.save_profile(report, dest_str, corr_id=corr_id)
            dt = time.perf_counter() - t0

            self._logger.info(
                "DataIOService: profile report written (corr=%s, path=%s, ms=%.1f, title=%r)",
                corr_id,
                fmt_path(dest_str),
                dt * 1000,
                title
            )
            return JobResult(ok=True, elapsed=dt, path=dest_str, corr_id=corr_id)
        except Exception as e:

            self._logger.exception(
                "DataIOService: export profile report failed (corr=%s, path=%s): %s",
                corr_id, fmt_path(dest_str), e)
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=False, error=str(e), corr_id=corr_id)

    # ------------------------------------------------------------------
    # Export: Profiling (comparison)
    # ------------------------------------------------------------------
    def export_dfs_profile(
            self,
            data: list[tuple[pd.DataFrame, str]],
            dest: str | Path,
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            job_id: str | None = None,
            job_scope: str | None = None,
            corr_id: str | None = None,
    ) -> JobResult:
        """Generates a ydata-comparison profile for multiple datasets and returns JobResult.

        Args:
            data: List of (DataFrame, name) tuples to compare.
            dest: Destination path for the HTML report.
            progress_cb: Optional callback for progress updates.
            cancel_cb: Optional callback to check for cancellation.
            job_id: Optional job identifier.
            job_scope: Optional job scope.
            corr_id: Optional correlation identifier.

        Returns:
            A JobResult containing the export status.
        """
        _ = progress_cb
        dest_str = str(dest)

        # Summarize inputs minimally (antal dataset + första titlar)
        try:
            number_of_datasets = len(data) if data else 0
            titles_preview = ", ".join([nm for _, nm in (data[:3] if data else [])])
        except Exception:
            number_of_datasets, titles_preview = 0, ""

        self._logger.debug(
            "DataIOService: export comparison profile start "
            "(corr=%s, path=%s, datasets=%s, preview=%r, job_id=%s, scope=%s)",
            corr_id, dest_str, number_of_datasets, titles_preview, job_id, job_scope
        )

        if cancel_cb and cancel_cb():
            self._logger.debug(
                "DataIOService: export comparison profile cancelled early (corr=%s, path=%s)",
                corr_id,
                fmt_path(dest_str)
            )
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=True, error=None, corr_id=corr_id)

        t0 = time.perf_counter()
        try:
            report = generate_comparison_profile_report(data, corr_id=corr_id)

            if cancel_cb and cancel_cb():
                self._logger.debug(
                    "DataIOService: export comparison profile cancelled mid-run (corr=%s, path=%s)",
                    corr_id,
                    fmt_path(dest_str)
                )
                return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=True, error=None, corr_id=corr_id)
            self._writer.save_profile(report, dest_str, corr_id=corr_id)
            dt = time.perf_counter() - t0

            self._logger.info(
                "DataIOService: comparison profile written (corr=%s, path=%s, ms=%.1f, datasets=%s)",
                corr_id,
                fmt_path(dest_str),
                dt * 1000,
                number_of_datasets
            )
            return JobResult(ok=True, elapsed=dt, path=dest_str, corr_id=corr_id)
        except Exception as e:

            self._logger.exception(
                "DataIOService: export comparison profile failed (corr=%s, path=%s): %s",
                corr_id,
                fmt_path(dest_str),
                e,
            )
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=False, error=str(e), corr_id=corr_id)

