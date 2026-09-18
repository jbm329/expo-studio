"""Header (column) filter actions for result tabs.

This module contains column-header actions related to row filtering:
- equals / not equals
- contains
- isna / notna
- numeric / datetime comparison
- numeric / datetime between

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


class ResultTabHeaderFilterActions:
    """Header (column) filter actions with explicit dependency injection."""

    # ------------------------------------------------------------------
    # i18n markers (pylupdate6-visible)
    # ------------------------------------------------------------------

    TR_FAILURE = QT_TR_NOOP("Failure")
    TR_COULD_NOT_PERFORM = QT_TR_NOOP("Could not perform the operation:\n{error}")

    # Equals / contains
    TR_FILTER_EQUAL_OPERATION = QT_TR_NOOP("filter equal")
    TR_FILTER_TITLE_EQUAL_TO = QT_TR_NOOP("Filter column equal to")
    TR_FILTERING_COLUMN_EQUAL_TO = QT_TR_NOOP("Filtering column '{column_name}' equal to '{value}'")
    TR_SELECT_FILTER_VALUE_IN_COLUMN = QT_TR_NOOP("Select value for '{column_name}':")
    TR_FILTERED_ROWS_WHERE_COLUMN_IS_VALUE = QT_TR_NOOP("Filtered rows where '{column_name}' = '{value}'")
    TR_FILTER_CONTAINS_OPERATION = QT_TR_NOOP("filter contains")
    TR_FILTER_TITLE_CONTAINS = QT_TR_NOOP("Filter column contains")
    TR_FILTERING_COLUMN_CONTAINS = QT_TR_NOOP("Filtering column '{column_name}' contains '{value}'")
    TR_SELECT_FILTER_SEARCH_STRING_IN_COLUMN = QT_TR_NOOP("Select search string for '{column_name}':")
    TR_CASE_SENSITIVITY = QT_TR_NOOP("Case sensitivity")
    TR_MATCH_CASE = QT_TR_NOOP("Match case?")
    TR_CASE_SENSITIVE = QT_TR_NOOP("Yes (case sensitive)")
    TR_CASE_INSENSITIVE = QT_TR_NOOP("No (case insensitive)")
    TR_FILTERED_ROWS_WHERE_COLUMN_CONTAINS_VALUE = QT_TR_NOOP("Filtered rows where '{column_name}' contains '{value}'")

    # NA
    TR_FILTER_NA_OPERATION = QT_TR_NOOP("filter NA")
    TR_FILTERING_COLUMN_IS_NA = QT_TR_NOOP("Filtering column '{column_name}' is empty/NA")
    TR_FILTERED_ROWS_WHERE_COLUMN_IS_NA = QT_TR_NOOP("Filtered rows where '{column_name}' is empty/NA")
    TR_FILTER_NOT_NA_OPERATION = QT_TR_NOOP("filter not NA")
    TR_FILTERING_COLUMN_IS_NOT_NA = QT_TR_NOOP("Filtering column '{column_name}' is not empty/NA")
    TR_FILTERED_ROWS_WHERE_COLUMN_IS_NOT_NA = QT_TR_NOOP("Filtered rows where '{column_name}' is not empty/NA")

    # Compare
    TR_FILTER_COMPARE_OPERATION = QT_TR_NOOP("filter compare")
    TR_FILTERING_COLUMN_COMPARED_TO = QT_TR_NOOP("Filtering column '{column_name}' {operator} '{value}'")
    TR_FILTER_TITLE_COMPARED_TO = QT_TR_NOOP("Filter column compared to")
    TR_OPERATOR_FOR_COLUMN = QT_TR_NOOP("Operator for column '{column_name}':")
    TR_VALUE_FOR_COLUMN = QT_TR_NOOP("Value for column '{column_name}':")
    TR_NOT_SUPPORTED_DATATYPE_TITLE = QT_TR_NOOP("Datatype not supported")
    TR_NOT_SUPPORTED_DATATYPE_TEXT = QT_TR_NOOP("The column '{column_name}' does not support range filtering")
    TR_FILTERED_ROWS_WHERE_COLUMN_COMPARED_TO = QT_TR_NOOP("Filtered rows where '{column_name}' {operator} '{value}'")

    # Between
    TR_FILTER_BETWEEN_OPERATION = QT_TR_NOOP("filter between")
    TR_FILTER_TITLE_BETWEEN = QT_TR_NOOP("Filter column between")
    TR_FILTERING_COLUMN_BETWEEN = QT_TR_NOOP("Filtering column '{column_name}' between '{low}' and '{high}'")
    TR_LOWER_LIMIT_FOR_COLUMN = QT_TR_NOOP("Lower limit for '{column_name}':")
    TR_UPPER_LIMIT_FOR_COLUMN = QT_TR_NOOP("Upper limit for '{column_name}':")
    TR_START_LIMIT_FOR_COLUMN = QT_TR_NOOP("Start for '{column_name}':")
    TR_END_LIMIT_FOR_COLUMN = QT_TR_NOOP("End for '{column_name}':")
    TR_INVALID_INTERVAL_TITLE = QT_TR_NOOP("Invalid interval")
    TR_INVALID_INTERVAL_TEXT = QT_TR_NOOP("Upper limit has to be greater than or equal to lower limit.")
    TR_BOTH_LIMITS = QT_TR_NOOP("both limits")
    TR_ONLY_LOWER_LIMIT = QT_TR_NOOP("only lower limit")
    TR_ONLY_UPPER_LIMIT = QT_TR_NOOP("only upper limit")
    TR_NO_LIMITS = QT_TR_NOOP("no limits")
    TR_FILTERED_ROWS_WHERE_COLUMN_LIMITS = QT_TR_NOOP(
        "Filtered rows where '{column_name}' between '{low}' and '{high}' ({limits})"
    )

    # ------------------------------------------------------------------
    # i18n helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tr(text: str) -> str:
        return tr("ResultTabHeaderFilterActions", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("ResultTabHeaderFilterActions", text, **kwargs)

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
        """Initialize the ResultTabHeaderFilterActions with dependencies.

        Args:
            parent (QWidget): The parent widget for dialogs and logging.
            dialogs (DialogService, optional): Service for showing dialogs. Defaults to QtDialogService.
            logger (logging.Logger, optional): Logger for logging errors. Defaults to applogger.ui logger.
            async_ops (AsyncOperationController): AsyncOperation controller for asynchronous operations.
            resolve_df_col_series (Callable): Function to resolve DataFrame column and series.
            get_series_semantics (Callable): Function to get Series semantics.
            apply_new_dataframe (Callable): Function to apply a new DataFrame to the view.
        """
        self._parent = parent
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._async_ops = async_ops
        self._resolve_df_col_series = resolve_df_col_series
        self._get_series_semantics = get_series_semantics
        self._apply_new_dataframe = apply_new_dataframe

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fail(self, exc: Exception) -> None:
        """Log and show a critical error dialog."""
        self._logger.error(
            "ResultTabHeaderFilterActions: operation failed: %s",
            exc,
        )
        self._dialogs.critical(
            parent=self._parent,
            title=self._tr(self.TR_FAILURE),
            text=self._tr_fmt(self.TR_COULD_NOT_PERFORM, error=str(exc)),
        )

    # ==================================================================
    # Filter equals
    # ==================================================================

    def filter_equals(self, view: QTableView, column: int) -> None:
        """Filter rows where column equals a user-provided value."""
        ok, df, col, _ = self._resolve_df_col_series(view, column)

        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        sem = self._get_series_semantics(view, column)
        if sem is None:
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_NOT_SUPPORTED_DATATYPE_TITLE),
                text=self._tr_fmt(
                    self.TR_NOT_SUPPORTED_DATATYPE_TEXT,
                    column_name=safe_col,
                ),
            )
            return

        # Defaults
        case_sensitive = True
        value = None

        try:
            # --------------------------------------------------
            # Boolean
            # --------------------------------------------------
            if sem.semantic_dtype == "bool":
                choice, ok = self._dialogs.prompt_choice(
                    parent=self._parent,
                    title=self._tr(self.TR_FILTER_TITLE_EQUAL_TO),
                    label=self._tr_fmt(
                        self.TR_SELECT_FILTER_VALUE_IN_COLUMN,
                        column_name=safe_col,
                    ),
                    choices=["False", "True"],
                    default_index=0,
                )
                if not ok:
                    return

                value = choice.lower() == "true"

            # --------------------------------------------------
            # Numeric
            # --------------------------------------------------
            elif sem.semantic_dtype in ("int", "float"):
                value, ok = self._dialogs.prompt_number(
                    parent=self._parent,
                    title=self._tr(self.TR_FILTER_TITLE_EQUAL_TO),
                    label=self._tr_fmt(
                        self.TR_SELECT_FILTER_VALUE_IN_COLUMN,
                        column_name=safe_col,
                    ),
                    default=None,
                    semantics=sem,
                )
                if not ok:
                    return

            # --------------------------------------------------
            # Datetime
            # --------------------------------------------------
            elif sem.semantic_dtype == "datetime":
                value, ok = self._dialogs.prompt_datetime(
                    parent=self._parent,
                    title=self._tr(self.TR_FILTER_TITLE_EQUAL_TO),
                    label=self._tr_fmt(
                        self.TR_SELECT_FILTER_VALUE_IN_COLUMN,
                        column_name=safe_col,
                    ),
                    default=None,
                    semantics=sem,
                )
                if not ok:
                    return

            # --------------------------------------------------
            # Text / category / fallback
            # --------------------------------------------------
            else:
                opts = self._dialogs.prompt_filter_match(
                    parent=self._parent,
                    title=self._tr(self.TR_FILTER_TITLE_EQUAL_TO),
                    label=self._tr_fmt(
                        self.TR_SELECT_FILTER_VALUE_IN_COLUMN,
                        column_name=safe_col,
                    ),
                    default_value="",
                )

                if not opts["ok"] or not opts["value"]:
                    return

                value = opts["value"]
                case_sensitive = opts["case_sensitive"]

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
            "ResultTabHeaderFilterActions: filter equal requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.filter import filter_equals

        def _work(*, progress_cb=None, cancel_cb=None, **_):
            if cancel_cb and cancel_cb():
                return None

            return filter_equals(
                safe_df,
                safe_col,
                value,
                case=case_sensitive,
            )

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df):
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_FILTERED_ROWS_WHERE_COLUMN_IS_VALUE,
                    column_name=safe_col,
                    value=str(value),
                ),
            )

            self._logger.info(
                "ResultTabHeaderFilterActions: filtered rows where column '%s' = '%s' (corr=%s).",
                safe_col,
                value,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_FILTERING_COLUMN_EQUAL_TO,
                column_name=safe_col,
                value=str(value),
            ),
            scope=f"filter_equal:{safe_col}",
            operation_name=self._tr(self.TR_FILTER_EQUAL_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Filter contains
    # ==================================================================

    def filter_contains(self, view: QTableView, column: int) -> None:
        """Filter rows where column contains a text match."""
        ok, df, col, _ = self._resolve_df_col_series(view, column)

        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        opts = self._dialogs.prompt_filter_match(
            parent=self._parent,
            title=self._tr(self.TR_FILTER_TITLE_CONTAINS),
            label=self._tr_fmt(
                self.TR_SELECT_FILTER_SEARCH_STRING_IN_COLUMN,
                column_name=safe_col,
            ),
            default_value="",
        )
        if not opts["ok"] or not opts["value"]:
            return

        value = opts["value"]
        case_sensitive = opts["case_sensitive"]

        self._logger.debug(
            "ResultTabHeaderFilterActions: filter contains requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.filter import filter_contains

        def _work(*, progress_cb=None, cancel_cb=None, **_):
            if cancel_cb and cancel_cb():
                return None

            return filter_contains(
                safe_df,
                safe_col,
                value,
                case=case_sensitive,
            )

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df):
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_FILTERED_ROWS_WHERE_COLUMN_CONTAINS_VALUE,
                    column_name=safe_col,
                    value=value,
                ),
            )

            self._logger.info(
                "ResultTabHeaderFilterActions: filtered rows where column '%s' contains '%s' (corr=%s).",
                safe_col,
                value,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_FILTERING_COLUMN_CONTAINS,
                column_name=safe_col,
                value=value,
            ),
            scope=f"filter_contains:{safe_col}",
            operation_name=self._tr(self.TR_FILTER_CONTAINS_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Filter isna / notna
    # ==================================================================

    def filter_isna(self, view: QTableView, column: int) -> None:
        """Filter rows where column is NA."""
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderFilterActions: filter NA requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.filter import filter_isna

        def _work(*, progress_cb=None, cancel_cb=None, **_):
            if cancel_cb and cancel_cb():
                return None

            return filter_isna(safe_df, safe_col)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df):
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_FILTERED_ROWS_WHERE_COLUMN_IS_NA,
                    column_name=safe_col,
                ),
            )

            self._logger.info(
                "ResultTabHeaderFilterActions: filtered rows where column '%s' is NA (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_FILTERING_COLUMN_IS_NA, column_name=safe_col),
            scope=f"filter_na:{safe_col}",
            operation_name=self._tr(self.TR_FILTER_NA_OPERATION),
            corr_id=corr_id,
        )

    def filter_notna(self, view: QTableView, column: int) -> None:
        """Filter rows where column is not NA."""
        ok, df, col, _ = self._resolve_df_col_series(view, column)

        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderFilterActions: filter not NA requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.filter import filter_notna

        def _work(*, progress_cb=None, cancel_cb=None, **_):
            if cancel_cb and cancel_cb():
                return None

            return filter_notna(safe_df, safe_col)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df):
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_FILTERED_ROWS_WHERE_COLUMN_IS_NOT_NA,
                    column_name=safe_col,
                ),
            )

            self._logger.info(
                "ResultTabHeaderFilterActions: filtered rows where column '%s' is not NA (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_FILTERING_COLUMN_IS_NOT_NA, column_name=safe_col),
            scope=f"filter_not_na:{safe_col}",
            operation_name=self._tr(self.TR_FILTER_NOT_NA_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Filter compare
    # ==================================================================

    def filter_compare(self, view: QTableView, column: int) -> None:
        """Filter rows using a comparison operator."""
        ok, df, col, s = self._resolve_df_col_series(view, column)

        if not ok or df is None or col is None or s is None:
            return

        safe_df = df
        safe_col = col

        sem = self._get_series_semantics(view, column)
        if sem is None:
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_NOT_SUPPORTED_DATATYPE_TITLE),
                text=self._tr_fmt(
                    self.TR_NOT_SUPPORTED_DATATYPE_TEXT,
                    column_name=safe_col,
                ),
            )
            return

        try:
            result = self._dialogs.prompt_compare(
                parent=self._parent,
                title=self._tr(self.TR_FILTER_TITLE_COMPARED_TO),
                label_op=self._tr_fmt(
                    self.TR_OPERATOR_FOR_COLUMN,
                    column_name=safe_col,
                ),
                label_value=self._tr_fmt(
                    self.TR_VALUE_FOR_COLUMN,
                    column_name=safe_col,
                ),
                default_op=">",
                default_value=None,
                semantics=sem,
            )

            if not result.get("ok", False):
                return

            op = result["op"]
            value = result["value"]

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
            "ResultTabHeaderFilterActions: filter compare requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.filter import filter_compare

        def _work(*, progress_cb=None, cancel_cb=None, **_):
            if cancel_cb and cancel_cb():
                return None

            return filter_compare(safe_df, safe_col, op, value)

        from expo_jbm329.services.data_profile.presentation import format_value_for_display

        value_str = format_value_for_display(value, sem)
        corr_id = uuid.uuid4().hex

        def _apply_result(new_df):
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_FILTERED_ROWS_WHERE_COLUMN_COMPARED_TO,
                    column_name=safe_col,
                    operator=op,
                    value=value_str,
                ),
            )

            self._logger.info(
                "ResultTabHeaderFilterActions: filtered rows where column '%s' %s '%s' (corr=%s).",
                safe_col,
                op,
                value_str,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_FILTERING_COLUMN_COMPARED_TO, column_name=safe_col, operator=op, value=value_str
            ),
            scope=f"filter_compare:{safe_col}",
            operation_name=self._tr(self.TR_FILTER_COMPARE_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Filter between
    # ==================================================================

    def filter_between(self, view: QTableView, column: int) -> None:
        """Filter rows where column values fall within a range."""
        ok, df, col, s = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None or s is None:
            return

        safe_df = df
        safe_col = col

        sem = self._get_series_semantics(view, column)
        if sem is None:
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_NOT_SUPPORTED_DATATYPE_TITLE),
                text=self._tr_fmt(
                    self.TR_NOT_SUPPORTED_DATATYPE_TEXT,
                    column_name=safe_col,
                ),
            )
            return

        try:
            result = self._dialogs.prompt_between(
                parent=self._parent,
                title=self._tr(self.TR_FILTER_TITLE_BETWEEN),
                label_low=self._tr_fmt(
                    self.TR_LOWER_LIMIT_FOR_COLUMN,
                    column_name=safe_col,
                ),
                label_high=self._tr_fmt(
                    self.TR_UPPER_LIMIT_FOR_COLUMN,
                    column_name=safe_col,
                ),
                default_low=None,
                default_high=None,
                inclusive_default="both",
                semantics=sem,
            )

            if not result.get("ok", False):
                return

            low = result["low"]
            high = result["high"]
            inclusive = result.get("inclusive", "both")

            if low is not None and high is not None and high < low:
                self._dialogs.warn(
                    parent=self._parent,
                    title=self._tr(self.TR_INVALID_INTERVAL_TITLE),
                    text=self._tr(self.TR_INVALID_INTERVAL_TEXT),
                )
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
            "ResultTabHeaderFilterActions: filter between requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.filter import filter_between

        def _work(*, progress_cb=None, cancel_cb=None, **_):
            if cancel_cb and cancel_cb():
                return None

            return filter_between(safe_df, safe_col, low, high, inclusive=inclusive)

        from expo_jbm329.services.data_profile.presentation import format_value_for_display

        low_str = format_value_for_display(low, sem)
        high_str = format_value_for_display(high, sem)

        incl_text = {
            "both": self._tr(self.TR_BOTH_LIMITS),
            "left": self._tr(self.TR_ONLY_LOWER_LIMIT),
            "right": self._tr(self.TR_ONLY_UPPER_LIMIT),
            "neither": self._tr(self.TR_NO_LIMITS),
        }.get(inclusive, self._tr(self.TR_BOTH_LIMITS))

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df):
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_FILTERED_ROWS_WHERE_COLUMN_LIMITS,
                    column_name=safe_col,
                    low=low_str,
                    high=high_str,
                    limits=incl_text,
                ),
            )

            self._logger.info(
                "ResultTabHeaderFilterActions: filtered rows where column '%s' between '%s' and '%s' "
                "(limits=%s, corr=%s).",
                safe_col,
                low_str,
                high_str,
                inclusive,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(
                self.TR_FILTERING_COLUMN_BETWEEN, column_name=safe_col, low=low_str, high=high_str
            ),
            scope=f"filter_between:{safe_col}",
            operation_name=self._tr(self.TR_FILTER_BETWEEN_OPERATION),
            corr_id=corr_id,
        )
