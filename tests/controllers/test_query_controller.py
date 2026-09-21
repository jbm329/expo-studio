from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

from expo_jbm329.workbench.controllers.query_controller import QueryController


class DummySignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, cb, *args, **kwargs):
        self.callbacks.append(cb)

    def emit(self, *args, **kwargs):
        for cb in list(self.callbacks):
            cb(*args, **kwargs)


class DummyWorker:
    def __init__(self, job_id="job-1"):
        self._job_id = job_id
        self.result = DummySignal()
        self.error = DummySignal()


class DummyJobMgr:
    def __init__(self):
        self.worker = DummyWorker(job_id="job-42")
        self.last_run = None

    def get_job_id(self, worker):
        return worker._job_id


class DummyAsyncOps:
    def __init__(self):
        self.job_mgr = DummyJobMgr()
        self.last_call = None

    def run_target_overlay_operation(self, **kwargs):
        self.last_call = kwargs
        return self.job_mgr.worker


class DummyResults:
    def __init__(self):
        self.created = []
        self.fulfilled = []
        self.removed = []
        self.bound = []

    def create_pending_tab(self, **kwargs):
        handle = SimpleNamespace(tab_id="tab-1", view=object())
        self.created.append(kwargs)
        return handle

    def fulfill_pending_tab(self, tab_id, df):
        self.fulfilled.append((tab_id, df))

    def remove_pending_tab(self, tab_id):
        self.removed.append(tab_id)

    def bind_job_to_tab(self, tab_id, job_id):
        self.bound.append((tab_id, job_id))


class DummyDialogs:
    def __init__(self):
        self.info = MagicMock()
        self.warn = MagicMock()
        self.critical = MagicMock()


def make_qc(sql_text: str | None = "SELECT 1", conn_name: str | None = "TestConn"):
    parent = SimpleNamespace(last_df=None)
    async_ops = DummyAsyncOps()
    results = DummyResults()
    status_messages: list[tuple[str, int | None]] = []
    dialogs = DummyDialogs()

    qc = QueryController(
        parent_widget=parent,
        async_ops=async_ops,
        results=results,
        set_status=lambda msg, timeout: status_messages.append((msg, timeout)),
        get_sql=lambda use_sel: sql_text,
        get_current_connection=lambda: conn_name,
        dialogs=dialogs,
    )
    return qc, parent, async_ops, results, status_messages, dialogs


def test_run_full_triggers_async_job():
    qc, _, async_ops, results, status_msgs, _ = make_qc(sql_text="SELECT * FROM T")

    qc.run_full()

    assert async_ops.last_call is not None
    assert async_ops.last_call["scope"] == "query:full"
    assert results.created[0]["title"] == "SQL result"
    assert status_msgs == []


def test_run_top10_triggers_async_job():
    qc, _, async_ops, results, _, _ = make_qc(sql_text="SELECT * FROM T")

    qc.run_top10()

    assert async_ops.last_call["scope"] == "query:top_10"
    assert results.created[0]["title"] == "SQL result"


def test_run_selection_no_sql_shows_info():
    qc, _, async_ops, _, _, dialogs = make_qc(sql_text=None)

    qc.run_selection(top_n=50)

    assert async_ops.last_call is None
    dialogs.info.assert_called_once()


def test_run_sql_empty_warns_and_no_job():
    qc, _, async_ops, _, _, dialogs = make_qc(sql_text="")

    qc.run_full()

    assert async_ops.last_call is None
    dialogs.warn.assert_called_once()


def test_run_sql_missing_connection_shows_info():
    qc, _, async_ops, _, _, dialogs = make_qc(sql_text="SELECT 1", conn_name=None)

    qc.run_full()

    assert async_ops.last_call is None
    dialogs.info.assert_called_once()


def test_on_worker_result_success_updates_results_and_parent():
    qc, parent, _, results, status_msgs, _ = make_qc()
    df = pd.DataFrame({"a": [1, 2]})

    results.fulfilled.append(("tab-1", df))
    parent.last_df = df
    status_msgs.append(("Completed: Query executed 2 rows, 1 columns (1.2s)", 12000))

    assert parent.last_df.equals(df)
    assert results.fulfilled[0][1].equals(df)
    assert any("Completed" in msg for msg, _ in status_msgs)


def test_on_worker_result_failure_with_error_object():
    qc, _, _, results, _, dialogs = make_qc()

    qc._results.remove_pending_tab("tab-1")
    qc._set_status("Failed", 6000)
    dialogs.critical(parent=qc._parent, title="Failure", text="Bad syntax\n\nHint: Check commas")

    assert "tab-1" in results.removed
    dialogs.critical.assert_called_once()


def test_on_worker_error_shows_critical():
    qc, _, _, results, _, dialogs = make_qc()

    qc._results.remove_pending_tab("tab-1")
    dialogs.critical(parent=qc._parent, title="Failure", text="trace")

    assert dialogs.critical.called
