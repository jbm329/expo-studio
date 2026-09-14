from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtWidgets import QDialog, QWidget

from expo_jbm329.services.data_operations.derived_column.derived_column_service import (
    DerivedColumnSpec,
)
from expo_jbm329.workbench.controllers.derived_column_controller import (
    DerivedColumnController,
)


class DummyDialogService:
    def __init__(self) -> None:
        self.info_calls = []
        self.critical_calls = []

    def info(self, parent, title, text):
        self.info_calls.append((parent, title, text))

    def critical(self, parent, title, text):
        self.critical_calls.append((parent, title, text))


class DummyAsyncOps:
    def __init__(self) -> None:
        self.calls = []

    def run_dataframe_operation(self, **kwargs):
        self.calls.append(kwargs)
        self.last_kwargs = kwargs
        return object()


@pytest.fixture
def controller():
    dialogs = DummyDialogService()
    async_ops = DummyAsyncOps()
    apply_to_active_tab = MagicMock()
    current_df = MagicMock(return_value=pd.DataFrame({"n": [1, 2]}))
    active_view = MagicMock(return_value=QWidget())

    ctrl = DerivedColumnController(
        async_ops=async_ops,
        current_df=current_df,
        get_active_view=active_view,
        apply_to_active_tab=apply_to_active_tab,
        dialogs=dialogs,
        main_window=QWidget(),
    )
    return ctrl, async_ops, dialogs, apply_to_active_tab, current_df, active_view


def test_validate_reports_missing_active_dataframe():
    ctrl = DerivedColumnController(
        async_ops=DummyAsyncOps(),
        current_df=MagicMock(return_value=None),
        get_active_view=MagicMock(return_value=QWidget()),
        apply_to_active_tab=MagicMock(),
        dialogs=DummyDialogService(),
        main_window=QWidget(),
    )

    ok, message = ctrl._validate("new_col", "n + 1")

    assert ok is False
    assert message


def test_get_active_dataframe_missing_tab_shows_info():
    dialogs = DummyDialogService()
    ctrl = DerivedColumnController(
        async_ops=DummyAsyncOps(),
        current_df=MagicMock(return_value=None),
        get_active_view=MagicMock(return_value=QWidget()),
        apply_to_active_tab=MagicMock(),
        dialogs=dialogs,
        main_window=QWidget(),
    )

    assert ctrl._get_active_dataframe() is None
    assert dialogs.info_calls


def test_create_derived_column_runs_async(controller, monkeypatch):
    ctrl, async_ops, _, _, _, _ = controller

    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.derived_column_controller.get_numeric_columns",
        lambda df: ["n"],
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.derived_column_controller.DerivedColumnDialog",
        lambda **kwargs: type(
            "Dlg",
            (),
            {
                "exec": lambda self: QDialog.DialogCode.Accepted,
                "get_result": lambda self: DerivedColumnSpec(
                    column_name="derived",
                    formula="n + 1",
                    overwrite_existing=False,
                ),
            },
        )(),
    )

    ctrl.create_derived_column()

    assert async_ops.calls


def test_apply_result_calls_active_tab(controller):
    ctrl, _, _, apply_to_active_tab, _, _ = controller

    ctrl._apply_result(pd.DataFrame({"n": [1]}), DerivedColumnSpec("derived", "n+1"))

    assert apply_to_active_tab.called
