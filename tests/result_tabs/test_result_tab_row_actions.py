"""Deterministic contracts for asynchronous, undoable duplicate removal."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableView, QTabWidget, QWidget

from expo_jbm329.services.data_profile.profile_cache import ColumnProfileCache
from expo_jbm329.utils.models import DataFrameModel
from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager
from expo_jbm329.workbench.controllers.result_tabs.result_tab_row_actions import ResultTabRowActions


@pytest.fixture
def row_actions(qt_app):
    source = pd.DataFrame({
        "id": pd.Series([2, None, 2, None, 1, 1], dtype="Int64"),
        "text": pd.Series(["b", None, "b", None, "a", "different"], dtype="string"),
    })
    source.index = pd.Index([8, 7, 6, 5, 4, 3], name="original")
    parent = QWidget()
    view = QTableView(parent)
    model = DataFrameModel(source, view)
    view.setModel(model)
    target = {"sales": (view, source, "Sales")}
    resolve = MagicMock(side_effect=target.get)
    apply = MagicMock(return_value=True)
    async_ops = MagicMock()
    dialogs = MagicMock()
    status = MagicMock()
    controller = ResultTabRowActions(
        parent=parent,
        dialogs=dialogs,
        logger=None,
        async_ops=async_ops,
        resolve_target=resolve,
        apply_new_dataframe=apply,
        set_status=status,
    )
    yield SimpleNamespace(
        controller=controller,
        source=source,
        parent=parent,
        view=view,
        model=model,
        target=target,
        resolve=resolve,
        apply=apply,
        async_ops=async_ops,
        dialogs=dialogs,
        status=status,
    )
    if async_ops.run_dataframe_operation.called:
        async_ops.run_dataframe_operation.call_args.kwargs["on_finished"]()
    parent.deleteLater()


def dispatch(env):
    env.controller.remove_duplicates("sales")
    return env.async_ops.run_dataframe_operation.call_args.kwargs


def test_dispatch_runs_only_in_worker_and_applies_count_with_current_title(row_actions) -> None:
    env = row_actions
    original = env.source.copy(deep=True)
    call = dispatch(env)
    assert call["runner"] == "pool"
    assert call["view"] is env.view
    assert call["scope"] == "remove_duplicates:sales"
    assert call["timeout_ms"] == 0
    assert len(call["corr_id"]) == 32
    assert env.controller.is_running("sales")
    env.apply.assert_not_called()
    env.status.assert_not_called()

    def apply_frame(view, result):
        assert view is env.view
        env.model.set_data_frame(result)
        env.target["sales"] = (view, result, "Renamed sales")
        return True

    env.apply.side_effect = apply_frame
    env.target["sales"] = (env.view, env.source, "Renamed sales")
    # Worker computation must not consult the host or any widget.
    env.resolve.side_effect = AssertionError("Worker must not resolve tabs")
    result = call["work"]()
    env.resolve.side_effect = env.target.get
    pd.testing.assert_frame_equal(result, original.iloc[[0, 1, 4, 5]].reset_index(drop=True))
    pd.testing.assert_frame_equal(env.source, original)
    call["apply_result"](result)
    env.apply.assert_called_once_with(env.view, result)
    env.status.assert_called_once_with('Removed 2 duplicate rows from dataset "Renamed sales".', 6000)
    env.dialogs.critical.assert_not_called()
    call["on_finished"]()
    assert not env.controller.is_running("sales")


@pytest.mark.parametrize("empty", [False, True])
def test_noop_preserves_frame_index_and_does_not_invoke_apply(row_actions, empty: bool) -> None:
    env = row_actions
    source = env.source.iloc[:0] if empty else env.source.iloc[[0, 1, 4, 5]]
    env.model.set_data_frame(source)
    env.target["sales"] = (env.view, source, "Sales")
    call = dispatch(env)
    call["apply_result"](call["work"]())
    env.apply.assert_not_called()
    assert env.model.data_frame() is source
    env.status.assert_called_once_with('No duplicate rows found in dataset "Sales".', 6000)
    env.dialogs.critical.assert_not_called()


def test_duplicate_dispatch_is_blocked_until_finished(row_actions) -> None:
    env = row_actions
    call = dispatch(env)
    env.controller.remove_duplicates("sales")
    env.async_ops.run_dataframe_operation.assert_called_once()
    call["on_finished"]()
    assert not env.controller.is_running("sales")
    env.controller.remove_duplicates("sales")
    assert env.async_ops.run_dataframe_operation.call_count == 2


@pytest.mark.parametrize("change", ["closed", "replaced", "reset_same", "edited", "model", "deleted"])
def test_stale_results_never_apply_or_report_success(row_actions, change: str) -> None:
    env = row_actions
    call = dispatch(env)
    result = call["work"]()
    if change == "closed":
        env.target.clear()
    elif change == "replaced":
        replacement = env.source.copy(deep=True)
        env.target["sales"] = (env.view, replacement, "Sales")
    elif change == "reset_same":
        env.model.set_data_frame(env.source)
    elif change == "edited":
        env.source.iloc[0, 0] = 9
        env.model.dataChanged.emit(env.model.index(0, 0), env.model.index(0, 0), [])
    elif change == "model":
        env.view.setModel(DataFrameModel(env.source, env.view))
    else:
        sip.delete(env.view)
    assert call["stale_check"]()
    call["apply_result"](result)
    call["on_error"]("late failure")
    call["on_finished"]()
    env.apply.assert_not_called()
    env.status.assert_not_called()
    env.dialogs.critical.assert_not_called()
    assert not env.controller.is_running("sales")


def test_display_sort_does_not_invalidate_source(row_actions) -> None:
    env = row_actions
    call = dispatch(env)
    env.model.sort(0, Qt.SortOrder.DescendingOrder)
    assert not call["stale_check"]()
    call["apply_result"](call["work"]())
    env.apply.assert_called_once()


@pytest.mark.parametrize("cancel_at", [1, 2])
def test_worker_checks_cancellation_before_and_after_service(row_actions, cancel_at: int) -> None:
    env = row_actions
    call = dispatch(env)
    cancelled = MagicMock(side_effect=[False] * (cancel_at - 1) + [True])
    assert call["work"](cancel_cb=cancelled) is None
    assert cancelled.call_count == cancel_at
    call["apply_result"](None)
    env.apply.assert_not_called()
    env.status.assert_not_called()


@pytest.mark.parametrize("nested", [[1], {"key": 1}])
def test_worker_errors_use_custom_dialog_once_and_release_running_state(row_actions, nested: object) -> None:
    env = row_actions
    frame = pd.DataFrame({"nested": [nested, nested], "other": [1, 1]})
    env.model.set_data_frame(frame)
    env.target["sales"] = (env.view, frame, "Sales")
    call = dispatch(env)
    with pytest.raises(TypeError, match="unhashable"):
        call["work"]()
    call["on_error"]("unhashable type")
    call["on_finished"]()
    env.dialogs.critical.assert_called_once()
    assert env.dialogs.critical.call_args.kwargs["parent"] is env.parent
    env.apply.assert_not_called()
    env.status.assert_not_called()
    assert not env.controller.is_running("sales")


@pytest.mark.parametrize("raises", [False, True])
def test_apply_failure_never_reports_success_or_duplicates_host_dialog(row_actions, raises: bool) -> None:
    env = row_actions
    call = dispatch(env)
    if raises:
        env.apply.side_effect = RuntimeError("apply failed")
    else:

        def handled_failure(view, frame):
            env.dialogs.critical(parent=env.parent, title="Failure", text="apply failed")
            return False

        env.apply.side_effect = handled_failure
    call["apply_result"](call["work"]())
    env.status.assert_not_called()
    env.dialogs.critical.assert_called_once()


def test_dispatch_failure_reports_custom_error_and_releases_connections(row_actions) -> None:
    env = row_actions
    before = env.model.receivers(env.model.dataChanged)
    env.async_ops.run_dataframe_operation.side_effect = RuntimeError("cannot start")
    dispatch(env)
    env.dialogs.critical.assert_called_once()
    assert not env.controller.is_running("sales")
    assert env.model.receivers(env.model.dataChanged) == before


def test_unavailable_target_does_not_start_job(row_actions) -> None:
    env = row_actions
    env.target.clear()
    env.controller.remove_duplicates("sales")
    env.async_ops.run_dataframe_operation.assert_not_called()


@pytest.fixture
def manager_actions(qt_app):
    parent = QWidget()
    tabs = QTabWidget(parent)
    dialogs = MagicMock()
    async_ops = MagicMock()
    status = MagicMock()
    cache = ColumnProfileCache()
    manager = ResultTabManager(
        parent_widget=parent,
        tabs=tabs,
        busy_overlay=SimpleNamespace(run=lambda view, fn, **kwargs: fn()),
        async_ops=async_ops,
        col_profile_cache=cache,
        set_status=status,
        dialogs=dialogs,
    )
    tabs.currentChanged.connect(manager.on_tab_changed)
    frame = pd.DataFrame({"id": pd.Series([2, None, 2, None, 1], dtype="Int64")})
    frame.index = pd.Index([9, 8, 7, 6, 5], name="original")
    manager.display_dataframe(frame, title="Sales")
    tab_id = manager.active_tab_id()
    view = manager.active_view()

    def resolve(stable_id):
        record = manager.tabs_by_id.get(stable_id)
        if record is None or not record.is_ready or record.df is None:
            return None
        return record.view, record.df, record.title

    controller = ResultTabRowActions(
        parent=parent,
        dialogs=dialogs,
        logger=None,
        async_ops=async_ops,
        resolve_target=resolve,
        apply_new_dataframe=manager._apply_new_dataframe_to_view,
        set_status=status,
    )
    status.reset_mock()
    yield SimpleNamespace(
        controller=controller,
        manager=manager,
        tabs=tabs,
        tab_id=tab_id,
        view=view,
        source=frame,
        async_ops=async_ops,
        dialogs=dialogs,
        status=status,
        cache=cache,
    )
    if async_ops.run_dataframe_operation.called:
        async_ops.run_dataframe_operation.call_args.kwargs["on_finished"]()
    parent.deleteLater()


def test_real_manager_updates_target_undo_and_cache_without_touching_active_tab(manager_actions, monkeypatch) -> None:
    env = manager_actions
    original = env.source.copy(deep=True)
    env.manager.display_dataframe(pd.DataFrame({"other": [1]}), title="Other")
    other_id = env.manager.active_tab_id()
    invalidation = MagicMock()
    monkeypatch.setattr(ColumnProfileCache, "invalidate_tab", invalidation)
    env.status.reset_mock()
    env.controller.remove_duplicates(env.tab_id)
    call = env.async_ops.run_dataframe_operation.call_args.kwargs
    result = call["work"]()
    call["apply_result"](result)
    call["on_finished"]()
    assert env.manager.active_tab_id() == other_id
    pd.testing.assert_frame_equal(
        env.manager.tabs_by_id[env.tab_id].df, original.iloc[[0, 1, 4]].reset_index(drop=True)
    )
    assert env.manager._undo.stack_size(env.tab_id) == 1
    invalidation.assert_called_with(env.tab_id)
    env.status.assert_called_once_with('Removed 2 duplicate rows from dataset "Sales".', 6000)

    env.tabs.setCurrentWidget(env.view)
    env.manager.undo()

    pd.testing.assert_frame_equal(env.manager.tabs_by_id[env.tab_id].df, original)
    assert env.manager._undo.stack_size(env.tab_id) == 0
    assert env.manager.last_df is env.manager.tabs_by_id[env.tab_id].df


@pytest.mark.parametrize("reason", ["disabled", "size", "copy"])
def test_real_manager_removal_still_succeeds_when_undo_not_retained(manager_actions, monkeypatch, reason: str) -> None:
    env = manager_actions
    if reason == "disabled":
        env.manager._undo.set_limits(undo_limit_per_tab=0, max_size_allow_undo_mb=100)
    elif reason == "size":
        env.manager._undo.set_limits(undo_limit_per_tab=20, max_size_allow_undo_mb=0)
    env.controller.remove_duplicates(env.tab_id)
    call = env.async_ops.run_dataframe_operation.call_args.kwargs
    result = call["work"]()
    if reason == "copy":
        monkeypatch.setattr(pd.DataFrame, "copy", MagicMock(side_effect=RuntimeError("snapshot copy failed")))
    call["apply_result"](result)
    assert len(env.manager.tabs_by_id[env.tab_id].df) == 3
    assert not env.manager._undo.has_undo(env.tab_id)
    env.dialogs.critical.assert_not_called()
    env.status.assert_called_once_with('Removed 2 duplicate rows from dataset "Sales".', 6000)


def test_real_manager_handled_apply_failure_returns_false_and_no_success(manager_actions, monkeypatch) -> None:
    env = manager_actions
    env.controller.remove_duplicates(env.tab_id)
    call = env.async_ops.run_dataframe_operation.call_args.kwargs
    result = call["work"]()
    monkeypatch.setattr(DataFrameModel, "set_data_frame", MagicMock(side_effect=RuntimeError("update failed")))
    call["apply_result"](result)
    env.dialogs.critical.assert_called_once()
    env.status.assert_not_called()
    assert env.manager.tabs_by_id[env.tab_id].df is env.source


def test_real_manager_noop_preserves_existing_undo_and_index(manager_actions) -> None:
    env = manager_actions
    previous = pd.DataFrame({"before": [4]})
    env.manager._undo.push_snapshot(env.tab_id, previous)
    unique = env.source.iloc[[0, 1, 4]]
    assert env.manager._apply_new_dataframe_to_view(env.view, unique, push_undo=False)
    env.controller.remove_duplicates(env.tab_id)
    call = env.async_ops.run_dataframe_operation.call_args.kwargs
    call["apply_result"](call["work"]())
    assert env.manager.tabs_by_id[env.tab_id].df is unique
    assert env.manager._undo.stack_size(env.tab_id) == 1
    pd.testing.assert_frame_equal(env.manager._undo.pop_snapshot(env.tab_id), previous)
