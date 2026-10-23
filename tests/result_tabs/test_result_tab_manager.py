from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QMenu

from expo_jbm329.gui.dialogs.workflows.reshape.reshape_dialog import ReshapeDialog
from expo_jbm329.workbench.controllers.reshape_controller import ReshapeController
from tests.result_tabs.conftest import make_manager


def test_display_dataframe_creates_tab(result_tabs_env):
    mgr, _, tabs, _, _, _, _ = make_manager(result_tabs_env)
    df = pd.DataFrame({"a": [1, 2]})

    mgr.display_dataframe(df, title="X")

    assert tabs.count() == 1
    assert mgr.last_df.equals(df)
    assert mgr.tabs_count == 1


def test_close_tabs_by_title(result_tabs_env):
    mgr, _, tabs, _, _, _, _ = make_manager(result_tabs_env)
    mgr.display_dataframe(pd.DataFrame({"a": [1]}), title="A")
    mgr.display_dataframe(pd.DataFrame({"b": [2]}), title="B")

    mgr.close_tabs_by_title("A")

    assert tabs.count() == 1
    assert [title for _, title in mgr.collect_all_tabs_data()] == ["B"]


def test_collect_all_tabs_data(result_tabs_env):
    mgr, _, _, _, _, _, _ = make_manager(result_tabs_env)
    mgr.display_dataframe(pd.DataFrame({"a": [1]}), title="A")
    mgr.display_dataframe(pd.DataFrame(), title="Empty")

    data = mgr.collect_all_tabs_data()
    assert len(data) == 1
    assert data[0][1] == "A"


def test_analysis_readiness_tracks_the_active_tab_not_other_ready_tabs(result_tabs_env):
    mgr, _, tabs, _, _, _, _ = make_manager(result_tabs_env)
    active_states: list[bool] = []
    any_data_states: list[bool] = []
    mgr.apply_toolbar_analysis_state(active_states.append)
    mgr.apply_toolbar_data_state(any_data_states.append)
    assert active_states == [False]

    mgr.display_dataframe(pd.DataFrame({"a": [1]}), title="Ready")
    ready_index = tabs.currentIndex()
    assert active_states[-1]
    assert any_data_states[-1]

    mgr.create_pending_tab(title="Pending")
    pending_index = tabs.currentIndex()
    assert pending_index != ready_index
    assert not active_states[-1]
    assert any_data_states[-1]

    tabs.setCurrentIndex(ready_index)
    mgr.on_tab_changed(ready_index)
    assert active_states[-1]
    assert any_data_states[-1]

    tabs.setCurrentIndex(pending_index)
    mgr.on_tab_changed(pending_index)
    assert not active_states[-1]
    assert any_data_states[-1]


def test_reshape_context_activates_clicked_dataset_without_creating_tabs(result_tabs_env, monkeypatch):
    mgr, _, tabs, _, _, _, _ = make_manager(result_tabs_env)
    source = pd.DataFrame({"a": [1]})
    mgr.display_dataframe(source, title="Source")
    mgr.display_dataframe(pd.DataFrame({"b": [2]}), title="Other")
    tabs.setCurrentIndex(1)
    controller = MagicMock()
    mgr.set_reshape_controller(controller)
    captured: list[str | None] = []
    controller.open_reshape_dialog.side_effect = lambda: captured.append(mgr.active_tab_id())

    def choose_reshape(menu, pos):
        actions = menu.actions()
        action = next(action for action in actions if action.text() == "Reshape…")
        assert action.isEnabled()
        assert actions[actions.index(action) - 1].text() == "Concatenate…"
        return action

    monkeypatch.setattr(QMenu, "exec", choose_reshape)
    mgr.on_tabbar_context_menu(QPoint(0, 0))
    assert tabs.currentIndex() == 0
    assert captured == [tabs.tabData(0)]
    assert tabs.count() == 2
    pd.testing.assert_frame_equal(mgr.get_df_by_tab_id(tabs.tabData(0)), source)


@pytest.mark.parametrize("pending", [False, True])
def test_reshape_context_readiness_with_one_tab(result_tabs_env, monkeypatch, pending):
    mgr, _, tabs, _, _, _, _ = make_manager(result_tabs_env)
    if pending:
        mgr.create_pending_tab(title="Pending")
    else:
        mgr.display_dataframe(pd.DataFrame({"a": [1]}), title="Ready")

    def inspect_menu(menu, pos):
        action = next(action for action in menu.actions() if action.text() == "Reshape…")
        assert action.isEnabled() is not pending

    monkeypatch.setattr(QMenu, "exec", inspect_menu)
    mgr.on_tabbar_context_menu(QPoint(0, 0))
    assert tabs.count() == 1


def test_reshape_context_removed_target_is_not_opened(result_tabs_env, monkeypatch):
    mgr, _, tabs, _, _, _, _ = make_manager(result_tabs_env)
    mgr.display_dataframe(pd.DataFrame({"a": [1]}), title="Source")
    controller = MagicMock()
    mgr.set_reshape_controller(controller)

    def remove_target(menu, pos):
        action = next(action for action in menu.actions() if action.text() == "Reshape…")
        mgr.close_tab(0)
        return action

    monkeypatch.setattr(QMenu, "exec", remove_target)
    mgr.on_tabbar_context_menu(QPoint(0, 0))
    controller.open_reshape_dialog.assert_not_called()
    assert tabs.count() == 0


def test_reshape_context_opens_real_dialog_for_clicked_source(result_tabs_env, monkeypatch):
    mgr, parent, tabs, _, _, _, _ = make_manager(result_tabs_env)
    dataframe = pd.DataFrame({"PatientId": [1, 2], "VisitId": ["a", "b"]})
    original = dataframe.copy(deep=True)
    mgr.display_dataframe(dataframe, title="Source")
    source_id = tabs.tabData(0)
    mgr.display_dataframe(pd.DataFrame({"Other": [3]}), title="Other")
    tabs.setCurrentIndex(1)
    controller = ReshapeController(parent_widget=parent, results=mgr)
    mgr.set_reshape_controller(controller)
    opened: list[str] = []

    def inspect_dialog(dialog):
        assert mgr.active_tab_id() == source_id
        assert "Source" in dialog.windowTitle()
        assert [dialog.dimensions.item(i).text() for i in range(dialog.dimensions.count())] == ["PatientId", "VisitId"]
        assert not dialog.apply_button.isEnabled()
        opened.append(dialog.windowTitle())
        return 0

    monkeypatch.setattr(ReshapeDialog, "exec", inspect_dialog)
    monkeypatch.setattr(
        QMenu,
        "exec",
        lambda menu, pos: next(action for action in menu.actions() if action.text() == "Reshape…"),
    )
    mgr.on_tabbar_context_menu(QPoint(0, 0))
    assert len(opened) == 1
    assert tabs.count() == 2
    pd.testing.assert_frame_equal(mgr.get_df_by_tab_id(source_id), original)
