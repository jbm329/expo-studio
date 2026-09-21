from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
from PyQt6.QtWidgets import QTableView, QWidget

from expo_jbm329.workbench.controllers.result_tabs.result_tab_header_category_actions import (
    ResultTabHeaderCategoryActions,
)


def test_category_actions_schedule_async():
    async_ops = MagicMock()
    dialogs = MagicMock()
    dialogs.prompt_category_rename.return_value = {"ok": False}
    dialogs.prompt_category_set_order.return_value = {"ok": False}
    ctrl = ResultTabHeaderCategoryActions(
        parent=QWidget(),
        dialogs=dialogs,
        logger=MagicMock(),
        async_ops=async_ops,
        resolve_df_col_series=MagicMock(
            return_value=(True, pd.DataFrame({"a": pd.Categorical(["x"])}), "a", pd.Series(pd.Categorical(["x"])))
        ),
        apply_new_dataframe=MagicMock(),
    )

    ctrl.remove_unused(QTableView(), 0)
    ctrl.set_order(QTableView(), 0)

    assert async_ops.run_dataframe_operation.call_count == 1
