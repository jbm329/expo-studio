from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtWidgets import QDialog, QWidget

from expo_jbm329.workbench.controllers.join_controller import JoinController


class DummyAsyncOps:
    def __init__(self) -> None:
        self.calls = []
        self.job_mgr = MagicMock(get_job_id=lambda job: "job-1")
        self.job = object()

    def run_target_overlay_operation(self, **kwargs):
        self.calls.append(kwargs)
        self.last_kwargs = kwargs
        return self.job


class DummyResults:
    def __init__(self) -> None:
        self.pending = []
        self.bind_calls = []
        self.fulfill_calls = []
        self.remove_calls = []
        self.tabs_by_id = {}

    def create_pending_tab(self, **kwargs):
        tab_id = "pending-join"
        self.pending.append(kwargs)
        self.tabs_by_id[tab_id] = type("R", (), {"is_pending": True})()
        return type("H", (), {"tab_id": tab_id, "view": QWidget()})()

    def fulfill_pending_tab(self, tab_id, df):
        self.fulfill_calls.append((tab_id, df))
        self.tabs_by_id[tab_id].is_pending = False

    def remove_pending_tab(self, tab_id):
        self.remove_calls.append(tab_id)

    def bind_job_to_tab(self, tab_id, job_id):
        self.bind_calls.append((tab_id, job_id))


class DummyDialog:
    def __init__(self, result):
        self._result = result
        self.btn_preview = type("B", (), {"clicked": type("S", (), {"connect": lambda self, cb: None})()})()
        self.btn_cancel = type("B", (), {"clicked": type("S", (), {"connect": lambda self, cb: None})()})()
        self.btn_ok = type("B", (), {"clicked": type("S", (), {"connect": lambda self, cb: None})()})()

    def exec(self):
        return QDialog.DialogCode.Accepted

    def build_result(self):
        return self._result


@pytest.fixture
def controller(monkeypatch):
    async_ops = DummyAsyncOps()
    results = DummyResults()
    status = MagicMock()

    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.join_controller.JoinDialog",
        lambda **kwargs: DummyDialog(
            result=type(
                "JoinResult",
                (),
                {
                    "left_tab_title": "left",
                    "right_tab_title": "right",
                    "left_on": ["id"],
                    "right_on": ["id"],
                    "join_type": "inner",
                    "suffix_left": "_l",
                    "suffix_right": "_r",
                },
            )()
        ),
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.join_controller.join_dataframes",
        lambda request: pd.DataFrame({"id": [1]}),
    )

    ctrl = JoinController(
        parent_widget=QWidget(),
        async_ops=async_ops,
        results=results,
        get_active_tab_title=lambda: "left",
        get_active_view=lambda: QWidget(),
        list_tab_titles=lambda: ["left", "right"],
        get_df_for_tab=lambda title: pd.DataFrame({"id": [1]}),
        set_status=status,
    )
    return ctrl, async_ops, results, status


def test_open_join_dialog_runs_join(controller):
    ctrl, async_ops, results, _ = controller

    ctrl.open_join_dialog()

    assert async_ops.calls
    assert results.pending
    assert results.bind_calls == [("pending-join", "job-1")]


def test_join_result_updates_pending_tab(controller):
    ctrl, async_ops, results, status = controller
    ctrl.open_join_dialog()
    on_result = async_ops.last_kwargs["on_result"]

    on_result(pd.DataFrame({"id": [1]}))

    assert results.fulfill_calls
    assert status.called
