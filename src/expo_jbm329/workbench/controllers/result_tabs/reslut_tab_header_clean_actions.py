"""Header (column) actions for result tabs.

This module contains column-header related operations such as:
- text cleaning
- simple transformations (digits / letters)

All UI concerns (dialogs, logging, i18n) are injected.
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


class ResultTabHeaderCleanActions:
    """Header (column) actions with explicit dependency injection."""

    # ------------------------------------------------------------------
    # i18n markers (pylupdate6-visible)
    # ------------------------------------------------------------------

    TR_TRIM_OPERATION = QT_TR_NOOP("trim column")
    TR_TRIMMING_COLUMN = QT_TR_NOOP("Trimming column: {column_name}")
    TR_TRIMMED_COLUMN = QT_TR_NOOP("Trimmed column: {column_name}")

    TR_LOWERCASE_OPERATION = QT_TR_NOOP("lowercase column")
    TR_CONVERTING_COLUMN_TO_LOWER = QT_TR_NOOP("Converting column to lower: {column_name}")
    TR_CONVERTED_TO_LOWER = QT_TR_NOOP("Converted column to lowercase: {column_name}")

    TR_UPPERCASE_OPERATION = QT_TR_NOOP("uppercase column")
    TR_CONVERTING_COLUMN_TO_UPPER = QT_TR_NOOP("Converting column to upper: {column_name}")
    TR_CONVERTED_TO_UPPER = QT_TR_NOOP("Converted column to uppercase: {column_name}")

    TR_TITLECASE_OPERATION = QT_TR_NOOP("titlecase column")
    TR_CONVERTING_COLUMN_TO_TITLE = QT_TR_NOOP("Converting column to titlecase: {column_name}")
    TR_CONVERTED_TO_TITLE = QT_TR_NOOP("Converted column to titlecase: {column_name}")

    TR_CAPITALIZE_OPERATION = QT_TR_NOOP("capitalize column")
    TR_CONVERTING_COLUMN_TO_CAPITALIZE = QT_TR_NOOP("Converting column to capitalize: {column_name}")
    TR_CONVERTED_TO_CAPITALIZE = QT_TR_NOOP("Converted column to capitalize: {column_name}")

    TR_KEEP_DIGITS_OPERATION = QT_TR_NOOP("keep digits")
    TR_KEEPING_ONLY_DIGITS = QT_TR_NOOP("Keeping only digits in column: {column_name}")
    TR_ONLY_DIGITS_KEPT = QT_TR_NOOP("Only digits kept in column: {column_name}")

    TR_KEEP_LETTERS_OPERATION = QT_TR_NOOP("keep letters")
    TR_KEEPING_ONLY_LETTERS = QT_TR_NOOP("Keeping only letters in column: {column_name}")
    TR_ONLY_LETTERS_KEPT = QT_TR_NOOP("Only letters kept in column: {column_name}")

    TR_NORMALIZE_WHITESPACE_OPERATION = QT_TR_NOOP("normalize whitespace")
    TR_NORMALIZING_WHITESPACE = QT_TR_NOOP("Normalizing whitespace in column: {column_name}")
    TR_NORMALIZED_WHITESPACE = QT_TR_NOOP("Normalized whitespace: {column_name}")

    TR_REMOVE_TEXT_OPERATION = QT_TR_NOOP("remove text")
    TR_REMOVING_TEXT = QT_TR_NOOP("Removing {text_remove} in column: {column_name}")
    TR_REMOVE_TEXT = QT_TR_NOOP("Remove text")
    TR_TEXT_TO_REMOVE = QT_TR_NOOP("Text to remove:")
    TR_REMOVED_TEXT = QT_TR_NOOP("Removed '{text_remove}' in column: {column_name}")

    TR_REMOVE_REGEX_OPERATION = QT_TR_NOOP("remove with regex")
    TR_REMOVING_REGEX = QT_TR_NOOP("Removing regex {regex_pattern} in column: {column_name}")
    TR_REMOVE_WITH_REGEX = QT_TR_NOOP("Remove with regular expression")
    TR_REGEX_PATTERN = QT_TR_NOOP("Regex pattern:")
    TR_REMOVED_REGEX = QT_TR_NOOP("Removed with regex in column: {column_name}")

    TR_REPLACE_TEXT_OPERATION = QT_TR_NOOP("replace text")
    TR_REPLACING_TEXT = QT_TR_NOOP("Replacing text in column: {column_name}")
    TR_REPLACE_TEXT = QT_TR_NOOP("Replace text")
    TR_REPLACED_TEXT = QT_TR_NOOP("Replaced '{old_text}' → '{new_text}' in column: {column_name}")

    TR_INSERT_TEXT_OPERATION = QT_TR_NOOP("insert text")
    TR_INSERTING_TEXT = QT_TR_NOOP("Inserting text in column: {column_name}")
    TR_INSERT_TEXT = QT_TR_NOOP("Insert text")
    TR_INSERTED_TEXT = QT_TR_NOOP("Inserted '{insert_text}' at position {position} in column: {column_name}")

    # ------------------------------------------------------------------
    # i18n helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tr(text: str) -> str:
        return tr("ResultTabHeaderCleanActions", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: object) -> str:
        return tr_fmt("ResultTabHeaderCleanActions", text, **kwargs)

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
        """Initialize ResultTabHeaderCleanActions with dependencies.

        Args:
            parent (QWidget): Parent widget for dialogs.
            dialogs (DialogService): Service for showing dialogs.
            logger (logging.Logger): Logger for logging operations.
            async_ops: Controller for managing async operations.
            resolve_df_col_series (Callable): Function to resolve dataframe column series.
            apply_new_dataframe (Callable): Function to apply new dataframe.
        """
        self._parent = parent
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._async_ops = async_ops
        self._resolve_df_col_series = resolve_df_col_series
        self._apply_new_dataframe = apply_new_dataframe

    # ==================================================================
    # Clean text
    # ==================================================================

    def clean_strip(self, view: QTableView, column: int) -> None:
        """Remove leading and trailing whitespace from a column in the result table.

        Args:
            view (QTableView): The result table view.
            column (int): The index of the column to clean.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCleanActions: trim requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.text import clean_text

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return clean_text(safe_df, safe_col, strip=True)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_TRIMMED_COLUMN, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderCleanActions: column '%s' trimmed (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_TRIMMING_COLUMN, column_name=col),
            scope=f"trim:{safe_col}",
            operation_name=self._tr(self.TR_TRIM_OPERATION),
            corr_id=corr_id,
        )

    def clean_lower(self, view: QTableView, column: int) -> None:
        """Convert a column in the result table to lowercase.

        Args:
            view (QTableView): The result table view.
            column (int): The index of the column to convert.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCleanActions: lowercase requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.text import clean_text

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return clean_text(safe_df, safe_col, lower=True)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_CONVERTED_TO_LOWER, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderCleanActions: lowercased column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_CONVERTING_COLUMN_TO_LOWER, column_name=safe_col),
            scope=f"lowercase:{safe_col}",
            operation_name=self._tr(self.TR_LOWERCASE_OPERATION),
            corr_id=corr_id,
        )

    def clean_upper(self, view: QTableView, column: int) -> None:
        """Convert a column in the result table to uppercase.

        Args:
            view (QTableView): The result table view.
            column (int): The index of the column to convert.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCleanActions: uppercase requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.text import clean_text

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return clean_text(safe_df, safe_col, upper=True)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_CONVERTED_TO_UPPER, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderCleanActions: uppercased column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_CONVERTING_COLUMN_TO_UPPER, column_name=safe_col),
            scope=f"uppercase:{safe_col}",
            operation_name=self._tr(self.TR_UPPERCASE_OPERATION),
            corr_id=corr_id,
        )

    def clean_title(self, view: QTableView, column: int) -> None:
        """Convert a column in the result table to titlecase.

        Args:
            view (QTableView): The result table view.
            column (int): The index of the column to convert.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCleanActions: titlecase requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.text import to_title_case

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return to_title_case(safe_df, safe_col)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_CONVERTED_TO_TITLE, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderCleanActions: titlecased column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_CONVERTING_COLUMN_TO_TITLE, column_name=safe_col),
            scope=f"titlecase:{safe_col}",
            operation_name=self._tr(self.TR_TITLECASE_OPERATION),
            corr_id=corr_id,
        )

    def clean_capitalize(self, view: QTableView, column: int) -> None:
        """Convert a column in the result table to capitalize.

        Args:
            view (QTableView): The result table view.
            column (int): The index of the column to convert.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCleanActions: capitalize requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.text import capitalize_first

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return capitalize_first(safe_df, safe_col)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_CONVERTED_TO_CAPITALIZE, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderCleanActions: capitalized column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_CONVERTING_COLUMN_TO_CAPITALIZE, column_name=safe_col),
            scope=f"capitalize:{safe_col}",
            operation_name=self._tr(self.TR_CAPITALIZE_OPERATION),
            corr_id=corr_id,
        )

    # ==================================================================
    # Keep digits / letters
    # ==================================================================

    def clean_keep_digits(self, view: QTableView, column: int) -> None:
        """Keep only digits in a column in the result table.

        Args:
            view (QTableView): The result table view.
            column (int): The index of the column to process.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCleanActions: keep digits requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.text import extract_digits

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return extract_digits(safe_df, safe_col)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_ONLY_DIGITS_KEPT, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderCleanActions: kept only digits in column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_KEEPING_ONLY_DIGITS, column_name=safe_col),
            scope=f"keep_digits:{safe_col}",
            operation_name=self._tr(self.TR_KEEP_DIGITS_OPERATION),
            corr_id=corr_id,
        )

    def clean_keep_letters(self, view: QTableView, column: int) -> None:
        """Keep only letters in a column in the result table.

        Args:
            view (QTableView): The result table view.
            column (int): The index of the column to process.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCleanActions: keep letters requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.text import extract_letters

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return extract_letters(safe_df, safe_col, keep_swedish=True)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_ONLY_LETTERS_KEPT, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderCleanActions: kept only letters in column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_KEEPING_ONLY_LETTERS, column_name=safe_col),
            scope=f"keep_letters:{safe_col}",
            operation_name=self._tr(self.TR_KEEP_LETTERS_OPERATION),
            corr_id=corr_id,
        )

    def clean_whitespace(self, view: QTableView, column: int) -> None:
        """Normalizes whitespace in a column in the result table.

        Args:
            view: The QTableView instance where the action is performed.
            column: The index of the column to clean whitespace from.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)

        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCleanActions: normalize whitespace requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.text import normalize_whitespace

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return normalize_whitespace(safe_df, safe_col)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_NORMALIZED_WHITESPACE, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderCleanActions: normalized whitespace in column '%s' (corr=%s).",
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_NORMALIZING_WHITESPACE, column_name=safe_col),
            scope=f"normalize_whitespace:{safe_col}",
            operation_name=self._tr(self.TR_NORMALIZE_WHITESPACE_OPERATION),
            corr_id=corr_id,
        )

    def clean_remove(self, view: QTableView, column: int) -> None:
        """Remove text from a column in the result table.

        Args:
            view: The QTableView instance.
            column: The index of the column to remove text from.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)

        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCleanActions: remove text requested for column '%s'.",
            safe_col,
        )

        opts = self._dialogs.prompt_filter_match(
            parent=self._parent,
            title=self._tr(self.TR_REMOVE_TEXT),
            label=self._tr(self.TR_TEXT_TO_REMOVE),
            default_value="",
        )
        if not opts["ok"] or not opts["value"]:
            return

        text = opts["value"]
        case_sensitive = opts["case_sensitive"]

        from expo_jbm329.services.data_operations.text import clean_text

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return clean_text(safe_df, safe_col, remove=text, case=case_sensitive)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_REMOVED_TEXT,
                    text_remove=text,
                    column_name=safe_col,
                ),
            )

            self._logger.info(
                "ResultTabHeaderCleanActions: removed text '%s' (case_sensitive=%s) in column '%s' (corr=%s).",
                text,
                case_sensitive,
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_REMOVING_TEXT, text_remove=text, column_name=safe_col),
            scope=f"remove_text:{safe_col}",
            operation_name=self._tr(self.TR_REMOVE_TEXT_OPERATION),
            corr_id=corr_id,
        )

    def clean_remove_regex(self, view: QTableView, column: int) -> None:
        """Remove text from a column in the result table using a regular expression.

        Args:
            view: The QTableView instance.
            column: The index of the column to remove text from.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)

        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCleanActions: remove with regex requested for column '%s'.",
            safe_col,
        )

        pattern, ok = self._dialogs.prompt_text(
            parent=self._parent,
            title=self._tr(self.TR_REMOVE_WITH_REGEX),
            label=self._tr(self.TR_REGEX_PATTERN),
        )
        if not ok or not pattern.strip():
            return

        from expo_jbm329.services.data_operations.text import remove_regex

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return remove_regex(safe_df, safe_col, pattern)

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(self.TR_REMOVED_REGEX, column_name=safe_col),
            )

            self._logger.info(
                "ResultTabHeaderCleanActions: removed with regex pattern '%s' in column '%s' (corr=%s).",
                pattern,
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_REMOVING_REGEX, regex_pattern=pattern, column_name=safe_col),
            scope=f"remove_regex:{safe_col}",
            operation_name=self._tr(self.TR_REMOVE_REGEX_OPERATION),
            corr_id=corr_id,
        )

    def clean_replace(self, view: QTableView, column: int) -> None:
        """Replace text in a column in the result table.

        Args:
            view: The QTableView instance.
            column: The index of the column to perform the operation on.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)

        if not ok or df is None or col is None:
            return

        safe_df = df
        safe_col = col

        self._logger.debug(
            "ResultTabHeaderCleanActions: replace text requested for column '%s'.",
            safe_col,
        )

        opts = self._dialogs.prompt_text_replace(
            parent=self._parent,
            title=self._tr(self.TR_REPLACE_TEXT),
        )
        if not opts.get("ok", False):
            return

        old_text = opts["old"]
        new_text = opts["new"]
        case = opts["case"]

        from expo_jbm329.services.data_operations.text import replace_text

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return replace_text(
                safe_df,
                safe_col,
                old=old_text,
                new=new_text,
                case=case,
            )

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_REPLACED_TEXT,
                    old_text=old_text,
                    new_text=new_text,
                    column_name=safe_col,
                ),
            )

            self._logger.info(
                "ResultTabHeaderCleanActions: replaced '%s' → '%s' in column '%s' (corr=%s).",
                old_text,
                new_text,
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_REPLACING_TEXT, column_name=safe_col),
            scope=f"replace_text:{safe_col}",
            operation_name=self._tr(self.TR_REPLACE_TEXT_OPERATION),
            corr_id=corr_id,
        )

    def clean_insert(self, view: QTableView, column: int) -> None:
        """Insert text into a column in the result table.

        Args:
            view (QTableView): The table view where the operation is performed.
            column (int): The column index where the text will be inserted.

        Returns:
            None
        """
        ok, df, col, _ = self._resolve_df_col_series(view, column)
        if not ok or df is None or col is None:
            return

        opts = self._dialogs.prompt_text_insert(
            parent=self._parent,
            title=self._tr(self.TR_INSERT_TEXT),
        )
        if not opts.get("ok", False):
            return

        safe_df = df
        safe_col = col

        text_insert = opts["insert"]
        position = opts["position"]

        self._logger.debug(
            "ResultTabHeaderCleanActions: insert text requested for column '%s'.",
            safe_col,
        )

        from expo_jbm329.services.data_operations.text import insert_text

        def _work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb and cancel_cb():
                return None

            return insert_text(
                safe_df,
                safe_col,
                insert=text_insert,
                position=position,
            )

        corr_id = uuid.uuid4().hex

        def _apply_result(new_df: pd.DataFrame | None) -> None:
            if new_df is None:
                return

            self._apply_new_dataframe(
                view,
                new_df,
                self._tr_fmt(
                    self.TR_INSERTED_TEXT,
                    insert_text=text_insert,
                    position=str(position),
                    column_name=safe_col,
                ),
            )

            self._logger.info(
                "ResultTabHeaderCleanActions: inserted '%s' at pos %s in column '%s' (corr=%s).",
                text_insert,
                position,
                safe_col,
                corr_id,
            )

        self._async_ops.run_dataframe_operation(
            view=view,
            runner="pool",
            work=_work,
            apply_result=_apply_result,
            busy_message=self._tr_fmt(self.TR_INSERTING_TEXT, column_name=safe_col),
            scope=f"insert_text:{safe_col}",
            operation_name=self._tr(self.TR_INSERT_TEXT_OPERATION),
            corr_id=corr_id,
        )
