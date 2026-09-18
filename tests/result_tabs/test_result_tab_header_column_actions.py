from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
from PyQt6.QtWidgets import QTableView, QWidget

from expo_jbm329.workbench.controllers.result_tabs.result_tab_header_column_actions import (
    ResultTabHeaderColumnActions,
)


def test_column_actions_schedule_async():
    async_ops = MagicMock()
    dialogs = MagicMock()
    dialogs.prompt_split_column.return_value = {"ok": False}
    dialogs.prompt_merge_columns.return_value = {"ok": False}
    dialogs.prompt_text.return_value = ("new", True)
    dialogs.confirm_delete.return_value = True
    ctrl = ResultTabHeaderColumnActions(
        parent=QWidget(),
        dialogs=dialogs,
        logger=MagicMock(),
        async_ops=async_ops,
        resolve_df_col_series=MagicMock(return_value=(True, pd.DataFrame({"a": [1]}), "a", pd.Series([1]))),
        apply_new_dataframe=MagicMock(),
    )

    ctrl.rename_column(QTableView(), 0)
    ctrl.remove_column(QTableView(), 0)

    assert async_ops.run_dataframe_operation.call_count == 2

