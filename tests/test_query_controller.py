# tests/test_query_controller.py
from __future__ import annotations
import pandas as pd
import pytest
from types import SimpleNamespace

from expo_jbm329.workbench.controllers.query_controller import QueryController
from tests.stubs import DummyJobManager, DummyResults, DummyStatusLogger, make_dialog_services, DummyResult

class DummyParent:
    def __init__(self):
        self.last_df = None

def make_qc(*, sql_text: str | None = "SELECT 1", conn_name: str = "TestConn"):
    parent = DummyParent()
    job_mgr = DummyJobManager()
    results = DummyResults()
    logger = DummyStatusLogger()
    dlg, _ = make_dialog_services()

    def get_sql(use_sel):
        return sql_text

    def get_conn_name():
        return conn_name

    def fmt_time(s):
        return f"{s:.1f}s"

    qc = QueryController(
        parent_widget=parent,
        job_mgr=job_mgr,
        results=results,
        set_status=logger.set_status,
        get_sql=get_sql,
        get_conn_name=get_conn_name,
        fmt_time=fmt_time,
        dialogs=dlg
    )
    return qc, parent, job_mgr, results, logger, dlg

def test_run_full_triggers_job():
    qc, _, job_mgr, _, logger, _ = make_qc(sql_text="SELECT * FROM T")
    qc.run_full()

    assert job_mgr.last_run is not None
    assert job_mgr.last_run["args"][1] == "SELECT * FROM T"
    assert job_mgr.last_run["args"][2] is None
    assert logger.messages[0][0] == "Kör SQL…"

def test_run_top10_triggers_job():
    qc, _, job_mgr, _, logger, _ = make_qc(sql_text="SELECT * FROM T")
    qc.run_top10()

    assert job_mgr.last_run is not None
    assert job_mgr.last_run["args"][2] == 10
    assert logger.messages[0][0] == "Kör SQL (topp 10)…"

def test_run_selection_no_sql_shows_info():
    qc, _, job_mgr, _, _, dlg = make_qc(sql_text=None)
    qc.run_selection(top_n=50)
    assert job_mgr.last_run is None
    assert any(c[0] == "info" and "Ingen markering" in str(c[1]) for c in dlg.calls)

def test_run_sql_empty_warns_and_no_job():
    qc, _, job_mgr, _, _, dlg = make_qc(sql_text="")
    qc.run_full()
    assert job_mgr.last_run is None
    assert any(c[0] == "warn" and "Ingen SQL" in str(c[1]) for c in dlg.calls)

def test_on_worker_result_success_updates_results_and_status():
    qc, parent, _, results, logger, _ = make_qc()
    df = pd.DataFrame({"a": [1, 2]})
    res = DummyResult(data=df, ok=True, rows=2, elapsed_s=1.234)
    
    qc._on_worker_result(res)
    
    assert len(results.display_calls) == 1
    assert results.display_calls[0].equals(df)
    assert parent.last_df.equals(df)
    
    # Check status message
    msg = logger.messages[-1][0]
    assert "Klar: 2 rader, 1 kolumner (1.2s)" in msg

def test_on_worker_result_failure_with_error_object():
    qc, _, _, results, logger, dlg = make_qc()
    err = SimpleNamespace(message="Bad syntax", hint="Check commas")
    res = DummyResult(ok=False, error=err)
    
    qc._on_worker_result(res)
    assert len(results.display_calls) == 0
    assert "Misslyckades." in logger.messages[-1][0]
    assert any(c[0] == "critical" and "Bad syntax" in str(c[1]) for c in dlg.calls)
    assert any(c[0] == "critical" and "Tips: Check commas" in str(c[1]) for c in dlg.calls)

def test_on_worker_error_shows_critical_and_status():
    qc, _, _, _, logger, dlg = make_qc()
    qc._on_worker_error("Some Traceback")
    
    assert "Misslyckades." in logger.messages[-1][0]
    assert any(c[0] == "critical" and "Fel vid SQL" in str(c[1]) for c in dlg.calls)

def test_run_sql_connects_worker_signals():
    qc, _, job_mgr, _, _, _ = make_qc()
    
    # Trigger job
    qc.run_full()
    
    worker = job_mgr.worker
    # Verify signals are connected
    # In DummySignal, we track callbacks in .callbacks
    assert len(worker.result.callbacks) == 1
    assert len(worker.error.callbacks) == 1
    
    # Verify the connected methods are correct
    assert worker.result.callbacks[0].__name__ == "_on_worker_result"
    assert worker.error.callbacks[0].__name__ == "_on_worker_error"

def test_worker_signals_trigger_callbacks():
    qc, parent, job_mgr, results, logger, dlg = make_qc()
    qc.run_full()
    
    worker = job_mgr.worker
    
    # 1. Test success signal
    df = pd.DataFrame({"x": [1]})
    res = DummyResult(data=df, ok=True, rows=1, elapsed_s=0.5)
    worker.result.emit(res)
    
    assert results.display_calls[0].equals(df)
    assert parent.last_df.equals(df)
    assert "0.5s" in logger.messages[-1][0]
    
    # 2. Test error signal
    worker.error.emit("Fatal thread error")
    assert "Misslyckades." in logger.messages[-1][0]
    assert any("Fatal thread error" in str(c[1]) for c in dlg.calls)
