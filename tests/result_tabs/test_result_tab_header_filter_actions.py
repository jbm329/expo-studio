from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
from PyQt6.QtWidgets import QTableView, QWidget

from expo_jbm329.workbench.controllers.result_tabs.result_tab_cell_actions import (
    ResultTabCellActions,
)


def test_cell_filter_and_replace_actions():
    async_ops = MagicMock()
    dialogs = MagicMock()
    dialogs.prompt_value_replace.return_value = {"ok": True, "new_value": "x", "replace_all": True}
    ctrl = ResultTabCellActions(
        parent=QWidget(),
        dialogs=dialogs,
        logger=MagicMock(),
        async_ops=async_ops,
        apply_new_dataframe=MagicMock(),
    )

    df = pd.DataFrame({"a": [1, 2]})
    ctrl.filter_keep(QTableView(), df, column_name="a", raw_value=1)
    ctrl.replace_value(QTableView(), df, row_index=0, column_name="a", raw_value=1)

    assert async_ops.run_dataframe_operation.call_count == 2
