"""Asynchronous whole-row actions for existing result datasets."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from PyQt6 import sip
from PyQt6.QtCore import QT_TR_NOOP, QObject

from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.services.data_operations.duplicates import remove_duplicate_rows
from expo_jbm329.utils.i18n_utils import translate, translate_fmt
from expo_jbm329.utils.models import DataFrameModel

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd
    from PyQt6.QtWidgets import QTableView, QWidget

    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.controllers.async_operation_controller import AsyncOperationController


class ResultTabRowActions:
    """Orchestrate row operations while the host owns tab identity and Undo."""

    TR_OPERATION = QT_TR_NOOP("remove duplicate rows")
    TR_BUSY = QT_TR_NOOP('Removing duplicate rows from dataset "{dataset}"')
    TR_REMOVED = QT_TR_NOOP('Removed {count} duplicate rows from dataset "{dataset}".')
    TR_UNCHANGED = QT_TR_NOOP('No duplicate rows found in dataset "{dataset}".')
    TR_FAILURE = QT_TR_NOOP("Failure")
    TR_COULD_NOT_PERFORM = QT_TR_NOOP("Could not perform the operation:\n{error}")

    __slots__ = (
        "__weakref__",
        "_apply_new_dataframe",
        "_async_ops",
        "_dialogs",
        "_logger",
        "_parent",
        "_resolve_target",
        "_running",
        "_set_status",
    )

    def __init__(
        self,
        *,
        parent: QWidget,
        dialogs: DialogService | None,
        logger: logging.Logger | None,
        async_ops: AsyncOperationController,
        resolve_target: Callable[[str], tuple[QTableView, pd.DataFrame, str] | None],
        apply_new_dataframe: Callable[[QTableView, pd.DataFrame], bool],
        set_status: Callable[[str, int | None], None],
    ) -> None:
        """Initialize row actions with explicit host callbacks.

        Args:
            parent: Parent for custom-service error dialogs.
            dialogs: Dialog service, defaulting to QtDialogService.
            logger: Optional application logger.
            async_ops: Existing asynchronous operation controller.
            resolve_target: Resolve a stable tab ID to its ready view, current
                dataframe and title, or None if unavailable. Called only on
                the GUI thread.
            apply_new_dataframe: Replace data using the host's existing
                best-effort Undo path. Return True only on successful apply;
                report handled apply errors through the host's dialog service.
            set_status: Display nonmodal completion feedback.
        """
        self._parent = parent
        self._dialogs = dialogs if dialogs is not None else QtDialogService()
        self._logger = logger if logger is not None else logging.getLogger("applogger.ui")
        self._async_ops = async_ops
        self._resolve_target = resolve_target
        self._apply_new_dataframe = apply_new_dataframe
        self._set_status = set_status
        self._running: set[str] = set()

    @staticmethod
    def _tr(text: str) -> str:
        return translate("ResultTabRowActions", text)

    @staticmethod
    def _tr_fmt(text: str, **kwargs: object) -> str:
        return translate_fmt("ResultTabRowActions", text, **kwargs)

    def is_running(self, tab_id: str) -> bool:
        """Return whether duplicate removal is already running for a tab."""
        return tab_id in self._running

    def _fail(self, error: str) -> None:
        self._dialogs.critical(
            parent=self._parent,
            title=self._tr(self.TR_FAILURE),
            text=self._tr_fmt(self.TR_COULD_NOT_PERFORM, error=error),
        )

    def remove_duplicates(self, tab_id: str) -> None:
        """Remove duplicates asynchronously from one stable, ready result tab.

        Args:
            tab_id: Identifier of the targeted tab, not the current tab index.
        """
        if self.is_running(tab_id):
            self._logger.debug("ResultTabRowActions: duplicate dispatch ignored for tab=%s.", tab_id)
            return
        target = self._resolve_target(tab_id)
        if target is None:
            self._logger.debug("ResultTabRowActions: target unavailable for tab=%s.", tab_id)
            return
        view, source, title = target
        if sip.isdeleted(view):
            return
        model = view.model()
        if not isinstance(model, DataFrameModel) or model.data_frame() is not source:
            self._logger.warning("ResultTabRowActions: target model does not match tab=%s.", tab_id)
            return

        row_count = len(source)
        changed = False

        def _mark_changed(*_: object) -> None:
            nonlocal changed
            changed = True

        # Read-only models replace frames; dataChanged also guards in-place edits.
        connections = [
            model.modelAboutToBeReset.connect(_mark_changed),
            model.dataChanged.connect(_mark_changed),
        ]
        self._running.add(tab_id)
        corr_id = uuid.uuid4().hex

        def _is_stale() -> bool:
            if changed or sip.isdeleted(view) or sip.isdeleted(model):
                return True
            current = self._resolve_target(tab_id)
            return (
                current is None
                or current[0] is not view
                or current[1] is not source
                or view.model() is not model
                or model.data_frame() is not source
            )

        def _work(
            *,
            cancel_cb: Callable[[], bool] | None = None,
            **_: object,
        ) -> pd.DataFrame | None:
            if cancel_cb is not None and cancel_cb():
                return None
            result = remove_duplicate_rows(source)
            if cancel_cb is not None and cancel_cb():
                return None
            return result

        def _apply_result(result: pd.DataFrame | None) -> None:
            if result is None or _is_stale():
                return
            current = self._resolve_target(tab_id)
            if current is None:
                return
            current_title = current[2]
            removed = row_count - len(result)
            if removed == 0:
                self._set_status(self._tr_fmt(self.TR_UNCHANGED, dataset=current_title), 6000)
                return
            try:
                applied = self._apply_new_dataframe(view, result)
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                self._logger.exception("ResultTabRowActions: apply failed (tab=%s corr=%s).", tab_id, corr_id)
                self._fail(str(error))
                return
            if applied:
                self._set_status(self._tr_fmt(self.TR_REMOVED, count=removed, dataset=current_title), 6000)
                self._logger.info(
                    "ResultTabRowActions: removed %s duplicate rows (tab=%s corr=%s).", removed, tab_id, corr_id
                )

        def _on_error(error: str) -> None:
            if not _is_stale():
                self._fail(error)

        def _finished() -> None:
            self._running.discard(tab_id)
            for connection in connections:
                QObject.disconnect(connection)
            connections.clear()

        try:
            self._async_ops.run_dataframe_operation(
                view=view,
                runner="pool",
                work=_work,
                apply_result=_apply_result,
                busy_message=self._tr_fmt(self.TR_BUSY, dataset=title),
                scope=f"remove_duplicates:{tab_id}",
                operation_name=self._tr(self.TR_OPERATION),
                on_error=_on_error,
                on_finished=_finished,
                stale_check=_is_stale,
                timeout_ms=0,
                corr_id=corr_id,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            _finished()
            self._logger.exception("ResultTabRowActions: could not start operation (tab=%s corr=%s).", tab_id, corr_id)
            _on_error(str(error))
