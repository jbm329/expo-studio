"""Apply uses a captured request and the standard pending result-tab lifecycle."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QObject, Qt
from PyQt6.QtWidgets import QDialog, QWidget

from expo_jbm329.gui.dialogs.workflows.reshape.reshape_dialog import ReshapeDialog
from expo_jbm329.services.data_operations.reshape_preview import (
    ReshapeError,
    ReshapeFunction,
    ReshapeMetric,
    ReshapeRequest,
)
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.workbench.controllers.reshape_controller import ReshapeController


@pytest.fixture
def apply_setup():
    source = pd.DataFrame({"group": list("gfedcba") * 2, "value": range(14)})
    results = MagicMock()
    results.active_tab_id.return_value = "source"
    results.tabs_by_id = {
        "source": SimpleNamespace(tab_id="source", title="Original", is_ready=True, df=source),
    }
    view = QWidget()

    def create(**kwargs):
        results.tabs_by_id["pending"] = SimpleNamespace(is_pending=True)
        return SimpleNamespace(tab_id="pending", view=view)

    def fulfill(tab_id, frame):
        results.tabs_by_id[tab_id] = SimpleNamespace(is_pending=False, df=frame)

    results.create_pending_tab.side_effect = create
    results.fulfill_pending_tab.side_effect = fulfill
    results.remove_pending_tab.side_effect = lambda tab_id: results.tabs_by_id.pop(tab_id, None)
    async_ops = MagicMock()
    job = QObject()
    async_ops.run_target_overlay_operation.return_value = job
    async_ops.job_mgr.get_job_id.return_value = "reshape-job"
    controller = ReshapeController(parent_widget=view, results=results, async_ops=async_ops, logger=MagicMock())
    request = ReshapeRequest((0,), (ReshapeMetric("Total", ReshapeFunction.SUM, 1),))
    return controller, source, request, results, async_ops, view, job


def test_apply_closes_dialog_before_starting_and_keeps_original_source(monkeypatch, apply_setup) -> None:
    controller, source, request, results, async_ops, view, job = apply_setup
    dialogs = []

    def execute(dialog):
        dialogs.append(dialog)
        dialog.dimensions.item(0).setCheckState(Qt.CheckState.Checked)
        dialog.metrics.cellWidget(0, 2).setCurrentIndex(1)
        dialog.metrics.item(0, 0).setText("Total")
        results.active_tab_id.return_value = "other"
        results.tabs_by_id["source"].df = pd.DataFrame({"replacement": [999]})
        assert dialog.preview_model is None
        assert dialog.apply_button.isEnabled()
        dialog.apply_button.click()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.applied_request == request
        results.create_pending_tab.assert_not_called()
        return dialog.result()

    monkeypatch.setattr(ReshapeDialog, "exec", execute)
    controller.open_reshape_dialog()
    call = async_ops.run_target_overlay_operation.call_args.kwargs
    assert call["target"] is view
    assert call["target"] is not dialogs[0].preview_panel
    assert call["runner"] == "pool" and call["cancelable"]
    assert call["indeterminate"] is False and call["timeout_ms"] == 0
    assert call["suppress_error_dialog"] is False
    assert call["corr_id"] and call["scope"] == "reshape:pending"
    results.create_pending_tab.assert_called_once_with(
        title="Reshaped data",
        origin_type="reshape",
        remove_on_cancel=True,
        remove_on_error=True,
        close_cancels_job=True,
    )
    results.bind_job_to_tab.assert_called_once_with("pending", "reshape-job")
    progress = []
    frame = call["work"](progress_cb=progress.append)
    assert progress[-1] == 100
    assert len(frame) == 7
    assert frame["group"].tolist() == list("gfedcba")
    assert frame["Total"].tolist() == [7, 9, 11, 13, 15, 17, 19]
    call["on_result"](frame)
    assert results.tabs_by_id["pending"].df is frame
    call["on_finished"]()
    results.remove_pending_tab.assert_not_called()
    results.active_tab_id.assert_called_once()
    assert source["value"].tolist() == list(range(14))


@pytest.mark.parametrize("cancelled_result", [False, True])
def test_cancellation_and_finished_without_result_remove_pending_tab(apply_setup, cancelled_result) -> None:
    controller, source, request, results, async_ops, view, job = apply_setup
    controller._run_reshape(source, request)
    call = async_ops.run_target_overlay_operation.call_args.kwargs
    assert call["work"](cancel_cb=lambda: True) is None
    if cancelled_result:
        call["on_result"](None)
    call["on_finished"]()
    results.remove_pending_tab.assert_called_once_with("pending")
    results.fulfill_pending_tab.assert_not_called()


def test_closed_pending_tab_does_not_reappear_on_late_result(apply_setup) -> None:
    controller, source, request, results, async_ops, view, job = apply_setup
    controller._run_reshape(source, request)
    call = async_ops.run_target_overlay_operation.call_args.kwargs
    frame = call["work"]()
    results.tabs_by_id.pop("pending")
    assert call["stale_check"]()
    call["on_result"](frame)
    call["on_finished"]()
    results.fulfill_pending_tab.assert_not_called()
    results.remove_pending_tab.assert_not_called()


def test_worker_errors_propagate_to_standard_error_dialog_and_cleanup(apply_setup) -> None:
    controller, source, request, results, async_ops, view, job = apply_setup
    invalid = ReshapeRequest((0,), ())
    controller._run_reshape(source, invalid)
    call = async_ops.run_target_overlay_operation.call_args.kwargs
    with pytest.raises(ReshapeError):
        call["work"]()
    assert call["suppress_error_dialog"] is False
    assert "on_error" not in call
    call["on_finished"]()
    results.remove_pending_tab.assert_called_once_with("pending")


def test_rejecting_dialog_never_creates_pending_result(monkeypatch, apply_setup) -> None:
    controller, source, request, results, async_ops, view, job = apply_setup
    monkeypatch.setattr(ReshapeDialog, "exec", lambda dialog: QDialog.DialogCode.Rejected)
    controller.open_reshape_dialog()
    results.create_pending_tab.assert_not_called()
    async_ops.run_target_overlay_operation.assert_not_called()


def test_apply_validates_configuration_without_accepting_invalid_or_pending_preview() -> None:
    dialog = ReshapeDialog(
        parent=None,
        source_dataset=DatasetRef("source", "Source", 1, 1),
        source_columns=("value",),
        source_dtypes=("int64",),
        numeric_column_positions=(0,),
        datetime_column_positions=(),
    )
    dialog.metrics.cellWidget(0, 2).setCurrentIndex(1)
    editor = dialog.metrics.cellWidget(0, 3)
    editor.text.setText("[value] > '1'")
    dialog._apply()
    assert dialog.applied_request is None
    assert dialog.result() != QDialog.DialogCode.Accepted
    editor.text.setText("[value] > 1")
    dialog.set_preview_busy(True)
    assert not dialog.apply_button.isEnabled()
    dialog._apply()
    assert dialog.applied_request is None
    dialog.set_preview_busy(False)
    dialog._apply()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.applied_request is not None
