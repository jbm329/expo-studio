from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
from PyQt6.QtWidgets import QTableView, QWidget

from expo_jbm329.workbench.controllers.result_tabs.result_tab_header_fill_actions import (
    ResultTabHeaderFillActions,
)


def test_fill_actions_schedule_async():
    async_ops = MagicMock()
    dialogs = MagicMock()
    ctrl = ResultTabHeaderFillActions(
        parent=QWidget(),
        dialogs=dialogs,
        logger=MagicMock(),
        async_ops=async_ops,
        resolve_df_col_series=MagicMock(return_value=(True, pd.DataFrame({"a": [1, None]}), "a", pd.Series([1, None]))),
        get_series_semantics=MagicMock(return_value=None),
        apply_new_dataframe=MagicMock(),
    )

    ctrl.fill_mean(QTableView(), 0)
    ctrl.fill_median(QTableView(), 0)
    ctrl.fill_mode(QTableView(), 0)

    assert async_ops.run_dataframe_operation.call_count >= 1
