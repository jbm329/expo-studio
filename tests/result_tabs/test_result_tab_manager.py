from __future__ import annotations

import pandas as pd

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

    assert tabs.count() == 2
    assert [title for _, title in mgr.collect_all_tabs_data()] == ["A", "B"]


def test_collect_all_tabs_data(result_tabs_env):
    mgr, _, _, _, _, _, _ = make_manager(result_tabs_env)
    mgr.display_dataframe(pd.DataFrame({"a": [1]}), title="A")
    mgr.display_dataframe(pd.DataFrame(), title="Empty")

    data = mgr.collect_all_tabs_data()
    assert len(data) == 1
    assert data[0][1] == "A"
