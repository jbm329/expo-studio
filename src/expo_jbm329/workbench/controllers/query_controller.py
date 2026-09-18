"""Query controller for executing SQL in the Expo application.

This module provides the QueryController class, which orchestrates asynchronous
SQL query execution. It handles full queries, TOP N queries, and selection-based
execution while maintaining a responsive UI by delegating work to background
worker threads via JobManager.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP

from expo_jbm329.db.base import execute_sql_safe
from expo_jbm329.db.core.models import SqlError
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.utils.format_utils import fmt_shape, fmt_time
from expo_jbm329.utils.i18n_utils import tr, tr_fmt

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.controllers.async_operation_controller import (
        AsyncOperationController,
    )


class QueryController:
    """Controller for executing SQL queries in the Expo application.

    This controller orchestrates asynchronous SQL execution via JobManager,
    supporting full queries, TOP N queries, and selection-based execution.
    It measures execution time, displays DataFrame results, and provides
    thread-safe UI feedback.

    Note: This controller does NOT execute SQL directly; it only orchestrates
    the worker job. All heavy work is performed in JobManager threads, keeping
    the SQL editor responsive even for large or slow queries.
    """

    # --- i18n markers (pylupdate6-visible) -----------------------------
    TR_SQL_RESULT_TAB = QT_TR_NOOP("SQL result")
    TR_RUNNING_SQL = QT_TR_NOOP("Running SQL…")
    TR_RUNNING_SQL_TOP10 = QT_TR_NOOP("Running SQL (top 10)…")
    TR_RUNNING_SQL_SELECTION = QT_TR_NOOP("Running SQL (selection)…")
    TR_NO_SELECTION = QT_TR_NOOP("No selection")
    TR_SELECT_SQL_TO_RUN = QT_TR_NOOP("Select SQL to run.")
    TR_NO_SQL = QT_TR_NOOP("No SQL")
    TR_NO_SQL_TO_RUN = QT_TR_NOOP("SQL editor is empty. Write SQL to run.")
    TR_SQL_COMPLETED = QT_TR_NOOP("Completed: Query executed {rows} rows, {cols} columns ({elapsed_time})")
    TR_SQL_CANCELLED = QT_TR_NOOP("SQL execution cancelled.")
    TR_SQL_FAILED = QT_TR_NOOP("SQL failed.")
    TR_FAILED_TO_RUN_SQL = QT_TR_NOOP("Failed to run SQL")
    TR_FAILED_TO_RUN_SQL_TRACE = QT_TR_NOOP("Failed to run SQL.\n\n{traceback_str}")
    TR_FAILURE = QT_TR_NOOP("Failure")
    TR_SQL_ERROR_HINT = QT_TR_NOOP("\n\nHint: {error_hint}")
    TR_NO_CONNECTION = QT_TR_NOOP("No connection")
    TR_SELECT_CONNECTION = QT_TR_NOOP("Please select a database connection.")

    @staticmethod
    def _tr(text: str) -> str:
        return tr("QueryController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: str) -> str:
        return tr_fmt("QueryController", text, **kwargs)

    __slots__ = (
        "__weakref__",
        "_async_ops",
        "_dialogs",
        "_get_current_connection",
        "_get_sql",
        "_logger",
        "_parent",
        "_results",
        "_set_status",
    )

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def __init__(
        self,
        *,
        parent_widget: QWidget,
        async_ops: AsyncOperationController,
        results,
        set_status: Callable[[str, int | None], None],
        get_sql: Callable[[bool], str | None],
        get_current_connection: Callable[[], str | None],
        dialogs: DialogService | None = None,
        logger: logging.Logger | None = None,
    ):
        """Initialize the QueryController.

        Args:
            parent_widget: The parent widget (main window).
            async_ops: AsyncOperationController for managing asynchronous operations.
            results: ResultTabManager for displaying DataFrames.
            set_status: Callback to set status messages.
            get_sql: Callback to extract full SQL or selected SQL.
            get_current_connection: Callback to get the current connection name.
            dialogs: Optional dialog service (QtDialogService by default).
            logger: Optional logger instance.
        """
        self._parent = parent_widget
        self._async_ops = async_ops
        self._results = results
        self._set_status = set_status
        self._get_sql = get_sql
        self._get_current_connection = get_current_connection
        self._dialogs = dialogs or QtDialogService()
        self._logger = logger or logging.getLogger("applogger.service")

    # ==================================================================
    # Public API - invoked by toolbar buttons / shortcuts
    # ==================================================================
    def run_top10(self):
        """Execute the full SQL query limited to TOP 10 rows."""
        self._logger.info(
            "QueryController: run_top10 called (active_connection=%s)",
            self._get_current_connection(),
        )

        self._run_sql(use_sel=False, top_n=10, started_msg=self._tr(self.TR_RUNNING_SQL_TOP10))

    def run_full(self):
        """Execute the entire SQL query with no row limit."""
        self._logger.info(
            "QueryController: run_full called (active_connection=%s)",
            self._get_current_connection(),
        )

        self._run_sql(use_sel=False, top_n=None, started_msg=self._tr(self.TR_RUNNING_SQL))

    def run_selection(self, top_n: int | None):
        """Execute only the selected SQL in the workbench.

        If no text is selected, the user is notified via dialog.

        Args:
            top_n: Optional row limit for the selection.
        """
        self._logger.info(
            "QueryController.run_selection called (active_connection=%s)",
            self._get_current_connection(),
        )

        sql = self._get_sql(True)
        if not sql:
            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_NO_SELECTION),
                text=self._tr(self.TR_SELECT_SQL_TO_RUN)
            )
            return

        self._run_sql(use_sel=True, top_n=top_n, started_msg=self._tr(self.TR_RUNNING_SQL_SELECTION))

    # ==================================================================
    # Internal SQL execution handler
    # ==================================================================
    def _run_sql(
        self,
        use_sel: bool,
        top_n: int | None,
        started_msg: str,
    ) -> None:
        """Start an asynchronous SQL execution job via AsyncOperationController.

        A pending result tab is created immediately and becomes the overlay target
        for the running SQL job. On success, the pending tab is fulfilled with the
        query result. On cancellation or failure, the pending tab is removed.

        Args:
            use_sel: Whether to use selected SQL or full SQL.
            top_n: Optional row limit.
            started_msg: User-facing message shown while the query is running.
        """
        sql_text = self._get_sql(use_sel)
        if not sql_text:
            self._dialogs.warn(
                parent=self._parent,
                title=self._tr(self.TR_NO_SQL),
                text=self._tr(self.TR_NO_SQL_TO_RUN),
            )
            return

        connection_name = self._get_current_connection()
        if not connection_name:
            self._logger.warning(
                "QueryController: BLOCKED - no active connection (sql_len=%d)",
                len(sql_text) if sql_text else 0,
            )

            self._dialogs.info(
                parent=self._parent,
                title=self._tr(self.TR_NO_CONNECTION),
                text=self._tr(self.TR_SELECT_CONNECTION),
            )
            return

        corr_id = uuid.uuid4().hex

        self._logger.info(
            "QueryController: STARTING SQL (conn=%s, top_n=%s, sql_len=%d, corr=%s)",
            connection_name,
            top_n,
            len(sql_text),
            corr_id,
        )

        pending_title = self._pending_result_title(use_sel, top_n)
        pending_handle = self._results.create_pending_tab(
            title=pending_title,
            origin_type="sql",
            remove_on_cancel=True,
            remove_on_error=True,
            close_cancels_job=True,
        )

        safe_connection_name = connection_name
        safe_sql_text = sql_text
        pending_tab_id = pending_handle.tab_id
        pending_view = pending_handle.view

        def _work(*, progress_cb=None, cancel_cb=None, job_id=None, job_scope=None, **_):
            _ = progress_cb
            _ = job_scope

            return execute_sql_safe(
                safe_connection_name,
                safe_sql_text,
                top_n=top_n,
                corr_id=corr_id,
                cancel_cb=cancel_cb,
                job_id=job_id,
            )

        def _on_result(payload) -> None:
            """Handle SQL result for the pending result tab."""
            res = payload

            if res is None:
                self._logger.error(
                    "QueryController: worker returned None payload (corr=%s, tab_id=%s).",
                    corr_id,
                    pending_tab_id,
                )
                self._results.remove_pending_tab(pending_tab_id)
                self._set_status(self._tr(self.TR_FAILED_TO_RUN_SQL), 6000)
                return

            # --------------------------------------------------
            # CANCELLED
            # --------------------------------------------------
            if res.cancelled:
                self._logger.info(
                    "QueryController: SQL execution cancelled (corr=%s, tab_id=%s).",
                    corr_id,
                    pending_tab_id,
                )
                self._results.remove_pending_tab(pending_tab_id)
                self._set_status(self._tr(self.TR_SQL_CANCELLED), 6000)
                return

            # --------------------------------------------------
            # FAILED
            # --------------------------------------------------

            if not res.ok:
                err = res.error if isinstance(res.error, SqlError) else None

                msg = (
                    tr("DbErrors", err.message) if err is not None else self._tr(self.TR_SQL_FAILED)
                )

                hint_str = tr("DbErrors", err.hint) if err is not None and err.hint else ""
                hint = self._tr_fmt(self.TR_SQL_ERROR_HINT, error_hint=hint_str) if hint_str else ""

                self._set_status(self._tr(self.TR_FAILED_TO_RUN_SQL), 6000)

                self._dialogs.critical(
                    parent=self._parent,
                    title=self._tr(self.TR_FAILURE),
                    text=msg + hint,
                )

                self._results.remove_pending_tab(pending_tab_id)

                self._logger.warning(
                    "QueryController: SQL failed (corr=%s, tab_id=%s, error=%s)",
                    corr_id,
                    pending_tab_id,
                    err.message if err is not None else "unknown",
                )
                return

            # --------------------------------------------------
            # SUCCESS
            # --------------------------------------------------
            df = res.data
            if df is None:
                self._logger.warning(
                    "QueryController: SQL returned no data (corr=%s, tab_id=%s).",
                    corr_id,
                    pending_tab_id,
                )
                self._results.remove_pending_tab(pending_tab_id)
                return

            rows = df.shape[0]

            self._logger.info(
                "QueryController: SQL completed (rows=%s, elapsed=%.3fs, corr=%s, tab_id=%s)",
                rows,
                getattr(res, "elapsed_s", -1.0),
                corr_id,
                pending_tab_id,
            )

            self._parent.last_df = df

            self._results.fulfill_pending_tab(pending_tab_id, df)

            rows_fmt, cols_fmt = fmt_shape(df)
            elapsed_time = fmt_time(res.elapsed_s)

            msg = self._tr_fmt(
                self.TR_SQL_COMPLETED,
                rows=rows_fmt,
                cols=cols_fmt,
                elapsed_time=elapsed_time,
            )

            self._set_status(msg, 12000)

        def _on_error(traceback_str: str) -> None:
            """Handle unexpected worker-level failure for the pending result tab."""
            self._results.remove_pending_tab(pending_tab_id)
            self._set_status(self._tr(self.TR_FAILED_TO_RUN_SQL), 6000)
            self._dialogs.critical(
                parent=self._parent,
                title=self._tr(self.TR_FAILURE),
                text=self._tr_fmt(
                    self.TR_FAILED_TO_RUN_SQL_TRACE,
                    traceback_str=traceback_str,
                ),
            )
        query_type = ":full"
        if use_sel:
            query_type = ":selection"
        if top_n is not None:
            if use_sel:
                query_type += f":top_{top_n}"
            else:
                query_type = f":top_{top_n}"

        job = self._async_ops.run_target_overlay_operation(
            target=pending_view,
            runner="thread",
            work=_work,
            on_result=_on_result,
            on_error=_on_error,
            busy_message=started_msg,
            scope=f"query{query_type}",
            operation_name=self._tr(self.TR_FAILED_TO_RUN_SQL),
            timeout_ms=0,
            indeterminate=True,
            cancelable=True,
            show_status_progress=False,
            show_started_in_status=False,
            suppress_error_dialog=True,
            corr_id=corr_id,
        )

        jobid = self._async_ops.job_mgr.get_job_id(job)
        if jobid is not None:
            self._results.bind_job_to_tab(pending_tab_id, jobid)
        else:
            self._logger.warning(
                "QueryController: could not bind SQL job to pending tab because job_id was missing "
                "(corr=%s, tab_id=%s).",
                corr_id,
                pending_tab_id,
            )

    # --------------------------------------------------
    # Internal helpers
    # --------------------------------------------------

    def _pending_result_title(self, use_sel: bool, top_n: int | None) -> str:
        """Return the base title for a pending SQL result tab.

        Args:
            use_sel: Whether the query uses selected SQL.
            top_n: Optional row limit.

        Returns:
            Base title for the result tab.
        """
        _ = use_sel
        _ = top_n
        return self._tr(self.TR_SQL_RESULT_TAB)
