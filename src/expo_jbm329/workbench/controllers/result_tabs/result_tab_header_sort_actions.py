"""Header (column) sort actions with explicit dependency injection."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP

from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.utils.i18n_utils import tr, tr_fmt

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd
    from PyQt6.QtWidgets import QTableView, QWidget

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )


class ResultTabHeaderSortActions:
    """Header (column) sort actions with explicit dependency injection."""

    # ------------------------------------------------------------------
    # i18n markers (pylupdate6-visible)
    # ------------------------------------------------------------------
    TR_SORT_OPERATION_ASC = QT_TR_NOOP("sort ascending")
    TR_SORTING_COLUMN_ASC = QT_TR_NOOP("Sorting ascending: {column_name}")
    TR_SORTED_ASC = QT_TR_NOOP("Sorted ascending by column: {column_name}")
    TR_SORT_OPERATION_DESC = QT_TR_NOOP("sort descending")
    TR_SORTING_COLUMN_DESC = QT_TR_NOOP("Sorting descending: {column_name}")
    TR_SORTED_DESC = QT_TR_NOOP("Sorted descending by column: {column_name}")

    TR_FAILURE = QT_TR_NOOP("Failure")
    TR_COULD_NOT_PERFORM = QT_TR_NOOP("Could not perform the operation:\n{error}")

    # ------------------------------------------------------------------
    # i18n helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tr(text: str) -> str:
        return tr("ResultTabHeaderSortActions", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: object) -> str:
        return tr_fmt("ResultTabHeaderSortActions", text, **kwargs)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    __slots__ = (
        "__weakref__",
        "_apply_new_dataframe",
        "_async_ops",
        "_dialogs",
        "_logger",
        "_parent",
        "_resolve_df_col_series",
    )

    def __init__(
        self,
        *,
        parent: QWidget,
        dialogs: DialogService,
        logger: logging.Logger,
        async_ops: AsyncOperationController,
        resolve_df_col_series: Callable[
            [QTableView, int],
            tuple[bool, pd.DataFrame | None, str | None, pd.Series | None],
        ],
        apply_new_dataframe: Callable[
            [QTableView, pd.DataFrame, str],
            None,
        ],
    ) -> None:
        """Initialize ResultTabHeaderSortActions with dependencies.

        Args:
        parent (QWidget): Parent widget for dialogs.
        dialogs (DialogService, optional): Service for showing dialogs. Defaults to QtDialogService.
        logger (logging.Logger, optional): Logger for logging errors. Defaults to applogger.ui logger.
        async_ops (AsyncOperationController): Controller for managing async operations.
        resolve_df_col_series (Callable): Function to resolve DataFrame, column, and series.
        apply_new_dataframe (Callable): Function to apply new DataFrame to view.
        """
        self._parent = parent
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._async_ops = async_ops
        self._resolve_df_col_series = resolve_df_col_series
        self._apply_new_dataframe = apply_new_dataframe

    def sort_ascending(self, view: QTableView, column: int) -> None:
        """Sort rows in ascending order by column.

        Args:
            view (QTableView): The table view containing the data.
            column (int): The column index to sort by.

        Returns:
            None: This method does not return a value.
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)

        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        from expo_jbm329.services.data_operations.columns import (
            sort_dataframe,
        )

        def _work(*, progress_cb: object=None, cancel_cb: object=None, **_: object) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return sort_dataframe(
                safe_df,
                safe_col,
                ascending=True,
            )

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: object) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_SORTED_ASC,
                    column_name=safe_col,
                ),
            )

            self._logger.info(
                "Sorted ascending by column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_SORTING_COLUMN_ASC,
                column_name=safe_col,
            ),
            scope=f"sort:ascending:{safe_col}",
            operation_name=self._tr(
                self.TR_SORT_OPERATION_ASC,
            ),
            corr_id=corr_id,
        )

    # ==================================================================
    # Sort descending
    # ==================================================================

    def sort_descending(self, view: QTableView, column: int) -> None:
        """Sort rows in descending order by column.

        Args:
            view (QTableView): The table view containing the data.
            column (int): The column index to sort by.

        Returns:
            None: This method does not return a value.
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)

        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        from expo_jbm329.services.data_operations.columns import (
            sort_dataframe,
        )

        def _work(*, progress_cb: object=None, cancel_cb: object=None, **_: object) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return sort_dataframe(
                safe_df,
                safe_col,
                ascending=False,
            )

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: object) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_SORTED_DESC,
                    column_name=safe_col,
                ),
            )

            self._logger.info(
                "Sorted descending by column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_SORTING_COLUMN_DESC,
                column_name=safe_col,
            ),
            scope=f"sort:descending:{safe_col}",
            operation_name=self._tr(
                self.TR_SORT_OPERATION_DESC,
            ),
            corr_id=corr_id,
        )
