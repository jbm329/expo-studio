"""Reshape configuration, preview and asynchronous result-tab orchestration."""

from __future__ import annotations

import logging
import uuid
from threading import Event
from typing import TYPE_CHECKING

from PyQt6 import sip
from PyQt6.QtCore import QT_TR_NOOP, QObject
from PyQt6.QtWidgets import QDialog

from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
from expo_jbm329.gui.dialogs.workflows.reshape.reshape_dialog import ReshapeDialog
from expo_jbm329.services.data_operations.dtypes import get_datetime_column_positions, get_numeric_column_positions
from expo_jbm329.services.data_operations.reshape_preview import (
    ReshapeError,
    ReshapePreview,
    ReshapeRequest,
    compute_reshape,
    compute_reshape_preview,
)
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.utils.i18n_utils import translate
from expo_jbm329.workbench.controllers.reshape_condition_controller import ReshapeConditionController

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd
    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.controllers.async_operation_controller import AsyncOperationController
    from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager


class ReshapeController:
    """Open an aggregation configuration bound to the active ready dataset."""

    TR_UNAVAILABLE = QT_TR_NOOP("Reshape unavailable")
    TR_READY_DATASET_REQUIRED = QT_TR_NOOP("Select a ready result dataset before opening Reshape.")
    TR_PREVIEW = QT_TR_NOOP("Calculating Reshape preview...")
    TR_OPERATION = QT_TR_NOOP("Reshape preview")
    TR_CANCELLED = QT_TR_NOOP("Preview cancelled. Press Preview to try again.")
    TR_FAILED = QT_TR_NOOP("Preview failed. Check the selected data and conditions, then try again.")
    TR_RESULT = QT_TR_NOOP("Reshaped data")
    TR_RESHAPING = QT_TR_NOOP("Reshaping dataset...")

    def __init__(
        self,
        *,
        parent_widget: QWidget,
        results: ResultTabManager,
        async_ops: AsyncOperationController,
        logger: logging.Logger | None = None,
        dialogs: DialogService | None = None,
    ) -> None:
        """Initialize the controller with explicit workbench dependencies.

        Args:
            parent_widget: Parent for configuration and warning dialogs.
            results: Manager owning dataset readiness and identity.
            async_ops: Workbench job facade for condition values, previews and results.
            logger: Optional UI logger.
            dialogs: Optional dialog service.
        """
        self._parent = parent_widget
        self._results = results
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._conditions = ReshapeConditionController(async_ops, self._logger)
        self._async_ops = async_ops

    @staticmethod
    def _tr(text: str) -> str:
        return translate("ReshapeController", text)

    def open_reshape_dialog(self) -> None:
        """Open configuration and preview against the original ready dataset."""
        tab_id = self._results.active_tab_id()
        record = self._results.tabs_by_id.get(tab_id) if tab_id is not None else None
        if record is None or not record.is_ready or record.df is None:
            self._logger.warning("ReshapeController: reshape unavailable (reason=ready_dataset_required)")
            self._dialogs.warn(
                self._parent,
                self._tr(self.TR_UNAVAILABLE),
                self._tr(self.TR_READY_DATASET_REQUIRED),
            )
            return

        dataset = DatasetRef(
            tab_id=record.tab_id,
            title=record.title,
            row_count=len(record.df),
            column_count=len(record.df.columns),
        )
        source = record.df
        dialog = ReshapeDialog(
            parent=self._parent,
            source_dataset=dataset,
            source_columns=list(record.df.columns),
            source_dtypes=[str(dtype) for dtype in record.df.dtypes],
            numeric_column_positions=get_numeric_column_positions(record.df),
            datetime_column_positions=get_datetime_column_positions(record.df),
        )

        def open_condition(candidate: object) -> None:
            if not isinstance(candidate, ConditionEditor):
                message = "Condition builder requires a metric condition editor."
                raise TypeError(message)
            self._conditions.open_dialog(dialog, candidate, source)

        dialog.condition_requested.connect(open_condition)
        self._connect_preview(dialog, source)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.applied_request is not None:
            self._run_reshape(source, dialog.applied_request)

    def _run_reshape(self, source: pd.DataFrame, request: ReshapeRequest) -> None:
        """Create a pending result tab and run the captured configuration."""
        corr_id = uuid.uuid4().hex
        self._logger.info(
            "ReshapeController: reshape requested (corr=%s, operation=apply, source_rows=%d, source_cols=%d, "
            "dimensions=%d, metrics=%d)",
            corr_id,
            len(source),
            len(source.columns),
            len(request.dimensions),
            len(request.metrics),
        )
        pending = self._results.create_pending_tab(
            title=self._tr(self.TR_RESULT),
            origin_type="reshape",
            remove_on_cancel=True,
            remove_on_error=True,
            close_cancels_job=True,
        )
        tab_id = pending.tab_id

        def stale() -> bool:
            record = self._results.tabs_by_id.get(tab_id)
            return record is None or not record.is_pending

        def work(
            *,
            progress_cb: Callable[[int], None] | None = None,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            return compute_reshape(
                source,
                request,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
                corr_id=corr_id,
            )

        def result(frame: pd.DataFrame | None) -> None:
            if stale():
                return
            if frame is None:
                self._results.remove_pending_tab(tab_id)
                self._logger.info(
                    "ReshapeController: result tab removed (corr=%s, tab_id=%s, outcome=cancelled)",
                    corr_id,
                    tab_id,
                )
                return
            self._results.fulfill_pending_tab(tab_id, frame)
            self._logger.info(
                "ReshapeController: result tab fulfilled (corr=%s, tab_id=%s, rows=%d)",
                corr_id,
                tab_id,
                len(frame),
            )

        def finished() -> None:
            if not stale():
                self._results.remove_pending_tab(tab_id)

        job = self._async_ops.run_target_overlay_operation(
            target=pending.view,
            runner="pool",
            work=work,
            on_result=result,
            on_finished=finished,
            busy_message=self._tr(self.TR_RESHAPING),
            operation_name=self._tr(self.TR_RESULT),
            scope=f"reshape:{tab_id}",
            corr_id=corr_id,
            stale_check=stale,
            cancelable=True,
            indeterminate=False,
            timeout_ms=0,
            show_status_progress=False,
            show_started_in_status=False,
            suppress_error_dialog=False,
            log_error_tracebacks=False,
        )
        job_id = self._async_ops.job_mgr.get_job_id(job if isinstance(job, QObject) else None)
        if job_id is not None:
            self._results.bind_job_to_tab(tab_id, job_id)
        else:
            self._logger.warning(
                "ReshapeController: result tab job binding unavailable (corr=%s, tab_id=%s)",
                corr_id,
                tab_id,
            )

    def _connect_preview(self, dialog: ReshapeDialog, source: pd.DataFrame) -> None:
        closed = False
        running = False
        job_id: str | None = None
        cancellation: Event | None = None
        busy_message = self._tr(self.TR_PREVIEW)
        operation_name = self._tr(self.TR_OPERATION)
        cancelled_message = self._tr(self.TR_CANCELLED)
        failed_message = self._tr(self.TR_FAILED)

        def invalidate() -> None:
            if cancellation is not None:
                cancellation.set()

        def close() -> None:
            nonlocal closed
            closed = True
            invalidate()
            if job_id is not None:
                self._async_ops.job_mgr.cancel_job(job_id)

        dialog.configuration_changed.connect(invalidate)
        dialog.finished.connect(close)
        dialog.destroyed.connect(close)

        def preview(candidate: object) -> None:
            nonlocal running, job_id, cancellation
            if not isinstance(candidate, ReshapeRequest):
                message = "Reshape preview requires a captured request."
                raise TypeError(message)
            if closed or running or sip.isdeleted(dialog):
                return
            running = True
            request = candidate
            revision = dialog.revision
            cancel_event = Event()
            cancellation = cancel_event
            corr_id = uuid.uuid4().hex
            handled = False

            def stale() -> bool:
                return closed or sip.isdeleted(dialog) or dialog.revision != revision

            def work(
                *,
                progress_cb: Callable[[int], None] | None = None,
                cancel_cb: Callable[[], bool] | None = None,
                **_: object,
            ) -> ReshapePreview | ReshapeError | None:
                def cancelled() -> bool:
                    return cancel_event.is_set() or (cancel_cb is not None and cancel_cb())

                try:
                    return compute_reshape_preview(
                        source,
                        request,
                        progress_cb=progress_cb,
                        cancel_cb=cancelled,
                        corr_id=corr_id,
                    )
                except ReshapeError as reshape_error:
                    return reshape_error

            def result(value: ReshapePreview | ReshapeError | None) -> None:
                nonlocal handled
                if stale():
                    return
                handled = True
                if isinstance(value, ReshapeError):
                    dialog.show_preview_problem(value)
                elif value is None:
                    dialog.show_preview_message(cancelled_message)
                else:
                    dialog.show_preview(value)

            def error(_traceback: str) -> None:
                nonlocal handled
                self._logger.error("ReshapeController: preview worker failed (corr=%s, stage=worker)", corr_id)
                if not stale():
                    handled = True
                    dialog.show_preview_message(failed_message)

            def finished() -> None:
                nonlocal running, job_id, cancellation
                running = False
                job_id = None
                cancellation = None
                if closed or sip.isdeleted(dialog):
                    return
                if not stale() and not handled:
                    dialog.show_preview_message(cancelled_message)
                dialog.set_preview_busy(False)

            dialog.set_preview_busy(True)
            self._logger.info(
                "ReshapeController: reshape requested (corr=%s, operation=preview, source_rows=%d, source_cols=%d, "
                "dimensions=%d, metrics=%d)",
                corr_id,
                len(source),
                len(source.columns),
                len(request.dimensions),
                len(request.metrics),
            )
            job = self._async_ops.run_target_overlay_operation(
                target=dialog.preview_panel,
                runner="pool",
                work=work,
                on_result=result,
                on_error=error,
                on_finished=finished,
                busy_message=busy_message,
                operation_name=operation_name,
                scope="reshape:preview",
                corr_id=corr_id,
                stale_check=stale,
                cancelable=True,
                indeterminate=False,
                timeout_ms=600_000,
                log_error_tracebacks=False,
            )
            job_id = self._async_ops.job_mgr.get_job_id(job if isinstance(job, QObject) else None)
            if job_id is None:
                self._logger.warning("Reshape preview has no cancellable job identity (corr=%s).", corr_id)

        dialog.preview_requested.connect(preview)
