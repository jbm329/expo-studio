from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtWidgets import QDialog, QWidget

from expo_jbm329.gui.dialogs.workflows.join.join_dialog import JoinDialogResult
from expo_jbm329.services.data_operations.joins import JoinMetadata, UnmatchedFill, join_dataframes
from expo_jbm329.workbench.controllers.join_controller import JoinController


class DummyAsyncOps:
    def __init__(self) -> None:
        self.calls = []
        self.job_mgr = MagicMock(get_job_id=lambda job: "job-1")
        self.job = object()

    def run_target_overlay_operation(self, **kwargs):
        self.calls.append(kwargs)
        self.last_kwargs = kwargs
        return self.job


class DummyResults:
    def __init__(self) -> None:
        self.pending = []
        self.bind_calls = []
        self.fulfill_calls = []
        self.remove_calls = []
        self.tabs_by_id = {}

    def create_pending_tab(self, **kwargs):
        tab_id = "pending-join"
        self.pending.append(kwargs)
        self.tabs_by_id[tab_id] = type("R", (), {"is_pending": True})()
        return type("H", (), {"tab_id": tab_id, "view": QWidget()})()

    def fulfill_pending_tab(self, tab_id, df):
        self.fulfill_calls.append((tab_id, df))
        self.tabs_by_id[tab_id].is_pending = False

    def remove_pending_tab(self, tab_id):
        self.remove_calls.append(tab_id)

    def bind_job_to_tab(self, tab_id, job_id):
        self.bind_calls.append((tab_id, job_id))


class DummyDialog:
    def __init__(self, result):
        self._result = result
        self.btn_preview = type("B", (), {"clicked": type("S", (), {"connect": lambda self, cb: None})()})()
        self.btn_cancel = type("B", (), {"clicked": type("S", (), {"connect": lambda self, cb: None})()})()
        self.btn_ok = type("B", (), {"clicked": type("S", (), {"connect": lambda self, cb: None})()})()

    def exec(self):
        return QDialog.DialogCode.Accepted

    def build_result(self):
        return self._result


@pytest.fixture
def controller(monkeypatch):
    async_ops = DummyAsyncOps()
    results = DummyResults()
    status = MagicMock()

    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.join_controller.JoinDialog",
        lambda **kwargs: DummyDialog(result=JoinDialogResult("left", "right", ["id"], ["id"], ["id"], ["id"], "inner")),
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.join_controller.join_dataframes",
        lambda request: pd.DataFrame({"id": [1]}),
    )

    ctrl = JoinController(
        parent_widget=QWidget(),
        async_ops=async_ops,
        results=results,
        get_active_tab_title=lambda: "left",
        get_active_view=lambda: QWidget(),
        list_tab_titles=lambda: ["left", "right"],
        get_df_for_tab=lambda title: pd.DataFrame({"id": [1]}),
        set_status=status,
    )
    return ctrl, async_ops, results, status


def test_open_join_dialog_runs_join(controller):
    ctrl, async_ops, results, _ = controller

    ctrl.open_join_dialog()

    assert async_ops.calls
    assert results.pending
    assert results.bind_calls == [("pending-join", "job-1")]


def test_open_join_dialog_injects_dialog_service(controller, monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, _, _, _ = controller
    dialogs = MagicMock()
    ctrl._dialogs = dialogs
    factory = MagicMock(return_value=MagicMock(exec=MagicMock(return_value=QDialog.DialogCode.Rejected)))
    monkeypatch.setattr("expo_jbm329.workbench.controllers.join_controller.JoinDialog", factory)

    ctrl.open_join_dialog()

    assert factory.call_args.kwargs["dialogs"] is dialogs


def test_join_preview_injects_dialog_service(controller, monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, _, _, _ = controller
    dialogs = MagicMock()
    ctrl._dialogs = dialogs
    ctrl._async_ops = MagicMock()
    dialog = MagicMock()
    dialog.build_result.return_value = MagicMock(left_tab_title="left", right_tab_title="right")
    monkeypatch.setattr(JoinController, "_precheck_join", lambda *args, **kwargs: 1)
    factory = MagicMock()
    monkeypatch.setattr("expo_jbm329.workbench.controllers.join_controller.JoinPreviewDialog", factory)

    ctrl._on_preview(dialog)
    data = pd.DataFrame({"id": [1], "join_status": ["both"]})
    metadata = JoinMetadata(1.0, 0.0, 0.0, "one-to-one", 1)
    ctrl._async_ops.run_with_overlay.call_args.kwargs["on_result"]((data, metadata))

    assert factory.call_args.kwargs["dialogs"] is dialogs
    assert factory.call_args.kwargs["parent"] is dialog
    assert factory.call_args.kwargs["df"] is data
    factory.return_value.exec.assert_called_once_with()


def test_join_result_updates_pending_tab(controller):
    ctrl, async_ops, results, status = controller
    ctrl.open_join_dialog()
    on_result = async_ops.last_kwargs["on_result"]

    on_result(pd.DataFrame({"id": [1]}))

    assert results.fulfill_calls
    assert status.called


def test_join_dialog_result_default_mappings_are_independent() -> None:
    """Existing callers receive empty defaults without shared mutable state."""
    first = JoinDialogResult("left", "right", ["id"], ["id"], [], [], "left")
    second = JoinDialogResult("left", "right", ["id"], ["id"], [], [], "left")
    first.right_fill["value"] = UnmatchedFill(0)
    assert first.left_fill == {}
    assert second.left_fill == {}
    assert second.right_fill == {}


@pytest.mark.parametrize("preview", [False, True])
def test_execute_join_passes_selection_and_defaults(controller, monkeypatch: pytest.MonkeyPatch, preview: bool) -> None:
    """Preview and final execution pass the same typed request to the service."""
    ctrl, _, _, _ = controller
    frames = {"left": pd.DataFrame({"id": [1]}), "right": pd.DataFrame({"other_id": [1]})}
    ctrl._get_df = frames.__getitem__
    cfg = JoinDialogResult(
        "left",
        "right",
        ["id"],
        ["other_id"],
        ["amount"],
        ["flag"],
        "outer",
        left_fill={"amount": UnmatchedFill(0)},
        right_fill={"flag": UnmatchedFill(False)},
    )
    output = pd.DataFrame({"id": range(150)})
    service = MagicMock(return_value=output)
    monkeypatch.setattr("expo_jbm329.workbench.controllers.join_controller.join_dataframes", service)
    result = ctrl._execute_join(cfg, preview=preview)
    request = service.call_args.args[0]
    assert request.left is frames["left"]
    assert request.right is frames["right"]
    assert request.left_on == cfg.left_on
    assert request.right_on == cfg.right_on
    assert request.how == cfg.join_type
    assert request.suffixes == ("_left", "_right")
    assert request.left_columns == cfg.left_selected_columns
    assert request.right_columns == cfg.right_selected_columns
    assert request.left_fill == cfg.left_fill
    assert request.right_fill == cfg.right_fill
    pd.testing.assert_frame_equal(result, output.sample(100, random_state=1) if preview else output)


def test_join_workers_apply_defaults_and_keep_filtering(controller, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real service output reaches both worker paths with keys and metadata retained."""
    ctrl, async_ops, _, _ = controller
    frames = {
        "left": pd.DataFrame({"id": [1, 2], "value": [10, 20], "unused": [1, 2]}),
        "right": pd.DataFrame({
            "other_id": [2, 3],
            "value": [30, 40],
            "flag": pd.Series([pd.NA, True], dtype="boolean"),
            "unused": [3, 4],
        }),
    }
    originals = {name: frame.copy(deep=True) for name, frame in frames.items()}
    ctrl._get_df = frames.__getitem__
    monkeypatch.setattr("expo_jbm329.workbench.controllers.join_controller.join_dataframes", join_dataframes)
    cfg = JoinDialogResult(
        "left",
        "right",
        ["id"],
        ["other_id"],
        ["value"],
        ["value", "flag"],
        "outer",
        left_fill={"value": UnmatchedFill(0)},
        right_fill={"value": UnmatchedFill(0), "flag": UnmatchedFill(False)},
    )
    ctrl._run_join(cfg)
    final = async_ops.last_kwargs["work"]()
    assert final is not None
    assert list(final.columns) == ["join_status", "id", "value_left", "other_id", "value_right", "flag"]
    assert final["value_left"].tolist() == [10, 20, 0]
    assert final["value_right"].tolist() == [0, 30, 40]
    assert str(final["value_left"].dtype) == "int64"
    assert str(final["value_right"].dtype) == "int64"
    assert not final.loc[0, "flag"]
    assert pd.isna(final.loc[1, "flag"])
    assert pd.isna(final.loc[0, "other_id"])
    assert pd.isna(final.loc[2, "id"])

    preview_ops = MagicMock()
    ctrl._async_ops = preview_ops
    dialog = MagicMock(build_result=MagicMock(return_value=cfg))
    ctrl._on_preview(dialog)
    preview_result = preview_ops.run_with_overlay.call_args.kwargs["work"]()
    assert preview_result is not None
    preview, metadata = preview_result
    pd.testing.assert_frame_equal(preview, final.sample(len(final), random_state=1))
    assert metadata.estimated_rows == 1
    assert metadata.match_rate == pytest.approx(1 / 3)
    for name, frame in frames.items():
        pd.testing.assert_frame_equal(frame, originals[name])


@pytest.mark.parametrize("preview", [False, True])
def test_execute_join_propagates_invalid_defaults(
    controller,
    monkeypatch: pytest.MonkeyPatch,
    preview: bool,
) -> None:
    """Service validation errors remain available to the async error handler."""
    ctrl, _, _, _ = controller
    frames = {"left": pd.DataFrame({"id": [1, 2]}), "right": pd.DataFrame({"id": [2], "value": [3]})}
    ctrl._get_df = frames.__getitem__
    monkeypatch.setattr("expo_jbm329.workbench.controllers.join_controller.join_dataframes", join_dataframes)
    cfg = JoinDialogResult(
        "left", "right", ["id"], ["id"], [], ["value"], "left", right_fill={"value": UnmatchedFill("invalid")}
    )
    with pytest.raises(ValueError, match="Invalid unmatched-row default"):
        ctrl._execute_join(cfg, preview=preview)
