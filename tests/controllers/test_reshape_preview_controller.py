"""Controlled preview jobs, real dialog states and overlay facade integration."""

from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, Qt

from expo_jbm329.gui.dialogs.workflows.reshape.reshape_dialog import ReshapeDialog
from expo_jbm329.services.data_operations.reshape_preview import (
    ReshapeError,
    ReshapeProblem,
)
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.workbench.controllers.reshape_controller import ReshapeController


def setup_preview():
    source = pd.DataFrame({"clinic": ["B", "A", "B"], "value": [1, 2, 3]})
    dialog = ReshapeDialog(
        parent=None,
        source_dataset=DatasetRef("fixed", "Source", 3, 2),
        source_columns=list(source.columns),
        source_dtypes=[str(dtype) for dtype in source.dtypes],
        numeric_column_positions=(1,),
        datetime_column_positions=(),
    )
    dialog.metrics.cellWidget(0, 2).setCurrentIndex(1)
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


def test_real_results_overlay_target_and_repeat_requests():
    dialog, source, async_ops, controller, job = setup_preview()
    call = dispatch(dialog, async_ops)
    assert call["target"] is dialog.preview_panel
    assert call["runner"] == "pool"
    assert call["cancelable"] is True and call["indeterminate"] is False
    assert call["corr_id"] and call["scope"] == "reshape:preview"
    assert not call["stale_check"]()
    progress = []
    result = call["work"](progress_cb=progress.append)
    assert progress[-1] == 100
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
