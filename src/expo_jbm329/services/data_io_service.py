"""Data I/O service providing a facade for loading and exporting data.

This module contains the DataIOService class which handles high-level data operations
using FileLoader and FileWriter.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, cast

import pandas as pd

from expo_jbm329.services.data_processing import (
    generate_comparison_profile_report,
    generate_profile_report,
)
from expo_jbm329.services.excel_chart import ExcelChartCancelledError, ExcelChartImage
from expo_jbm329.services.file_loader import FileLoader, OperationCancelledError
from expo_jbm329.services.file_writer import ExportCancelledError, FileWriter
from expo_jbm329.services.job_result import JobResult
from expo_jbm329.utils.format_utils import fmt_path, fmt_shape

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

_EXCEL_CHART_PREPARATION_SHARE = 24
_EXCEL_TABLE_PROGRESS_START = 25
_EXCEL_PROGRESS_COMPLETE = 100


class DataIOService:
    """Enterprise DI facade for data I/O (always returns JobResult).

    Responsibilities:
      • Resolve & load DataFrames using FileLoader
      • Export DataFrames to CSV/Excel/datafile using FileWriter
      • Generate fg-data-profiling reports (single/compare) and write to HTML

    Notes:
      - Logs & docstrings are English. UI strings live in controllers.
      - Progress emits integers in [0..100].
      - Cancellation returns JobResult(cancelled=True, ok=False, elapsed=None).
      - Load returns JobResult with `data` (the DataFrame payload).
    """

    def __init__(self, loader: FileLoader, writer: FileWriter, logger: logging.Logger | None = None) -> None:
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
    def reload_settings(self, settings: dict[str, object]) -> None:
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
    # Export CSV
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
            corr_id,
            fmt_path(dest_str),
            rows,
            columns,
            job_id,
            job_scope,
        )

        if cancel_cb and cancel_cb():
            self._logger.debug(
                "DataIOService: export CSV cancelled early (corr=%s, path=%s)", corr_id, fmt_path(dest_str)
            )
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=True, error=None, corr_id=corr_id)

        t0 = time.perf_counter()
        try:
            self._writer.save_csv(df, dest_str, progress_cb=progress_cb, cancel_cb=cancel_cb, corr_id=corr_id)
            dt = time.perf_counter() - t0
            self._logger.info(
                "DataIOService: CSV written (corr=%s, path=%s, ms=%.1f, rows=%s, cols=%s)",
                corr_id,
                fmt_path(dest_str),
                dt * 1000,
                rows,
                columns,
            )
            return JobResult(ok=True, elapsed=dt, path=dest_str, corr_id=corr_id)

        except ExportCancelledError as ce:
            dt = time.perf_counter() - t0
            self._logger.info(
                "DataIOService: export CSV cancelled (corr=%s, path=%s, ms=%.1f, rows_written=%s of %s)",
                corr_id,
                fmt_path(dest_str),
                dt * 1000,
                getattr(ce, "rows_written", None),
                rows,
            )
            return JobResult(ok=False, elapsed=dt, path=dest_str, cancelled=True, error=None, corr_id=corr_id)

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
            self._logger.exception("DataIOService: export CSV failed (corr=%s, path=%s)", corr_id, fmt_path(dest_str))
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=False, error=str(e), corr_id=corr_id)

    # ------------------------------------------------------------------
    # Export Excel
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
        """Export a single DataFrame with the existing Excel job semantics.

        Args:
            df: DataFrame to export.
            dest: Destination workbook.
            progress_cb: Optional progress notification.
            cancel_cb: Optional cancellation check.
            job_id: Optional job identifier for logging.
            job_scope: Optional job scope for logging.
            corr_id: Optional correlation identifier.

        Returns:
            Export status, elapsed time, path, and correlation identifier.
        """
        return self._export_excel(
            df,
            dest,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
            job_id=job_id,
            job_scope=job_scope,
            corr_id=corr_id,
        )

    def validate_excel_sheets(
        self,
        sheets: Mapping[str, pd.DataFrame],
        *,
        chart_sheet_name: str | None = None,
        allow_empty: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Capture and validate ordered sheets against the current writer settings.

        Frames remain caller-owned and must be stable through export completion.

        Args:
            sheets: Exact sheet names and caller-owned frames in workbook order.
            chart_sheet_name: Optional reserved worksheet for chart content.
            allow_empty: Permit an empty table mapping when charts will populate
                the workbook.

        Returns:
            A new mapping containing the original frame references.

        Raises:
            ValueError: Invalid names, collisions, frame shape, or settings.
            TypeError: Invalid mapping or frame types.
        """
        return self._writer.validate_excel_sheets(
            sheets,
            chart_sheet_name=chart_sheet_name,
            allow_empty=allow_empty,
        )

    def export_dfs_excel(
        self,
        sheets: Mapping[str, pd.DataFrame],
        dest: str | Path,
        *,
        chart_factory: Callable[
            [Callable[[int], None] | None, Callable[[], bool] | None],
            Sequence[ExcelChartImage],
        ]
        | None = None,
        chart_sheet_name: str | None = None,
        progress_cb: Callable[[int], None] | None = None,
        cancel_cb: Callable[[], bool] | None = None,
        job_id: str | None = None,
        job_scope: str | None = None,
        corr_id: str | None = None,
    ) -> JobResult:
        """Export an ordered named workbook atomically using the Excel job flow.

        Caller-owned frames must remain stable until this operation completes.
        Invalid requests return failed results; cancellation preserves the destination.

        Args:
            sheets: Exact sheet names and caller-owned frames in workbook order.
            dest: Destination workbook, replaced only after a successful write.
            chart_factory: Optional worker-safe producer for embedded chart images.
            chart_sheet_name: Exact worksheet name reserved for the chart images.
            progress_cb: Optional monotonic whole-workbook progress notification.
            cancel_cb: Optional cancellation check, including before replacement.
            job_id: Optional job identifier for logging.
            job_scope: Optional job scope for logging.
            corr_id: Optional correlation identifier.

        Returns:
            Export status, elapsed time, path, and correlation identifier.
        """
        return self._export_excel(
            sheets,
            dest,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
            job_id=job_id,
            job_scope=job_scope,
            corr_id=corr_id,
            named=True,
            chart_factory=chart_factory,
            chart_sheet_name=chart_sheet_name,
        )

    def _export_excel(
        self,
        df: pd.DataFrame | Mapping[str, pd.DataFrame],
        dest: str | Path,
        *,
        progress_cb: Callable[[int], None] | None = None,
        cancel_cb: Callable[[], bool] | None = None,
        job_id: str | None = None,
        job_scope: str | None = None,
        corr_id: str | None = None,
        named: bool = False,
        chart_factory: Callable[
            [Callable[[int], None] | None, Callable[[], bool] | None],
            Sequence[ExcelChartImage],
        ]
        | None = None,
        chart_sheet_name: str | None = None,
    ) -> JobResult:
        """Run the shared single-frame and named-workbook Excel job handling.

        Args:
            df: The DataFrame or ordered named frames to export.
            dest: Destination path.
            progress_cb: Optional callback for progress updates.
            cancel_cb: Optional callback to check for cancellation.
            job_id: Optional job identifier.
            job_scope: Optional job scope.
            corr_id: Optional correlation identifier.
            named: Require named-workbook validation and atomic output.
            chart_factory: Optional background chart producer for named workbooks.
            chart_sheet_name: Worksheet name reserved for generated chart images.

        Returns:
            A JobResult containing the export status.

        Semantics:
            - Success → ok=True, cancelled=False, elapsed populated, path set.
            - Cancellation (raised by FileWriter) → ok=False, cancelled=True, elapsed populated.
            - Failure (unexpected exception) → ok=False, cancelled=False, error populated.

        Notes:
            - Legacy pandas exports honor cancellation only before writing.
            - Named pandas exports also check between sheets and before replacement.
            - When using streaming (openpyxl write_only), mid-write cancellation is supported.
        """
        dest_str = str(dest)
        rows, columns = fmt_shape(df) if not named and isinstance(df, pd.DataFrame) else ("?", "mixed")

        if (chart_factory is None) != (chart_sheet_name is None):
            message = "A chart producer and worksheet name must be supplied together."
            self._logger.error("DataIOService: %s (corr=%s, path=%s)", message, corr_id, fmt_path(dest_str))
            return JobResult(ok=False, elapsed=None, path=dest_str, error=message, corr_id=corr_id)
        if chart_factory is not None and not named:
            message = "Charts are supported only in named Excel workbooks."
            self._logger.error("DataIOService: %s (corr=%s, path=%s)", message, corr_id, fmt_path(dest_str))
            return JobResult(ok=False, elapsed=None, path=dest_str, error=message, corr_id=corr_id)

        self._logger.debug(
            "DataIOService: export excel start (corr=%s, path=%s, rows=%s, cols=%s, job_id=%s, scope=%s)",
            corr_id,
            fmt_path(dest_str),
            rows,
            columns,
            job_id,
            job_scope,
        )

        # Early cancellation before any I/O
        if cancel_cb and cancel_cb():
            self._logger.debug(
                "DataIOService: export excel cancelled early (corr=%s, path=%s)", corr_id, fmt_path(dest_str)
            )
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=True, error=None, corr_id=corr_id)

        t0 = time.perf_counter()
        try:
            # Delegate to FileWriter; it will raise ExportCancelledError on user cancellation.
            if not named and isinstance(df, pd.DataFrame):
                self._writer.save_excel(
                    df,
                    dest_str,
                    progress_cb=progress_cb,
                    cancel_cb=cancel_cb,
                    corr_id=corr_id,
                    na_rep="",
                )
            else:
                df = self.validate_excel_sheets(
                    cast("Mapping[str, pd.DataFrame]", df),
                    chart_sheet_name=chart_sheet_name,
                    allow_empty=chart_factory is not None,
                )
                rows = str(sum(len(frame) for frame in df.values()))
                self._logger.debug(
                    "DataIOService: named Excel workbook (corr=%s, rows=%s, sheets=%s)",
                    corr_id,
                    rows,
                    len(df),
                )
                charts: Sequence[ExcelChartImage] = ()
                writer_progress = progress_cb
                if chart_factory is not None:
                    last_progress = -1

                    def report_progress(value: int) -> None:
                        nonlocal last_progress
                        if progress_cb is not None and value > last_progress:
                            last_progress = value
                            progress_cb(value)

                    def chart_progress(value: int) -> None:
                        report_progress(
                            min(
                                _EXCEL_CHART_PREPARATION_SHARE,
                                int(value * _EXCEL_CHART_PREPARATION_SHARE / _EXCEL_PROGRESS_COMPLETE),
                            )
                        )

                    report_progress(0)
                    charts = chart_factory(chart_progress if progress_cb is not None else None, cancel_cb)
                    if not charts:
                        message = "The chart producer did not return any chart images."
                        self._logger.error("DataIOService: %s (corr=%s)", message, corr_id)
                        return JobResult(
                            ok=False,
                            elapsed=time.perf_counter() - t0,
                            path=dest_str,
                            error=message,
                            corr_id=corr_id,
                        )
                    if cancel_cb is not None and cancel_cb():
                        self._logger.info(
                            "DataIOService: Excel export cancelled after chart preparation (corr=%s, path=%s)",
                            corr_id,
                            fmt_path(dest_str),
                        )
                        return JobResult(
                            ok=False,
                            elapsed=time.perf_counter() - t0,
                            path=dest_str,
                            cancelled=True,
                            error=None,
                            corr_id=corr_id,
                        )

                    def mapped_writer_progress(value: int) -> None:
                        report_progress(
                            _EXCEL_PROGRESS_COMPLETE
                            if value >= _EXCEL_PROGRESS_COMPLETE
                            else _EXCEL_TABLE_PROGRESS_START + int(value * 74 / _EXCEL_PROGRESS_COMPLETE)
                        )

                    writer_progress = mapped_writer_progress

                if charts and chart_sheet_name is not None:
                    self._writer.save_excel_sheets(
                        df,
                        dest_str,
                        chart_images=charts,
                        chart_sheet_name=chart_sheet_name,
                        progress_cb=writer_progress,
                        cancel_cb=cancel_cb,
                        corr_id=corr_id,
                        na_rep="",
                    )
                else:
                    self._writer.save_excel_sheets(
                        df,
                        dest_str,
                        progress_cb=writer_progress,
                        cancel_cb=cancel_cb,
                        corr_id=corr_id,
                        na_rep="",
                    )

            dt = time.perf_counter() - t0
            self._logger.info(
                "DataIOService: excel written (corr=%s, path=%s, ms=%.1f, rows=%s, cols=%s)",
                corr_id,
                fmt_path(dest_str),
                dt * 1000,
                rows,
                columns,
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
                    corr_id,
                    fmt_path(dest_str),
                    dt * 1000,
                    rows_written,
                    rows,
                    sheets_written,
                )
            elif rows_written is not None:
                self._logger.info(
                    "DataIOService: export excel cancelled (corr=%s, path=%s, ms=%.1f, rows_written=%s of %s)",
                    corr_id,
                    fmt_path(dest_str),
                    dt * 1000,
                    rows_written,
                    rows,
                )
            else:
                self._logger.info(
                    "DataIOService: export excel cancelled (corr=%s, path=%s, ms=%.1f)",
                    corr_id,
                    fmt_path(dest_str),
                    dt * 1000,
                )

            return JobResult(
                ok=False,
                elapsed=dt,
                path=dest_str,
                cancelled=True,
                error=None,
                corr_id=corr_id,
            )

        except ExcelChartCancelledError:
            dt = time.perf_counter() - t0
            self._logger.info("DataIOService: Excel chart preparation cancelled (corr=%s)", corr_id)
            return JobResult(
                ok=False,
                elapsed=dt,
                path=dest_str,
                cancelled=True,
                error=None,
                corr_id=corr_id,
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
            # Unexpected failure path
            self._logger.exception("DataIOService: export excel failed (corr=%s, path=%s)", corr_id, fmt_path(dest_str))
            return JobResult(
                ok=False,
                elapsed=None,
                path=dest_str,
                cancelled=False,
                error=str(e),
                corr_id=corr_id,
            )

    # ------------------------------------------------------------------
    # Export Datafile suffix-routed
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
            corr_id,
            fmt_path(dest_str),
            rows,
            columns,
            job_id,
            job_scope,
        )

        if progress_cb:
            progress_cb(0)
        if cancel_cb and cancel_cb():
            self._logger.debug(
                "DataIOService: export data file cancelled early (corr=%s, path=%s)", corr_id, fmt_path(dest_str)
            )
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=True, error=None, corr_id=corr_id)

        t0 = time.perf_counter()
        try:
            self._writer.save_datafile(df, dest_str, corr_id=corr_id)
            dt = time.perf_counter() - t0
            if progress_cb:
                progress_cb(100)
            self._logger.info(
                "DataIOService: data file written (corr=%s, path=%s, ms=%.1f, rows=%s, cols=%s)",
                corr_id,
                fmt_path(dest_str),
                dt * 1000,
                rows,
                columns,
            )
            return JobResult(ok=True, elapsed=dt, path=dest_str, corr_id=corr_id)
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
            if progress_cb:
                progress_cb(100)
            self._logger.exception(
                "DataIOService: export data file failed (corr=%s, path=%s)",
                corr_id,
                fmt_path(dest_str),
            )
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=False, error=str(e), corr_id=corr_id)

    # ------------------------------------------------------------------
    # Export Profiling single
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
        """Generates a fg-data-profiling report for one DataFrame and returns JobResult.

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
            corr_id,
            fmt_path(dest_str),
            title,
            rows,
            columns,
            job_id,
            job_scope,
        )

        if cancel_cb and cancel_cb():
            self._logger.debug(
                "DataIOService: export profile report cancelled early (corr=%s, path=%s)", corr_id, fmt_path(dest_str)
            )
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
                title,
            )
            return JobResult(ok=True, elapsed=dt, path=dest_str, corr_id=corr_id)
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
            self._logger.exception(
                "DataIOService: export profile report failed (corr=%s, path=%s)", corr_id, fmt_path(dest_str)
            )
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=False, error=str(e), corr_id=corr_id)

    # ------------------------------------------------------------------
    # Export Profiling comparison
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
            number_of_datasets, titles_preview = 0, ""

        self._logger.debug(
            "DataIOService: export comparison profile start "
            "(corr=%s, path=%s, datasets=%s, preview=%r, job_id=%s, scope=%s)",
            corr_id,
            dest_str,
            number_of_datasets,
            titles_preview,
            job_id,
            job_scope,
        )

        if cancel_cb and cancel_cb():
            self._logger.debug(
                "DataIOService: export comparison profile cancelled early (corr=%s, path=%s)",
                corr_id,
                fmt_path(dest_str),
            )
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=True, error=None, corr_id=corr_id)

        t0 = time.perf_counter()
        try:
            report = generate_comparison_profile_report(data, corr_id=corr_id)

            if cancel_cb and cancel_cb():
                self._logger.debug(
                    "DataIOService: export comparison profile cancelled mid-run (corr=%s, path=%s)",
                    corr_id,
                    fmt_path(dest_str),
                )
                return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=True, error=None, corr_id=corr_id)
            self._writer.save_profile(report, dest_str, corr_id=corr_id)
            dt = time.perf_counter() - t0

            self._logger.info(
                "DataIOService: comparison profile written (corr=%s, path=%s, ms=%.1f, datasets=%s)",
                corr_id,
                fmt_path(dest_str),
                dt * 1000,
                number_of_datasets,
            )
            return JobResult(ok=True, elapsed=dt, path=dest_str, corr_id=corr_id)
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
            self._logger.exception(
                "DataIOService: export comparison profile failed (corr=%s, path=%s)",
                corr_id,
                fmt_path(dest_str),
            )
            return JobResult(ok=False, elapsed=None, path=dest_str, cancelled=False, error=str(e), corr_id=corr_id)
