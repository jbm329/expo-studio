"""Service for writing DataFrames and other data to disk.

This module provides the FileWriter class, which supports exporting data to CSV,
Excel, Parquet, Feather, Pickle, and JSON formats.
"""
from __future__ import annotations

import json
import logging
import pickle
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import pandas as pd

from expo_jbm329.utils.format_utils import fmt_path, fmt_shape


class ExportCancelledError(Exception):
    """Raised when a user-initiated cancellation occurs during export.

    Attributes:
        path: Destination path (a partial file may exist).
        rows_written: Number of data rows successfully written so far (if known).
        sheets_written: Number of completed/active sheets written (Excel streaming).
        corr_id: Correlation id for logging correlation.
    """
    def __init__(
        self,
        message: str,
        *,
        path: str,
        rows_written: int | None = None,
        sheets_written: int | None = None,
        corr_id: str | None = None,
    ):
        """Initialize ExportCancelledError."""
        super().__init__(message)
        self.path = path
        self.rows_written = rows_written
        self.sheets_written = sheets_written
        self.corr_id = corr_id


class FileWriter:
    """FileWriter: single responsibility for writing data to disk.

    Progress & cancel:
    - progress_cb is a callable that accepts integer values [0..100].
    - cancel_cb is a callable returning True if the operation should be aborted.
    - On user-initiated cancellation, writers raise ExportCancelledError (a partial file may exist).
    """
    __slots__ = (
        "_csv_encoding_default",
        "_csv_max_rows_per_sheet_default",
        "_csv_streaming_default",
        "_csv_write_chunk_size",
        "_csv_write_chunk_size_default",
        "_excel_chunk_size",
        "_excel_chunk_size_default",
        "_excel_max_rows_per_sheet",
        "_excel_max_rows_per_sheet_default",
        "_excel_streaming",
        "_excel_streaming_default",
        "_logger",
    )

    def __init__(self, logger: logging.Logger | None = None):
        """Initialize FileWriter.

        Args:
            logger: Optional logger instance.
        """
        self._logger = logger or logging.getLogger("applogger.service")

        # Settings
        self._csv_encoding_default = "utf-8"

        self._csv_write_chunk_size_default = 100_000
        self._csv_write_chunk_size = self._csv_write_chunk_size_default
        self._excel_chunk_size_default = 25_000
        self._excel_chunk_size = self._excel_chunk_size_default
        self._excel_max_rows_per_sheet_default = 1_048_576
        self._excel_max_rows_per_sheet = self._excel_max_rows_per_sheet_default
        self._excel_streaming_default = True
        self._excel_streaming = self._excel_streaming_default

    # ----------------------------------------------------------------------
    # Settings reload
    # ----------------------------------------------------------------------
    def reload_settings(self, settings: dict) -> None:
        """Reload configuration for CSV/Excel writing.

        Updates:
            • csv_chunk_size_rows
            • excel_chunk_size_rows
            • excel_streaming
            • excel_max_rows_per_sheet
        """
        try:
            csv_settings = settings.get("csv", {}) or {}
            self._csv_encoding_default = (csv_settings.get(
                "default_encoding", self._csv_encoding_default) or "").strip() or "utf-8"
            self._csv_write_chunk_size = int(csv_settings.get(
                "write_chunk_size_rows",
                self._csv_write_chunk_size_default)
            )

            excel_settings = settings.get("excel", {}) or {}
            self._excel_chunk_size = int(excel_settings.get("chunk_size_rows", self._excel_chunk_size_default))
            self._excel_max_rows_per_sheet = int(excel_settings.get(
                "max_rows_per_sheet", self._excel_max_rows_per_sheet_default))
            self._excel_streaming = bool(excel_settings.get("streaming", self._excel_streaming_default))

            self._logger.debug(
                "FileWriter: settings reloaded (csv_chunk=%s, excel_chunk=%s, excel_streaming=%s, excel_max_rows=%s)",
                self._csv_write_chunk_size,
                self._excel_chunk_size, self._excel_streaming, self._excel_max_rows_per_sheet
            )
        except Exception:
            self._logger.exception("FileWriter: failed reloading settings")

    # noinspection PyMethodMayBeStatic
    def _validate_excel_sheet_name(self, name: str) -> None:
        """Validate sheet name per Excel constraints.

          - Non-empty, not only whitespace
          - Max 31 characters
          - Cannot contain: :
          - Cannot start or end with a single quote (')
          - Cannot contain ASCII control chars (< 0x20)

        Raises:
            ValueError on invalid input.
        """
        if not isinstance(name, str):
            raise ValueError("Invalid sheet name: not a string")

        # Trim only for validation of emptiness; Excel behåller mellanslag om man vill
        if name.strip() == "":
            raise ValueError("Invalid sheet name: empty or whitespace only")

        if len(name) > 31:
            raise ValueError(f"Invalid sheet name (too long): '{name}' (max 31)")

        # Explicit illegal character set (Excel)
        illegal_chars = {":", "\\", "/", "?", "*", "[", "]"}
        if any(ch in illegal_chars for ch in name):
            raise ValueError(f"Invalid sheet name (illegal chars): '{name}'")

        # Cannot start or end with single quote
        if name.startswith("'") or name.endswith("'"):
            raise ValueError(f"Invalid sheet name (leading/trailing apostrophe): '{name}'")

        # Disallow ASCII control characters (0x00..0x1F)
        if any(ord(ch) < 32 for ch in name):
            raise ValueError(f"Invalid sheet name (control characters): '{name}'")

    # ----------------------------------------------------------------------
    # CSV (chunked for large datasets)
    # ----------------------------------------------------------------------
    def save_csv(
            self,
            df: pd.DataFrame,
            dest: str | Path,
            *,
            encoding: str = "utf-8",
            sep: str = ",",
            index: bool = False,
            na_rep: str | None = None,
            chunk_size_rows: int | None = None,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            corr_id: str | None = None,
    ) -> Path:
        """Writes CSV to disk.

        - For large datasets, writes in row chunks to reduce memory pressure.
        - Emits progress (0..100) when possible.
        - If cancellation is requested, raises ExportCancelledError (a partial file may exist).

        Cancellation semantics:
            * No-chunk path (single pandas call): only honored before the write begins.
            * Chunked path: honored before and during the write; rows_written reports progress.

        Returns:
            Path: The destination path (created or updated).
        """
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)

        rows, columns = fmt_shape(df)
        self._logger.debug(
            "FileWriter: save CSV (corr=%s, path=%s, rows=%s, cols=%s, chunk_size_rows=%s, sep=%r, index=%s)",
            corr_id, fmt_path(path), rows, columns, chunk_size_rows, sep, index
        )

        total = len(df.index)
        if chunk_size_rows is None:
            chunk_size_rows = self._csv_write_chunk_size

        t0 = time.perf_counter()

        # No-chunk (single call) path
        if total == 0 or not chunk_size_rows or total <= chunk_size_rows:
            self._logger.debug(
                "FileWriter: save CSV no-chunk path (corr=%s, total=%s, chunk_size_rows=%s)",
                corr_id, total, chunk_size_rows
            )
            if progress_cb:
                progress_cb(0)
            if cancel_cb and cancel_cb():
                self._logger.debug(
                    "FileWriter: save CSV cancelled before write (corr=%s, path=%s)", corr_id, fmt_path(path)
                )
                raise ExportCancelledError(
                    "CSV export cancelled before write",
                    path=fmt_path(path),
                    rows_written=0,
                    corr_id=corr_id,
                )

            df.to_csv(path, encoding=encoding, sep=sep, index=index, na_rep=na_rep)

            if progress_cb:
                progress_cb(100)

            dt = (time.perf_counter() - t0) * 1000.0
            self._logger.info(
                "FileWriter: CSV written (corr=%s, path=%s, ms=%.1f, rows=%s, cols=%s)",
                corr_id, fmt_path(path), dt, rows, columns
            )
            return path

        # Chunked path
        self._logger.debug(
            "FileWriter: save CSV chunked path (corr=%s, total=%s, chunk_size_rows=%s)",
            corr_id, total, chunk_size_rows
        )

        if progress_cb:
            progress_cb(0)

        rows_written = 0
        last_pct = -1

        # Write header once
        df.head(0).to_csv(path, encoding=encoding, sep=sep, index=index, na_rep=na_rep, mode="w")

        step = chunk_size_rows
        for start in range(0, total, step):
            if cancel_cb and cancel_cb():
                self._logger.debug(
                    "FileWriter: save CSV cancelled mid-run (corr=%s, path=%s, rows_written=%s)",
                    corr_id, fmt_path(path), rows_written
                )
                raise ExportCancelledError(
                    "FileWriter: CSV export cancelled during write",
                    path=fmt_path(path),
                    rows_written=rows_written,
                    corr_id=corr_id,
                )

            end = min(start + step, total)
            chunk = df.iloc[start:end]

            # Append without header
            chunk.to_csv(path, encoding=encoding, sep=sep, index=index, na_rep=na_rep, header=False, mode="a")

            rows_written += len(chunk)
            if progress_cb:
                pct = int(rows_written * 100 / total)
                if pct != last_pct:
                    last_pct = pct
                    progress_cb(pct)

        if progress_cb:
            progress_cb(100)

        dt = (time.perf_counter() - t0) * 1000.0
        self._logger.info(
            "FileWriter: CSV written (corr=%s, path=%s, ms=%.1f, rows=%s, cols=%s)",
            corr_id, fmt_path(path), dt, rows, columns
        )
        return path

    # ----------------------------------------------------------------------
    # Excel (pandas fallback or write-only streaming via openpyxl)
    # ----------------------------------------------------------------------
    def save_excel(
            self,
            df: pd.DataFrame,
            dest: str | Path,
            *,
            sheet_name: str = "Data",
            index: bool = False,
            na_rep: Any = None,
            streaming: bool | None = None,
            max_rows_per_sheet: int | None = None,
            chunk_size_rows: int | None = None,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            corr_id: str | None = None,
    ) -> Path:
        """Writes Excel to disk.

        Modes:
          - streaming=True  → write-only via openpyxl (minimal RAM usage, cancellable mid-write)
          - streaming=False → pandas.to_excel (suited for small/medium datasets, cancellable only before write)

        Behavior:
          - If rows exceed Excel's limit, automatically split across sheets: 'Data', 'Data_2', ...
          - Emits progress (0..100) when possible.
          - On cancellation, raises ExportCancelledError (a partial file may exist in streaming mode).
        """
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)

        self._validate_excel_sheet_name(sheet_name)

        if streaming is None:
            streaming = self._excel_streaming
        if max_rows_per_sheet is None:
            max_rows_per_sheet = self._excel_max_rows_per_sheet
        if chunk_size_rows is None:
            chunk_size_rows = self._excel_chunk_size

        rows, columns = fmt_shape(df)
        self._logger.debug(
            "FileWriter: save excel start (corr=%s, path=%s, rows=%s, cols=%s, streaming=%s, "
            "sheet=%r, index=%s, max_rows_per_sheet=%s, chunk_size_rows=%s)",
            corr_id, fmt_path(path), rows, columns, streaming, sheet_name, index, max_rows_per_sheet, chunk_size_rows
        )

        t0 = time.perf_counter()

        # Pandas fallback (single call)
        if not streaming:
            self._logger.debug(
                "FileWriter: save excel (pandas) path (corr=%s, rows=%s, columns=%s)",
                corr_id, rows, columns
            )
            if progress_cb:
                progress_cb(0)
            if cancel_cb and cancel_cb():
                self._logger.debug(
                    "FileWriter: save excel (pandas) cancelled before write (corr=%s, path=%s)", corr_id, fmt_path(path)
                )
                raise ExportCancelledError(
                    "FileWriter: excel export cancelled before write (pandas path)",
                    path=fmt_path(path),
                    rows_written=0,
                    corr_id=corr_id,
                )
            try:
                with pd.ExcelWriter(path, engine="openpyxl") as excel_writer:
                    df.to_excel(excel_writer, sheet_name=sheet_name, index=index, na_rep=na_rep)
            except Exception:
                self._logger.error(
                    "FileWriter: save excel (pandas) failed (corr=%s, path=%s)",
                    corr_id,
                    fmt_path(path),
                    exc_info=True
                )
                raise
            if progress_cb:
                progress_cb(100)
            dt = (time.perf_counter() - t0) * 1000.0
            self._logger.info(
                "FileWriter: excel written (pandas) "
                "(corr=%s, engine=%s, sheets=%s, path=%s, ms=%.1f, rows=%s, cols=%s)",
                corr_id,
                "openpyxl",
                1,
                fmt_path(path),
                dt,
                rows,
                columns
            )
            return path

        # Streaming via openpyxl write-only (supports mid-write cancellation)
        return self._save_excel_streaming(
            df=df,
            path=path,
            sheet_name=sheet_name,
            index=index,
            na_rep=na_rep,
            max_rows_per_sheet=max_rows_per_sheet,
            chunk_size_rows=chunk_size_rows,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
            corr_id=corr_id,
            t0=t0,
            rows=rows,
            cols=columns,
        )

    # ----------------------------------------------------------------------
    # Excel streaming
    # ----------------------------------------------------------------------
    def _save_excel_streaming(
            self,
            df: pd.DataFrame,
            path: Path,
            *,
            sheet_name: str = "Data",
            index: bool = False,
            na_rep: Any = None,
            max_rows_per_sheet: int | None = None,
            chunk_size_rows: int | None = None,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            corr_id: str | None = None,
            t0: float | None = None,
            rows: str = "?",
            cols: str = "?",
    ) -> Path:
        """Streamed Excel export using openpyxl (write_only mode).

        Features:
            - Writes rows in chunks to minimize memory usage
            - Automatically splits data across multiple sheets when Excel's row limit is reached
            - Progress callback (0..100)
            - Early exit when cancellation callback returns True
            - Handles tz-aware datetimes, numpy scalars, bytes, and NA types safely
        """
        import time
        from datetime import date, datetime, timedelta

        import numpy as np
        from openpyxl import Workbook

        # ----------------------------------------------------------------------
        # Per-cell Excel-safe normalizer
        # ----------------------------------------------------------------------
        def clean_cell(value, *, _na_rep=na_rep):
            """Normalize a single cell value into a type compatible with openpyxl/Excel.

            Rules:
                - pd.NA/NaN/NaT -> None (or na_rep if provided)
                - tz-aware datetime -> timezone-naive datetime
                - bytes/bytearray -> UTF-8 decoded string (errors='replace')
                - numpy scalar types -> converted to Python native types
                - float NaN/Inf -> None/na_rep
                - pd.Interval / pd.Period -> string
                - everything else returned unchanged
            """
            try:
                if pd.isna(value):
                    return _na_rep if _na_rep is not None else None
            except Exception:
                pass

            # Pandas Timestamp → timezone-naive datetime
            try:
                if isinstance(value, pd.Timestamp):
                    return (
                        value.tz_localize(None).to_pydatetime()
                        if value.tz is not None
                        else value.to_pydatetime()
                    )
            except Exception:
                pass

            # Native datetime/date/timedelta
            if isinstance(value, (datetime, date, timedelta)):
                return value

            # Numpy → Python native
            if isinstance(value, np.integer):
                return int(value)
            if isinstance(value, np.floating):
                fv = float(value)
                if np.isnan(fv) or np.isinf(fv):
                    return _na_rep if _na_rep is not None else None
                return fv
            if isinstance(value, np.bool_):
                return bool(value)

            # Bytes → UTF-8
            if isinstance(value, (bytes, bytearray)):
                try:
                    return value.decode("utf-8", errors="replace")
                except Exception:
                    return str(value)

            # Interval / Period → string
            try:
                if isinstance(value, (pd.Interval, pd.Period)):
                    return str(value)
            except Exception:
                pass

            return value

        total = len(df.index)
        if progress_cb:
            progress_cb(0)

        if max_rows_per_sheet is None:
            max_rows_per_sheet = self._excel_max_rows_per_sheet
        rows_limit_for_data = max_rows_per_sheet - 1

        if chunk_size_rows is None:
            chunk_size_rows = self._excel_chunk_size

        self._logger.debug(
            "FileWriter: save excel (streaming) start "
            "(corr=%s, path=%s, sheet=%r, index=%s, total_rows=%s, rows_limit_for_data=%s, chunk_size_rows=%s)",
            corr_id, fmt_path(path), sheet_name, index, total, rows_limit_for_data, chunk_size_rows
        )

        t_start = t0 if t0 is not None else time.perf_counter()
        wb = Workbook(write_only=True)

        with suppress(Exception):
            default_ws = wb.active
            wb.remove(default_ws)

        def start_new_sheet(name: str):
            self._validate_excel_sheet_name(name)
            ws = wb.create_sheet(title=name)
            headers = []
            if index:
                headers.append(df.index.name or "index")
            headers.extend(list(df.columns))
            ws.append(headers)
            return ws

        if total == 0:
            try:
                _ = start_new_sheet(sheet_name)
                wb.save(path)
            finally:
                with suppress(Exception):
                    wb.close()
            if progress_cb:
                progress_cb(100)
            dt_ms = (time.perf_counter() - t_start) * 1000.0
            self._logger.info(
                "FileWriter: excel written (streaming) "
                "(corr=%s, engine=%s, sheets=%s, path=%s, ms=%.1f, rows=%s, cols=%s)",
                corr_id, "openpyxl-writeonly", 1, fmt_path(path), dt_ms, rows, cols
            )
            return path

        sheet_ix = 1
        current_ws = start_new_sheet(sheet_name)
        rows_in_current_sheet = 0
        written = 0
        last_pct = -1

        def maybe_progress():
            nonlocal last_pct
            if not progress_cb:
                return
            pct = int(written * 100 / total) if total else 100
            if pct != last_pct:
                last_pct = pct
                progress_cb(pct)

        def ensure_new_sheet_if_needed():
            nonlocal sheet_ix, current_ws, rows_in_current_sheet
            if rows_in_current_sheet >= rows_limit_for_data:
                sheet_ix += 1
                current_ws = start_new_sheet(f"{sheet_name}_{sheet_ix}")
                rows_in_current_sheet = 0

        step = chunk_size_rows or total

        for start in range(0, total, step):
            if cancel_cb and cancel_cb():
                # Flush partial workbook, then raise
                try:
                    wb.save(path)
                finally:
                    with suppress(Exception):
                        wb.close()
                self._logger.debug(
                    "FileWriter: save excel (streaming) cancelled mid-run "
                    "(corr=%s, path=%s, rows_written=%s, sheets_written=%s)",
                    corr_id,
                    fmt_path(path),
                    written,
                    sheet_ix
                )
                raise ExportCancelledError(
                    "Excel export cancelled during streaming write",
                    path=fmt_path(path),
                    rows_written=written,
                    sheets_written=sheet_ix,
                    corr_id=corr_id,
                )

            end = min(start + step, total)
            chunk = df.iloc[start:end].copy()

            with suppress(Exception):
                tz_cols = chunk.select_dtypes(include=["datetimetz"]).columns
                for col in tz_cols:
                    with suppress(Exception):
                        chunk.loc[:, col] = chunk[col].dt.tz_localize(None)

            for col in chunk.columns:
                try:
                    col_vals = chunk[col]
                    if col_vals.map(lambda v: isinstance(v, (bytes, bytearray))).any():
                        chunk.loc[:, col] = col_vals.map(
                            lambda v: v.decode("utf-8", "replace") if isinstance(v, (bytes, bytearray)) else v
                        )
                except Exception:
                    pass

            ws_append = current_ws.append

            if index:
                idx_values = chunk.index.to_list()
                for j, row_vals in enumerate(chunk.itertuples(index=False, name=None)):
                    if cancel_cb and cancel_cb():
                        try:
                            wb.save(path)
                        finally:
                            with suppress(Exception):
                                wb.close()
                        self._logger.debug(
                            "FileWriter: save excel (streaming) cancelled mid-run "
                            "(corr=%s, path=%s, rows_written=%s, sheets_written=%s)",
                            corr_id, fmt_path(path), written, sheet_ix
                        )
                        raise ExportCancelledError(
                            "Excel export cancelled during streaming write",
                            path=fmt_path(path),
                            rows_written=written,
                            sheets_written=sheet_ix,
                            corr_id=corr_id,
                        )

                    ensure_new_sheet_if_needed()

                    idx_clean = clean_cell(idx_values[j])
                    cleaned = tuple(clean_cell(x) for x in row_vals)
                    ws_append((idx_clean, *cleaned))

                    rows_in_current_sheet += 1
                    written += 1
                    maybe_progress()
            else:
                for row_vals in chunk.itertuples(index=False, name=None):
                    if cancel_cb and cancel_cb():
                        try:
                            wb.save(path)
                        finally:
                            with suppress(Exception):
                                wb.close()
                        self._logger.debug(
                            "FileWriter: save excel (streaming) cancelled mid-run "
                            "(corr=%s, path=%s, rows_written=%s, sheets_written=%s)",
                            corr_id, fmt_path(path), written, sheet_ix
                        )
                        raise ExportCancelledError(
                            "Excel export cancelled during streaming write",
                            path=fmt_path(path),
                            rows_written=written,
                            sheets_written=sheet_ix,
                            corr_id=corr_id,
                        )

                    ensure_new_sheet_if_needed()

                    cleaned = tuple(clean_cell(x) for x in row_vals)
                    ws_append(cleaned)

                    rows_in_current_sheet += 1
                    written += 1
                    maybe_progress()

        try:
            wb.save(path)
        finally:
            with suppress(Exception):
                wb.close()

        if progress_cb:
            progress_cb(100)

        dt_ms = (time.perf_counter() - t_start) * 1000.0
        self._logger.info(
            "FileWriter: excel written (streaming) (corr=%s, engine=%s, sheets=%s, path=%s, ms=%.1f, rows=%s, cols=%s)",
            corr_id, "openpyxl-writeonly", sheet_ix, fmt_path(path), dt_ms, rows, cols
        )
        return path

    # ----------------------------------------------------------------------
    # Data file dispatcher (suffix-based)
    # ----------------------------------------------------------------------
    def save_datafile(
        self,
        df: pd.DataFrame,
        dest: str | Path,
        *,
        corr_id: str | None = None,
    ) -> Path:
        """Dispatches to a concrete writer based on file suffix.

          .df       → pickle
          .feather  → feather
          .ft       → feather
          .parquet  → parquet.

        Raises:
            ValueError: if suffix is unsupported.
        """
        suffix = Path(dest).suffix.lower()
        rows, columns = fmt_shape(df)
        self._logger.debug(
            "FileWriter: save datafile entry (corr=%s, path=%s, rows=%s, cols=%s, suffix=%s)",
            corr_id, fmt_path(dest), rows, columns, suffix)

        if suffix == ".df":
            out = self._save_pickle(df, dest, corr_id=corr_id)
        elif suffix in (".feather", ".ft"):
            out = self._save_feather(df, dest, corr_id=corr_id)
        elif suffix == ".parquet":
            out = self._save_parquet(df, dest, corr_id=corr_id)
        else:
            raise ValueError(f"Unsupported data file suffix: {suffix}")

        self._logger.info("FileWriter: data file written (corr=%s, path=%s, rows=%s, cols=%s)",
                          corr_id, fmt_path(out), rows, columns)
        return out

    # ----------------------------------------------------------------------
    # Other formats (atomic JSON; data formats via pandas)
    # ----------------------------------------------------------------------
    def save_json(self, data: Any, dest: str | Path, *, indent: int = 2, corr_id: str | None = None) -> Path:
        """Writes JSON to disk via atomic replace (tmp + move)."""
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._logger.debug("FileWriter: save JSON entry (corr=%s, path=%s)", corr_id, fmt_path(path))
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8")
        tmp.replace(path)
        self._logger.info(
            "FileWriter: JSON written (corr=%s, path=%s, bytes=%s)",
            corr_id,
            fmt_path(path),
            path.stat().st_size if path.exists() else "?"
        )
        return path

    def _save_pickle(self, obj: Any, dest: str | Path, *, corr_id: str | None = None) -> Path:
        """Writes a pickle (.df is used upstream for DataFrame pickles)."""
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._logger.debug("FileWriter: pickle write (corr=%s, path=%s)", corr_id, fmt_path(path))
        with path.open("wb") as f:
            pickle.dump(obj, f)
        return path

    def _save_feather(self, df: pd.DataFrame, dest: str | Path, *, corr_id: str | None = None) -> Path:
        """Writes a Feather file."""
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._logger.debug("FileWriter: feather write (corr=%s, path=%s)", corr_id, fmt_path(path))
        df.to_feather(path)
        return path

    def _save_parquet(self, df: pd.DataFrame, dest: str | Path, *, corr_id: str | None = None) -> Path:
        """Writes a Parquet file using pyarrow (index=False by default)."""
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._logger.debug("FileWriter: parquet write (corr=%s, path=%s)", corr_id, fmt_path(path))
        df.to_parquet(path, engine="pyarrow", index=False)
        return path

    def save_profile(self, profile, dest: str | Path, *, corr_id: str | None = None) -> Path:
        """Writes a ydata-profiling ProfileReport to HTML."""
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._logger.debug("FileWriter: save profile start (corr=%s, path=%s)", corr_id, fmt_path(path))
        profile.to_file(path)
        self._logger.info("FileWriter: profile (HTML) written (corr=%s, path=%s)", corr_id, fmt_path(path))
        return path
