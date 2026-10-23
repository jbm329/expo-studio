"""Coordinate condition dialogs and cancellable value-page jobs."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from PyQt6 import sip
from PyQt6.QtCore import QT_TR_NOOP
from PyQt6.QtWidgets import QDialog

from expo_jbm329.gui.dialogs.workflows.reshape.condition_dialog import ConditionDialog
from expo_jbm329.gui.dialogs.workflows.reshape.condition_value_picker import ConditionValuePicker
from expo_jbm329.services.data_operations.reshape_condition_values import (
    ValuePage,
    ValuePageRequest,
    ValueRequestCancelledError,
    distinct_value_page,
)
from expo_jbm329.services.data_operations.reshape_conditions import (
    ConditionError,
    ConditionProblem,
    condition_columns,
)
from expo_jbm329.utils.i18n_utils import translate

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

    import pandas as pd
    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.gui.dialogs.workflows.reshape.condition_editor import ConditionEditor
    from expo_jbm329.workbench.controllers.async_operation_controller import AsyncOperationController


class ReshapeConditionController:
    """Keep DataFrame access and async lifetime management out of the widgets."""

    TR_LOADING = QT_TR_NOOP("Loading condition values")
    TR_FAILED = QT_TR_NOOP("Could not load values. Change the column or search to retry.")
    TR_UNSUPPORTED = QT_TR_NOOP(
        "This column contains unsupported values. Select a column with scalar text, numbers or dates."
    )
    TR_AMBIGUOUS = QT_TR_NOOP(
        "Different values have identical condition text. Convert the column to an unambiguous type first."
    )

    def __init__(self, async_ops: AsyncOperationController, logger: logging.Logger) -> None:
        """Reuse the workbench's async facade and UI logger."""
        self._async_ops = async_ops
        self._logger = logger

    @staticmethod
    def _tr(text: str) -> str:
        return translate("ReshapeConditionController", text)

    def open_dialog(self, parent: QWidget, editor: ConditionEditor, source: pd.DataFrame) -> None:
        """Open a builder bound to one metric and its captured source DataFrame."""
        initial = editor.restorable_group()
        dialog = ConditionDialog(
            parent=parent,
            columns=condition_columns(list(source.columns)),
            initial=initial,
            replaces_manual_text=bool(editor.text.text()) and initial is None,
        )
        closed = False
        jobs: dict[ConditionValuePicker, str] = {}
        session_id = uuid.uuid4().hex
        # Capture translated strings on the GUI thread before workers run.
        loading_text = self._tr(self.TR_LOADING)
        errors = {
            ConditionProblem.UNSUPPORTED_VALUE: self._tr(self.TR_UNSUPPORTED),
            ConditionProblem.AMBIGUOUS_VALUE: self._tr(self.TR_AMBIGUOUS),
            ConditionProblem.INVALID_RULE: self._tr(self.TR_FAILED),
        }
        failed_text = self._tr(self.TR_FAILED)

        def invalidate(candidate: object) -> None:
            if not isinstance(candidate, ConditionValuePicker):
                message = "Condition request owner must be a value picker."
                raise TypeError(message)
            job_id = jobs.pop(candidate, None)
            if job_id is not None:
                self._async_ops.job_mgr.cancel_job(job_id)

        def request_page(candidate: object, payload: object) -> None:
            if not isinstance(candidate, ConditionValuePicker) or not isinstance(payload, ValuePageRequest):
                message = "Invalid condition page request."
                raise TypeError(message)
            picker, request = candidate, payload
            invalidate(picker)
            generation = picker.generation

            def stale() -> bool:
                return closed or sip.isdeleted(picker) or picker.generation != generation

            def work(
                *,
                cancel_cb: Callable[[], bool] | None = None,
                **_: object,
            ) -> ValuePage | ConditionProblem | None:
                try:
                    return distinct_value_page(source, request, cancel_cb=cancel_cb)
                except ValueRequestCancelledError:
                    return None
                except ConditionError as exc:
                    self._logger.warning(
                        "Reshape condition value request rejected (column=%s, problem=%s, session=%s).",
                        request.column_position,
                        exc.problem.value,
                        session_id,
                    )
                    return exc.problem

            def result(value: ValuePage | ConditionProblem | None) -> None:
                if stale():
                    return
                if isinstance(value, ValuePage):
                    picker.receive_page(value)
                elif isinstance(value, ConditionProblem):
                    picker.show_error(errors[value])
                else:
                    picker.show_error(failed_text)

            def error(_traceback: str) -> None:
                if not stale():
                    picker.show_error(failed_text)

            def finished() -> None:
                if not stale():
                    jobs.pop(picker, None)
                    if picker.loading:
                        picker.show_error(failed_text)

            job = self._async_ops.run_operation(
                work=work,
                on_result=result,
                on_error=error,
                on_finished=finished,
                busy_message=loading_text,
                scope=f"reshape-condition:{session_id}:{id(picker)}",
                runner="pool",
                foreground=False,
                stale_check=stale,
                show_overlay=False,
                show_status_progress=False,
                show_started_in_status=False,
                corr_id=uuid.uuid4().hex,
            )
            job_id = self._async_ops.job_mgr.get_job_id(job)
            if job_id is not None:
                jobs[picker] = job_id
            else:
                self._logger.warning("Reshape condition page job has no cancellation identifier.")

        def close() -> None:
            nonlocal closed
            closed = True
            for picker in tuple(jobs):
                invalidate(picker)

        dialog.page_requested.connect(request_page)
        dialog.request_invalidated.connect(invalidate)
        dialog.finished.connect(close)
        try:
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
            if accepted and not sip.isdeleted(editor):
                group = dialog.applied_group
                if group is None:
                    message = "Accepted condition builder has no complete rule group."
                    raise ValueError(message)
                editor.apply_group(group)
        finally:
            close()
            if not sip.isdeleted(dialog):
                dialog.deleteLater()
