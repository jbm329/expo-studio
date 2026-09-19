"""Header (column) fill actions for result tabs.

This module contains column-header actions related to filling missing values:
- mean
- median
- mode
- custom value

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
    from expo_jbm329.services.data_profile.semantics import SeriesSemantics
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )


class ResultTabHeaderFillActions:
    """Header (column) fill actions with explicit dependency injection."""

    # ------------------------------------------------------------------
    # i18n markers (pylupdate6-visible)
    # ------------------------------------------------------------------

    TR_FAILURE = QT_TR_NOOP("Failure")
    TR_COULD_NOT_PERFORM = QT_TR_NOOP("Could not perform the operation:\n{error}")

    TR_NO_NA = QT_TR_NOOP("No missing values")
    TR_NO_NA_IN_COLUMN = QT_TR_NOOP("No missing values in column: {column_name}")

    TR_FILL_NA = QT_TR_NOOP("Fill missing values")
    TR_FILL_NA_IN_COLUMN = QT_TR_NOOP("Select value for column '{column_name}':")

    TR_FILL_NA_MEAN_OPERATION = QT_TR_NOOP("fill missing with mean")
    TR_FILLING_NA_MEAN = QT_TR_NOOP("Filling missing values with mean: {column_name}")
    TR_FILLED_NA_MEAN = QT_TR_NOOP("Filled missing values with mean in column: {column_name}")

    TR_FILL_NA_MEDIAN_OPERATION = QT_TR_NOOP("fill missing with median")
    TR_FILLING_NA_MEDIAN = QT_TR_NOOP("Filling missing values with median: {column_name}")
    TR_FILLED_NA_MEDIAN = QT_TR_NOOP("Filled missing values with median in column: {column_name}")

    TR_FILL_NA_MODE_OPERATION = QT_TR_NOOP("fill missing with mode")
    TR_FILLING_NA_MODE = QT_TR_NOOP("Filling missing values with mode: {column_name}")
    TR_FILLED_NA_MODE = QT_TR_NOOP("Filled missing values with mode in column: {column_name}")

    TR_FILL_NA_CUSTOM_OPERATION = QT_TR_NOOP("fill missing with custom value")
    TR_FILLING_NA_CUSTOM = QT_TR_NOOP("Filling missing values with '{custom_value}' in column: {column_name}")
    TR_FILLED_NA_CUSTOM = QT_TR_NOOP("Filled missing values with '{custom_value}' in column: {column_name}")
    TR_NOT_SUPPORTED_DATATYPE_TITLE = QT_TR_NOOP("Datatype not supported")
    TR_NOT_SUPPORTED_DATATYPE_TEXT = QT_TR_NOOP("Column '{column_name}' can not be filled with a custom value.")

    # ------------------------------------------------------------------
    # i18n helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tr(text: str) -> str:
        return tr("ResultTabHeaderFillActions", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: object) -> str:
        return tr_fmt("ResultTabHeaderFillActions", text, **kwargs)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    __slots__ = (
        "_apply_new_dataframe",
        "_async_ops",
        "_dialogs",
        "_get_series_semantics",
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
        get_series_semantics: Callable[
            [QTableView, int],
            SeriesSemantics | None,
        ],
        apply_new_dataframe: Callable[
            [QTableView, pd.DataFrame, str],
            None,
        ],
    ) -> None:
        """Initialize ResultTabHeaderFillActions with dependencies.

        Args:
            parent: Parent widget for dialogs.
            dialogs: Service for showing dialogs.
            logger: Logger for logging errors.
            async_ops: Controller for managing asynchronous operations.
            resolve_df_col_series: Function to resolve DataFrame and column series.
            get_series_semantics: Function to get Series semantics.
            apply_new_dataframe: Function to apply a new DataFrame to the view.
        """
        self._parent = parent
        self._async_ops = async_ops
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._resolve_df_col_series = resolve_df_col_series
        self._get_series_semantics = get_series_semantics
        self._apply_new_dataframe = apply_new_dataframe

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fail(self, exc: Exception) -> None:
        """Log and show a critical error dialog.

        Args:
            exc: Exception that occurred.
        """
        self._logger.error(
            "ResultTabHeaderFillActions: operation failed: %s",
            exc,
        )
        self._dialogs.critical(
            parent=self._parent,
            title=self._tr(self.TR_FAILURE),
            text=self._tr_fmt(self.TR_COULD_NOT_PERFORM, error=str(exc)),
        )

    def _ensure_missing(self, s: pd.Series, col: str) -> bool:
        """Ensure that the column contains missing values.

        Args:
            s: Column series.
            col: Column name.

        Returns:
            True if missing values exist, otherwise False.
        """
        if not s.isna().any():
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_NO_NA),
                text=self._tr_fmt(
                    self.TR_NO_NA_IN_COLUMN,
                    column_name=col or "",
                ),
            )
            return False
        return True

    # ==================================================================
    # Fill mean
    # ==================================================================

    def fill_mean(self, view: QTableView, column: int) -> None:
        """Fill missing values using the column mean.

        Args:
            view: The QTableView containing the data.
            column: The index of the column to fill.

        Returns:
            None
        """
        ok, df, col, s = self._resolve_df_col_series(view, column)

        if not ok or df is None or col is None or s is None:
            return

        safe_df = df
        safe_col = col
        safe_s = s

        if not self._ensure_missing(safe_s, safe_col):
            return

        self._logger.debug(
            "ResultTabHeaderFillActions: fill NA with mean requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.fill import fillna_mean

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return fillna_mean(safe_df, safe_col)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_FILLED_NA_MEAN, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderFillActions: filled NA with mean in column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_FILLING_NA_MEAN, column_name=safe_col),
            scope=f"fill_na_mean:{safe_col}",
            operation_name=self._tr(self.TR_FILL_NA_MEAN_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Fill median
    # ==================================================================

    def fill_median(self, view: QTableView, column: int) -> None:
        """Fill missing values using the column median.

        Args:
            view: The QTableView containing the data.
            column: The index of the column to fill.

        Returns:
            None
        """
        ok, df, col, s = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None or s is None:
            return

        safe_df = df
        safe_col = col
        safe_s = s

        if not self._ensure_missing(safe_s, safe_col):
            return

        self._logger.debug(
            "ResultTabHeaderFillActions: fill NA with median requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.fill import fillna_median

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return fillna_median(safe_df, safe_col)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_FILLED_NA_MEDIAN, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderFillActions: filled NA with median in column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_FILLING_NA_MEDIAN, column_name=safe_col),
            scope=f"fill_na_median:{safe_col}",
            operation_name=self._tr(self.TR_FILL_NA_MEDIAN_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Fill mode
    # ==================================================================

    def fill_mode(self, view: QTableView, column: int) -> None:
        """Fill missing values using the column mode.

        Args:
            view: The QTableView containing the data.
            column: The index of the column to fill.

        Returns:
            None
        """
        ok, df, col, s = self._resolve_df_col_series(view, column)

        if not ok or df is None or col is None or s is None:
            return

        safe_df = df
        safe_col = col
        safe_s = s

        if not self._ensure_missing(safe_s, safe_col):
            return

        self._logger.debug(
            "ResultTabHeaderFillActions: fill NA with mode requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.fill import fillna_mode

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return fillna_mode(safe_df, safe_col)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_FILLED_NA_MODE, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderFillActions: filled NA with mode in column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_FILLING_NA_MODE, column_name=safe_col),
            scope=f"fill_na_mode:{safe_col}",
            operation_name=self._tr(self.TR_FILL_NA_MODE_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Fill: custom value
    # ==================================================================

    def fill_custom(self, view: QTableView, column: int) -> None:
        """Fill missing values using a user-provided custom value.

        Args:
            view: The QTableView containing the data.
            column: The index of the column to fill.

        Returns:
            None
        """
        ok, df, col, s = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None or s is None:
            return

        safe_df = df
        safe_col = col
        safe_s = s

        if not self._ensure_missing(safe_s, safe_col):
            return

        sem = self._get_series_semantics(view, column)
        if sem is None:
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_NOT_SUPPORTED_DATATYPE_TITLE),
                text=self._tr_fmt(
                    self.TR_NOT_SUPPORTED_DATATYPE_TEXT,
                    column_name=col,
                ),
            )
            return

        typed_value: object
        try:
            # Boolean
            if sem.semantic_dtype == "bool":
                choice, ok = self._dialogs.prompt_choice(
                    parent=self._parent,
                    title=self._tr(self.TR_FILL_NA),
                    label=self._tr_fmt(
                        self.TR_FILL_NA_IN_COLUMN,
                        column_name=col,
                    ),
                    choices=["False", "True"],
                    default_index=0,
                )
                if not ok:
                    return
                typed_value = choice.lower() == "true"

            # Numeric
            elif sem.semantic_dtype in ("int", "float"):
                typed_value, ok = self._dialogs.prompt_number(
                    parent=self._parent,
                    title=self._tr(self.TR_FILL_NA),
                    label=self._tr_fmt(
                        self.TR_FILL_NA_IN_COLUMN,
                        column_name=col,
                    ),
                    default=None,
                    semantics=sem,
                )
                if not ok:
                    return

            # Datetime
            elif sem.semantic_dtype == "datetime":
                typed_value, ok = self._dialogs.prompt_datetime(
                    parent=self._parent,
                    title=self._tr(self.TR_FILL_NA),
                    label=self._tr_fmt(
                        self.TR_FILL_NA_IN_COLUMN,
                        column_name=col,
                    ),
                    default=None,
                    semantics=sem,
                )
                if not ok:
                    return

            # Text / fallback
            else:
                typed_value, ok = self._dialogs.prompt_text(
                    parent=self._parent,
                    title=self._tr(self.TR_FILL_NA),
                    label=self._tr_fmt(
                        self.TR_FILL_NA_IN_COLUMN,
                        column_name=col,
                    ),
                    default="",
                )
                if not ok:
                    return

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
            self._fail(e)
            return

        self._logger.debug(
            "ResultTabHeaderFillActions: fill NA with custom value requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.fill import fillna

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return fillna(safe_df, safe_col, typed_value)

        from expo_jbm329.services.data_profile.presentation import format_value_for_display

        value_str = format_value_for_display(typed_value, sem)
        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_FILLED_NA_CUSTOM,
                    column_name=safe_col,
                    custom_value=value_str,
                ),
            )

            self._logger.info(
                "ResultTabHeaderFillActions: filled NA with '%s' in column '%s' (corr=%s).",
                value_str,
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_FILLING_NA_CUSTOM, column_name=safe_col, custom_value=value_str),
            scope=f"fill_na_custom:{safe_col}",
            operation_name=self._tr(self.TR_FILL_NA_CUSTOM_OPERATION),
            corr_id=corr_id,
        )
