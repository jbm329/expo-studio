"""Centralized async operation controller with BusyOverlay integration.

This controller standardizes:
    • JobManager integration
    • BusyOverlay lifecycle
    • progress wiring
    • error handling
    • stale-safe guards
    • async result dispatching
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal, Protocol, TypeVar, cast

from PyQt6.QtCore import QT_TR_NOOP, QObject, QTimer
from PyQt6.QtWidgets import QApplication, QTableView, QWidget

from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.utils.i18n_utils import tr, tr_fmt

if TYPE_CHECKING:
    from collections.abc import Callable

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.services.job_manager import JobManager
    from expo_jbm329.workbench.controllers.busy_overlay_controller import (
        BusyOverlayController,
    )

T = TypeVar("T")
RunnerKind = Literal["pool", "thread"]


class _Signal(Protocol):
    """Protocol for Qt-like signals used by async job handles."""

    def connect(self, slot: Callable[..., object]) -> object:
        """Connect a slot to the signal."""
        ...


class _AsyncJobHandle(Protocol):
    """Signal contract exposed by JobManager worker handles."""

    progress: _Signal
    result: _Signal
    error: _Signal
    finished: _Signal


class AsyncOperationController:
    """Centralized async operation runner."""

    # ------------------------------------------------------------------
    # i18n markers
    # ------------------------------------------------------------------

    TR_FAILURE = QT_TR_NOOP("Failure")
    TR_OPERATION_FAILED = QT_TR_NOOP("Could not {operation}.\n\n{error}")
    TR_COULD_NOT_PERFORM = QT_TR_NOOP("Could not perform the operation:\n{error}")

    # ------------------------------------------------------------------
    # i18n helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tr(text: str) -> str:
        return tr("AsyncOperationController", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: object) -> str:
        return tr_fmt(
            "AsyncOperationController",
            text,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    __slots__ = (
        "_busy",
        "_dialogs",
        "_job_mgr",
        "_logger",
        "_parent",
    )

    def __init__(
        self,
        *,
        parent: QWidget,
        job_mgr: JobManager,
        busy: BusyOverlayController,
        dialogs: DialogService | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize AsyncOperationController.

        Args:
            parent: Parent widget.
            job_mgr: Shared JobManager instance.
            busy: BusyOverlayController instance.
            dialogs: Dialog service.
            logger: Logger instance.
        """
        self._parent = parent

        self._job_mgr = job_mgr

        self._busy = busy

        self._dialogs = dialogs if dialogs is not None else QtDialogService()

        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")

    # ==================================================================
    # Properties
    # ==================================================================

    @property
    def job_mgr(self) -> JobManager:
        """Return the shared JobManager instance."""
        return self._job_mgr

    # ==================================================================
    # Public API
    # ==================================================================
    def run_operation(
        self,
        *,
        work: Callable[..., T],
        on_result: Callable[[T], None],
        busy_message: str,
        scope: str,
        target: QWidget | None = None,
        runner: RunnerKind = "pool",
        operation_name: str | None = None,
        on_finished: Callable[[], None] | None = None,
        on_progress: Callable[[int], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        timeout_ms: int = 60_000,
        indeterminate: bool = True,
        cancelable: bool = False,
        show_overlay: bool = False,
        auto_hide_overlay: bool = True,
        foreground: bool = True,
        suppress_error_dialog: bool = False,
        stale_check: Callable[[], bool] | None = None,
        show_status_progress: bool = False,
        show_started_in_status: bool = False,
        corr_id: str | None = None,
    ) -> QObject:
        """Run an async operation through the centralized workbench facade.

        This is the generic entry point for async work. It supports both
        ThreadPoolExecutor-backed jobs and QThread/Worker-backed jobs while
        keeping result, error, progress, stale-check, and overlay handling in
        one place.

        Args:
            work: Background callable. JobManager may inject progress_cb,
                cancel_cb, job_id, and job_scope depending on callable signature.
            on_result: GUI-thread callback receiving the result payload.
            busy_message: User-facing operation message.
            scope: Job scope used for logging/cancellation grouping.
            target: Optional widget to cover with BusyOverlay.
            runner: Execution backend: "pool" or "thread".
            operation_name: Human-readable operation name for errors.
            on_finished: Optional callback invoked when the worker finishes.
            on_progress: Optional callback invoked on progress updates.
            on_error: Optional custom error handler. If provided and it returns
                normally, the default error dialog is suppressed.
            timeout_ms: Overlay watchdog timeout.
            indeterminate: Whether progress is indeterminate.
            cancelable: Whether the operation supports cooperative cancellation.
            show_overlay: Whether to show BusyOverlay over target.
            auto_hide_overlay: Whether this method should hide overlay automatically.
            foreground: Whether the job is a foreground job.
            suppress_error_dialog: Suppress default error dialogs.
            stale_check: Optional callback. If True, result is ignored.
            show_status_progress: Delegate status-progress UI to JobManager for now.
            show_started_in_status: Delegate started status to JobManager for now.
            corr_id: Correlation ID.

        Returns:
            Job handle returned by JobManager.
        """
        job_obj = self._start_job(
            runner=runner,
            work=work,
            busy_message=busy_message,
            scope=scope,
            foreground=foreground,
            indeterminate=indeterminate,
            show_status_progress=show_status_progress,
            show_started_in_status=show_started_in_status,
            corr_id=corr_id,
        )
        job = cast("_AsyncJobHandle", job_obj)

        job_id = self._job_mgr.get_job_id(job_obj)

        def _handle_overlay_cancel() -> None:
            """Handle cancel button clicks from the overlay."""
            if not cancelable:
                return

            if job_id is None:
                self._logger.warning(
                    "AsyncOperationController: cancel requested but no job_id was available (scope=%s corr=%s).",
                    scope,
                    corr_id,
                )
                return

            cancelled = self._job_mgr.cancel_job(job_id)
            if cancelled:
                self._logger.info(
                    "AsyncOperationController: cancel requested from overlay (scope=%s corr=%s job_id=%s).",
                    scope,
                    corr_id,
                    job_id,
                )
            else:
                self._logger.warning(
                    "AsyncOperationController: cancel requested from overlay but job was not tracked "
                    "(scope=%s corr=%s job_id=%s).",
                    scope,
                    corr_id,
                    job_id,
                )

        if show_overlay and target is not None:
            self._busy.show(
                target,
                message=busy_message,
                indeterminate=indeterminate,
                timeout_ms=timeout_ms,
                cancelable=cancelable,
                on_cancel=_handle_overlay_cancel if cancelable else None,
            )

        def _hide_overlay_later() -> None:
            if show_overlay and auto_hide_overlay and target is not None:
                QTimer.singleShot(0, lambda: self._busy.hide(target))

        def _handle_progress(value: int) -> None:
            try:
                value_i = int(value)

                if show_overlay and target is not None:
                    self._busy.set_progress(target, value_i)

                if on_progress is not None:
                    on_progress(value_i)

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
            ):
                self._logger.exception(
                    "AsyncOperationController: progress handler failed (scope=%s corr=%s).",
                    scope,
                    corr_id,
                )

        def _handle_result(result: T) -> None:
            try:
                is_stale = stale_check() if stale_check is not None else False
                if is_stale:
                    self._logger.debug(
                        "AsyncOperationController: stale result ignored (scope=%s corr=%s).",
                        scope,
                        corr_id,
                    )
                    return

                on_result(result)

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
                self._logger.exception(
                    "AsyncOperationController: result handler failed (scope=%s corr=%s).",
                    scope,
                    corr_id,
                )

                if not suppress_error_dialog:
                    self._show_error_dialog(
                        operation_name=operation_name,
                        error=str(e),
                    )

            finally:
                _hide_overlay_later()

        def _handle_error(tb: str) -> None:
            try:
                self._logger.error(
                    "AsyncOperationController: async job failed (scope=%s corr=%s).\n%s",
                    scope,
                    corr_id,
                    tb,
                )

                if on_error is not None:
                    try:
                        on_error(tb)
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
                    ):
                        self._logger.exception(
                            "AsyncOperationController: custom error handler failed (scope=%s corr=%s).",
                            scope,
                            corr_id,
                        )
                    else:
                        return

                if not suppress_error_dialog:
                    self._show_error_dialog(
                        operation_name=operation_name,
                        error=tb,
                    )

            finally:
                _hide_overlay_later()

        def _handle_finished() -> None:
            try:
                if on_finished is not None:
                    on_finished()

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
            ):
                self._logger.exception(
                    "AsyncOperationController: finished handler failed (scope=%s corr=%s).",
                    scope,
                    corr_id,
                )

            finally:
                _hide_overlay_later()

        job.progress.connect(_handle_progress)
        job.result.connect(_handle_result)
        job.error.connect(_handle_error)
        job.finished.connect(_handle_finished)

        return job_obj

    def run_with_overlay(
        self,
        *,
        view: QTableView,
        work: Callable[..., T],
        on_result: Callable[[T], None],
        on_finished: Callable[[], None] | None = None,
        on_progress: Callable[[int], None] | None = None,
        busy_message: str,
        scope: str,
        operation_name: str | None = None,
        on_error: Callable[[str], None] | None = None,
        timeout_ms: int = 60_000,
        indeterminate: bool = True,
        cancelable: bool = False,
        show_overlay: bool = True,
        auto_hide_overlay: bool = True,
        foreground: bool = True,
        suppress_error_dialog: bool = False,
        stale_check: Callable[[], bool] | None = None,
        show_status_progress: bool = False,
        show_started_in_status: bool = False,
        corr_id: str | None = None,
        runner: RunnerKind = "pool",
    ) -> QObject:
        """Run async work with BusyOverlay handling for a QTableView."""
        return self.run_operation(
            target=self._target_for_view(view),
            work=work,
            on_result=on_result,
            on_finished=on_finished,
            on_progress=on_progress,
            busy_message=busy_message,
            scope=scope,
            runner=runner,
            operation_name=operation_name,
            on_error=on_error,
            timeout_ms=timeout_ms,
            indeterminate=indeterminate,
            cancelable=cancelable,
            show_overlay=show_overlay,
            auto_hide_overlay=auto_hide_overlay,
            foreground=foreground,
            suppress_error_dialog=suppress_error_dialog,
            stale_check=stale_check if stale_check is not None else lambda: self._is_stale(view),
            show_status_progress=show_status_progress,
            show_started_in_status=show_started_in_status,
            corr_id=corr_id,
        )

    def run_dataframe_operation(
        self,
        *,
        view: QTableView,
        work: Callable[..., T],
        apply_result: Callable[[T], None],
        busy_message: str,
        scope: str,
        operation_name: str | None = None,
        on_finished: Callable[[], None] | None = None,
        on_progress: Callable[[int], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        timeout_ms: int = 60_000,
        indeterminate: bool = True,
        cancelable: bool = False,
        foreground: bool = True,
        suppress_error_dialog: bool = False,
        stale_check: Callable[[], bool] | None = None,
        show_status_progress: bool = False,
        show_started_in_status: bool = False,
        corr_id: str | None = None,
        runner: RunnerKind = "pool",
    ) -> QObject:
        """Run a DataFrame operation with overlay kept during GUI apply."""
        target = self._target_for_view(view)

        self._busy.show(
            target,
            message=busy_message,
            indeterminate=indeterminate,
            timeout_ms=timeout_ms,
            cancelable=False,
            on_cancel=None,
        )

        def _apply_and_finalize(result: T) -> None:
            try:
                is_stale = stale_check() if stale_check is not None else self._is_stale(view)
                if is_stale:
                    self._logger.debug(
                        "AsyncOperationController: stale view detected (scope=%s corr=%s).",
                        scope,
                        corr_id,
                    )
                    return

                apply_result(result)
                QApplication.processEvents()

            finally:
                QTimer.singleShot(0, lambda: self._busy.hide(target))

        def _error_wrapper(tb: str) -> None:
            try:
                if on_error is not None:
                    on_error(tb)
                    return

                if not suppress_error_dialog:
                    self._show_error_dialog(
                        operation_name=operation_name,
                        error=tb,
                    )

            finally:
                QTimer.singleShot(0, lambda: self._busy.hide(target))

        return self.run_operation(
            target=target,
            work=work,
            on_result=_apply_and_finalize,
            on_finished=on_finished,
            on_progress=on_progress,
            busy_message=busy_message,
            scope=scope,
            runner=runner,
            operation_name=operation_name,
            on_error=_error_wrapper,
            timeout_ms=timeout_ms,
            indeterminate=indeterminate,
            cancelable=cancelable,
            show_overlay=False,
            auto_hide_overlay=False,
            foreground=foreground,
            suppress_error_dialog=True,
            stale_check=stale_check if stale_check is not None else lambda: self._is_stale(view),
            show_status_progress=show_status_progress,
            show_started_in_status=show_started_in_status,
            corr_id=corr_id,
        )

    def run_dataframe_creation_operation(
        self,
        *,
        view: QTableView,
        work: Callable[..., T],
        create_result: Callable[[T], None],
        busy_message: str,
        scope: str,
        operation_name: str | None = None,
        on_finished: Callable[[], None] | None = None,
        on_progress: Callable[[int], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        timeout_ms: int = 60_000,
        indeterminate: bool = True,
        cancelable: bool = False,
        foreground: bool = True,
        suppress_error_dialog: bool = False,
        stale_check: Callable[[], bool] | None = None,
        show_status_progress: bool = False,
        show_started_in_status: bool = False,
        corr_id: str | None = None,
        runner: RunnerKind = "pool",
    ) -> object:
        """Run async DataFrame-producing work that creates a new result tab."""
        target = self._target_for_view(view)

        self._busy.show(
            target,
            message=busy_message,
            indeterminate=indeterminate,
            timeout_ms=timeout_ms,
            cancelable=False,
            on_cancel=None,
        )

        def _create_and_finalize(result: T) -> None:
            try:
                is_stale = stale_check() if stale_check is not None else self._is_stale(view)
                if is_stale:
                    self._logger.debug(
                        "AsyncOperationController: stale view detected (scope=%s corr=%s).",
                        scope,
                        corr_id,
                    )
                    return

                create_result(result)
                QApplication.processEvents()

            finally:
                QTimer.singleShot(0, lambda: self._busy.hide(target))

        def _error_wrapper(tb: str) -> None:
            try:
                if on_error is not None:
                    on_error(tb)
                    return

                if not suppress_error_dialog:
                    self._show_error_dialog(
                        operation_name=operation_name,
                        error=tb,
                    )

            finally:
                QTimer.singleShot(0, lambda: self._busy.hide(target))

        return self.run_operation(
            target=target,
            work=work,
            on_result=_create_and_finalize,
            on_finished=on_finished,
            on_progress=on_progress,
            busy_message=busy_message,
            scope=scope,
            runner=runner,
            operation_name=operation_name,
            on_error=_error_wrapper,
            timeout_ms=timeout_ms,
            indeterminate=indeterminate,
            cancelable=cancelable,
            show_overlay=False,
            auto_hide_overlay=False,
            foreground=foreground,
            suppress_error_dialog=True,
            stale_check=stale_check if stale_check is not None else lambda: self._is_stale(view),
            show_status_progress=show_status_progress,
            show_started_in_status=show_started_in_status,
            corr_id=corr_id,
        )

    def run_target_overlay_operation(
        self,
        *,
        target: QWidget,
        work: Callable[..., T],
        on_result: Callable[[T], None],
        busy_message: str,
        scope: str,
        operation_name: str | None = None,
        on_finished: Callable[[], None] | None = None,
        on_progress: Callable[[int], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        timeout_ms: int = 60_000,
        indeterminate: bool = True,
        cancelable: bool = False,
        foreground: bool = True,
        suppress_error_dialog: bool = False,
        stale_check: Callable[[], bool] | None = None,
        show_status_progress: bool = False,
        show_started_in_status: bool = False,
        corr_id: str | None = None,
        runner: RunnerKind = "thread",
    ) -> object:
        """Run an async operation with overlay on any QWidget target.

        Intended for first-load file operations, exports, SQL result area
        operations, or any workflow where there may be no QTableView yet.
        """
        return self.run_operation(
            target=target,
            work=work,
            on_result=on_result,
            on_finished=on_finished,
            on_progress=on_progress,
            busy_message=busy_message,
            scope=scope,
            runner=runner,
            operation_name=operation_name,
            on_error=on_error,
            timeout_ms=timeout_ms,
            indeterminate=indeterminate,
            cancelable=cancelable,
            show_overlay=True,
            auto_hide_overlay=True,
            foreground=foreground,
            suppress_error_dialog=suppress_error_dialog,
            stale_check=stale_check,
            show_status_progress=show_status_progress,
            show_started_in_status=show_started_in_status,
            corr_id=corr_id,
        )

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _start_job(
        self,
        *,
        runner: RunnerKind,
        work: Callable[..., T],
        busy_message: str,
        scope: str,
        foreground: bool,
        indeterminate: bool,
        show_status_progress: bool,
        show_started_in_status: bool,
        corr_id: str | None,
    ) -> QObject:
        """Start a job using the selected backend.

        JobManager is treated as execution infrastructure here.
        AsyncOperationController owns UI behavior for facade-based jobs.
        """
        _ = busy_message
        _ = foreground
        _ = indeterminate
        _ = show_status_progress
        _ = show_started_in_status

        if runner == "thread":
            return self._job_mgr.run(
                work,
                scope=scope,
                corr_id=corr_id,
            )

        return self._job_mgr.run_pool(
            work,
            scope=scope,
            corr_id=corr_id,
        )

    def _show_error_dialog(
        self,
        *,
        operation_name: str | None,
        error: str,
    ) -> None:
        """Show a standardized async operation error dialog."""
        if operation_name:
            text = self._tr_fmt(
                self.TR_OPERATION_FAILED,
                operation=operation_name,
                error=error,
            )
        else:
            text = self._tr_fmt(
                self.TR_COULD_NOT_PERFORM,
                error=error,
            )

        self._dialogs.critical(
            parent=self._parent,
            title=self._tr(self.TR_FAILURE),
            text=text,
        )

    @staticmethod
    def _target_for_view(view: QTableView) -> QWidget:
        """Return the best overlay target for a table view."""
        viewport = view.viewport()
        return viewport if viewport is not None else view

    @staticmethod
    def _is_stale(view: QTableView) -> bool:
        """Return True if the view is stale/deleted."""
        try:
            return view is None or view.model() is None
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
        ):
            return True
