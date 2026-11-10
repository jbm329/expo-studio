from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtWidgets import QDialog, QWidget

from expo_jbm329.gui.dialogs.workflows.concat.concat_dialog import ConcatDialog, ConcatDialogResult
from expo_jbm329.services.data_operations.column_defaults import ColumnFill, describe_fill_column
from expo_jbm329.services.data_operations.concat import ConcatRequest, concat_dataframes
from expo_jbm329.workbench.controllers.concat_controller import ConcatController


@dataclass
class DummyPendingHandle:
    tab_id: str
    view: QWidget


class DummyResults:
    def __init__(self) -> None:
        self.pending = []
        self.bind_calls = []
        self.fulfill_calls = []
        self.remove_calls = []
        self.tabs_by_id = {}

    def create_pending_tab(self, **kwargs):
        handle = DummyPendingHandle(tab_id="pending-1", view=QWidget())
        self.pending.append(kwargs)
        self.tabs_by_id[handle.tab_id] = SimpleNamespace(is_pending=True)
        return handle

    def fulfill_pending_tab(self, tab_id, df):
        self.fulfill_calls.append((tab_id, df))
        self.tabs_by_id[tab_id] = SimpleNamespace(is_pending=False)

    def remove_pending_tab(self, tab_id):
        self.remove_calls.append(tab_id)
        self.tabs_by_id.pop(tab_id, None)

    def bind_job_to_tab(self, tab_id, job_id):
        self.bind_calls.append((tab_id, job_id))


class DummyJobMgr:
    def get_job_id(self, job):
        return "job-1"


class DummyAsyncOps:
    def __init__(self) -> None:
        self.job_mgr = DummyJobMgr()
        self.calls = []
        self.job = object()

    def run_target_overlay_operation(self, **kwargs):
        self.calls.append(kwargs)
        self.last_kwargs = kwargs
        return self.job


class DummyDialog:
    def __init__(self, accepted=True, result=None):
        self._accepted = accepted
        self._result = result

    def exec(self):
        return QDialog.DialogCode.Accepted if self._accepted else QDialog.DialogCode.Rejected

    def build_result(self):
        return self._result


@pytest.fixture
def controller(monkeypatch):
    async_ops = DummyAsyncOps()
    results = DummyResults()
    status = MagicMock()
    df_map = {
        "left": pd.DataFrame({"a": [1]}),
        "right": pd.DataFrame({"b": [2]}),
    }

    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.concat_controller.ConcatDialog",
        lambda **kwargs: DummyDialog(
            result=ConcatDialogResult(
                left_tab_title="left",
                right_tab_title="right",
                remove_duplicates=True,
            )
        ),
    )
    ctrl = ConcatController(
        parent_widget=QWidget(),
        async_ops=async_ops,
        results=results,
        get_active_tab_title=lambda: "left",
        list_tab_titles=lambda: ["left", "right"],
        get_df_for_tab=lambda title: df_map[title],
        set_status=status,
        dialogs=MagicMock(),
    )
    return ctrl, async_ops, results, status


def test_open_concat_dialog_runs_concat(controller):
    ctrl, async_ops, results, _ = controller

    ctrl.open_concat_dialog()

    assert async_ops.calls
    assert results.pending
    assert results.bind_calls == [("pending-1", "job-1")]


def test_open_concat_dialog_injects_dialog_service(controller, monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, _, _, _ = controller
    dialogs = ctrl._dialogs
    factory = MagicMock(return_value=DummyDialog(accepted=False))
    monkeypatch.setattr("expo_jbm329.workbench.controllers.concat_controller.ConcatDialog", factory)

    ctrl.open_concat_dialog()

    assert factory.call_args.kwargs["dialogs"] is dialogs


def test_concat_result_updates_pending_tab(controller):
    ctrl, async_ops, results, status = controller
    ctrl.open_concat_dialog()
    on_result = async_ops.last_kwargs["on_result"]

    on_result(pd.DataFrame({"a": [1], "b": [2]}))

    assert results.fulfill_calls
    assert status.called


def test_result_default_mappings_are_independent() -> None:
    first = ConcatDialogResult("left", "right", False)
    second = ConcatDialogResult("left", "right", False)
    first.left_fill["value"] = ColumnFill(0)
    assert first.right_fill == {}
    assert second.left_fill == {}
    assert second.right_fill == {}
    assert first.left_columns is None
    assert first.right_columns is None


def test_dialog_metadata_is_optional_and_copied(qt_app) -> None:
    metadata = {"value": describe_fill_column(pd.Series([], name="value", dtype="Int64"))}
    right_metadata = {"right": dict(metadata)}
    dialog = ConcatDialog(
        parent=None,
        left_tab_title="left",
        right_tab_titles=["right"],
        left_columns=["value"],
        right_columns_map={"right": ["value"]},
        left_column_metadata=metadata,
        right_column_metadata=right_metadata,
    )
    metadata.clear()
    right_metadata["right"].clear()
    assert dialog._left_column_metadata["value"].dtype == "Int64"
    assert dialog._right_column_metadata["right"]["value"].kind == "integer"
    assert dialog.build_result() == ConcatDialogResult("left", "right", False)
    dialog.close()


def test_controller_captures_metadata_without_scanning_values(controller, monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, async_ops, _, _ = controller
    frames = {
        "left": pd.DataFrame({"n": pd.Series([None, 2**62 + 1], dtype="Int64"), "flag": [True, False]}),
        "right": pd.DataFrame({"text": ["a", "b"], "date": pd.to_datetime(["2024-01-01", None])}),
    }
    ctrl._get_df = MagicMock(side_effect=frames.__getitem__)
    monkeypatch.setattr(pd.Series, "dropna", lambda *args, **kwargs: pytest.fail("Metadata must not scan rows"))
    factory = MagicMock(return_value=DummyDialog(accepted=False))
    monkeypatch.setattr("expo_jbm329.workbench.controllers.concat_controller.ConcatDialog", factory)
    ctrl.open_concat_dialog()
    kwargs = factory.call_args.kwargs
    assert kwargs["left_column_metadata"]["n"].dtype == "Int64"
    assert kwargs["left_column_metadata"]["flag"].kind == "boolean"
    assert kwargs["right_column_metadata"]["right"]["text"].kind == "text"
    assert kwargs["right_column_metadata"]["right"]["date"].kind == "datetime"
    assert ctrl._get_df.call_count == 2
    assert async_ops.calls == []


def test_duplicate_schema_metadata_does_not_change_existing_dialog_opening(
    controller,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctrl, _, _, _ = controller
    ctrl._get_df = lambda title: pd.DataFrame([[1, 2]], columns=["a", "a"])
    factory = MagicMock(return_value=DummyDialog(accepted=False))
    monkeypatch.setattr("expo_jbm329.workbench.controllers.concat_controller.ConcatDialog", factory)
    ctrl.open_concat_dialog()
    assert factory.call_args.kwargs["left_column_metadata"] == {}
    assert factory.call_args.kwargs["right_column_metadata"] == {"right": {}}
    assert factory.call_args.kwargs["left_columns"] == ["a", "a"]


@pytest.mark.parametrize("remove_duplicates", [False, True])
def test_real_worker_forwards_defaults_and_preserves_lifecycle(
    controller,
    monkeypatch: pytest.MonkeyPatch,
    remove_duplicates: bool,
) -> None:
    ctrl, async_ops, results, status = controller
    frames = {
        "left": pd.DataFrame({
            "id": [1, 1],
            "n": pd.Series([None, 2**62 + 1], dtype="Int64"),
        }),
        "right": pd.DataFrame({"id": [2, 2], "flag": [True, True]}),
    }
    originals = {name: frame.copy(deep=True) for name, frame in frames.items()}
    ctrl._get_df = MagicMock(side_effect=frames.__getitem__)
    cfg = ConcatDialogResult(
        "left",
        "right",
        remove_duplicates,
        left_fill={"n": ColumnFill(0)},
        right_fill={"flag": ColumnFill(False)},
    )
    service = MagicMock(wraps=concat_dataframes)
    monkeypatch.setattr("expo_jbm329.workbench.controllers.concat_controller.concat_dataframes", service)
    ctrl._run_concat(cfg)
    kwargs = async_ops.last_kwargs
    cancel = MagicMock(return_value=False)
    result = kwargs["work"](cancel_cb=cancel, progress_cb=MagicMock(), job_id="job-1", job_scope="test")
    assert isinstance(result, pd.DataFrame)
    request = service.call_args.args[0]
    assert isinstance(request, ConcatRequest)
    assert request.left is frames["left"]
    assert request.right is frames["right"]
    assert request.left_fill == cfg.left_fill
    assert request.right_fill == cfg.right_fill
    assert request.remove_duplicates is remove_duplicates
    assert cancel.call_count == 3
    assert str(result["n"].dtype) == "Int64"
    assert str(result["flag"].dtype) == "bool"
    assert pd.isna(result.loc[0, "n"])
    assert result.loc[1, "n"] == 2**62 + 1
    assert result.loc[2, "n"] == 0
    assert result["flag"].tolist() == ([False, False, True] if remove_duplicates else [False, False, True, True])
    assert results.pending[0]["origin_type"] == "concat"
    assert results.pending[0]["remove_on_error"] is True
    assert results.bind_calls == [("pending-1", "job-1")]
    assert kwargs["runner"] == "pool"
    assert kwargs["suppress_error_dialog"] is False
    assert kwargs["cancelable"] is True
    assert len(kwargs["corr_id"]) == 32
    kwargs["on_result"](result)
    kwargs["on_finished"]()
    assert results.fulfill_calls[0][0] == "pending-1"
    pd.testing.assert_frame_equal(results.fulfill_calls[0][1], result)
    assert results.remove_calls == []
    assert status.called
    for name in frames:
        pd.testing.assert_frame_equal(frames[name], originals[name])


@pytest.mark.parametrize("cancel_at", [1, 2, 3])
def test_worker_cancellation_checks_cleanup_pending_tab(
    controller,
    monkeypatch: pytest.MonkeyPatch,
    cancel_at: int,
) -> None:
    ctrl, async_ops, results, status = controller
    lookup = MagicMock(wraps=ctrl._get_df)
    ctrl._get_df = lookup
    service = MagicMock(wraps=concat_dataframes)
    monkeypatch.setattr("expo_jbm329.workbench.controllers.concat_controller.concat_dataframes", service)
    ctrl._run_concat(ConcatDialogResult("left", "right", False))
    kwargs = async_ops.last_kwargs
    cancel = MagicMock(side_effect=[False] * (cancel_at - 1) + [True])
    result = kwargs["work"](cancel_cb=cancel)
    assert result is None
    assert lookup.call_count == (0 if cancel_at == 1 else 2)
    assert service.call_count == (1 if cancel_at == 3 else 0)
    kwargs["on_result"](result)
    kwargs["on_finished"]()
    assert results.remove_calls == ["pending-1"]
    assert results.fulfill_calls == []
    assert status.called


def test_worker_validation_error_propagates_and_finished_removes_pending(controller) -> None:
    ctrl, async_ops, results, status = controller
    ctrl._run_concat(ConcatDialogResult("left", "right", False, left_fill={"unknown": ColumnFill(0)}))
    kwargs = async_ops.last_kwargs
    with pytest.raises(ValueError, match="owned only by its source dataset"):
        kwargs["work"]()
    assert kwargs["suppress_error_dialog"] is False
    kwargs["on_finished"]()
    assert results.remove_calls == ["pending-1"]
    assert results.fulfill_calls == []
    status.assert_not_called()


def test_worker_lookup_error_propagates_and_finished_cleans_pending(controller) -> None:
    ctrl, async_ops, results, _ = controller
    ctrl._get_df = MagicMock(side_effect=KeyError("closed dataset"))
    ctrl._run_concat(ConcatDialogResult("left", "right", False))
    kwargs = async_ops.last_kwargs
    with pytest.raises(KeyError, match="closed dataset"):
        kwargs["work"]()
    kwargs["on_finished"]()
    assert results.remove_calls == ["pending-1"]


@pytest.mark.parametrize("source_first", [False, True])
def test_real_worker_forwards_selection_before_applying_defaults(
    controller, monkeypatch: pytest.MonkeyPatch, source_first: bool
) -> None:
    ctrl, async_ops, results, _ = controller
    source = pd.DataFrame({"value": pd.Series([None, 2**62 + 1], dtype="Int64"), "drop": [1, 2]})
    other = pd.DataFrame({"value": [3, 4], "drop": [5, 6]})
    frames = {"left": source if source_first else other, "right": other if source_first else source}
    ctrl._get_df = frames.__getitem__
    cfg = ConcatDialogResult(
        "left",
        "right",
        False,
        left_columns=["value"] if source_first else [],
        right_columns=[] if source_first else ["value"],
        left_fill={"value": ColumnFill(0)} if source_first else {},
        right_fill={} if source_first else {"value": ColumnFill(0)},
    )
    factory = MagicMock(return_value=DummyDialog(result=cfg))
    monkeypatch.setattr("expo_jbm329.workbench.controllers.concat_controller.ConcatDialog", factory)
    service = MagicMock(wraps=concat_dataframes)
    monkeypatch.setattr("expo_jbm329.workbench.controllers.concat_controller.concat_dataframes", service)
    ctrl.open_concat_dialog()
    kwargs = async_ops.last_kwargs
    result = kwargs["work"]()
    request = service.call_args.args[0]
    assert request.left_columns == cfg.left_columns
    assert request.right_columns == cfg.right_columns
    expected = [None, 2**62 + 1, 0, 0] if source_first else [0, 0, None, 2**62 + 1]
    pd.testing.assert_frame_equal(result, pd.DataFrame({"value": pd.Series(expected, dtype="Int64")}))
    kwargs["on_result"](result)
    kwargs["on_finished"]()
    assert results.remove_calls == []
    pd.testing.assert_frame_equal(results.fulfill_calls[0][1], result)


@pytest.mark.parametrize(
    "left_columns,right_columns,message",
    [
        (["unknown"], None, "Unknown columns"),
        ([], [], "at least one selected output column"),
    ],
)
def test_worker_selection_errors_propagate_and_cleanup_pending(
    controller, left_columns: list[str], right_columns: list[str] | None, message: str
) -> None:
    ctrl, async_ops, results, status = controller
    ctrl._run_concat(ConcatDialogResult("left", "right", False, left_columns=left_columns, right_columns=right_columns))
    kwargs = async_ops.last_kwargs
    with pytest.raises(ValueError, match=message):
        kwargs["work"]()
    assert kwargs["suppress_error_dialog"] is False
    kwargs["on_finished"]()
    assert results.remove_calls == ["pending-1"]
    assert results.fulfill_calls == []
    status.assert_not_called()
