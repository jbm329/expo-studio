from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QObject, QPoint, Qt
from PyQt6.QtWidgets import QDialog, QMenu, QTabWidget, QWidget

from expo_jbm329.gui.menus.result_tab_column_header_context_menu import ResultTabColumnHeaderContextMenu
from expo_jbm329.gui.menus.result_tab_header_context import build_header_context
from expo_jbm329.services.data_operations.derived_column.derived_column_service import DerivedColumnSpec
from expo_jbm329.services.data_profile.profile_cache import ColumnProfileCache
from expo_jbm329.workbench.controllers.async_operation_controller import AsyncOperationController
from expo_jbm329.workbench.controllers.derived_column_controller import DerivedColumnController
from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager


@pytest.fixture
def derived_env(qt_app, monkeypatch):
    parent = QWidget()
    tabs = QTabWidget(parent)
    dialogs = MagicMock()
    cache = ColumnProfileCache()
    transport = MagicMock(return_value=QObject())
    monkeypatch.setattr(AsyncOperationController, "run_operation", transport)
    async_ops = AsyncOperationController(parent=parent, job_mgr=MagicMock(), busy=MagicMock(), dialogs=dialogs)
    manager = ResultTabManager(
        parent_widget=parent,
        tabs=tabs,
        busy_overlay=SimpleNamespace(run=lambda view, fn, **kwargs: fn()),
        async_ops=async_ops,
        col_profile_cache=cache,
        set_status=MagicMock(),
        dialogs=dialogs,
    )
    tabs.currentChanged.connect(manager.on_tab_changed)
    controller = DerivedColumnController(
        async_ops=async_ops, apply_to_view=manager.apply_to_view, dialogs=dialogs, main_window=parent
    )
    manager.set_derived_column_controller(controller)
    yield manager, tabs, transport, dialogs, cache
    qt_app.processEvents()
    parent.deleteLater()


def choose_derived(monkeypatch, manager, view, column: int) -> None:
    def execute(menu, pos):
        action = next(
            action for action in menu.actions() if action.text() == ResultTabColumnHeaderContextMenu.TR_DERIVED_COLUMN
        )
        assert action.isEnabled()
        return action

    monkeypatch.setattr(QMenu, "exec", execute)
    header = view.horizontalHeader()
    manager._on_header_context_menu(view, QPoint(header.sectionViewportPosition(column) + 2, 2))


@pytest.mark.parametrize("one", [False, True])
def test_derived_menu_action_follows_single_column_pattern(derived_env, one) -> None:
    manager, _, _, _, _ = derived_env
    source = pd.DataFrame({"a": [1], "b": [2]})
    manager.display_dataframe(source, title="Source")
    view = manager.active_view()
    ctx = build_header_context(view=view, df=source, column=0, column_name="a", only_one_selected=one)
    menu, action_map = ResultTabColumnHeaderContextMenu(view).build(ctx)
    action = next(action for action, action_id in action_map.items() if action_id == "column.derived")
    assert action.text() == ResultTabColumnHeaderContextMenu.TR_DERIVED_COLUMN
    assert action.isEnabled() is one
    actions = menu.actions()
    assert action_map[actions[actions.index(action) + 1]] == "column.split"


def test_tab_menu_no_longer_offers_derived_column(derived_env, monkeypatch) -> None:
    manager, tabs, transport, _, _ = derived_env
    manager.display_dataframe(pd.DataFrame({"a": [1]}), title="Source")
    inspected = []

    def execute(menu, pos):
        labels = [action.text() for action in menu.actions()]
        assert ResultTabColumnHeaderContextMenu.TR_DERIVED_COLUMN not in labels
        assert manager._tr(manager.TR_RESHAPE) in labels
        assert manager._tr(manager.TR_JOIN) in labels
        assert manager._tr(manager.TR_CONCATENATE) in labels
        inspected.append(True)

    monkeypatch.setattr(QMenu, "exec", execute)
    manager.on_tabbar_context_menu(tabs.tabBar().tabRect(0).center())
    assert inspected == [True]
    transport.assert_not_called()


@pytest.mark.parametrize("column", [0, 1, 2])
@pytest.mark.parametrize("row_count", [0, 2])
@pytest.mark.parametrize("formula", ["[c] + 1", "IF([c] > 5; 'High'; 'Low')"])
@pytest.mark.parametrize("dtype", ["Float64", "Int64", "UInt64"])
def test_header_creation_inserts_after_clicked_column_and_preserves_target_and_undo(
    derived_env, monkeypatch, qt_app, column, row_count, formula, dtype: str
) -> None:
    manager, tabs, transport, dialogs, cache = derived_env
    other = pd.DataFrame({"other": [9]})
    manager.display_dataframe(other, title="Other")
    other_id = manager.active_tab_id()
    source = pd.DataFrame({
        "a": pd.Series([1, 2], dtype="Int64"),
        "b": pd.Series(["x", None], dtype="string"),
        "c": pd.Series([4.5, 5.5] if dtype == "Float64" else [2**53 + 1, 2**53 + 3], dtype=dtype),
    }).iloc[:row_count]
    source.index = pd.Index([20, 10][:row_count], name="row")
    original = source.copy(deep=True)
    manager.display_dataframe(source, title="Source")
    source_id = manager.active_tab_id()
    view = manager.active_view()
    cache.set((source_id, "a"), MagicMock())
    cache.set((other_id, "other"), MagicMock())
    captured = {}

    def dialog(**kwargs):
        captured.update(kwargs)

        def accept():
            # A tab switch while the modal dialog is open must not change its dataset.
            tabs.setCurrentIndex(0)
            assert captured["validate_callback"]("Result", formula)[0].ok
            return QDialog.DialogCode.Accepted

        return SimpleNamespace(exec=accept, get_result=lambda: DerivedColumnSpec(" Result ", f" {formula} "))

    monkeypatch.setattr("expo_jbm329.workbench.controllers.derived_column_controller.DerivedColumnDialog", dialog)
    choose_derived(monkeypatch, manager, view, column)
    assert captured["df"] is source
    transport.assert_called_once()
    call = transport.call_args.kwargs
    assert call["runner"] == "pool"
    assert call["scope"] == "derived_column:Result"
    assert call["corr_id"]
    assert not manager._undo.has_undo(source_id)
    result = call["work"]()
    assert result[0]
    call["on_result"](result)

    expected_columns = list(source.columns)
    expected_columns.insert(column + 1, "Result")
    expected = original.copy()
    if formula == "[c] + 1":
        expected["Result"] = original["c"] + 1
    else:
        labels = ["Low", "High"] if dtype == "Float64" else ["High", "High"]
        expected["Result"] = pd.Series(labels[:row_count], index=original.index, dtype="string")
    expected = expected.loc[:, expected_columns]
    pd.testing.assert_frame_equal(manager.get_df_by_tab_id(source_id), expected)
    pd.testing.assert_frame_equal(view.model().data_frame(), expected)
    pd.testing.assert_frame_equal(manager.get_df_by_title("Source"), expected)
    collected = {title: df for df, title in manager.collect_all_tabs_data()}
    if row_count:
        pd.testing.assert_frame_equal(collected["Source"], expected)
    else:
        assert "Source" not in collected
    assert [
        view.model().headerData(i, Qt.Orientation.Horizontal) for i in range(len(expected_columns))
    ] == expected_columns
    assert manager.active_tab_id() == other_id
    pd.testing.assert_frame_equal(manager.current_df(), other)
    pd.testing.assert_frame_equal(manager.last_df, other)
    pd.testing.assert_frame_equal(source, original)
    assert tabs.count() == 2
    assert manager._undo.stack_size(source_id) == 1
    assert not manager._undo.has_undo(other_id)
    assert cache.get((source_id, "a")) is None
    assert cache.get((other_id, "other")) is not None
    tabs.setCurrentIndex(1)
    qt_app.processEvents()
    pd.testing.assert_frame_equal(manager.last_df, expected)
    manager.undo()
    pd.testing.assert_frame_equal(manager.current_df(), original)
    assert not manager._undo.has_undo(source_id)
    dialogs.critical.assert_not_called()


@pytest.mark.parametrize("completion", ["cancelled", "closed", "stale"])
def test_cancelled_or_stale_derived_operation_does_not_update_another_tab(derived_env, monkeypatch, completion) -> None:
    manager, tabs, transport, dialogs, _ = derived_env
    other = pd.DataFrame({"other": [9]})
    manager.display_dataframe(other, title="Other")
    manager.display_dataframe(pd.DataFrame({"a": [1]}), title="Source")
    source_id = manager.active_tab_id()
    view = manager.active_view()
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.derived_column_controller.DerivedColumnDialog",
        lambda **kwargs: SimpleNamespace(
            exec=lambda: QDialog.DialogCode.Accepted,
            get_result=lambda: DerivedColumnSpec("Result", "[a] + 1"),
        ),
    )
    choose_derived(monkeypatch, manager, view, 0)
    call = transport.call_args.kwargs
    result = call["work"](cancel_cb=lambda: completion == "cancelled")
    if completion == "closed":
        manager.close_tab(1)
        assert call["stale_check"]()
    elif completion == "stale":
        view.setModel(None)
        assert call["stale_check"]()
    tabs.setCurrentIndex(0)
    call["on_result"](result)
    pd.testing.assert_frame_equal(manager.current_df(), other)
    assert not manager._undo.has_undo(source_id)
    dialogs.critical.assert_not_called()


def test_multiple_selected_columns_do_not_start_derived_workflow(derived_env, monkeypatch) -> None:
    manager, _, transport, _, _ = derived_env
    manager.display_dataframe(pd.DataFrame({"a": [1], "b": [2]}), title="Source")
    view = manager.active_view()
    view.selectAll()
    inspected = []

    def execute(menu, pos):
        action = next(
            action for action in menu.actions() if action.text() == ResultTabColumnHeaderContextMenu.TR_DERIVED_COLUMN
        )
        assert not action.isEnabled()
        inspected.append(True)
        return action

    monkeypatch.setattr(QMenu, "exec", execute)
    manager._on_header_context_menu(view, QPoint(2, 2))
    assert inspected == [True]
    transport.assert_not_called()


def test_missing_derived_controller_is_logged(derived_env, monkeypatch, caplog) -> None:
    manager, _, transport, _, _ = derived_env
    manager.display_dataframe(pd.DataFrame({"a": [1]}), title="Source")
    manager._derived_column_controller = None
    choose_derived(monkeypatch, manager, manager.active_view(), 0)
    assert "Derived column controller is not available" in caplog.text
    transport.assert_not_called()
