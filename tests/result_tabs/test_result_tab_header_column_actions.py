from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import pandas as pd
import pytest
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


@pytest.fixture
def movement_actions() -> tuple[ResultTabHeaderColumnActions, pd.DataFrame, MagicMock, MagicMock, MagicMock]:
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6], "d": [7, 8]}, index=[20, 10])
    async_ops = MagicMock()
    apply_new = MagicMock()
    resolve = MagicMock(return_value=(True, df, "b", df["b"]))
    ctrl = ResultTabHeaderColumnActions(
        parent=QWidget(),
        dialogs=MagicMock(),
        logger=MagicMock(),
        async_ops=async_ops,
        resolve_df_col_series=resolve,
        apply_new_dataframe=apply_new,
    )
    return ctrl, df, async_ops, apply_new, resolve


@pytest.mark.parametrize(
    ("method", "expected_columns", "position"),
    [
        ("move_right", ["a", "c", "b", "d"], 3),
        ("move_left", ["b", "a", "c", "d"], 1),
        ("move_to_first", ["b", "a", "c", "d"], 1),
        ("move_to_last", ["a", "c", "d", "b"], 4),
    ],
)
def test_movement_schedules_worker_and_applies_result(
    movement_actions, method: str, expected_columns: list[str], position: int
) -> None:
    ctrl, df, async_ops, apply_new, resolve = movement_actions
    original = df.copy(deep=True)
    view = QTableView()

    getattr(ctrl, method)(view, 1)

    resolve.assert_called_once_with(view, 1)
    async_ops.run_dataframe_operation.assert_called_once()
    call = async_ops.run_dataframe_operation.call_args.kwargs
    assert call["view"] is view
    assert call["runner"] == "pool"
    assert call["scope"] == "move:b"
    assert call["operation_name"] == "move column"
    assert call["busy_message"] == "Moving column: b"
    assert UUID(call["corr_id"]).version == 4
    apply_new.assert_not_called()

    new_df = call["work"](progress_cb=MagicMock(), cancel_cb=lambda: False)

    assert new_df is not df
    pd.testing.assert_frame_equal(new_df, original.loc[:, expected_columns])
    pd.testing.assert_frame_equal(df, original)
    call["apply_result"](new_df)
    apply_new.assert_called_once()
    args = apply_new.call_args.args
    assert args[0] is view
    assert args[1] is new_df
    assert args[2] == f"Moved column 'b' to position {position}"


@pytest.mark.parametrize(
    ("method", "column", "column_count"),
    [
        ("move_left", 0, 4),
        ("move_to_first", 0, 4),
        ("move_right", 3, 4),
        ("move_to_last", 3, 4),
        ("move_left", 0, 1),
        ("move_to_first", 0, 1),
        ("move_right", 0, 1),
        ("move_to_last", 0, 1),
    ],
)
def test_movement_at_boundary_does_not_schedule_or_apply(
    movement_actions, method: str, column: int, column_count: int
) -> None:
    ctrl, df, async_ops, apply_new, resolve = movement_actions
    df = df.iloc[:, :column_count]
    resolve.return_value = (True, df, str(df.columns[column]), df.iloc[:, column])

    getattr(ctrl, method)(QTableView(), column)

    async_ops.run_dataframe_operation.assert_not_called()
    apply_new.assert_not_called()
    ctrl._logger.debug.assert_called_once()


@pytest.mark.parametrize("method", ["move_right", "move_left", "move_to_first", "move_to_last"])
@pytest.mark.parametrize("missing", ["resolution", "dataframe", "column"])
def test_movement_unavailable_target_does_not_schedule(movement_actions, method: str, missing: str) -> None:
    ctrl, df, async_ops, apply_new, resolve = movement_actions
    resolve.return_value = (
        missing != "resolution",
        None if missing == "dataframe" else df,
        None if missing == "column" else "b",
        None,
    )

    getattr(ctrl, method)(QTableView(), 1)

    async_ops.run_dataframe_operation.assert_not_called()
    apply_new.assert_not_called()


def test_movement_cancelled_worker_does_not_apply(movement_actions, monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, _, async_ops, apply_new, _ = movement_actions
    move = MagicMock()
    monkeypatch.setattr("expo_jbm329.services.data_operations.columns.move_column", move)
    ctrl.move_right(QTableView(), 1)
    call = async_ops.run_dataframe_operation.call_args.kwargs

    result = call["work"](cancel_cb=lambda: True)
    call["apply_result"](result)

    assert result is None
    move.assert_not_called()
    apply_new.assert_not_called()


def test_movement_worker_propagates_service_errors(movement_actions, monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, _, async_ops, apply_new, _ = movement_actions
    monkeypatch.setattr(
        "expo_jbm329.services.data_operations.columns.move_column",
        MagicMock(side_effect=IndexError("Invalid source column index")),
    )
    ctrl.move_right(QTableView(), 1)
    call = async_ops.run_dataframe_operation.call_args.kwargs

    with pytest.raises(IndexError, match="Invalid source column index"):
        call["work"]()

    apply_new.assert_not_called()


def test_movement_captures_status_before_worker_dispatch(movement_actions, monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl, _, async_ops, apply_new, _ = movement_actions
    translate = MagicMock(side_effect=lambda text, **kwargs: text.format(**kwargs))
    monkeypatch.setattr(ResultTabHeaderColumnActions, "_tr_fmt", staticmethod(translate))
    ctrl.move_right(QTableView(), 1)
    call = async_ops.run_dataframe_operation.call_args.kwargs
    translate.side_effect = AssertionError("Translation must not occur after dispatch")

    call["apply_result"](call["work"]())

    assert apply_new.call_args.args[2] == "Moved column 'b' to position 3"


def test_movement_operations_have_unique_correlation_ids(movement_actions) -> None:
    ctrl, _, async_ops, _, _ = movement_actions

    ctrl.move_right(QTableView(), 1)
    ctrl.move_left(QTableView(), 1)

    first, second = async_ops.run_dataframe_operation.call_args_list
    assert first.kwargs["corr_id"] != second.kwargs["corr_id"]
