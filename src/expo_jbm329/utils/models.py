"""Qt model for displaying pandas DataFrames in QTableView.

This module provides:
  - DataFrameModel: optimized, read-only model with:
      • robust sorting (numeric, datetime, object),
      • predictable display:
          - datetime via strftime,
          - categorical and object/string via fmt_category (safe, "" for NA),
          - numeric values left raw (no thousand separators, no rounding).

Design principles:
  • Read-only by default, predictable behavior.
  • Defensive programming with safe fallbacks.
  • English docstrings/comments; Swedish visible UI text preserved.
  • Drop-in compatibility with existing code (public API unchanged).
"""

from __future__ import annotations

import contextlib
import datetime
from typing import TYPE_CHECKING, Any, override

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype
from PyQt6.QtCore import QAbstractTableModel, QDateTime, QLocale, QModelIndex, Qt, pyqtSignal
from PyQt6.QtGui import QColor

from expo_jbm329.utils.format_utils import (
    fmt_category,
)

if TYPE_CHECKING:
    from collections.abc import Callable


# ======================================================================
# DataFrameModel - read-only display with safe datetime/text formatting
# ======================================================================
class DataFrameModel(QAbstractTableModel):
    """Read-only model for pandas.DataFrame in QTableView.

    Display policy:
      - Row numbers are shown via the vertical header (1-based).
      - Datetime columns: fmt_datetime_auto (date-only as YYYY-MM-DD).
      - Categorical + object/string columns: fmt_category ("" for NA).
      - Numeric columns: RAW (no thousand separators, no rounding).
      - Tooltips mirror display text; EditRole returns raw value.

    Sorting:
      - Rows sorted via internal row index mapping (_row_ix).
      - Datetime sorted by int64 timestamps; NA sink to bottom.
      - Object sorted by safe-string keys; NA -> "".
      - Numeric sorted with dtype max sentinels for NA to sink on ascending.

    Signals:
      - data_frame_replaced: emitted after set_data_frame completes.
    """

    data_frame_replaced = pyqtSignal()

    def __init__(
        self,
        df: pd.DataFrame,
        parent=None,
        *,
        na_rep: str = "",
        formatters: dict[str, Callable[[Any], str]] | None = None
    ):
        """Initialize the DataFrameModel.

        Args:
            df: The pandas DataFrame to display.
            parent: The parent QObject. Defaults to None.
            na_rep: String representation for NA values. Defaults to "".
            formatters: Optional dict of custom column formatters.
        """
        super().__init__(parent)

        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)

        self._df = df
        self._row_ix = np.arange(len(df), dtype=np.int64)
        self._na_rep = na_rep
        self._formatters = formatters or {}

        # Column metadata caches
        self._numeric_cols = {col: is_numeric_dtype(df[col]) for col in df.columns}
        self._datetime_cols = {col: is_datetime64_any_dtype(df[col]) for col in df.columns}

    # ------------------------------------------------------------------
    # Basic model API
    # ------------------------------------------------------------------
    @override
    def rowCount(self, parent: QModelIndex | None = None) -> int:
        """Number of rows; returns 0 for child indexes."""
        parent = parent or QModelIndex()
        if parent.isValid():
            return 0
        return len(self._row_ix)

    @override
    def columnCount(self, parent: QModelIndex | None = None) -> int:
        """Number of columns; includes synthetic leading '#' column."""
        parent = parent or QModelIndex()
        if parent.isValid():
            return 0
        return self._df.shape[1]

    # ------------------------------------------------------------------
    # DATA
    # ------------------------------------------------------------------
    @override
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Return the data for the given index and role.

        Args:
            index: The model index.
            role: The item data role. Defaults to DisplayRole.

        Returns:
            The data at the index for the specified role.
        """
        try:
            if not index.isValid():
                return None

            r = index.row()
            c = index.column()
            if r < 0 or r >= len(self._row_ix):
                return None

            real_r = int(self._row_ix[r])

            # ----- Data columns -----
            df_col_ix = c
            col_name = self._df.columns[df_col_ix]
            val = self._df.iloc[real_r, df_col_ix]

            # DISPLAY
            if role == Qt.ItemDataRole.DisplayRole:
                # 1) Optional custom per-column formatter (safe)
                if col_name in self._formatters:
                    try:
                        return self._formatters[col_name](val)
                    except Exception:
                        # Fall back to defaults on formatter failure
                        pass

                # NA -> na_rep
                if pd.isna(val):
                    return self._na_rep

                # Datetime → localized via QLocale

                if self._datetime_cols.get(col_name, False):
                    try:
                        # Normalize pandas / python datetime safely
                        py_dt: datetime.datetime | None = None

                        if isinstance(val, pd.Timestamp):
                            py_dt = val.to_pydatetime()
                        elif isinstance(val, datetime.datetime):
                            py_dt = val
                        elif isinstance(val, datetime.date):
                            py_dt = datetime.datetime.combine(val, datetime.time.min)

                        if py_dt is None:
                            return self._na_rep

                        qdt = QDateTime(
                            py_dt.year,
                            py_dt.month,
                            py_dt.day,
                            py_dt.hour,
                            py_dt.minute,
                            py_dt.second,
                        )

                        return QLocale().toString(qdt, QLocale.FormatType.ShortFormat)

                    except Exception:
                        return self._na_rep

                # Category OR object/string -> safe text
                import pandas.api.types as pdt
                if isinstance(self._df[col_name].dtype, pd.CategoricalDtype) or \
                   pdt.is_object_dtype(self._df[col_name]) or \
                   pdt.is_string_dtype(self._df[col_name]):
                    return fmt_category(val)

                # Numeric (and other) -> raw string representation
                return str(val)

            # ALIGNMENT
            if role == Qt.ItemDataRole.TextAlignmentRole:
                if self._numeric_cols.get(col_name, False):
                    return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

            # TOOLTIP
            if role == Qt.ItemDataRole.ToolTipRole:
                return self._na_rep if pd.isna(val) else str(val)

            # EDIT ROLE (raw value)
            if role == Qt.ItemDataRole.EditRole:
                return val

            return None

        except Exception:
            # Defensive: never crash the delegate/view due to bad data
            return None

    # ------------------------------------------------------------------
    # HEADER
    # ------------------------------------------------------------------
    @override
    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        """Return the header data for the given section and orientation.

        Args:
            section: The section number.
            orientation: The orientation (Horizontal or Vertical).
            role: The item data role. Defaults to DisplayRole.

        Returns:
            The header data for the specified section and role.
        """
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < self._df.shape[1]:
                return str(self._df.columns[section])
            return None

        if orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)

        return None

    # ------------------------------------------------------------------
    # SORTING
    # ------------------------------------------------------------------
    @override
    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """Sort the model by the given column and order.

        Efficiently reorders row indexes using layoutAboutToBeChanged/layoutChanged.
        No beginResetModel/endResetModel is used - avoids empty-table bug.

        Args:
            column: The column index to sort by.
            order: The sort order (Ascending or Descending). Defaults to Ascending.
        """
        if self._df is None or self._df.shape[0] <= 1:
            return

        # Tell Qt we are about to reorder rows
        self.layoutAboutToBeChanged.emit()

        # -----------------------------------------
        # Data columns
        # -----------------------------------------
        df_col_ix = column
        s = self._df.iloc[:, df_col_ix]
        arr = s.to_numpy(copy=False)

        try:
            # Datetime
            if is_datetime64_any_dtype(s):
                arr64 = s.astype("int64", copy=False).to_numpy()
                nan_mask = s.isna().to_numpy()
                key = arr64.copy()
                key[nan_mask] = np.iinfo(np.int64).max
                sorted_pos = np.argsort(key)

            # Object-like
            elif arr.dtype == object:
                key = np.array(
                    [("" if (x is None or (isinstance(x, float) and np.isnan(x))) else str(x)) for x in arr],
                    dtype=object,
                )
                sorted_pos = np.argsort(key)

            # Numeric (and others)
            else:
                nan_mask = pd.isna(arr)
                if np.issubdtype(arr.dtype, np.floating):
                    fill_val = np.finfo(arr.dtype).max
                else:
                    try:
                        fill_val = np.iinfo(arr.dtype).max
                    except Exception:
                        fill_val = np.iinfo(np.int64).max

                key = arr.copy()
                key[nan_mask] = fill_val
                sorted_pos = np.argsort(key)

            if order == Qt.SortOrder.DescendingOrder:
                sorted_pos = sorted_pos[::-1]

            self._row_ix = sorted_pos.astype(np.int64)

        except Exception:
            # Fallback: string sort
            arr_fallback = s.astype(str).to_numpy()
            sorted_pos = np.argsort(arr_fallback)
            if order == Qt.SortOrder.DescendingOrder:
                sorted_pos = sorted_pos[::-1]
            self._row_ix = sorted_pos.astype(np.int64)

        # Let Qt know sorting is complete
        self.layoutChanged.emit()
    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    def set_data_frame(self, df: pd.DataFrame):
        """Replace the underlying DataFrame and reset all cached metadata.

        Emits
        -----
        data_frame_replaced : pyqtSignal
            Emitted after the model is reset and new data is active.
        """
        self.beginResetModel()

        self._df = df
        self._row_ix = np.arange(len(df), dtype=np.int64)
        self._numeric_cols = {col: is_numeric_dtype(df[col]) for col in df.columns}
        self._datetime_cols = {col: is_datetime64_any_dtype(df[col]) for col in df.columns}

        self.endResetModel()
        with contextlib.suppress(Exception):
            self.data_frame_replaced.emit()

    def data_frame(self) -> pd.DataFrame:
        """Return the underlying DataFrame reference."""
        return self._df


class JoinPreviewModel(DataFrameModel):
    """Model for previewing joined dataframes in a QTableView.

    Inherits from DataFrameModel and adds specific functionality for joined data.
    """
    @override
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Return the data for the given index and role."""
        # --- custom preview logic ---
        if role == Qt.ItemDataRole.BackgroundRole:
            if not index.isValid():
                return None

            col_name = self._df.columns[index.column()]
            raw = self._df.iloc[self._row_ix[index.row()], index.column()]

            if col_name == "join_status":
                if raw == "left_only":
                    return QColor("#fff3cd")  # yellow
                if raw == "right_only":
                    return QColor("#f8d7da")  # red

        # fallback to base model
        return super().data(index, role)
