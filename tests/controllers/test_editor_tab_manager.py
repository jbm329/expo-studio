from __future__ import annotations

from expo_jbm329.workbench.controllers.editor_tab_manager import (
    EditorTabManager,
    EditorTabState,
)


def test_create_and_manage_tabs():
    mgr = EditorTabManager()
    tab = mgr.create_tab()

    assert tab.base_title.startswith("Query")
    assert mgr.get_active_tab() == tab
    assert mgr.tab_count() == 1
    assert mgr.can_execute_sql() is False


def test_bind_state_and_dirty_flags():
    mgr = EditorTabManager()
    tab = mgr.create_tab()

    mgr.bind_tab_to_connection(tab.tab_id, "conn")
    assert mgr.get_tab(tab.tab_id).connection_name == "conn"

    mgr.on_connection_disconnected("conn")
    assert mgr.get_tab(tab.tab_id).state == EditorTabState.DISCONNECTED

    mgr.on_connection_reconnected("conn")
    assert mgr.get_tab(tab.tab_id).state == EditorTabState.BOUND

    mgr.mark_dirty(tab.tab_id)
    assert mgr.get_tab(tab.tab_id).is_dirty is True
    assert "*" in mgr.build_tab_title(mgr.get_tab(tab.tab_id))

    mgr.clear_dirty(tab.tab_id)
    assert mgr.get_tab(tab.tab_id).is_dirty is False


def test_file_path_and_close():
    mgr = EditorTabManager()
    tab = mgr.create_tab()

    mgr.set_file_path(tab.tab_id, "C:/tmp/test.sql")
    assert mgr.get_tab(tab.tab_id).file_path.endswith("test.sql")

    assert mgr.close_tab(tab.tab_id) is True
    assert mgr.tab_count() == 0
