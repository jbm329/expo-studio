from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
from PyQt6.QtWidgets import QWidget, QTableView

from expo_jbm329.workbench.controllers.result_tabs.result_tab_header_sort_actions import (
    ResultTabHeaderSortActions,
)


def test_sort_actions_call_async_and_apply():
    async_ops = MagicMock()
    resolve = MagicMock(return_value=(True, pd.DataFrame({"a": [2, 1]}), "a", pd.Series([2, 1])))
    apply_new = MagicMock()
    ctrl = ResultTabHeaderSortActions(
        parent=QWidget(),
        dialogs=MagicMock(),
        logger=MagicMock(),
        async_ops=async_ops,
        resolve_df_col_series=resolve,
        apply_new_dataframe=apply_new,
    )

    ctrl.sort_ascending(QTableView(), 0)

    assert async_ops.run_dataframe_operation.called

