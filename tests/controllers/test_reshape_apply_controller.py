"""Apply uses a captured request and the standard pending result-tab lifecycle."""

import logging
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QObject, Qt
from PyQt6.QtWidgets import QDialog, QWidget

from expo_jbm329.gui.dialogs.workflows.reshape.reshape_dialog import ReshapeDialog
from expo_jbm329.services.data_operations.dtypes import get_datetime_column_positions, get_numeric_column_positions
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


def test_apply_closes_dialog_before_starting_and_keeps_original_source(monkeypatch, apply_setup, caplog) -> None:
    controller, source, request, results, async_ops, view, job = apply_setup
    caplog.set_level(logging.DEBUG, logger="applogger.service")
    dialogs = []

    def execute(dialog):
        dialogs.append(dialog)
        dialog.dimensions.item(0).setCheckState(Qt.CheckState.Checked)
        dialog.metrics.cellWidget(0, 2).value.setCurrentIndex(1)
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
    assert any(f"corr={call['corr_id']}, operation=apply" in record.getMessage() for record in caplog.records)
    assert len(frame) == 7
    assert frame["group"].tolist() == list("gfedcba")
    assert frame["Total"].tolist() == [7, 9, 11, 13, 15, 17, 19]
    call["on_result"](frame)
    assert results.tabs_by_id["pending"].df is frame
    call["on_finished"]()
    results.remove_pending_tab.assert_not_called()
    results.active_tab_id.assert_called_once()
    assert source["value"].tolist() == list(range(14))


def test_median_apply_worker_uses_shared_aggregation_path(apply_setup):
    controller, source, request, results, async_ops, view, job = apply_setup
    median_request = ReshapeRequest((0,), (ReshapeMetric("Median", ReshapeFunction.MEDIAN, 1),))

    controller._run_reshape(source, median_request)
    call = async_ops.run_target_overlay_operation.call_args.kwargs
    result = call["work"]()

    assert result["group"].tolist() == list("gfedcba")
    assert result["Median"].tolist() == [3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]


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
    dialog.metrics.cellWidget(0, 2).value.setCurrentIndex(1)
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


def test_ordered_apply_matches_preview_and_uses_captured_order_after_widget_edits(
    monkeypatch, apply_setup, ordered_reshape_case
) -> None:
    controller, _, _, results, async_ops, view, job = apply_setup
    source, expected, configure = ordered_reshape_case
    original = source.copy(deep=True)
    results.tabs_by_id["source"].df = source
    captured = []
    previews = []

    def execute(dialog: ReshapeDialog) -> int:
        configure(dialog)
        request = dialog.capture_request()
        dialog.preview_button.click()
        preview_call = async_ops.run_target_overlay_operation.call_args.kwargs
        preview = preview_call["work"]()
        preview_call["on_result"](preview)
        preview_call["on_finished"]()
        previews.append(preview)
        pd.testing.assert_frame_equal(preview.frame, expected.head(5))
        dialog.apply_button.click()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.applied_request == request
        captured.append(request)
        results.create_pending_tab.assert_not_called()
        for row, order in ((1, 3), (2, 2)):
            cell = dialog.metrics.cellWidget(row, 2)
            cell.order.setCurrentIndex(cell.order.findData(order))
        dialog.metrics.item(1, 0).setText("Edited after Apply")
        assert dialog.capture_request() != request
        results.active_tab_id.return_value = "other"
        results.tabs_by_id["source"].df = pd.DataFrame({"replacement": [999]})
        return dialog.result()

    monkeypatch.setattr(ReshapeDialog, "exec", execute)
    controller.open_reshape_dialog()
    call = async_ops.run_target_overlay_operation.call_args.kwargs
    assert call["target"] is view and call["runner"] == "pool" and call["cancelable"]
    results.bind_job_to_tab.assert_called_once_with("pending", "reshape-job")
    progress: list[int] = []
    frame = call["work"](progress_cb=progress.append)
    pd.testing.assert_frame_equal(frame, expected)
    pd.testing.assert_frame_equal(frame.head(5), previews[0].frame)
    assert [metric.order_position for metric in captured[0].metrics] == [None, 2, 3]
    assert progress[0] == 0 and progress[-1] == 100
    call["on_result"](frame)
    call["on_finished"]()
    assert results.tabs_by_id["pending"].df is frame
    results.remove_pending_tab.assert_not_called()
    pd.testing.assert_frame_equal(source, original)


@pytest.mark.parametrize("outcome", ["cancel", "error", "closed"])
def test_ordered_apply_keeps_pending_tab_cleanup_and_error_propagation(
    apply_setup, ordered_reshape_case, outcome: str
) -> None:
    controller, _, _, results, async_ops, view, job = apply_setup
    source, expected, configure = ordered_reshape_case
    original = source.copy(deep=True)
    dialog = ReshapeDialog(
        parent=None,
        source_dataset=DatasetRef("source", "Source", len(source), len(source.columns)),
        source_columns=list(source.columns),
        source_dtypes=[str(dtype) for dtype in source.dtypes],
        numeric_column_positions=get_numeric_column_positions(source),
        datetime_column_positions=get_datetime_column_positions(source),
    )
    configure(dialog)
    request = dialog.capture_request()
    if outcome == "error":
        request = replace(request, metrics=(replace(request.metrics[1], order_position=-1),))
    controller._run_reshape(source, request)
    call = async_ops.run_target_overlay_operation.call_args.kwargs
    assert call["suppress_error_dialog"] is False and call["cancelable"]
    if outcome == "cancel":
        assert call["work"](cancel_cb=lambda: True) is None
        call["on_result"](None)
    elif outcome == "error":
        with pytest.raises(ReshapeError):
            call["work"]()
    else:
        frame = call["work"]()
        pd.testing.assert_frame_equal(frame, expected)
        results.tabs_by_id.pop("pending")
        assert call["stale_check"]()
        call["on_result"](frame)
    call["on_finished"]()
    if outcome == "closed":
        results.remove_pending_tab.assert_not_called()
    else:
        results.remove_pending_tab.assert_called_once_with("pending")
    assert "pending" not in results.tabs_by_id
    results.fulfill_pending_tab.assert_not_called()
    pd.testing.assert_frame_equal(source, original)
    dialog.close()
