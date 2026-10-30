from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QMenu, QStyleOptionViewItem, QTableView, QTabWidget, QWidget

from expo_jbm329.gui.menus.result_tab_column_header_context_menu import ResultTabColumnHeaderContextMenu
from expo_jbm329.gui.menus.result_tab_header_context import build_header_context
from expo_jbm329.services.data_profile.profile_cache import ColumnProfileCache
from expo_jbm329.workbench.controllers.result_tabs.result_tab_column_presentation_delegate import (
    ResultTabColumnPresentationDelegate,
)
from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager


@pytest.mark.parametrize(
    ("column", "column_count", "one", "enabled"),
    [
        (0, 3, True, [True, False, False, True]),
        (1, 3, True, [True, True, True, True]),
        (2, 3, True, [False, True, True, False]),
        (0, 1, True, [False, False, False, False]),
        (1, 3, False, [False, False, False, False]),
    ],
)
@pytest.mark.parametrize("row_count", [0, 2])
def test_order_menu_labels_ids_and_availability(
    column: int, column_count: int, one: bool, enabled: list[bool], row_count: int
) -> None:
    view = QTableView()
    df = pd.DataFrame({f"c{i}": range(row_count) for i in range(column_count)})
    ctx = build_header_context(view=view, df=df, column=column, column_name=f"c{column}", only_one_selected=one)
    menu, action_map = ResultTabColumnHeaderContextMenu(view).build(ctx)
    order = next(action.menu() for action in menu.actions() if action.text() == "Order")

    assert order.isEnabled() == any(enabled)
    assert [action.text() for action in order.actions()] == ["Move right", "Move left", "Move to first", "Move to last"]
    assert [action_map[action] for action in order.actions()] == [
        "column.move_right",
        "column.move_left",
        "column.move_first",
        "column.move_last",
    ]
    assert [action.isEnabled() for action in order.actions()] == enabled
    assert ctx.can_move_left == (column > 0)
    assert ctx.can_move_right == (column < column_count - 1)


@pytest.mark.parametrize("missing", ["dataframe", "column", "index"])
def test_order_menu_unavailable_context_disables_moves(missing: str) -> None:
    view = QTableView()
    ctx = build_header_context(
        view=view,
        df=None if missing == "dataframe" else pd.DataFrame({"a": [1], "b": [2]}),
        column=-1 if missing == "index" else 0,
        column_name="missing" if missing == "column" else "a",
        only_one_selected=True,
    )
    menu, _ = ResultTabColumnHeaderContextMenu(view).build(ctx)
    order = next(action.menu() for action in menu.actions() if action.text() == "Order")

    assert not ctx.can_move_left and not ctx.can_move_right
    assert not order.isEnabled()
    assert not any(action.isEnabled() for action in order.actions())


def test_order_menu_uses_captured_availability() -> None:
    view = QTableView()
    df = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
    ctx = build_header_context(view=view, df=df, column=1, column_name="b", only_one_selected=True)
    del df["a"]
    del df["c"]

    menu, _ = ResultTabColumnHeaderContextMenu(view).build(ctx)
    order = next(action.menu() for action in menu.actions() if action.text() == "Order")

    assert all(action.isEnabled() for action in order.actions())


@pytest.fixture
def order_env(qt_app):
    parent = QWidget()
    tabs = QTabWidget(parent)
    async_ops = MagicMock()
    dialogs = MagicMock()
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
    yield manager, tabs, async_ops, dialogs, status, cache
    qt_app.processEvents()
    parent.deleteLater()


def choose_order(monkeypatch, manager, view, column: int, label: str) -> None:
    def execute(menu, pos):
        order = next(action.menu() for action in menu.actions() if action.text() == "Order")
        action = next(action for action in order.actions() if action.text() == label)
        assert action.isEnabled()
        return action

    monkeypatch.setattr(QMenu, "exec", execute)
    header = view.horizontalHeader()
    manager._on_header_context_menu(view, QPoint(header.sectionViewportPosition(column) + 2, 2))


@pytest.mark.parametrize(
    ("label", "expected_columns"),
    [
        ("Move right", ["a", "c", "b", "d"]),
        ("Move left", ["b", "a", "c", "d"]),
        ("Move to first", ["b", "a", "c", "d"]),
        ("Move to last", ["a", "c", "d", "b"]),
    ],
)
def test_order_menu_updates_dataset_consumers_and_undo(order_env, monkeypatch, label, expected_columns) -> None:
    manager, tabs, async_ops, dialogs, status, cache = order_env
    source = pd.DataFrame({"a": [2, 1], "b": [4, 3], "c": [6, 5], "d": [8, 7]}, index=[20, 10])
    original = source.copy(deep=True)
    other = pd.DataFrame({"other": [9]})
    manager.display_dataframe(other, title="Other")
    other_id = manager.active_tab_id()
    manager.display_dataframe(source, title="Source")
    source_id = manager.active_tab_id()
    view = manager.active_view()
    cache.set((source_id, "b"), MagicMock())
    cache.set((other_id, "other"), MagicMock())

    choose_order(monkeypatch, manager, view, 1, label)
    async_ops.run_dataframe_operation.assert_called_once()
    call = async_ops.run_dataframe_operation.call_args.kwargs
    assert call["view"] is view
    pd.testing.assert_frame_equal(manager.current_df(), original)
    assert not manager._undo.has_undo(source_id)

    result = call["work"]()
    call["apply_result"](result)
    expected = original.loc[:, expected_columns]
    pd.testing.assert_frame_equal(manager.current_df(), expected)
    pd.testing.assert_frame_equal(manager.last_df, expected)
    pd.testing.assert_frame_equal(manager.get_df_by_tab_id(source_id), expected)
    pd.testing.assert_frame_equal(manager.get_df_by_title("Source"), expected)
    collected = {title: df for df, title in manager.collect_all_tabs_data()}
    pd.testing.assert_frame_equal(collected["Source"], expected)
    pd.testing.assert_frame_equal(manager.get_df_by_tab_id(other_id), other)
    pd.testing.assert_frame_equal(source, original)
    assert manager._undo.stack_size(source_id) == 1
    assert not manager._undo.has_undo(other_id)
    assert cache.get((source_id, "b")) is None
    assert cache.get((other_id, "other")) is not None
    assert tabs.count() == 2
    model = view.model()
    assert [model.headerData(i, Qt.Orientation.Horizontal) for i in range(4)] == expected_columns
    assert status.call_args.args[0].startswith("Moved column 'b' to position")

    manager.undo()

    pd.testing.assert_frame_equal(manager.current_df(), original)
    pd.testing.assert_frame_equal(manager.get_df_by_tab_id(source_id), original)
    assert not manager._undo.has_undo(source_id)
    dialogs.critical.assert_not_called()


def test_repeated_moves_resolve_current_positions(order_env, monkeypatch) -> None:
    manager, _, async_ops, dialogs, _, _ = order_env
    source = pd.DataFrame({"a": [1], "b": [2], "c": [3], "d": [4]})
    manager.display_dataframe(source, title="Source")
    view = manager.active_view()

    for column, label, expected in (
        (1, "Move to last", ["a", "c", "d", "b"]),
        (3, "Move left", ["a", "c", "b", "d"]),
        (2, "Move to first", ["b", "a", "c", "d"]),
    ):
        choose_order(monkeypatch, manager, view, column, label)
        call = async_ops.run_dataframe_operation.call_args.kwargs
        call["apply_result"](call["work"]())
        assert list(manager.current_df().columns) == expected

    manager.undo()
    assert list(manager.current_df().columns) == ["a", "c", "b", "d"]
    manager.undo()
    assert list(manager.current_df().columns) == ["a", "c", "d", "b"]
    manager.undo()
    pd.testing.assert_frame_equal(manager.current_df(), source)
    dialogs.critical.assert_not_called()


def test_header_multi_selection_disables_order(order_env, monkeypatch) -> None:
    manager, _, async_ops, _, _, _ = order_env
    manager.display_dataframe(pd.DataFrame({"a": [1], "b": [2], "c": [3]}), title="Source")
    view = manager.active_view()
    view.selectAll()
    inspected = []

    def execute(menu, pos):
        order = next(action.menu() for action in menu.actions() if action.text() == "Order")
        assert not order.isEnabled()
        assert not any(action.isEnabled() for action in order.actions())
        inspected.append(True)

    monkeypatch.setattr(QMenu, "exec", execute)
    manager._on_header_context_menu(view, QPoint(2, 2))

    assert inspected == [True]
    async_ops.run_dataframe_operation.assert_not_called()


@pytest.mark.parametrize("indicator_shown", [False, True])
def test_order_preserves_header_identity_and_rebuilds_formatting(order_env, monkeypatch, indicator_shown) -> None:
    manager, _, async_ops, dialogs, _, _ = order_env
    source = pd.DataFrame({
        "number": [1.5, 2.5],
        "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "text": ["a", "b"],
    })
    manager._formatting_enabled = True
    manager.display_dataframe(source, title="Source")
    view = manager.active_view()
    old_delegate = view.itemDelegate()
    header = view.horizontalHeader()
    header.setStretchLastSection(False)
    sizes = [180, 210, 240]
    for i, size in enumerate(sizes):
        header.resizeSection(i, size)
    header.setSortIndicator(1, Qt.SortOrder.DescendingOrder)
    header.setSortIndicatorShown(indicator_shown)

    choose_order(monkeypatch, manager, view, 1, "Move to first")
    call = async_ops.run_dataframe_operation.call_args.kwargs
    call["apply_result"](call["work"]())

    assert header.sortIndicatorSection() == 0
    assert header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    assert header.isSortIndicatorShown() == indicator_shown
    assert [header.sectionSize(i) for i in range(3)] == [210, 180, 240]
    delegate = view.itemDelegate()
    assert isinstance(delegate, ResultTabColumnPresentationDelegate)
    assert delegate is not old_delegate
    assert delegate._semantics_by_column_index[0].semantic_dtype == "datetime"
    assert delegate._semantics_by_column_index[0].is_date_only
    assert delegate._semantics_by_column_index[1].semantic_dtype == "float"
    option = QStyleOptionViewItem()
    delegate.initStyleOption(option, view.model().index(0, 0))
    assert option.text == "2026-01-01"
    pd.testing.assert_frame_equal(manager.current_df(), source.loc[:, ["date", "number", "text"]])

    manager.undo()

    assert header.sortIndicatorSection() == 1
    assert header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    assert header.isSortIndicatorShown() == indicator_shown
    assert [header.sectionSize(i) for i in range(3)] == sizes
    pd.testing.assert_frame_equal(manager.current_df(), source)
    dialogs.critical.assert_not_called()
