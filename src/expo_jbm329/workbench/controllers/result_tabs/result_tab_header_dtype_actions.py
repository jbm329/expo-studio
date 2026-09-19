"""Header (column) dtype actions for result tabs.

This module contains column-header actions related to dtype conversions:
- to string
- to integer
- to float
- to datetime / date-only
- to boolean
- to category

All dependencies are injected explicitly.
No dependency on ResultTabManager exists.
"""

from __future__ import annotations

import logging
import uuid
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Literal, cast

from PyQt6.QtCore import QT_TR_NOOP

from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.utils.i18n_utils import tr, tr_fmt

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    import pandas as pd
    from PyQt6.QtWidgets import QTableView, QWidget

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )


class ResultTabHeaderDtypeActions:
    """Header (column) dtype conversion actions with explicit dependency injection."""

    # ------------------------------------------------------------------
    # i18n markers (pylupdate6-visible)
    # ------------------------------------------------------------------

    # Generic dtype
    TR_CONVERT_TO_TEXT_OPERATION = QT_TR_NOOP("convert to text")
    TR_CONVERTING_TO_TEXT = QT_TR_NOOP("Converting column to text: {column_name}")
    TR_CONVERTED_TO_TEXT = QT_TR_NOOP("Converted column to text (string): {column_name}")

    # Int
    TR_CONVERT_TO_INT_OPERATION = QT_TR_NOOP("convert to integer")
    TR_CONVERTING_TO_INT = QT_TR_NOOP("Converting to integer: {column_name}")
    TR_CONVERTED_TO_INT = QT_TR_NOOP("Converted column to integer (Int64): {column_name}")

    # Float
    TR_CONVERT_TO_FLOAT_OPERATION = QT_TR_NOOP("convert to float")
    TR_CONVERTING_TO_FLOAT = QT_TR_NOOP("Converting to float: {column_name}")
    TR_CONVERTED_TO_FLOAT = QT_TR_NOOP("Converted column to float (Float64): {column_name}")

    # Datetime
    TR_CONVERT_TO_DATETIME_OPERATION = QT_TR_NOOP("convert to datetime")
    TR_CONVERTING_TO_DATETIME = QT_TR_NOOP("Converting to {mode}: {column_name}")
    TR_CONVERT_TO_DATETIME = QT_TR_NOOP("Convert to datetime")
    TR_DATE = QT_TR_NOOP("date")
    TR_DATETIME = QT_TR_NOOP("datetime")
    TR_CONVERTED_TO_DATETIME = QT_TR_NOOP("Converted column to {mode}: {column_name}")

    # Boolean
    TR_CONVERT_TO_BOOL_OPERATION = QT_TR_NOOP("convert to boolean")
    TR_CONVERTING_TO_BOOL = QT_TR_NOOP("Converting to bool: {column_name}")
    TR_CONVERT_TO_BOOL = QT_TR_NOOP("Convert to bool")
    TR_UNKNOWN_ERROR_LABEL_NA = QT_TR_NOOP("unknown → NA")
    TR_UNKNOWN_ERROR_LABEL_ERROR = QT_TR_NOOP("unknown → error")
    TR_CONVERTED_TO_BOOL = QT_TR_NOOP("Converted column to bool ({error_label}): {column_name}")

    # Category
    TR_CONVERT_TO_CATEGORIES_OPERATION = QT_TR_NOOP("convert to categories")
    TR_CONVERTING_TO_CATEGORIES = QT_TR_NOOP("Converting to categories: {column_name}")
    TR_CONVERT_TO_CATEGORIES = QT_TR_NOOP("Convert to categories")
    TR_ORDER_LABEL_ALPHA = QT_TR_NOOP("alphabetically")
    TR_ORDER_LABEL_FREQ = QT_TR_NOOP("after frequency")
    TR_ORDER_LABEL_PRESERVE = QT_TR_NOOP("preserve order")
    TR_ORDERED = QT_TR_NOOP("ordered")
    TR_UNORDERED = QT_TR_NOOP("unordered")
    TR_CONVERTED_TO_CATEGORIES = QT_TR_NOOP("Converted column to categories: {column_name} ({order}, {ordered})")

    # ------------------------------------------------------------------
    # Order labels
    # ------------------------------------------------------------------

    _CATEGORY_ORDER_LABELS: ClassVar[Mapping[str, str]] = MappingProxyType({
        "alpha": TR_ORDER_LABEL_ALPHA,
        "freq": TR_ORDER_LABEL_FREQ,
        "preserve": TR_ORDER_LABEL_PRESERVE,
    })

    # ------------------------------------------------------------------
    # i18n helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tr(text: str) -> str:
        return tr("ResultTabHeaderDtypeActions", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: object) -> str:
        return tr_fmt("ResultTabHeaderDtypeActions", text, **kwargs)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    __slots__ = (
        "_apply_new_dataframe",
        "_async_ops",
        "_conversion_error_handling",
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
        """Initialize ResultTabHeaderDtypeActions with dependencies.

        Args:
            parent: Parent widget for dialogs.
            dialogs: Service for showing dialogs.
            logger: Logger for logging errors.
            async_ops: Controller for managing async operations.
            resolve_df_col_series: Function to resolve DataFrame, column, and series.
            apply_new_dataframe: Function to apply a new DataFrame to the view.
        """
        self._parent = parent
        self._dialogs = dialogs or QtDialogService()
        self._logger = logger or logging.getLogger("applogger.ui")
        self._async_ops = async_ops
        self._resolve_df_col_series = resolve_df_col_series
        self._apply_new_dataframe = apply_new_dataframe

        self._conversion_error_handling: Literal["coerce", "raise"] = "coerce"

    # ==================================================================
    # To string
    # ==================================================================

    def to_string(self, view: QTableView, column: int) -> None:
        """Convert column to pandas StringDtype.

        Args:
            view: The QTableView instance.
            column: The column index to convert.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderDtypeActions: convert to string requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.convert import to_string

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return to_string(safe_df, safe_col)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_CONVERTED_TO_TEXT, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderDtypeActions: column '%s' converted to string (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_CONVERTING_TO_TEXT, column_name=safe_col),
            scope=f"convert:to_string:{safe_col}",
            operation_name=self._tr(self.TR_CONVERT_TO_TEXT_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # To integer
    # ==================================================================

    def to_integer(self, view: QTableView, column: int) -> None:
        """Convert column to nullable integer dtype (Int64).

        Args:
            view: The QTableView instance.
            column: The column index to convert.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderDtypeActions: convert to int requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.convert import to_integer

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return to_integer(
                safe_df,
                safe_col,
                errors=self._conversion_error_handling,
            )

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_CONVERTED_TO_INT, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderDtypeActions: column '%s' converted to int (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_CONVERTING_TO_INT, column_name=safe_col),
            scope=f"convert:to_int:{safe_col}",
            operation_name=self._tr(self.TR_CONVERT_TO_INT_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # To float
    # ==================================================================

    def to_float(self, view: QTableView, column: int) -> None:
        """Convert column to float dtype.

        Args:
            view: The QTableView instance.
            column: The column index to convert.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderDtypeActions: convert to float requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.convert import to_float

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return to_float(
                safe_df,
                safe_col,
                errors=self._conversion_error_handling,
            )

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_CONVERTED_TO_FLOAT, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderDtypeActions: column '%s' converted to float (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_CONVERTING_TO_FLOAT, column_name=safe_col),
            scope=f"convert:to_float:{safe_col}",
            operation_name=self._tr(self.TR_CONVERT_TO_FLOAT_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # To datetime / date-only
    # ==================================================================

    def to_datetime(self, view: QTableView, column: int) -> None:
        """Convert column to date or datetime using an explicit format choice."""
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        # Prompt user for conversion options
        opts = self._dialogs.prompt_datetime_conversion(
            parent=self._parent,
            title=self._tr(self.TR_CONVERT_TO_DATETIME),
            default_format_key="auto",
            default_target="datetime",
        )
        if not opts["ok"]:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderDtypeActions: convert to datetime (mode=%s) requested for column '%s'.",
            opts["target"],
            safe_col,
        )

        from expo_jbm329.services.data_operations.convert import to_datetime
        from expo_jbm329.services.data_operations.datetime_formats import (
            FORMAT_MAP,
        )

        format_key = opts["format_key"]
        target = opts["target"]

        fmt_cfg = cast("dict[str, object]", FORMAT_MAP[format_key])
        fmt_obj = fmt_cfg["fmt"]
        date_only = target == "date"

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return to_datetime(
                safe_df,
                safe_col,
                fmt=fmt_obj if isinstance(fmt_obj, str) else None,
                dayfirst=bool(fmt_cfg["dayfirst"]),
                yearfirst=bool(fmt_cfg["yearfirst"]),
                date_only=date_only,
                errors=self._conversion_error_handling,
            )

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_CONVERTED_TO_DATETIME,
                    column_name=safe_col,
                    mode=mode,
                ),
            )

            self._logger.info(
                "ResultTabHeaderDtypeActions: column '%s' converted to datetime (mode=%s corr=%s).",
                safe_col,
                target,
                corr_id,
            )

        mode = self._tr(self.TR_DATE) if date_only else self._tr(self.TR_DATETIME)

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_CONVERTING_TO_DATETIME, mode=mode, column_name=safe_col),
            scope=f"convert:to_datetime:{safe_col}",
            operation_name=self._tr(self.TR_CONVERT_TO_DATETIME_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # To boolean
    # ==================================================================

    def to_boolean(self, view: QTableView, column: int) -> None:
        """Convert column to nullable boolean dtype.

        Args:
            view: The QTableView instance.
            column: The column index to convert.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        # Ask user how to interpret boolean values
        opts = self._dialogs.prompt_boolean_conversion(
            parent=self._parent,
            title=self._tr(self.TR_CONVERT_TO_BOOL),
            default_true_values=["true", "1", "yes"],
            default_false_values=["false", "0", "no"],
        )
        if not opts["ok"]:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderDtypeActions: convert to bool requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.convert import to_boolean

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return to_boolean(
                safe_df,
                safe_col,
                true_values=opts["true_values"],
                false_values=opts["false_values"],
                errors=self._conversion_error_handling,
            )

        corr_id = uuid.uuid4().hex

        error_label = {
            "coerce": self._tr(self.TR_UNKNOWN_ERROR_LABEL_NA),
            "raise": self._tr(self.TR_UNKNOWN_ERROR_LABEL_ERROR),
        }[self._conversion_error_handling]

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_CONVERTED_TO_BOOL,
                    column_name=safe_col,
                    error_label=error_label,
                ),
            )

            self._logger.info(
                "ResultTabHeaderDtypeActions: column '%s' converted to bool (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_CONVERTING_TO_BOOL, column_name=safe_col),
            scope=f"convert:to_bool:{safe_col}",
            operation_name=self._tr(self.TR_CONVERT_TO_BOOL_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # To category
    # ==================================================================

    def to_category(self, view: QTableView, column: int) -> None:
        """Convert column to categorical dtype with user-defined ordering.

        Args:
            view: The QTableView instance.
            column: The column index to convert.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        opts = self._dialogs.prompt_category_conversion(
            parent=self._parent,
            title=self._tr(self.TR_CONVERT_TO_CATEGORIES),
            default_order="alpha",
            default_ordered=False,
            default_strict=True,
        )
        if not opts.get("ok", False):
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderDtypeActions: convert to category requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.convert import to_category

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,  # noqa: ARG001
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return to_category(
                safe_df,
                safe_col,
                order=opts["order"],
                ordered=opts["ordered"],
                strict=opts["strict"],
            )

        corr_id = uuid.uuid4().hex

        order_label = self._tr(self._CATEGORY_ORDER_LABELS[opts["order"]])

        ordered_label = self._tr(self.TR_ORDERED) if opts["ordered"] else self._tr(self.TR_UNORDERED)

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_CONVERTED_TO_CATEGORIES,
                    column_name=safe_col,
                    order=order_label,
                    ordered=ordered_label,
                ),
            )

            self._logger.info(
                "ResultTabHeaderDtypeActions: column '%s' converted to category (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_CONVERTING_TO_CATEGORIES, column_name=col),
            scope=f"convert:to_category:{safe_col}",
            operation_name=self._tr(self.TR_CONVERT_TO_CATEGORIES_OPERATION),
            corr_id=corr_id,
        )
