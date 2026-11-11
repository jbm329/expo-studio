from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest
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


@pytest.mark.parametrize("dtype", ["float64", "Int64", "boolean"])
@pytest.mark.parametrize("missing_selection", [False, True])
def test_cell_remove_worker_preserves_approved_missing_value_policy(dtype: str, missing_selection: bool) -> None:
    frame = pd.DataFrame({"value": pd.Series([1, 0, None], dtype=dtype)})
    original = frame.copy(deep=True)
    async_ops = MagicMock()
    apply_result = MagicMock()
    view = QTableView()
    controller = ResultTabCellActions(
        parent=QWidget(),
        dialogs=MagicMock(),
        logger=MagicMock(),
        async_ops=async_ops,
        apply_new_dataframe=apply_result,
    )
    selected_value = frame["value"].iloc[2 if missing_selection else 0]

    controller.filter_remove(view, frame, column_name="value", raw_value=selected_value)

    operation = async_ops.run_dataframe_operation.call_args.kwargs
    assert operation["view"] is view
    assert operation["runner"] == "pool"
    assert operation["work"](cancel_cb=lambda: True) is None
    result = operation["work"](cancel_cb=lambda: False)
    expected = original.iloc[[0, 1] if missing_selection else [1, 2]]
    pd.testing.assert_frame_equal(result, expected)
    operation["apply_result"](None)
    apply_result.assert_not_called()
    operation["apply_result"](result)
    assert apply_result.call_args.args[0] is view
    pd.testing.assert_frame_equal(apply_result.call_args.args[1], expected)
    pd.testing.assert_frame_equal(frame, original)
