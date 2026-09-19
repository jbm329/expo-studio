"""Cell-based actions for result tab tables.

This module contains all operations triggered from the *cell context menu*
(right-click on a cell), such as value replacement.

Design principles:
------------------
• No direct access to ResultTabManager internals
• All UI interaction handled here (dialogs, messages)
• Data mutation delegated to service layer
• Defensive programming (None-guards, type checks)
• Qt-safe and linter-clean
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

import pandas as pd
from PyQt6.QtCore import QT_TR_NOOP

from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.utils.i18n_utils import tr, tr_fmt

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QTableView, QWidget

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )


class ResultTabCellActions:
    """Cell-level actions for a result tab QTableView."""

    # --- i18n markers (pylupdate6-visible) -----------------------------

    # Filter
    TR_KEEP_ROWS_OPERATION = QT_TR_NOOP("filter keep rows")
    TR_KEEP_ROWS = QT_TR_NOOP("Keep rows")
    TR_KEEPING_ROWS_WHERE = QT_TR_NOOP("Keeping rows where '{column_name}' = '{value}'")
    TR_KEPT_ROWS_WHERE = QT_TR_NOOP("Kept rows where '{column_name}' = '{value}'")

    TR_REMOVE_ROWS_OPERATION = QT_TR_NOOP("filter remove rows")
    TR_REMOVE_ROWS = QT_TR_NOOP("Remove rows")
    TR_REMOVING_ROWS_WHERE = QT_TR_NOOP("Removing rows where '{column_name}' = '{value}'")
    TR_REMOVED_ROWS_WHERE = QT_TR_NOOP("Removed rows where '{column_name}' = '{value}'")

    # Replace
    TR_REPLACE_VALUE = QT_TR_NOOP("Replace value")
    TR_REPLACING_VALUES = QT_TR_NOOP("Replacing '{old_value}' → '{new_value}' in '{column_name}'")

    TR_REPLACE_ALL_OPERATION = QT_TR_NOOP("replace all values")
    TR_REPLACED_ALL_VALUES = QT_TR_NOOP("Replaced all '{old_value}' → '{new_value}' in column: {column_name}")

    TR_REPLACE_SINGLE_OPERATION = QT_TR_NOOP("replace single cell value")
    TR_REPLACED_SINGLE_VALUE = QT_TR_NOOP("Replaced '{old_value}' → '{new_value}' on row {row} in '{column_name}'")

    # ------------------------------------------------------------------
    @staticmethod
    def _tr(text: str) -> str:
        return tr("ResultTabCellActions", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: object) -> str:
        return tr_fmt("ResultTabCellActions", text, **kwargs)

    # ------------------------------------------------------------------
    __slots__ = (
        "_apply_new_dataframe",
        "_async_ops",
        "_dialogs",
        "_logger",
        "_parent",
    )

    def __init__(
        self,
        *,
        parent: QWidget,
        dialogs: DialogService,
        logger: logging.Logger,
        async_ops: AsyncOperationController,
        apply_new_dataframe: Callable[
            [QTableView, pd.DataFrame, str],
            None,
        ],
    ) -> None:
        """Initialize cell actions.

        Args:
            parent: Parent widget for dialogs.
            dialogs: DialogService instance.
            logger: Logger instance.
            async_ops: Controller instance managing async operations.
            apply_new_dataframe: Callback to apply a new DataFrame to a view.
                                  Signature: (view, new_df, status_text)
        """
        self._parent = parent
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._async_ops = async_ops
        self._apply_new_dataframe = apply_new_dataframe

    # ==================================================================
    # INTERNAL HELPERS
    # ==================================================================

    def _validate(
        self,
        view: QTableView,
        df: pd.DataFrame,
        column_name: str,
    ) -> bool:
        """Common defensive validation for cell actions.

        Args:
            view: The QTableView instance.
            df: The DataFrame to operate on.
            column_name: The name of the column to validate.

        Returns:
            True if validation passes, False otherwise.
        """
        _ = self._logger
        if view is None:
            return False
        if not isinstance(df, pd.DataFrame):
            return False
        if not isinstance(column_name, str):
            return False
        return column_name in df.columns

    # ==================================================================
    # FILTER ACTIONS
    # ==================================================================

    def filter_keep(
        self,
        view: QTableView,
        df: pd.DataFrame,
        *,
        column_name: str,
        raw_value: object,
    ) -> None:
        """Keep rows where column equals the given cell value.

        Args:
            view: The QTableView instance.
            df: The DataFrame to operate on.
            column_name: The name of the column to filter by.
            raw_value: The value to filter for.

        Returns:
            None
        """
        if not self._validate(view, df, column_name):
            return

        self._logger.debug(
            "ResultTabCellActions: filter keep cell value requested for column '%s'.",
            column_name,
        )

        from expo_jbm329.services.data_operations.filter import (
            filter_equals,
            filter_isna,
        )

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            if bool(pd.isna([raw_value])[0]):
                return filter_isna(df, column_name)

            return filter_equals(df, column_name, raw_value)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_KEPT_ROWS_WHERE, column_name=column_name, value=raw_value),
            )

            self._logger.info(
                "ResultTabCellActions: kept rows where '%s' = '%s' (corr=%s).",
                column_name,
                raw_value,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_KEEPING_ROWS_WHERE, column_name=column_name, value=raw_value),
            scope=f"filter_keep:{column_name}",
            operation_name=self._tr(self.TR_KEEP_ROWS_OPERATION),
            corr_id=corr_id,
        )

    def filter_remove(
        self,
        view: QTableView,
        df: pd.DataFrame,
        *,
        column_name: str,
        raw_value: object,
    ) -> None:
        """Remove rows where column equals the given cell value.

        Args:
            view: The QTableView instance.
            df: The DataFrame to operate on.
            column_name: The name of the column to filter.
            raw_value: The value to filter by.

        Returns:
            None
        """
        if not self._validate(view, df, column_name):
            return

        self._logger.debug(
            "ResultTabCellActions: filter remove cell value requested for column '%s'.",
            column_name,
        )

        from expo_jbm329.services.data_operations.filter import (
            filter_not_equals,
            filter_notna,
        )

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            if bool(pd.isna([raw_value])[0]):
                return filter_notna(df, column_name)

            return filter_not_equals(df, column_name, raw_value)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_REMOVED_ROWS_WHERE, column_name=column_name, value=raw_value),
            )

            self._logger.info(
                "ResultTabCellActions: removed rows where '%s' = '%s' (corr=%s).",
                column_name,
                raw_value,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_REMOVING_ROWS_WHERE, column_name=column_name, value=raw_value),
            scope=f"filter_remove:{column_name}",
            operation_name=self._tr(self.TR_REMOVE_ROWS_OPERATION),
            corr_id=corr_id,
        )

    # ------------------------------------------------------------------
    # REPLACE ACTIONS
    # ------------------------------------------------------------------
    def replace_value(
        self,
        view: QTableView,
        df: pd.DataFrame,
        *,
        row_index: int,
        column_name: str,
        raw_value: object,
    ) -> None:
        """Replace a value in a cell or column.

        Supports:
          • replacing only the selected cell
          • replacing all matching values in the column

        Args:
            view: The QTableView instance.
            df: The DataFrame to operate on.
            row_index: The index of the row to replace.
            column_name: The name of the column to replace.
            raw_value: The new value to replace with.

        Returns:
            None
        """
        # ------------------------------
        # Defensive guards
        # ------------------------------
        if view is None:
            return
        if not isinstance(df, pd.DataFrame):
            return
        if not isinstance(column_name, str):
            return
        if row_index < 0 or row_index >= len(df):
            return

        self._logger.debug(
            "ResultTabCellActions: replace value requested for column '%s' (row=%s, value=%s).",
            column_name,
            row_index,
            raw_value,
        )

        # ------------------------------
        # Prompt user
        # ------------------------------
        opts = self._dialogs.prompt_value_replace(
            parent=self._parent,
            title=self._tr(self.TR_REPLACE_VALUE),
            column=column_name,
            current_value=str(raw_value),
            default_new_value="" if bool(pd.isna([raw_value])[0]) else str(raw_value),
            default_replace_all=False,
        )

        if not opts.get("ok", False):
            return

        new_value = opts.get("new_value")
        replace_all = bool(opts.get("replace_all"))

        # ------------------------------
        # Perform operation
        # ------------------------------
        from expo_jbm329.services.data_operations.text import (
            replace_values,
            set_cell_value_text,
        )

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            if replace_all:
                return replace_values(
                    df,
                    column_name,
                    pattern=raw_value,
                    replacement=new_value,
                    regex=False,
                )

            return set_cell_value_text(
                df,
                column_name,
                row_index,
                new_value,
            )

        corr_id = uuid.uuid4().hex

        old_value_str = str(raw_value)
        new_value_str = str(new_value)

        if replace_all:
            operation = self._tr(self.TR_REPLACE_ALL_OPERATION)

            status = self._tr_fmt(
                self.TR_REPLACED_ALL_VALUES,
                old_value=old_value_str,
                new_value=new_value_str,
                column_name=column_name,
            )
        else:
            operation = self._tr(self.TR_REPLACE_SINGLE_OPERATION)

            status = self._tr_fmt(
                self.TR_REPLACED_SINGLE_VALUE,
                old_value=old_value_str,
                new_value=new_value_str,
                row=str(row_index + 1),
                column_name=column_name,
            )

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                status,
            )
            if replace_all:
                self._logger.info(
                    "ResultTabCellActions: replaced all '%s' -> '%s' in column '%s' (corr=%s).",
                    old_value_str,
                    new_value_str,
                    column_name,
                    corr_id,
                )
            else:
                self._logger.info(
                    "ResultTabCellActions: replaced '%s' -> '%s' in '%s' at row %s (corr=%s).",
                    old_value_str,
                    new_value_str,
                    column_name,
                    str(row_index + 1),
                    corr_id,
                )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_REPLACING_VALUES, old_value=old_value_str, new_value=new_value_str, column_name=column_name
            ),
            scope=f"replace_value:{column_name}",
            operation_name=operation,
            corr_id=corr_id,
        )
