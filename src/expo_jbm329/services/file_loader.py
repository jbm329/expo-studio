"""Service for loading dataframes from various file formats.

This module provides the FileLoader class, which supports loading CSV, Excel,
Parquet, Feather, Pickle, and JSON files into pandas DataFrames.
"""

from __future__ import annotations

import logging
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import pandas as pd
from openpyxl.utils.cell import range_boundaries
from pyqvd import QvdTable

from expo_jbm329.utils.format_utils import fmt_path, fmt_path_size
from expo_jbm329.utils.path_manager import get_documents_dir
from expo_jbm329.utils.paths import expand

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class ReadRequest:
    """Dataclass for read requests."""

    path: Path
    index_col: int | str | None = None
    sheet_name: str | int | None = None
    progress_cb: Callable[[int], None] | None = None
    cancel_cb: Callable[[], bool] | None = None


class OperationCancelledError(Exception):
    """Raised when a cooperative operation is cancelled."""


class DataFrameReader(Protocol):
    """Protocol for functions that read a DataFrame from a file path."""

    def __call__(self, req: ReadRequest) -> pd.DataFrame:
        """Read a DataFrame from a file path."""
        ...


class FileLoader:
    """Low-level, robust DataFrame loader with progress support.

    Responsibilities:
      • Expand and resolve absolute paths
      • CSV reader (chunked or direct)
      • XLSX streaming reader (progress-friendly)
      • Parquet/Feather/Pickle/JSON via pandas
      • Settings hydration via reload_settings()
      • No fallback search logic (only optional Documents fallback)

    Notes:
      - All readers are thread-safe and provide basic error handling.
      - Progress reporting is available for CSV and Excel formats.
    """

    __slots__ = (
        "_config",
        "_csv_default_sep",
        "_csv_encoding_default",
        "_csv_read_chunk_size",
        "_csv_read_chunk_size_default",
        "_csv_sniff_delimiter",
        "_encoding_detector",
        "_excel_chunk_size",
        "_excel_chunk_size_default",
        "_lock",
        "_logger",
        "_readers",
    )

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        encoding_detector: Callable[[Path], str] | None = None,
    ) -> None:
        """Initialize the FileLoader.

        Args:
            logger: Optional logger instance.
            encoding_detector: Optional callable to detect file encoding.
        """
        self._logger = logger or logging.getLogger("applogger.service")

        # Settings (hydrated in reload_settings)
        self._config: dict = {}

        self._csv_encoding_default = "utf-8"
        self._csv_read_chunk_size_default = 100_000
        self._csv_read_chunk_size = self._csv_read_chunk_size_default
        self._csv_sniff_delimiter: bool = True
        self._csv_default_sep: str | None = None

        self._excel_chunk_size_default = 25_000
        self._excel_chunk_size = self._excel_chunk_size_default

        self._encoding_detector = encoding_detector or self._default_detect_encoding
        self._lock = threading.RLock()

        # Supported readers by suffix (simple dispatch)
        self._readers: dict[str, DataFrameReader] = {
            ".csv": self._read_csv,
            ".xlsx": self._read_excel,
            ".xls": self._read_excel,
            ".json": self._read_json,
            ".parquet": self._read_parquet,
            ".feather": self._read_feather,
            ".ft": self._read_feather,
            ".pkl": self._read_pickle,
            ".pickle": self._read_pickle,
            ".df": self._read_pickle,
            ".qvd": self._read_qvd,
            ".dta": self._read_stata,
            ".sav": self._read_spss,
        }

    # ================================================================
    # Settings hydration
    # ================================================================
    def reload_settings(self, settings: dict) -> None:
        """Apply runtime settings for CSV/Excel reading.

        Args:
            settings: Dictionary of new settings.
        """
        with self._lock:
            try:
                csv_settings = settings.get("csv", {}) or {}
                excel_settings = settings.get("excel", {}) or {}

                enc = csv_settings.get("default_encoding", self._csv_encoding_default)
                self._csv_encoding_default = (enc or "").strip() or "utf-8"

                # Guard: ensure these are ints and > 0 if used
                try:
                    self._csv_read_chunk_size = int(
                        csv_settings.get("read_chunk_size_rows", self._csv_read_chunk_size_default)
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
                    self._csv_read_chunk_size = self._csv_read_chunk_size_default

                # CSV sniff toggle and default sep
                try:
                    self._csv_sniff_delimiter = bool(csv_settings.get("sniff_delimiter", True))

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
                    self._csv_sniff_delimiter = True

                # Optional default separator if sniff is disabled (or as a fallback)
                sep_val = csv_settings.get("default_sep")
                self._csv_default_sep = sep_val if isinstance(sep_val, str) and sep_val else None

                try:
                    self._excel_chunk_size = int(excel_settings.get("chunk_size_rows", self._excel_chunk_size_default))
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
                    self._excel_chunk_size = self._excel_chunk_size_default

                # Used for Documents fallback resolution
                self._config = dict(settings)

                self._logger.debug(
                    "FileLoader: settings reloaded (csv_chunk=%s, enc=%s, sniff_del='%s', def_sep='%s' excel_chunk=%s)",
                    self._csv_read_chunk_size,
                    self._csv_encoding_default,
                    self._csv_sniff_delimiter,
                    self._csv_default_sep,
                    self._excel_chunk_size,
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
                # Developer diagnostics: keep stack trace
                self._logger.exception("FileLoader: failed reloading settings")

    # ================================================================
    # Path resolution
    # ================================================================
    def resolve(self, file_name_or_path: str) -> Path | None:
        """Resolve a path by expanding user/vars and checking for fallback.

        Args:
            file_name_or_path: The path or name to resolve.

        Returns:
            The resolved Path or None if not found.
        """
        # 1) Expand and return if absolute or exists
        raw = expand(file_name_or_path)
        if raw.is_absolute() or raw.exists():
            return raw

        # 2) Minimal fallback: Documents/<filename>
        try:
            docs = get_documents_dir(self._config)
            candidate = expand(docs) / Path(file_name_or_path).name
            if candidate.exists():
                return candidate
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
            # Non-fatal; simply return None if fallback fails
            pass

        # 3) No match
        return None

    # ================================================================
    # Public API
    # ================================================================
    def load_df_auto(
        self,
        file_name_or_path: str,
        *,
        index_col: int | str | None = None,
        sheet_name: str | int | None = None,
        progress_cb: Callable[[int], None] | None = None,
        cancel_cb: Callable[[], bool] | None = None,
        corr_id: str | None = None,
    ) -> pd.DataFrame:
        """Auto-detect the file type by suffix and load it into a DataFrame.

        Args:
            file_name_or_path: File path or logical name resolvable via fallback rules.
            index_col: Optional index column.
            sheet_name: Optional Excel sheet name or index.
            progress_cb: Optional progress callback receiving values 0..100.
            cancel_cb: Optional callback returning True if cancellation was requested.
            corr_id: Optional correlation id for logging.

        Returns:
            The loaded DataFrame.

        Raises:
            FileNotFoundError: If the path cannot be resolved.
            ValueError: If the file format is unsupported.
            OperationCancelledError: If cancellation is requested.
            Exception: If the underlying reader fails.
        """
        self._logger.debug(
            "FileLoader: load dataframe auto (corr=%s, input=%r, index_col=%r, sheet=%r)",
            corr_id,
            fmt_path(file_name_or_path),
            index_col,
            sheet_name,
        )

        path = self.resolve(file_name_or_path)
        if path is None:
            self._logger.warning(
                "FileLoader: failed to resolve (corr=%s, input=%r)",
                corr_id,
                fmt_path(file_name_or_path),
            )
            msg = f"Could not resolve file: {file_name_or_path}"
            raise FileNotFoundError(msg)

        suffix = path.suffix.lower()
        reader = self._readers.get(suffix)
        if reader is None:
            self._logger.warning(
                "FileLoader: unsupported file format (corr=%s, path=%s, suffix=%s)",
                corr_id,
                fmt_path(path),
                suffix,
            )
            msg = f"Unsupported file format: {suffix}"
            raise ValueError(msg)

        if cancel_cb is not None and cancel_cb():
            msg = "Loading was cancelled before start."
            raise OperationCancelledError(msg)

        req = ReadRequest(
            path=path,
            sheet_name=sheet_name,
            index_col=index_col,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
        )

        try:
            if progress_cb is not None:
                progress_cb(0)

            df = reader(req)

            if cancel_cb is not None and cancel_cb():
                msg = "Loading was cancelled during read."
                raise OperationCancelledError(msg)

            if progress_cb is not None:
                progress_cb(100)

            return df

        except OperationCancelledError:
            self._logger.info(
                "FileLoader: load cancelled (corr=%s, path=%s, suffix=%s)",
                corr_id,
                fmt_path(path),
                suffix,
            )
            raise

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
                "FileLoader: could not read file (corr=%s, path=%s, suffix=%s): %s",
                corr_id,
                fmt_path(path),
                suffix,
                e,
            )
            raise

    # ================================================================
    # CSV reader
    # ================================================================

    def _read_csv(self, req: ReadRequest) -> pd.DataFrame:
        """Read a CSV file with cooperative cancellation support.

        This method prefers chunked reading whenever cancellation support is needed,
        because a single-shot ``pd.read_csv()`` call cannot be interrupted
        cooperatively while parsing is in progress.

        Args:
            req: Read request with path, callbacks, and parsing options.

        Returns:
            The loaded DataFrame.

        Raises:
            OperationCancelledError: If cancellation is requested.
            Exception: If pandas or file handling fails.
        """
        enc = self._encoding_detector(req.path)

        if self._csv_sniff_delimiter:
            sep = self._sniff_delimiter(req.path, enc)
            if sep is None and self._csv_default_sep:
                sep = self._csv_default_sep
        else:
            sep = self._csv_default_sep

        total_size = max(1, req.path.stat().st_size)

        def _raise_if_cancelled() -> None:
            if req.cancel_cb is not None and req.cancel_cb():
                msg = "CSV loading cancelled."
                raise OperationCancelledError(msg)

        # If cancellation support is present, prefer chunked reading even for
        # relatively small files. A single-shot pd.read_csv() call is not
        # cooperatively cancellable while parsing is in progress.
        use_chunking = self._csv_read_chunk_size is not None and self._csv_read_chunk_size > 0
        if req.cancel_cb is not None:
            use_chunking = True

        _raise_if_cancelled()

        if req.progress_cb is not None:
            req.progress_cb(0)

        if not use_chunking:
            df = pd.read_csv(
                req.path,
                sep=(sep or None),
                engine="python",
                encoding=enc,
                index_col=req.index_col,
            )

            _raise_if_cancelled()

            if req.progress_cb is not None:
                req.progress_cb(100)
            return df

        chunks: list[pd.DataFrame] = []

        from typing import BinaryIO, cast

        with req.path.open("rb") as raw_f:
            f = cast("BinaryIO", raw_f)
            it = pd.read_csv(
                f,
                sep=(sep or None),
                engine="python",
                encoding=enc,
                index_col=req.index_col,
                chunksize=self._csv_read_chunk_size,
            )

            last_pct = -1

            for chunk in it:
                _raise_if_cancelled()

                chunks.append(chunk)

                _raise_if_cancelled()

                try:
                    pos = f.tell()
                    pct = int((pos * 100) / total_size)
                    if req.progress_cb is not None and pct != last_pct:
                        req.progress_cb(pct)
                        last_pct = pct
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
                    # Never fail on progress reporting.
                    pass

        _raise_if_cancelled()

        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()

        _raise_if_cancelled()

        if req.progress_cb is not None:
            req.progress_cb(100)

        return df

    # ================================================================
    # Excel reader (streaming)
    # ================================================================
    def _read_excel(self, req: ReadRequest) -> pd.DataFrame:
        """Read XLSX with a streaming approach (openpyxl read_only).

        Keeps memory usage reasonable and emits progress periodically.
        Fallback to pandas.read_excel when openpyxl is unavailable.
        """
        # Try streaming path first
        try:
            from openpyxl import load_workbook
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
            # Fallback: pandas (fast; usually 0→100 progress)
            if req.progress_cb:
                req.progress_cb(0)
            df = pd.read_excel(str(req.path), sheet_name=req.sheet_name or 0, index_col=req.index_col)
            if req.progress_cb:
                req.progress_cb(100)
            return df

        if req.progress_cb:
            req.progress_cb(0)
        wb = load_workbook(str(req.path), read_only=True, data_only=True)

        try:
            # Robust sheet selection
            if isinstance(req.sheet_name, int):
                try:
                    ws = wb.worksheets[req.sheet_name]
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
                    msg = f"Sheet index out of range: {req.sheet_name}"
                    raise ValueError(msg) from e
            else:
                name = str(req.sheet_name) if req.sheet_name is not None else str(wb.worksheets[0].title)
                try:
                    ws = wb[name]
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
                    msg = f"Sheet name not found: {req.sheet_name}"
                    raise ValueError(msg) from e

            rows_iter = ws.iter_rows(values_only=True)

            # Header
            try:
                header = list(next(rows_iter))
            except StopIteration:
                if req.progress_cb:
                    req.progress_cb(100)
                return pd.DataFrame()

            # Estimate total rows (best effort)
            try:
                dim = ws.calculate_dimension()
                _, _, _, max_row = range_boundaries(dim)
                total_rows = max(0, int(max_row) - 1)  # exclude header
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
                total_rows = 0

            # If dimension unreliable (0 or 1), quickly recount
            if total_rows <= 1:
                total_rows = 0
                for _ in ws.iter_rows(values_only=True):
                    total_rows += 1
                total_rows = max(0, total_rows - 1)  # exclude header

            # Read parameters
            batch_size = self._excel_chunk_size or self._excel_chunk_size_default
            batch_size = max(1, int(batch_size))

            # Progress parameters
            emit_every = max(1, total_rows // 100) if total_rows > 0 else 1000

            read_rows = 0
            last_emitted = -1
            data: list[list[Any]] = []
            batch: list[tuple[Any, ...] | None] = []

            def emit_progress(force: bool = False) -> None:
                """Emit bounded progress [1..99] while streaming; 100 is sent at exit."""
                nonlocal last_emitted
                if not req.progress_cb:
                    return
                if total_rows > 0:
                    pct = int((read_rows * 100) / total_rows)
                    pct = max(1, min(99, pct)) if read_rows < total_rows else 100
                else:
                    # Unknown total: tick slowly upward towards 99
                    pct = min(99, (last_emitted + 1) if last_emitted >= 0 else 1)
                if force or pct != last_emitted:
                    last_emitted = pct
                    req.progress_cb(pct)

            # Row streaming
            count_since_emit = 0
            for row in rows_iter:
                if req.cancel_cb and req.cancel_cb():
                    return pd.DataFrame()

                batch.append(row)
                read_rows += 1
                count_since_emit += 1

                # Dump batch into data to avoid huge list growth
                if len(batch) >= batch_size:
                    data.extend([list(r) for r in batch if r is not None])
                    batch.clear()

                # Emit progress by interval
                if count_since_emit >= emit_every:
                    emit_progress()
                    count_since_emit = 0

            # Final batch flush
            if batch:
                data.extend([list(r) for r in batch if r is not None])
                batch.clear()
                emit_progress(force=True)

            df = pd.DataFrame(data, columns=header)

            # Optional index assignment (robust + warn if it fails)
            if req.index_col is not None and not df.empty:
                try:
                    if isinstance(req.index_col, int):
                        df = df.set_index(df.columns[req.index_col])
                    else:
                        df = df.set_index(req.index_col)
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
                    self._logger.warning(
                        "FileLoader: excel index assignment failed (index_col=%r, cols=%s): %s",
                        req.index_col,
                        list(df.columns),
                        e,
                    )

            if req.progress_cb:
                req.progress_cb(100)
            return df

        finally:
            with suppress(Exception):
                wb.close()

    # ================================================================
    # JSON reader
    # ================================================================
    # noinspection PyMethodMayBeStatic
    def _read_json(self, req: ReadRequest) -> pd.DataFrame:
        """Read a JSON file into a pandas DataFrame."""
        df = pd.read_json(req.path)

        if req.index_col is not None:
            df = df.set_index(req.index_col)

        return df

    # ================================================================
    # Pickle reader
    # ================================================================
    # noinspection PyMethodMayBeStatic
    def _read_pickle(self, req: ReadRequest) -> pd.DataFrame:
        """Read a Pickle file into a pandas DataFrame."""
        df = pd.read_pickle(req.path)

        if not isinstance(df, pd.DataFrame):
            msg = "Pickle file did not contain a pandas DataFrame"
            raise TypeError(msg)

        if req.index_col is not None:
            df = df.set_index(req.index_col)

        return df

    # ================================================================
    # Feather reader
    # ================================================================
    # noinspection PyMethodMayBeStatic
    def _read_feather(self, req: ReadRequest) -> pd.DataFrame:
        """Read a Feather file into a pandas DataFrame."""
        df = pd.read_feather(req.path)

        if req.index_col is not None:
            df = df.set_index(req.index_col)

        return df

    # ================================================================
    # Parquet reader
    # ================================================================
    # noinspection PyMethodMayBeStatic
    def _read_parquet(self, req: ReadRequest) -> pd.DataFrame:
        """Read a Parquet file into a pandas DataFrame."""
        df = pd.read_parquet(req.path)

        if req.index_col is not None:
            df = df.set_index(req.index_col)

        return df

    # ================================================================
    # QVD reader
    # ================================================================
    # noinspection PyMethodMayBeStatic
    def _read_qvd(self, req: ReadRequest) -> pd.DataFrame:
        """Load a QVD file into a pandas DataFrame."""
        self._logger.debug(
            "FileLoader: reading QVD (path=%s%s)",
            fmt_path(req.path),
            fmt_path_size(req.path),
        )

        if req.cancel_cb and req.cancel_cb():
            return pd.DataFrame()

        table = QvdTable.from_qvd(req.path)

        if isinstance(table, QvdTable):
            df = table.to_pandas()
        else:
            # fallback om library faktiskt returnerar iterator
            tables = list(table)
            if not tables:
                return pd.DataFrame()
            df = tables[0].to_pandas()

        return df

    # ================================================================
    # SPSS reader
    # ================================================================
    # noinspection PyMethodMayBeStatic
    def _read_spss(self, req: ReadRequest) -> pd.DataFrame:
        """Load a SPSS file into a pandas DataFrame."""
        self._logger.debug(
            "FileLoader: reading SPSS file (path=%s%s)",
            fmt_path(req.path),
            fmt_path_size(req.path),
        )

        if req.cancel_cb and req.cancel_cb():
            return pd.DataFrame()

        df = pd.read_spss(req.path)

        if req.index_col is not None:
            df = df.set_index(req.index_col)

        return df

    # ================================================================
    # Stata reader
    # ================================================================
    # noinspection PyMethodMayBeStatic
    def _read_stata(self, req: ReadRequest) -> pd.DataFrame:
        """Load a stata file into a pandas DataFrame."""
        self._logger.debug(
            "FileLoader: reading Stata file (path=%s%s)",
            fmt_path(req.path),
            fmt_path_size(req.path),
        )

        if req.cancel_cb and req.cancel_cb():
            return pd.DataFrame()

        df_or_iter = pd.read_stata(req.path)

        if isinstance(df_or_iter, pd.DataFrame):
            return df_or_iter

        return pd.concat(list(df_or_iter), ignore_index=True)

    # ================================================================
    # Utility helpers
    # ================================================================
    # noinspection PyMethodMayBeStatic
    def _sniff_delimiter(self, path: Path, encoding: str) -> str | None:
        r"""Heuristic delimiter detection for CSV. Returns one of , ; \\t | or None."""
        try:
            import csv

            with path.open("r", encoding=encoding, newline="") as f:
                sample = f.read(2048)
            return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
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
            return None

    def _default_detect_encoding(self, path: Path) -> str:
        """Best-effort encoding detection.

        - BOM check for utf-8-sig and utf-16
        - Trial read with a short list of likely encodings
        - Fallback to iso-8859-1.
        """
        candidates = [
            "utf-8",
            "utf-8-sig",
            "cp1252",
            "iso-8859-1",
        ]
        if self._csv_encoding_default and self._csv_encoding_default not in candidates:
            candidates.append(self._csv_encoding_default)

        try:
            with path.open("rb") as f:
                head = f.read(4096)
            if head.startswith(b"\xef\xbb\xbf"):
                return "utf-8-sig"
            if head.startswith(b"\xff\xfe"):
                return "utf-16le"
            if head.startswith(b"\xfe\xff"):
                return "utf-16be"
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
            pass

        for enc in candidates:
            try:
                with path.open("r", encoding=enc, errors="strict") as f:
                    for _ in range(5):
                        if not f.readline():
                            break
                return enc
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
                continue
        return "iso-8859-1"
