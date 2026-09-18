"""Header (column) category actions for result tabs.

This module contains column-header actions related to categorical data:
- convert to category
- set category order
- remove unused categories
- rename single category

All dependencies are injected explicitly.
No dependency on ResultTabManager exists.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

import pandas as pd
from PyQt6.QtCore import QT_TR_NOOP
from PyQt6.QtWidgets import QTableView, QWidget

from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.utils.i18n_utils import tr, tr_fmt
from expo_jbm329.workbench.controllers.async_operation_controller import AsyncOperationController


class ResultTabHeaderCategoryActions:
    """Header (column) category actions with explicit dependency injection."""

    # ------------------------------------------------------------------
    # i18n markers (pylupdate6-visible)
    # ------------------------------------------------------------------

    TR_IS_NOT_CATEGORY = QT_TR_NOOP("Not category")
    TR_COLUMN_IS_NOT_CATEGORY = QT_TR_NOOP(
        "Column '{column_name}' is not categorical."
    )

    TR_ORDER_CATEGORIES_OPERATION = QT_TR_NOOP("order categories")
    TR_ORDERING_CATEGORIES = QT_TR_NOOP("Ordering categories: {column_name}")
    TR_ORDER_LABEL_ALPHA = QT_TR_NOOP("alphabetically")
    TR_ORDER_LABEL_FREQ = QT_TR_NOOP("after frequency")
    TR_ORDER_LABEL_PRESERVE = QT_TR_NOOP("preserve order")
    TR_ORDERED = QT_TR_NOOP("ordered")
    TR_UNORDERED = QT_TR_NOOP("unordered")
    TR_ORDER_CATEGORIES = QT_TR_NOOP("Order categories")
    TR_INVALID_ORDER = QT_TR_NOOP("Invalid order")
    TR_ORDER_CAN_NOT_BE_EMPTY = QT_TR_NOOP("Order can not be empty.")
    TR_ORDERED_CATEGORIES_IN_COLUMN = QT_TR_NOOP(
        "Category order set for column: {column_name} ({ordered})"
    )

    TR_REMOVE_UNUSED_CATEGORY_OPERATION = QT_TR_NOOP("remove unused categories")
    TR_REMOVING_UNUSED_CATEGORIES = QT_TR_NOOP("Removing unused categories: {column_name}")
    TR_REMOVED_UNUSED_CATEGORIES = QT_TR_NOOP(
        "Removed unused categories in column: {column_name}"
    )

    TR_RENAME_CATEGORY_OPERATION = QT_TR_NOOP("rename category")
    TR_RENAMING_CATEGORY = QT_TR_NOOP("Renaming category: {column_name}")
    TR_RENAME_CATEGORY = QT_TR_NOOP("Rename category")
    TR_CATEGORY_RENAMED = QT_TR_NOOP("Renamed category: {old_name} → {new_name}")
    TR_NO_CATEGORIES = QT_TR_NOOP("No categories")
    TR_NO_CATEGORIES_TO_RENAME = QT_TR_NOOP(
        "There are no categories to rename."
    )

    # ------------------------------------------------------------------
    # i18n helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tr(text: str) -> str:
        return tr("ResultTabHeaderCategoryActions", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("ResultTabHeaderCategoryActions", text, **kwargs)

    # ------------------------------------------------------------------
    # Init (DI)
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
    ):
        """Initialize ResultTabHeaderCategoryActions with dependencies.

        Args:
            parent (QWidget): Parent widget for dialogs and logging.
            dialogs (DialogService, optional): Service for showing dialogs. Defaults to QtDialogService.
            logger (logging.Logger, optional): Logger for logging. Defaults to applogger.ui logger.
            async_ops (AsyncOperationController): Controller for managing async operations.
            resolve_df_col_series (Callable): Function to resolve DataFrame column and series.
            apply_new_dataframe (Callable): Function to apply new DataFrame to view.
        """
        self._parent = parent
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._async_ops = async_ops
        self._resolve_df_col_series = resolve_df_col_series
        self._apply_new_dataframe = apply_new_dataframe

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_categorical(self, s: pd.Series, col: str) -> bool:
        """Ensure that the series is categorical.

        Args:
            s: Column series.
            col: Column name.

        Returns:
            True if categorical, otherwise False (dialog shown).
        """
        if not isinstance(s.dtype, pd.CategoricalDtype):
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_IS_NOT_CATEGORY),
                text=self._tr_fmt(
                    self.TR_COLUMN_IS_NOT_CATEGORY,
                    column_name=col,
                ),
            )
            return False
        return True

    # ==================================================================
    # Remove unused categories
    # ==================================================================

    def remove_unused(self, view: QTableView, column: int) -> None:
        """Remove unused categories from a categorical column.

        Args:
            view (QTableView): View containing the DataFrame.
            column (int): Column index to process.

        Returns:
            None
        """
        ok, df, col, s = self._resolve_df_col_series(
            view,
            column
        )
        if not ok or df is None or col is None or s is None:
            return

        if not self._ensure_categorical(s, col):
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCategoryActions: remove unused categories requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.category import (
            category_remove_unused,
        )

        def _work(*, progress_cb=None, cancel_cb=None, **_):
            if cancel_cb and cancel_cb():
                return None

            return category_remove_unused(safe_df, safe_col)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df):
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_REMOVED_UNUSED_CATEGORIES,
                    column_name=safe_col,
                ),
            )

            self._logger.info(
                "ResultTabHeaderCategoryActions: removed unused categories in column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_REMOVING_UNUSED_CATEGORIES, column_name=safe_col),
            scope=f"remove_unused_categories:{safe_col}",
            operation_name=self._tr(self.TR_REMOVE_UNUSED_CATEGORY_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Rename single category
    # ==================================================================

    def rename_single(self, view: QTableView, column: int) -> None:
        """Rename a single category value."""
        ok, df, col, s = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None or s is None:
            return

        if not self._ensure_categorical(s, col):
            return

        categories = [str(c) for c in s.cat.categories]
        if not categories:
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_NO_CATEGORIES),
                text=self._tr(self.TR_NO_CATEGORIES_TO_RENAME),
            )
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCategoryActions: rename category requested for column '%s'.",
            safe_col,
        )

        # Default selection: first category (UI allows changing this)
        default_old = categories[0]

        opts = self._dialogs.prompt_category_rename(
            parent=self._parent,
            title=self._tr_fmt(
                self.TR_RENAME_CATEGORY,
                column_name=col,
            ),
            categories=categories,
            default_old_value=default_old,
            default_new_value=default_old,
        )
        if not opts["ok"]:
            return

        old = opts["old"].strip()
        new = opts["new"].strip()

        if not old or not new or old == new:
            return

        from expo_jbm329.services.data_operations.category import (
            category_rename_single,
        )

        def _work(*, progress_cb=None, cancel_cb=None, **_):
            if cancel_cb and cancel_cb():
                return None

            return category_rename_single(safe_df, safe_col, old, new)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df):
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_CATEGORY_RENAMED,
                    old_name=old,
                    new_name=new,
                ),
            )

            self._logger.info(
                "ResultTabHeaderCategoryActions: renamed category '%s' → '%s' in column '%s' (corr=%s).",
                old,
                new,
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_RENAMING_CATEGORY,
                column_name=safe_col,
            ),
            scope=f"rename_category:{safe_col}",
            operation_name=self._tr(self.TR_RENAME_CATEGORY_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Set category order
    # ==================================================================

    def set_order(self, view: QTableView, column: int) -> None:
        """Set explicit order for categories."""
        ok, df, col, s = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None or s is None:
            return

        if not self._ensure_categorical(s, col):
            return

        categories = [str(c) for c in s.cat.categories]
        if not categories:
            self._dialogs.warn(
                parent=self._parent,
                title=self._tr(self.TR_INVALID_ORDER),
                text=self._tr(self.TR_ORDER_CAN_NOT_BE_EMPTY),
            )
            return

        opts = self._dialogs.prompt_category_set_order(
            parent=self._parent,
            title=self._tr_fmt(
                self.TR_ORDER_CATEGORIES,
                column_name=col,
            ),
            default_order_list=categories,
            default_ordered=True,
            default_strict=False,
            default_append_missing_tail=True,
        )
        if not opts["ok"]:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCategoryActions: order categories requested for column '%s'.",
            safe_col,
        )

        order_list = opts["order_list"]
        if not order_list:
            self._dialogs.warn(
                parent=self._parent,
                title=self._tr(self.TR_INVALID_ORDER),
                text=self._tr(self.TR_ORDER_CAN_NOT_BE_EMPTY),
            )
            return

        ordered = opts["ordered"]
        strict = opts["strict"]
        append_missing_tail = opts["append_missing_tail"]
        ordered_label = (
            self._tr(self.TR_ORDERED) if opts["ordered"] else self._tr(self.TR_UNORDERED)
        )

        from expo_jbm329.services.data_operations.category import (
            category_set_order,
        )

        def _work(*, progress_cb=None, cancel_cb=None, **_):
            if cancel_cb and cancel_cb():
                return None

            return category_set_order(
                safe_df,
                safe_col,
                order_list,
                ordered=ordered,
                strict=strict,
                append_missing_tail=append_missing_tail,
            )

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df):
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_ORDERED_CATEGORIES_IN_COLUMN,
                    column_name=safe_col,
                    ordered=ordered_label,
                ),
            )

            self._logger.info(
                "ResultTabHeaderCategoryActions: ordered categories in column '%s' (ordered=%s, corr=%s).",
                safe_col,
                ordered,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_ORDERING_CATEGORIES,
                column_name=safe_col,
            ),
            scope=f"order_categories:{safe_col}",
            operation_name=self._tr(self.TR_ORDER_CATEGORIES_OPERATION),
            corr_id=corr_id,
        )
