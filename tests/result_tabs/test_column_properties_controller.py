from __future__ import annotations

import pandas as pd

from tests.result_tabs.conftest import make_manager


def test_column_properties_invalid_column_no_crash(result_tabs_env):
    mgr, _, tabs, _, _, dialogs, _ = make_manager(result_tabs_env)
    mgr.display_dataframe(pd.DataFrame({"a": [1]}), title="A")
    view = tabs.widget(0)

    mgr._column_properties.open(view, 99)

    assert dialogs.calls == []
