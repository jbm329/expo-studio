from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtWidgets import QDialog, QTableView, QWidget

from expo_jbm329.gui.dialogs.workflows.join.join_dialog import JoinDialog, JoinDialogResult
from expo_jbm329.services.data_operations.joins import (
    JoinHow,
    JoinMetadata,
    JoinResult,
    UnmatchedFill,
    join_dataframes_with_status,
)
from expo_jbm329.workbench.controllers.async_operation_controller import AsyncOperationController
from expo_jbm329.workbench.controllers.join_controller import JoinController
from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService


class TestableJoinController(JoinController):
    """Expose the controller's orchestration seams for typed unit tests."""

    __test__ = False

    def set_frames(self, frames: dict[str, pd.DataFrame]) -> None:
        self._get_df = frames.__getitem__

    def set_dialogs(self, dialogs: DialogService) -> None:
        self._dialogs = dialogs

    def set_async_ops(self, async_ops: AsyncOperationController) -> None:
        self._async_ops = async_ops

    def run_join(self, cfg: JoinDialogResult) -> None:
        self._run_join(cfg)

    def preview_join(self, dialog: JoinDialog) -> None:
        self._on_preview(dialog)

    def execute_join(self, cfg: JoinDialogResult, *, preview: bool = False) -> JoinResult:
        return self._execute_join(cfg, preview=preview)

    def precheck_join(self, cfg: JoinDialogResult) -> int | None:
        return self._precheck_join(cfg, parent=QWidget())


ControllerFixture = tuple[TestableJoinController, MagicMock, MagicMock, MagicMock]


@pytest.fixture
def controller(monkeypatch: pytest.MonkeyPatch) -> ControllerFixture:
    async_ops = MagicMock(spec=AsyncOperationController)
    async_ops.job_mgr = MagicMock()
    async_ops.job_mgr.get_job_id.return_value = "job-1"
    results = MagicMock(spec=ResultTabManager)
    results.create_pending_tab.return_value = MagicMock(tab_id="pending-join", view=QTableView())
    status = MagicMock()

    dialog = MagicMock()
    dialog.exec.return_value = QDialog.DialogCode.Accepted
    dialog.build_result.return_value = JoinDialogResult("left", "right", ["id"], ["id"], ["id"], ["id"], "inner")
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.join_controller.JoinDialog",
        MagicMock(return_value=dialog),
    )
    ctrl = TestableJoinController(
        parent_widget=QWidget(),
        async_ops=async_ops,
        results=results,
        get_active_tab_title=lambda: "left",
        get_active_view=QTableView,
        list_tab_titles=lambda: ["left", "right"],
        get_df_for_tab=lambda title: pd.DataFrame({"id": [1]}),
        set_status=status,
    )
    return ctrl, async_ops, results, status


def test_open_join_dialog_runs_join(controller: ControllerFixture) -> None:
    ctrl, async_ops, results, _ = controller

    ctrl.open_join_dialog()

    async_ops.run_target_overlay_operation.assert_called_once()
    results.create_pending_tab.assert_called_once()
    results.bind_job_to_tab.assert_called_once_with("pending-join", "job-1")


def test_open_join_dialog_injects_dialog_service(
    controller: ControllerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctrl, _, _, _ = controller
    dialogs = MagicMock()
    ctrl.set_dialogs(dialogs)
    factory = MagicMock(return_value=MagicMock(exec=MagicMock(return_value=QDialog.DialogCode.Rejected)))
    monkeypatch.setattr("expo_jbm329.workbench.controllers.join_controller.JoinDialog", factory)

    ctrl.open_join_dialog()

    assert factory.call_args.kwargs["dialogs"] is dialogs
    assert factory.call_args.kwargs["column_dtypes_for_tab"] == {"left": {"id": "int64"}, "right": {"id": "int64"}}


@pytest.mark.parametrize(
    "left_dtype,right_dtype,expected",
    [
        ("int64", "Int64", True),
        ("Int64", "int64", True),
        ("int32", "Int64", False),
        ("float64", "Int64", False),
    ],
)
def test_join_dialog_key_eligibility_for_mixed_integer_dtypes(
    controller: ControllerFixture,
    monkeypatch: pytest.MonkeyPatch,
    left_dtype: str,
    right_dtype: str,
    expected: bool,
) -> None:
    ctrl, _, _, _ = controller
    frames = {
        "left": pd.DataFrame({"left_key": pd.Series([1], dtype=left_dtype)}),
        "right": pd.DataFrame({"right_key": pd.Series([1], dtype=right_dtype)}),
    }
    ctrl.set_frames(frames)
    factory = MagicMock(return_value=MagicMock(exec=MagicMock(return_value=QDialog.DialogCode.Rejected)))
    monkeypatch.setattr("expo_jbm329.workbench.controllers.join_controller.JoinDialog", factory)

    ctrl.open_join_dialog()

    joinable_map = factory.call_args.kwargs["joinable_map"]
    eligible_keys = joinable_map.get(("left", "left_key", "right"), set())
    assert ("right_key" in eligible_keys) is expected


def test_execute_join_supports_mixed_integer_key_dtypes_without_mutating_inputs(
    controller: ControllerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    ctrl, _, _, _ = controller
    frames = {
        "left": pd.DataFrame({"left_key": pd.Series([1, 2], dtype="int64")}),
        "right": pd.DataFrame({"right_key": pd.Series([2, 3], dtype="Int64")}),
    }
    originals = {name: frame.copy(deep=True) for name, frame in frames.items()}
    ctrl.set_frames(frames)
    cfg = JoinDialogResult("left", "right", ["left_key"], ["right_key"], [], [], "inner")

    assert ctrl.precheck_join(cfg) == 1
    assert "JoinController: dtype mismatch" not in caplog.text

    result = ctrl.execute_join(cfg)

    assert result.frame[["left_key", "right_key"]].to_dict("records") == [{"left_key": 2, "right_key": 2}]
    assert str(result.frame["left_key"].dtype) == "int64"
    assert str(result.frame["right_key"].dtype) == "Int64"
    for name, original in originals.items():
        pd.testing.assert_frame_equal(frames[name], original)


def test_join_preview_injects_dialog_service(controller: ControllerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, async_ops, _, _ = controller
    dialogs = MagicMock()
    ctrl.set_dialogs(dialogs)
    dialog = MagicMock()
    dialog.build_result.return_value = MagicMock(left_tab_title="left", right_tab_title="right")
    monkeypatch.setattr(JoinController, "_precheck_join", MagicMock(return_value=1))
    factory = MagicMock()
    monkeypatch.setattr("expo_jbm329.workbench.controllers.join_controller.JoinPreviewDialog", factory)

    ctrl.preview_join(dialog)
    data = pd.DataFrame({"id": [1], "join_status": ["both"]})
    metadata = JoinMetadata(1.0, 0.0, 0.0, "one-to-one", 1)
    async_ops.run_with_overlay.call_args.kwargs["on_result"]((JoinResult(data, "join_status"), metadata))

    assert factory.call_args.kwargs["dialogs"] is dialogs
    assert factory.call_args.kwargs["parent"] is dialog
    assert factory.call_args.kwargs["df"] is data
    assert factory.call_args.kwargs["status_column"] == "join_status"
    factory.return_value.exec.assert_called_once_with()


def test_join_result_updates_pending_tab(controller: ControllerFixture) -> None:
    ctrl, async_ops, results, status = controller
    ctrl.open_join_dialog()
    on_result = async_ops.run_target_overlay_operation.call_args.kwargs["on_result"]

    on_result(pd.DataFrame({"id": [1]}))

    results.fulfill_pending_tab.assert_called_once()
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
def test_execute_join_passes_selection_and_defaults(
    controller: ControllerFixture, monkeypatch: pytest.MonkeyPatch, preview: bool
) -> None:
    """Preview and final execution pass the same typed request to the service."""
    ctrl, _, _, _ = controller
    frames = {"left": pd.DataFrame({"id": [1]}), "right": pd.DataFrame({"other_id": [1]})}
    ctrl.set_frames(frames)
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
    service = MagicMock(return_value=JoinResult(output, "generated-status"))
    monkeypatch.setattr("expo_jbm329.workbench.controllers.join_controller.join_dataframes_with_status", service)
    result = ctrl.execute_join(cfg, preview=preview)
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
    assert request.status_column_base == "join_status (left FULL OUTER right)"
    assert result.status_column == "generated-status"
    pd.testing.assert_frame_equal(result.frame, output.sample(100, random_state=1) if preview else output)


def test_join_workers_apply_defaults_and_keep_filtering(
    controller: ControllerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    ctrl.set_frames(frames)
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.join_controller.join_dataframes_with_status", join_dataframes_with_status
    )
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
    ctrl.run_join(cfg)
    final = async_ops.run_target_overlay_operation.call_args.kwargs["work"]()
    assert final is not None
    assert list(final.columns) == [
        "join_status (left FULL OUTER right)",
        "id",
        "value_left",
        "other_id",
        "value_right",
        "flag",
    ]
    assert final["value_left"].tolist() == [10, 20, 0]
    assert final["value_right"].tolist() == [0, 30, 40]
    assert str(final["value_left"].dtype) == "int64"
    assert str(final["value_right"].dtype) == "int64"
    assert not final.loc[0, "flag"]
    assert pd.isna(final.loc[1, "flag"])
    assert pd.isna(final.loc[0, "other_id"])
    assert pd.isna(final.loc[2, "id"])

    preview_ops = MagicMock()
    ctrl.set_async_ops(preview_ops)
    dialog = MagicMock(build_result=MagicMock(return_value=cfg))
    ctrl.preview_join(dialog)
    preview_result = preview_ops.run_with_overlay.call_args.kwargs["work"]()
    assert preview_result is not None
    preview, metadata = preview_result
    pd.testing.assert_frame_equal(preview.frame, final.sample(len(final), random_state=1))
    assert preview.status_column == "join_status (left FULL OUTER right)"
    assert metadata.estimated_rows == 1
    assert metadata.match_rate == pytest.approx(1 / 3)
    for name, frame in frames.items():
        pd.testing.assert_frame_equal(frame, originals[name])


@pytest.mark.parametrize("preview", [False, True])
def test_execute_join_propagates_invalid_defaults(
    controller: ControllerFixture,
    monkeypatch: pytest.MonkeyPatch,
    preview: bool,
) -> None:
    """Service validation errors remain available to the async error handler."""
    ctrl, _, _, _ = controller
    frames = {"left": pd.DataFrame({"id": [1, 2]}), "right": pd.DataFrame({"id": [2], "value": [3]})}
    ctrl.set_frames(frames)
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.join_controller.join_dataframes_with_status", join_dataframes_with_status
    )
    cfg = JoinDialogResult(
        "left", "right", ["id"], ["id"], [], ["value"], "left", right_fill={"value": UnmatchedFill("invalid")}
    )
    with pytest.raises(ValueError, match="Invalid unmatched-row default"):
        ctrl.execute_join(cfg, preview=preview)


@pytest.mark.parametrize(
    "how,label", [("inner", "INNER"), ("left", "LEFT"), ("right", "RIGHT"), ("outer", "FULL OUTER")]
)
@pytest.mark.parametrize("keep_history", [False, True])
def test_workers_use_generated_identity_with_occupied_descriptive_name(
    controller: ControllerFixture, monkeypatch: pytest.MonkeyPatch, how: JoinHow, label: str, keep_history: bool
) -> None:
    """Both worker callbacks use current provenance while preserving selected history."""
    ctrl, async_ops, results, _ = controller
    base = f"join_status (Film {label} Actor)"
    frames = {
        "Film": pd.DataFrame({
            "id": [1, 2],
            "join_status": pd.Series(["right_only", pd.NA], dtype="string"),
            base: ["old", "old"],
            "title_Film": ["A", "B"],
        }),
        "Actor": pd.DataFrame({"id": [2, 3], "value": [20, 30]}),
    }
    originals = {name: frame.copy(deep=True) for name, frame in frames.items()}
    ctrl.set_frames(frames)
    cfg = JoinDialogResult(
        "Film",
        "Actor",
        ["id"],
        ["id"],
        ["title_Film", "join_status", base] if keep_history else ["title_Film"],
        ["value"],
        how,
        right_fill={"value": UnmatchedFill(0)} if how in {"left", "outer"} else {},
    )
    ctrl.run_join(cfg)
    callbacks = async_ops.run_target_overlay_operation.call_args.kwargs
    final = callbacks["work"]()
    assert isinstance(final, pd.DataFrame)
    assert final.columns[0] == f"{base} 2"
    assert ("join_status" in final.columns) is keep_history
    assert (base in final.columns) is keep_history
    assert "title_Film" in final.columns
    if how in {"left", "outer"}:
        assert final.loc[final["id"] == 1, "value"].tolist() == [0]
    callbacks["on_result"](final)
    assert results.fulfill_pending_tab.call_args.args[1] is final

    factory = MagicMock()
    monkeypatch.setattr("expo_jbm329.workbench.controllers.join_controller.JoinPreviewDialog", factory)
    dialog = MagicMock(build_result=MagicMock(return_value=cfg))
    ctrl.preview_join(dialog)
    preview_callbacks = async_ops.run_with_overlay.call_args.kwargs
    preview_result = preview_callbacks["work"]()
    preview, metadata = preview_result
    assert isinstance(preview, JoinResult)
    assert preview.status_column == f"{base} 2"
    pd.testing.assert_frame_equal(preview.frame, final.sample(len(final), random_state=1))
    counts = final[f"{base} 2"].value_counts(normalize=True)
    assert metadata.match_rate == pytest.approx(counts.get("both", 0.0))
    assert metadata.left_only == pytest.approx(counts.get("left_only", 0.0))
    assert metadata.right_only == pytest.approx(counts.get("right_only", 0.0))
    preview_callbacks["on_result"](preview_result)
    assert factory.call_args.kwargs["status_column"] == f"{base} 2"
    assert factory.call_args.kwargs["df"] is preview.frame
    for name, original in originals.items():
        pd.testing.assert_frame_equal(frames[name], original)


def test_worker_keeps_suffixed_keys_and_selected_history(controller: ControllerFixture) -> None:
    """Different key names overlapping non-key columns retain both source keys."""
    ctrl, async_ops, _, _ = controller
    frames = {
        "left": pd.DataFrame({"id": [1], "other_id": [10], "join_status": ["historical-left"]}),
        "right": pd.DataFrame({"other_id": [1], "id": [20], "join_status": ["historical-right"]}),
    }
    ctrl.set_frames(frames)
    cfg = JoinDialogResult("left", "right", ["id"], ["other_id"], [], ["join_status"], "inner")
    ctrl.run_join(cfg)
    final = async_ops.run_target_overlay_operation.call_args.kwargs["work"]()
    assert list(final.columns) == ["join_status (left INNER right)", "id_left", "other_id_right", "join_status_right"]
    assert final["join_status_right"].tolist() == ["historical-right"]
