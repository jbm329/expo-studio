from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from PyQt6.QtWidgets import QDialog, QWidget

from expo_jbm329.workbench.controllers.concat_controller import ConcatController


@dataclass
class DummyPendingHandle:
    tab_id: str
    view: QWidget


class DummyResults:
    def __init__(self) -> None:
        self.pending = []
        self.bind_calls = []
        self.fulfill_calls = []
        self.remove_calls = []
        self.tabs_by_id = {}

    def create_pending_tab(self, **kwargs):
        handle = DummyPendingHandle(tab_id="pending-1", view=QWidget())
        self.pending.append(kwargs)
        self.tabs_by_id[handle.tab_id] = SimpleNamespace(is_pending=True)
        return handle

    def fulfill_pending_tab(self, tab_id, df):
        self.fulfill_calls.append((tab_id, df))
        self.tabs_by_id[tab_id] = SimpleNamespace(is_pending=False)

    def remove_pending_tab(self, tab_id):
        self.remove_calls.append(tab_id)
        self.tabs_by_id.pop(tab_id, None)

    def bind_job_to_tab(self, tab_id, job_id):
        self.bind_calls.append((tab_id, job_id))


class DummyJobMgr:
    def get_job_id(self, job):
        return "job-1"


class DummyAsyncOps:
    def __init__(self) -> None:
        self.job_mgr = DummyJobMgr()
        self.calls = []
        self.job = object()

    def run_target_overlay_operation(self, **kwargs):
        self.calls.append(kwargs)
        self.last_kwargs = kwargs
        return self.job


class DummyDialog:
    def __init__(self, accepted=True, result=None):
        self._accepted = accepted
        self._result = result

    def exec(self):
        return QDialog.DialogCode.Accepted if self._accepted else QDialog.DialogCode.Rejected

    def build_result(self):
        return self._result


@pytest.fixture
def controller(monkeypatch):
    async_ops = DummyAsyncOps()
    results = DummyResults()
    status = MagicMock()
    df_map = {
        "left": pd.DataFrame({"a": [1]}),
        "right": pd.DataFrame({"b": [2]}),
    }

    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.concat_controller.ConcatDialog",
        lambda **kwargs: DummyDialog(
            result=SimpleNamespace(
                left_tab_title="left",
                right_tab_title="right",
                remove_duplicates=True,
            )
        ),
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.concat_controller.concat_dataframes",
        lambda request: pd.concat([request.left, request.right], axis=1),
    )

    ctrl = ConcatController(
        parent_widget=QWidget(),
        async_ops=async_ops,
        results=results,
        get_active_tab_title=lambda: "left",
        list_tab_titles=lambda: ["left", "right"],
        get_df_for_tab=lambda title: df_map[title],
        set_status=status,
    )
    return ctrl, async_ops, results, status


def test_open_concat_dialog_runs_concat(controller):
    ctrl, async_ops, results, _ = controller

    ctrl.open_concat_dialog()

    assert async_ops.calls
    assert results.pending
    assert results.bind_calls == [("pending-1", "job-1")]


def test_concat_result_updates_pending_tab(controller):
    ctrl, async_ops, results, status = controller
    ctrl.open_concat_dialog()
    on_result = async_ops.last_kwargs["on_result"]

    on_result(pd.DataFrame({"a": [1], "b": [2]}))

    assert results.fulfill_calls
    assert status.called

