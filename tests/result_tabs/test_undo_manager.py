from __future__ import annotations

import pandas as pd

from expo_jbm329.workbench.controllers.result_tabs.result_tab_undo_manager import (
    ResultTabUndoManager,
)


def test_register_push_pop_clear():
    mgr = ResultTabUndoManager()
    df = pd.DataFrame({"a": [1, 2]})

    mgr.register_tab("tab1")
    assert mgr.has_undo("tab1") is False

    assert mgr.push_snapshot("tab1", df) is True
    assert mgr.has_undo("tab1") is True
    assert mgr.stack_size("tab1") == 1

    snap = mgr.pop_snapshot("tab1")
    assert snap.equals(df)
    assert mgr.has_undo("tab1") is False

    mgr.clear()
    assert mgr.stack_size("tab1") == 0


def test_reload_settings_and_limits():
    mgr = ResultTabUndoManager(undo_limit_per_tab=2, max_size_allow_undo_mb=1)
    mgr.reload_settings({"workbench": {"undo_limit_per_tab": 1, "max_size_allow_undo_mb": 1}})
    assert mgr.stack_size("missing") == 0
