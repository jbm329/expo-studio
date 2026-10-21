from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pandas as pd
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint
from PyQt6.QtWidgets import QApplication, QMenu, QTabWidget, QWidget

from expo_jbm329.gui.dialogs.service.null_dialog_service import NullDialogService
from expo_jbm329.services.data_profile.profile_cache import ColumnProfileCache
from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabHandle, ResultTabManager
from tests.stubs import DummyAsyncOps

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from PyQt6.QtGui import QAction

ClosingEnv = tuple[ResultTabManager, QTabWidget]


@pytest.fixture
def closing_env(qt_app: QApplication) -> Iterator[ClosingEnv]:
    parent = QWidget()
    tabs = QTabWidget(parent)
    manager = ResultTabManager(
        parent_widget=parent,
        tabs=tabs,
        busy_overlay=SimpleNamespace(),
        async_ops=DummyAsyncOps(),
        col_profile_cache=ColumnProfileCache(),
        set_status=lambda *_: None,
        dialogs=NullDialogService(),
    )
    tabs.currentChanged.connect(manager.on_tab_changed)
    tabs.tabCloseRequested.connect(manager.close_tab)
    yield manager, tabs
    qt_app.processEvents()
    parent.deleteLater()


def tab_ids(tabs: QTabWidget) -> list[str]:
    return [tabs.tabBar().tabData(i) for i in range(tabs.count())]


def choose_close_action(
    monkeypatch: pytest.MonkeyPatch,
    manager: ResultTabManager,
    tabs: QTabWidget,
    index: int,
    text: str,
    before_choice: Callable[[], None] | None = None,
) -> None:
    def execute(menu: QMenu, _pos: QPoint) -> QAction:
        if before_choice is not None:
            before_choice()
        return next(action for action in menu.actions() if action.text() == text)

    monkeypatch.setattr(QMenu, "exec", execute)
    manager.on_tabbar_context_menu(tabs.tabBar().tabRect(index).center())


@pytest.mark.parametrize("index", [0, 1, 3])
def test_close_others_with_real_queued_callbacks(
    closing_env: ClosingEnv, monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, index: int
) -> None:
    manager, tabs = closing_env
    handles = [manager.create_pending_tab(title=f"Tab {i}") for i in range(4)]
    assert tabs.currentIndex() == 3

    choose_close_action(monkeypatch, manager, tabs, index, manager.TR_CLOSE_OTHERS)

    assert tab_ids(tabs) == [handles[index].tab_id]
    qt_app.processEvents()
    assert not manager._closing_tabs


def test_duplicate_close_does_not_remove_next_tab(closing_env: ClosingEnv, qt_app: QApplication) -> None:
    manager, tabs = closing_env
    handles = [manager.create_pending_tab(title=f"Tab {i}") for i in range(3)]

    tabs.tabCloseRequested.emit(0)
    tabs.tabCloseRequested.emit(0)

    assert tab_ids(tabs) == [handle.tab_id for handle in handles[1:]]
    qt_app.processEvents()
    manager.close_tab(0)
    assert tab_ids(tabs) == [handles[2].tab_id]


@pytest.mark.parametrize("index", [0, 1, 3])
@pytest.mark.parametrize("move_tab", [False, True])
def test_close_right_uses_visual_order(
    closing_env: ClosingEnv, monkeypatch: pytest.MonkeyPatch, index: int, move_tab: bool
) -> None:
    manager, tabs = closing_env
    for i in range(4):
        manager.create_pending_tab(title=f"Tab {i}")
    if move_tab:
        tabs.tabBar().moveTab(3, 0)
    original = tab_ids(tabs)

    choose_close_action(monkeypatch, manager, tabs, index, manager.TR_CLOSE_RIGHT)

    assert tab_ids(tabs) == original[: index + 1]


@pytest.mark.parametrize("count", [1, 3])
def test_close_menu_order_and_enabled_states(
    closing_env: ClosingEnv, monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    manager, tabs = closing_env
    for i in range(count):
        manager.create_pending_tab(title=f"Tab {i}")

    def execute(menu: QMenu, _pos: QPoint) -> None:
        actions = [action for action in menu.actions() if action.text().startswith("Close")]
        assert [action.text() for action in actions] == [
            manager.TR_CLOSE,
            manager.TR_CLOSE_OTHERS,
            manager.TR_CLOSE_RIGHT,
            manager.TR_CLOSE_ALL,
        ]
        assert [action.isEnabled() for action in actions] == [True, count > 1, count > 1, count > 1]

    monkeypatch.setattr(QMenu, "exec", execute)
    manager.on_tabbar_context_menu(tabs.tabBar().tabRect(count - 1).center())
    assert tabs.count() == count


@pytest.mark.parametrize("text", ["Close", "Close others", "Close all to the right", "Close all"])
def test_removed_menu_target_never_closes_another_tab(
    closing_env: ClosingEnv, monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, text: str
) -> None:
    manager, tabs = closing_env
    handles = [manager.create_pending_tab(title=f"Tab {i}") for i in range(3)]

    def remove_target() -> None:
        manager.close_tab(1)
        qt_app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert sip.isdeleted(handles[1].view)

    choose_close_action(monkeypatch, manager, tabs, 1, text, remove_target)

    assert tab_ids(tabs) == [handles[0].tab_id, handles[2].tab_id]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Close", [0, 2, 3]),
        ("Close others", [1]),
        ("Close all to the right", [1]),
        ("Close all", []),
    ],
)
def test_menu_target_tracks_reordering(
    closing_env: ClosingEnv, monkeypatch: pytest.MonkeyPatch, text: str, expected: list[int]
) -> None:
    manager, tabs = closing_env
    handles = [manager.create_pending_tab(title=f"Tab {i}") for i in range(4)]

    choose_close_action(monkeypatch, manager, tabs, 1, text, lambda: tabs.tabBar().moveTab(1, 0))

    assert tab_ids(tabs) == [handles[i].tab_id for i in expected]


def make_ready(manager: ResultTabManager, title: str) -> ResultTabHandle:
    handle = manager.create_pending_tab(title=title)
    manager.fulfill_pending_tab(handle.tab_id, pd.DataFrame({"a": [1, 2]}))
    manager._undo.push_snapshot(handle.tab_id, pd.DataFrame({"a": [0]}))
    return handle


@pytest.mark.parametrize("text", ["Close others", "Close all to the right", "Close all"])
def test_bulk_cleanup_and_pending_cancellation(
    closing_env: ClosingEnv, monkeypatch: pytest.MonkeyPatch, qt_app: QApplication, text: str
) -> None:
    manager, tabs = closing_env
    keep = make_ready(manager, "Keep")
    ready = make_ready(manager, "Ready")
    pending = manager.create_pending_tab(title="Pending")
    uncancelled = manager.create_pending_tab(title="Uncancelled", close_cancels_job=False)
    manager.bind_job_to_tab(keep.tab_id, "ready-job")
    manager.bind_job_to_tab(pending.tab_id, "pending-job")
    manager.bind_job_to_tab(uncancelled.tab_id, "uncancelled-job")
    cancelled: list[str] = []

    def cancel(job_id: str) -> bool:
        cancelled.append(job_id)
        manager.close_tab(0)
        return True

    manager._cancel_job = cancel
    shapes: list[tuple[int | None, int | None]] = []
    manager._set_shape = lambda rows, columns: shapes.append((rows, columns))
    has_data: list[bool] = []
    analysis_ready: list[bool] = []
    multiple: list[bool] = []
    manager.apply_toolbar_data_state(has_data.append)
    manager.apply_toolbar_analysis_state(analysis_ready.append)
    manager._notify_toolbar_multi_dataset_cb = multiple.append
    qt_app.processEvents()

    choose_close_action(monkeypatch, manager, tabs, 0, text)
    qt_app.processEvents()

    all_closed = text == "Close all"
    assert cancelled == ["pending-job"]
    assert tab_ids(tabs) == ([] if all_closed else [keep.tab_id])
    assert list(manager._tabs_by_id) == ([] if all_closed else [keep.tab_id])
    assert list(manager._undo._stacks) == ([] if all_closed else [keep.tab_id])
    assert has_data[-1] is not all_closed
    assert analysis_ready[-1] is not all_closed
    assert multiple[-1] is False
    assert shapes[-1] == ((None, None) if all_closed else (2, 1))
    if all_closed:
        assert manager.last_df is None
    else:
        pd.testing.assert_frame_equal(manager.last_df, pd.DataFrame({"a": [1, 2]}))
        assert manager._undo.has_undo(keep.tab_id)
    closed_handles = [ready, pending, uncancelled] + ([keep] if all_closed else [])
    assert all(handle.view.model() is None for handle in closed_handles)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert all(sip.isdeleted(handle.view) for handle in closed_handles)


def test_close_all_handles_empty_and_single_tab(closing_env: ClosingEnv, qt_app: QApplication) -> None:
    manager, tabs = closing_env
    manager.close_all_tabs()
    assert not manager._closing_tabs
    handle = make_ready(manager, "Only")
    manager.close_all_tabs()
    qt_app.processEvents()
    assert tabs.count() == 0
    assert handle.tab_id not in manager._tabs_by_id
    assert manager.last_df is None


def test_missing_bulk_anchor_is_safe(closing_env: ClosingEnv) -> None:
    manager, tabs = closing_env
    handle = manager.create_pending_tab(title="Keep")
    manager.close_other_tabs("missing")
    manager.close_tabs_to_right("missing")
    assert tab_ids(tabs) == [handle.tab_id]
    assert not manager._closing_tabs


def test_title_closing_removes_all_matching_tabs(closing_env: ClosingEnv, qt_app: QApplication) -> None:
    manager, tabs = closing_env
    for i in range(4):
        make_ready(manager, f"Tab {i}")
        tabs.setTabText(i, "Match" if i != 1 else "Keep")
    keep_id = tab_ids(tabs)[1]

    manager.close_tabs_by_title(" Match ")
    qt_app.processEvents()

    assert tab_ids(tabs) == [keep_id]
    assert manager.current_df() is manager.last_df


def test_batch_snapshot_survives_cancellation_reordering(closing_env: ClosingEnv) -> None:
    manager, tabs = closing_env
    handles = [manager.create_pending_tab(title=f"Tab {i}") for i in range(4)]
    manager.bind_job_to_tab(handles[3].tab_id, "job")

    def cancel(_job_id: str) -> bool:
        tabs.tabBar().moveTab(3, 0)
        manager.create_pending_tab(title="New")
        return True

    manager._cancel_job = cancel
    manager.close_other_tabs(handles[1].tab_id)

    assert tabs.count() == 2
    assert tab_ids(tabs)[0] == handles[1].tab_id
    assert tabs.tabText(1).startswith("New")


def test_reentrant_pending_removal_does_not_interrupt_batch(closing_env: ClosingEnv) -> None:
    manager, tabs = closing_env
    handles = [manager.create_pending_tab(title=f"Tab {i}") for i in range(4)]
    for handle in handles:
        manager.bind_job_to_tab(handle.tab_id, handle.tab_id)
    cancelled: list[str] = []

    def cancel(job_id: str) -> bool:
        cancelled.append(job_id)
        manager.remove_pending_tab(job_id)
        return True

    manager._cancel_job = cancel
    manager.close_all_tabs()

    assert cancelled == [handle.tab_id for handle in reversed(handles)]
    assert tabs.count() == 0
    assert not manager._tabs_by_id


def test_cancellation_failure_is_logged_and_other_tabs_still_close(
    closing_env: ClosingEnv, caplog: pytest.LogCaptureFixture
) -> None:
    manager, tabs = closing_env
    handle = manager.create_pending_tab(title="Pending")
    manager.bind_job_to_tab(handle.tab_id, "job")
    manager.create_pending_tab(title="Other")

    def cancel(_job_id: str) -> bool:
        message = "Cancellation failed"
        raise RuntimeError(message)

    manager._cancel_job = cancel
    manager.close_all_tabs()

    assert tabs.count() == 0
    assert "failed to cancel pending job on tab close" in caplog.text


def test_empty_tabbar_does_not_open_menu(closing_env: ClosingEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    manager, _tabs = closing_env

    def execute(_menu: QMenu, _pos: QPoint) -> None:
        pytest.fail("Empty tab bar must not open a menu")

    monkeypatch.setattr(QMenu, "exec", execute)
    manager.on_tabbar_context_menu(QPoint(0, 0))
