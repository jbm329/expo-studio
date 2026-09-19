"""Header (column) actions for result tabs.

This module contains column-header actions related to column structure:
- split a column into multiple columns
- merge multiple columns into a single column
- rename a column
- remove a column

All dependencies are injected explicitly.
No dependency on ResultTabManager exists.
"""

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


class ResultTabHeaderColumnActions:
    """Header (column) split & merge actions with explicit dependency injection."""

    # ------------------------------------------------------------------
    # i18n markers (pylupdate6-visible)
    # ------------------------------------------------------------------

    # Split
    TR_SPLIT_OPERATION = QT_TR_NOOP("split column")
    TR_SPLIT_COLUMN = QT_TR_NOOP("Split column")
    TR_SPLITTING_COLUMN = QT_TR_NOOP("Splitting column: {column_name}")
    TR_SPLIT_COLUMN_BY = QT_TR_NOOP("Split '{column_name}' by:")
    TR_SPLIT_INTO_N_COLUMNS = QT_TR_NOOP("Split column '{column_name}' into {count} columns")
    TR_INVALID_SPLIT = QT_TR_NOOP("Invalid split")
    TR_SPLIT_RESULTED_IN_NO_NEW_COLUMNS = QT_TR_NOOP("The split did not produce any new columns.")
    TR_SPLIT_COLUMN_DONE = QT_TR_NOOP("Split column: {column_name} ({original})")

    # Merge
    TR_MERGE_OPERATION = QT_TR_NOOP("merge columns")
    TR_MERGE_COLUMNS = QT_TR_NOOP("Merge columns")
    TR_MERGING_COLUMNS = QT_TR_NOOP("Merging columns: {columns_merged}")
    TR_SELECT_COLUMNS_TO_MERGE = QT_TR_NOOP("Select columns to merge:")
    TR_MERGED_COLUMNS = QT_TR_NOOP("Merged columns into '{column_name}'")
    TR_NEED_AT_LEAST_TWO_COLUMNS = QT_TR_NOOP("You must select at least two columns to merge.")
    TR_KEPT_ORIGINAL = QT_TR_NOOP("kept original")
    TR_REMOVED_ORIGINAL = QT_TR_NOOP("removed original")
    TR_SELECT_TWO = QT_TR_NOOP("Select at least two columns.")
    TR_MERGE_COLUMNS_DONE = QT_TR_NOOP("Merged columns '{columns_merged}' → '{new_name}' ({original})")

    # Rename
    TR_RENAME_OPERATION = QT_TR_NOOP("rename column")
    TR_RENAME_COLUMN = QT_TR_NOOP("Rename column")
    TR_RENAMING_COLUMN = QT_TR_NOOP("Renaming column: {column_name} → {new_name}")
    TR_NEW_NAME_FOR_COLUMN = QT_TR_NOOP("New name for '{column_name}':")
    TR_NAME_TAKEN = QT_TR_NOOP("Name taken")
    TR_NAME_ALREADY_EXISTS = QT_TR_NOOP("A column with the name '{column_name}' already exists.")
    TR_RENAMED_COLUMN = QT_TR_NOOP("Renamed column '{old_name}' → '{new_name}'")

    # Remove
    TR_REMOVE_OPERATION = QT_TR_NOOP("remove column")
    TR_REMOVE_COLUMN = QT_TR_NOOP("Remove column")
    TR_REMOVING_COLUMN = QT_TR_NOOP("Removing column: {column_name}")
    TR_COLUMN_AND_NAME = QT_TR_NOOP("Remove column: {column_name}")
    TR_REMOVED_COLUMN = QT_TR_NOOP("Removed column: {column_name}")

    # ------------------------------------------------------------------
    # i18n helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tr(text: str) -> str:
        return tr("ResultTabHeaderColumnActions", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: object) -> str:
        return tr_fmt("ResultTabHeaderColumnActions", text, **kwargs)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    __slots__ = (
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
        """Initialize ResultTabHeaderColumnActions with dependencies.

        Args:
            parent: The parent widget for dialogs and logging.
            dialogs: Service for showing dialogs, defaults to QtDialogService.
            logger: Logger for logging, defaults to applogger.ui logger.
            async_ops: Controller for managing async operations.
            resolve_df_col_series: Callable to resolve dataframe, column, and series.
            apply_new_dataframe: Callable to apply new dataframe to view.
        """
        self._parent = parent
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._async_ops = async_ops
        self._resolve_df_col_series = resolve_df_col_series
        self._apply_new_dataframe = apply_new_dataframe

    # ==================================================================
    # Split column
    # ==================================================================

    def split_column(self, view: QTableView, column: int) -> None:
        """Split a single column into multiple columns.

        Args:
            view: The QTableView containing the data.
            column: The index of the column to split.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        opts = self._dialogs.prompt_split_column(
            parent=self._parent,
            title=self._tr(self.TR_SPLIT_COLUMN),
            column=col or "",
            default_delimiter="-",
            default_keep_original=True,
            default_mode="first",
        )

        if not opts.get("ok", False):
            return

        delimiter: str | None = opts.get("delimiter")
        mode = opts.get("mode", "first")
        keep_original = bool(opts.get("keep_original", True))

        self._logger.debug(
            "ResultTabHeaderColumnActions: split requested for column '%s' on delimiter '%s'.",
            col,
            delimiter,
        )

        if not delimiter:
            return

        safe_df = df
        safe_col = col
        safe_delimiter = delimiter

        from expo_jbm329.services.data_operations.columns import split_column

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return split_column(
                safe_df,
                safe_col,
                delimiter=safe_delimiter,
                mode=mode,
                keep_original=keep_original,
            )

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_SPLIT_INTO_N_COLUMNS,
                    column_name=safe_col,
                    count="two",
                ),
            )

            self._logger.info("Column '%s' is split (corr=%s).", safe_col, corr_id)

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_SPLITTING_COLUMN,
                column_name=safe_col,
            ),
            scope=f"split:{safe_col}",
            operation_name=self._tr(self.TR_SPLIT_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Merge columns
    # ==================================================================

    def merge_columns(self, view: QTableView, column: int) -> None:
        """Merge multiple columns into a single column."""
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        all_columns = [str(c) for c in df.columns]

        res = self._dialogs.prompt_merge_columns(
            parent=self._parent,
            title=self._tr(self.TR_MERGE_COLUMNS),
            all_columns=all_columns,
            default_columns=[col],
            default_delimiter=" ",
            default_new_name=col,
            default_keep_original=True,
        )
        if not res["ok"]:
            return

        safe_df = df

        from expo_jbm329.services.data_operations.columns import join_columns

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return join_columns(
                safe_df,
                res["columns"],
                delimiter=res["delimiter"],
                new_name=res["new_name"],
                keep_original=res["keep_original"],
            )

        cols_merged = ", ".join(res["columns"])
        original = self._tr(self.TR_KEPT_ORIGINAL) if res["keep_original"] else self._tr(self.TR_REMOVED_ORIGINAL)

        new_name = res["new_name"]

        self._logger.debug(
            "ResultTabHeaderColumnActions: merge requested for columns '%s -> %s'.", cols_merged, new_name
        )

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_MERGE_COLUMNS_DONE,
                    columns_merged=cols_merged,
                    new_name=new_name,
                    original=original,
                ),
            )

            self._logger.info("Merged columns: '%s' -> '%s' (corr=%s).", cols_merged, new_name, corr_id)

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_MERGING_COLUMNS,
                columns_merged=cols_merged,
            ),
            scope=f"merge:{new_name}",
            operation_name=self._tr(self.TR_MERGE_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Rename column
    # ==================================================================

    def rename_column(self, view: QTableView, column: int) -> None:
        """Rename a column.

        Prompts the user for a new column name and applies the rename
        operation using the service layer.

        Args:
            view: The QTableView instance where the column is located.
            column: The index of the column to be renamed.

        Returns:
            None
        """
        ok, df, col_name, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col_name is None:
            return

        new_name, ok = self._dialogs.prompt_text(
            parent=self._parent,
            title=self._tr(self.TR_RENAME_COLUMN),
            label=self._tr_fmt(
                self.TR_NEW_NAME_FOR_COLUMN,
                column_name=col_name,
            ),
            default=col_name,
        )
        if not ok:
            return

        safe_df = df
        safe_col = col_name

        self._logger.debug(
            "ResultTabHeaderColumnActions: rename requested for column '%s'.",
            safe_col,
        )

        new_name = (new_name or "").strip()
        if not new_name or new_name == safe_col:
            return

        from expo_jbm329.services.data_operations.columns import rename_column

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return rename_column(safe_df, safe_col, new_name)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_RENAMED_COLUMN,
                    old_name=safe_col,
                    new_name=new_name,
                ),
            )

            self._logger.info(
                "ResultTabHeaderColumnActions: column '%s' renamed to '%s' (corr=%s).",
                safe_col,
                new_name,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_RENAMING_COLUMN, column_name=col_name, new_name=new_name),
            scope=f"rename:{safe_col}",
            operation_name=self._tr(self.TR_RENAME_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Remove column
    # ==================================================================

    def remove_column(self, view: QTableView, column: int) -> None:
        """Remove a column from the DataFrame.

        Prompts the user for confirmation and removes the column using
        the service layer.

        Args:
            view: The QTableView instance where the column is located.
            column: The index of the column to be removed.

        Returns:
            None
        """
        ok, df, col_name, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col_name is None:
            return

        self._logger.debug(
            "ResultTabHeaderColumnActions: remove requested for column '%s'.",
            col_name,
        )

        confirm = self._dialogs.confirm_delete(
            parent=self._parent,
            title=self._tr(self.TR_REMOVE_COLUMN),
            name=self._tr_fmt(
                self.TR_COLUMN_AND_NAME,
                column_name=col_name,
            ),
            full_path="",
            size_hint=None,
        )
        if not confirm:
            return

        safe_df = df
        safe_col = col_name

        from expo_jbm329.services.data_operations.columns import safe_drop_column

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None
            return safe_drop_column(safe_df, column)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_REMOVED_COLUMN,
                    column_name=safe_col,
                ),
            )

            self._logger.info("ResultTabHeaderColumnActions: column '%s' removed (corr=%s).", col_name, corr_id)

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_REMOVING_COLUMN, column_name=col_name),
            scope=f"remove:{safe_col}",
            operation_name=self._tr(self.TR_REMOVE_OPERATION),
            corr_id=corr_id,
        )
