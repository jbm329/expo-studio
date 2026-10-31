"""Controlled preview jobs, real dialog states and overlay facade integration."""

import logging
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, Qt

from expo_jbm329.gui.dialogs.workflows.reshape.reshape_dialog import ReshapeDialog
from expo_jbm329.services.data_operations.dtypes import get_datetime_column_positions, get_numeric_column_positions
from expo_jbm329.services.data_operations.reshape_preview import (
    ReshapeError,
    ReshapeProblem,
)
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.workbench.controllers.reshape_controller import ReshapeController


def setup_preview(source: pd.DataFrame | None = None):
    if source is None:
        source = pd.DataFrame({"clinic": ["B", "A", "B"], "value": [1, 2, 3]})
    dialog = ReshapeDialog(
        parent=None,
        source_dataset=DatasetRef("fixed", "Source", len(source), len(source.columns)),
        source_columns=list(source.columns),
        source_dtypes=[str(dtype) for dtype in source.dtypes],
        numeric_column_positions=get_numeric_column_positions(source),
        datetime_column_positions=get_datetime_column_positions(source),
    )
    dialog.metrics.cellWidget(0, 2).value.setCurrentIndex(1)
    dialog.dimensions.item(0).setCheckState(Qt.CheckState.Checked)
    async_ops = MagicMock()
    job = QObject()
    async_ops.run_target_overlay_operation.return_value = job
    async_ops.job_mgr.get_job_id.return_value = "preview-job"
    controller = ReshapeController(parent_widget=dialog, results=MagicMock(), async_ops=async_ops, logger=MagicMock())
    controller._connect_preview(dialog, source)
    return dialog, source, async_ops, controller, job


def dispatch(dialog, async_ops):
    assert dialog.preview_button.isEnabled()
    dialog.preview_button.click()
    assert not dialog.preview_button.isEnabled()
    return async_ops.run_target_overlay_operation.call_args.kwargs


def test_real_results_overlay_target_and_repeat_requests(caplog):
    dialog, source, async_ops, controller, job = setup_preview()
    caplog.set_level(logging.DEBUG, logger="applogger.service")
    call = dispatch(dialog, async_ops)
    assert call["target"] is dialog.preview_panel
    assert call["runner"] == "pool"
    assert call["cancelable"] is True and call["indeterminate"] is False
    assert call["corr_id"] and call["scope"] == "reshape:preview"
    assert not call["stale_check"]()
    progress = []
    result = call["work"](progress_cb=progress.append)
    assert progress[-1] == 100
    assert any(f"corr={call['corr_id']}, operation=preview" in record.getMessage() for record in caplog.records)
    assert result.frame["Sum value"].tolist() == [4, 2]
    call["on_result"](result)
    assert "Showing 2 of 2 output rows" in dialog.preview_placeholder.text()
    assert dialog.preview_model.rowCount() == 2
    assert dialog.preview_model.columnCount() == 2
    assert dialog.preview_model.data(dialog.preview_model.index(0, 1), Qt.ItemDataRole.EditRole) == 4
    assert not dialog.apply_button.isEnabled()
    call["on_finished"]()
    assert dialog.preview_button.isEnabled()
    assert dialog.apply_button.isEnabled()
    second = dispatch(dialog, async_ops)
    assert call["corr_id"] != second["corr_id"]
    assert source["value"].tolist() == [1, 2, 3]
    second["on_finished"]()
    dialog.close()


def test_median_preview_worker_uses_shared_aggregation_path():
    dialog, source, async_ops, controller, job = setup_preview()
    dialog.metrics.cellWidget(0, 1).setCurrentText("MEDIAN")
    dialog.metrics.item(0, 0).setText("Median value")

    call = dispatch(dialog, async_ops)
    result = call["work"]()

    assert result.frame["Median value"].tolist() == [2.0, 2.0]
    dialog.close()


def test_edits_during_job_cancel_cooperatively_and_discard_all_callbacks():
    dialog, source, async_ops, controller, job = setup_preview()
    call = dispatch(dialog, async_ops)
    result = call["work"]()
    dialog.metrics.item(0, 0).setText("New name")
    assert call["stale_check"]()
    assert call["work"]() is None
    assert "out of date" in dialog.preview_placeholder.text()
    call["on_result"](result)
    call["on_error"]("late exception")
    assert dialog.preview_model is None
    assert "out of date" in dialog.preview_placeholder.text()
    call["on_finished"]()
    assert dialog.preview_button.isEnabled()
    dialog.close()


def test_cancelled_job_and_unexpected_error_restore_controls():
    dialog, source, async_ops, controller, job = setup_preview()
    call = dispatch(dialog, async_ops)
    assert call["work"](cancel_cb=lambda: True) is None
    call["on_result"](None)
    call["on_finished"]()
    assert "cancelled" in dialog.preview_placeholder.text()
    assert dialog.preview_button.isEnabled()
    call = dispatch(dialog, async_ops)
    call["on_error"]("unexpected worker traceback")
    call["on_finished"]()
    assert "Preview failed" in dialog.preview_placeholder.text()
    assert dialog.preview_button.isEnabled()
    controller._logger.error.assert_called()
    assert "unexpected worker traceback" not in repr(controller._logger.error.call_args)
    dialog.close()


def test_expected_error_is_translated_not_a_success_result():
    dialog, source, async_ops, controller, job = setup_preview()
    dialog.metrics.cellWidget(0, 3).text.setText("[clinic] > 'A'")
    dialog.validate_conditions()
    call = dispatch(dialog, async_ops)
    call["on_result"](ReshapeError(ReshapeProblem.VALUE, "clinic"))
    call["on_finished"]()
    assert "cannot be interpreted" in dialog.preview_placeholder.text()
    assert "clinic" in dialog.preview_placeholder.text()
    assert dialog.preview_model is None
    dialog.close()


@pytest.mark.parametrize("delete", [False, True])
def test_close_and_delete_cancel_job_and_guard_late_callbacks(qt_app, delete):
    dialog, source, async_ops, controller, job = setup_preview()
    call = dispatch(dialog, async_ops)
    result = call["work"]()
    if delete:
        dialog.deleteLater()
        qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert sip.isdeleted(dialog)
    else:
        dialog.reject()
    async_ops.job_mgr.cancel_job.assert_called_with("preview-job")
    assert call["stale_check"]()
    assert call["work"]() is None
    call["on_result"](result)
    call["on_error"]("late failure")
    call["on_finished"]()


def test_invalid_configuration_disabled_search_does_not_invalidate_and_changes_do():
    dialog, source, async_ops, controller, job = setup_preview()
    call = dispatch(dialog, async_ops)
    call["on_result"](call["work"]())
    call["on_finished"]()
    revision = dialog.revision
    dialog.dimension_search.setText("absent")
    assert dialog.revision == revision
    dialog.metrics.item(0, 0).setText("clinic")
    assert not dialog.preview_button.isEnabled()
    assert "unique" in dialog.preview_button.toolTip()
    dialog.metrics.item(0, 0).setText("Total")
    assert dialog.preview_button.isEnabled()
    condition = dialog.metrics.cellWidget(0, 3)
    condition.text.setText("[value] > '1'")
    assert not dialog.preview_button.isEnabled()
    assert not dialog.validate_conditions()
    condition.text.setText("[value] > 1")
    assert dialog.validate_conditions()
    assert dialog.preview_button.isEnabled()
    dialog.metrics.selectAll()
    dialog.remove_metric_button.click()
    assert not dialog.preview_button.isEnabled()
    dialog.close()


def test_no_duplicate_dispatch_and_plain_readonly_table():
    dialog, source, async_ops, controller, job = setup_preview()
    request = dialog.capture_request()
    dispatch(dialog, async_ops)
    dialog.preview_requested.emit(request)
    async_ops.run_target_overlay_operation.assert_called_once()
    call = async_ops.run_target_overlay_operation.call_args.kwargs
    call["on_result"](call["work"]())
    call["on_finished"]()
    model = dialog.preview_model
    assert not (model.flags(model.index(0, 0)) & Qt.ItemFlag.ItemIsEditable)
    dialog.close()


def test_ordered_preview_captures_conditions_and_displays_five_full_data_groups(ordered_reshape_case) -> None:
    source, expected, configure = ordered_reshape_case
    original = source.copy(deep=True)
    dialog, source, async_ops, controller, job = setup_preview(source)
    configure(dialog)
    request = dialog.capture_request()
    assert [metric.order_position for metric in request.metrics] == [None, 2, 3]
    assert request.metrics[1].condition and request.metrics[2].condition
    call = dispatch(dialog, async_ops)
    progress: list[int] = []
    preview = call["work"](progress_cb=progress.append)
    assert preview.request == request and preview.total_rows == 7
    pd.testing.assert_frame_equal(preview.frame, expected.head(5))
    assert progress[0] == 0 and progress[-1] == 100
    call["on_result"](preview)
    call["on_finished"]()
    assert dialog.preview_model.rowCount() == 5 and dialog.preview_model.columnCount() == 4
    assert dialog.preview_model.data(dialog.preview_model.index(0, 2), Qt.ItemDataRole.EditRole) == "early G"
    assert dialog.preview_model.data(dialog.preview_model.index(0, 3), Qt.ItemDataRole.EditRole) == "end G"
    assert "Showing 5 of 7 output rows" in dialog.preview_placeholder.text()
    assert dialog.apply_button.isEnabled()
    pd.testing.assert_frame_equal(source, original)
    dialog.close()


def test_order_edits_cancel_stale_preview_and_old_results_cannot_replace_new_preview(ordered_reshape_case) -> None:
    source, expected, configure = ordered_reshape_case
    dialog, source, async_ops, controller, job = setup_preview(source)
    configure(dialog)
    initial = dispatch(dialog, async_ops)
    initial["on_result"](initial["work"]())
    initial["on_finished"]()
    assert dialog.preview_model is not None
    stale_call = dispatch(dialog, async_ops)
    stale_result = stale_call["work"]()
    ordering = dialog.metrics.cellWidget(1, 2).order
    ordering.setCurrentIndex(ordering.findData(3))
    assert stale_call["stale_check"]()
    assert stale_call["work"]() is None
    assert dialog.preview_table.isHidden() and "out of date" in dialog.preview_placeholder.text()
    stale_call["on_result"](stale_result)
    stale_call["on_error"]("stale ordering failure")
    assert "out of date" in dialog.preview_placeholder.text()
    stale_call["on_finished"]()
    updated_call = dispatch(dialog, async_ops)
    updated = updated_call["work"]()
    expected = expected.head(5).copy()
    expected["Earliest status"] = pd.Series(["late G", None, None, "late D", "late C"], dtype="string")
    pd.testing.assert_frame_equal(updated.frame, expected)
    updated_call["on_result"](updated)
    updated_call["on_finished"]()
    new_model = dialog.preview_model
    stale_call["on_result"](stale_result)
    assert dialog.preview_model is new_model
    assert new_model.data(new_model.index(0, 2), Qt.ItemDataRole.EditRole) == "late G"
    dialog.close()


@pytest.mark.parametrize("outcome", ["cancel", "error", "close"])
def test_ordered_preview_preserves_cancel_error_and_close_lifecycle(ordered_reshape_case, outcome: str) -> None:
    source, expected, configure = ordered_reshape_case
    original = source.copy(deep=True)
    dialog, source, async_ops, controller, job = setup_preview(source)
    configure(dialog)
    call = dispatch(dialog, async_ops)
    if outcome == "cancel":
        assert call["work"](cancel_cb=lambda: True) is None
        call["on_result"](None)
        call["on_finished"]()
        assert "cancelled" in dialog.preview_placeholder.text()
    elif outcome == "error":
        call["on_error"]("ordered worker failure")
        call["on_finished"]()
        assert "Preview failed" in dialog.preview_placeholder.text()
    else:
        result = call["work"]()
        dialog.reject()
        async_ops.job_mgr.cancel_job.assert_called_with("preview-job")
        assert call["stale_check"]() and call["work"]() is None
        call["on_result"](result)
        call["on_finished"]()
    assert dialog.preview_model is None
    if outcome != "close":
        assert dialog.preview_button.isEnabled() and dialog.apply_button.isEnabled()
    pd.testing.assert_frame_equal(source, original)
    dialog.close()
