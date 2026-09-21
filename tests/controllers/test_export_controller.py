from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.gui.dialogs.service.dialog_service import ProfileChoice
from expo_jbm329.services.job_result import JobResult
from expo_jbm329.workbench.controllers.export_controller import ExportController, ExportKind
from tests.stubs import (
    DummyAsyncOps,
    DummyDataIO,
    DummyDialogState,
    DummyFileJobs,
    DummyResults,
    make_dialog_services,
)


def make_controller(
    *,
    df: pd.DataFrame | None = None,
    tabs_count: int = 1,
    data_all: list[tuple[pd.DataFrame, str]] | None = None,
    dialog_choice: ProfileChoice = ProfileChoice.ACTIVE,
):
    parent = object()
    results = DummyResults(df=df, tabs_count=tabs_count, data_all=data_all)
    status_msgs: list[tuple[str, int | None]] = []

    def set_status(text: str, timeout: int | None) -> None:
        status_msgs.append((text, timeout))

    file_jobs = DummyFileJobs()
    async_ops = DummyAsyncOps()

    def get_tab_title() -> str:
        return "MinTabb"

    open_url_called = {"ok": False}

    def open_url(uri: str) -> bool:
        open_url_called["ok"] = True
        return True

    data_io = DummyDataIO()
    dialog_state = DummyDialogState()
    dialogs, file_dialogs = make_dialog_services(profile_choice=dialog_choice)

    ctrl = ExportController(
        parent_widget=parent,
        async_ops=async_ops,
        operation_target=object(),
        results=results,
        set_status=set_status,
        file_jobs=file_jobs,
        get_tab_title=get_tab_title,
        open_url=open_url,
        data_io=data_io,
        dialogs=dialogs,
        file_dialogs=file_dialogs,
        dialog_state=dialog_state,
    )
    ctrl.reload_settings({"paths": {"documents": "C:/tmp"}})
    return ctrl, dialogs, file_dialogs, file_jobs, status_msgs, open_url_called, async_ops


def test_export_csv_no_df_shows_info_and_returns():
    ctrl, dlg, fdlg, file_jobs, _, _, async_ops = make_controller(df=None)

    ctrl.export_csv()

    assert file_jobs.run_calls == 0
    assert any(call[0] == "info" for call in dlg.calls)


def test_export_csv_user_cancels_does_not_run():
    df = pd.DataFrame({"a": [1]})
    ctrl, _, fdlg, file_jobs, _, _, async_ops = make_controller(df=df)

    fdlg.enqueue_save_response("", "")

    ctrl.export_csv()

    assert file_jobs.run_calls == 0


def test_export_csv_runs_with_scope_and_suffix():
    df = pd.DataFrame({"a": [1]})
    ctrl, _, fdlg, file_jobs, _, _, async_ops = make_controller(df=df)
    fdlg.enqueue_save_response("C:/tmp/data.csv", "CSV files (*.csv)")

    ctrl.export_csv()

    assert len(async_ops.calls) == 1
    assert async_ops.calls[0]["scope"] == "export:csv"
    assert file_jobs.coerce_save_suffix("C:/tmp/data.csv", "CSV files (*.csv)", ".csv") == "C:/tmp/data.csv"


def test_export_excel_runs_with_scope_and_suffix():
    df = pd.DataFrame({"a": [1]})
    ctrl, _, fdlg, file_jobs, _, _, async_ops = make_controller(df=df)
    fdlg.enqueue_save_response("C:/tmp/data.xlsx", "Excel files (*.xlsx)")

    ctrl.export_excel()

    assert len(async_ops.calls) == 1
    assert async_ops.calls[0]["scope"] == "export:excel"


@pytest.mark.parametrize(
    "chosen_path, expected_scope",
    [
        ("C:/tmp/data.df", "export:df"),
        ("C:/tmp/data.feather", "export:feather"),
        ("C:/tmp/data.ft", "export:ft"),
        ("C:/tmp/data.parquet", "export:parquet"),
    ],
)
def test_export_data_runs_with_correct_scope(chosen_path: str, expected_scope: str):
    df = pd.DataFrame({"a": [1]})
    ctrl, _, fdlg, file_jobs, _, _, async_ops = make_controller(df=df)
    fdlg.enqueue_save_response(chosen_path, "All data files (*.df *.feather *.ft *.parquet)")

    ctrl.export_data()

    assert len(async_ops.calls) == 1
    assert async_ops.calls[0]["scope"] == expected_scope


def test_export_data_no_df_shows_info_and_returns():
    ctrl, dlg, _, file_jobs, _, _, async_ops = make_controller(df=None)

    ctrl.export_data()

    assert len(async_ops.calls) == 0
    assert any(call[0] == "info" for call in dlg.calls)


def test_profile_report_single_tab_runs_profile_single():
    df = pd.DataFrame({"a": [1]})
    ctrl, _, fdlg, _, _, _, async_ops = make_controller(df=df, tabs_count=1)
    fdlg.enqueue_save_response("C:/tmp/report.html", "HTML files (*.html)")

    ctrl.profile_report()

    assert len(async_ops.calls) == 1
    assert async_ops.calls[0]["scope"] == "processdata:y-data-single"


def test_profile_report_multi_tabs_cancel_does_not_run():
    df = pd.DataFrame({"a": [1]})
    ctrl, dlg, _, _, _, _, async_ops = make_controller(df=df, tabs_count=3, dialog_choice=ProfileChoice.CANCEL)

    ctrl.profile_report()

    assert len(async_ops.calls) == 0


def test_profile_report_multi_tabs_active_runs_single():
    df = pd.DataFrame({"a": [1]})
    ctrl, _, fdlg, _, _, _, async_ops = make_controller(df=df, tabs_count=3, dialog_choice=ProfileChoice.ACTIVE)
    fdlg.enqueue_save_response("C:/tmp/single.html", "HTML files (*.html)")

    ctrl.profile_report()

    assert len(async_ops.calls) == 1
    assert async_ops.calls[0]["scope"] == "processdata:y-data-single"


def test_profile_report_multi_tabs_all_runs_comparison():
    df = pd.DataFrame({"a": [1]})
    data_all = [(pd.DataFrame({"x": [1]}), "A"), (pd.DataFrame({"y": [2]}), "B")]
    ctrl, _, fdlg, _, _, _, async_ops = make_controller(
        df=df, tabs_count=3, data_all=data_all, dialog_choice=ProfileChoice.ALL
    )
    fdlg.enqueue_save_response("C:/tmp/compare.html", "HTML files (*.html)")

    ctrl.profile_report()

    assert len(async_ops.calls) == 1
    assert async_ops.calls[0]["scope"] == "processdata:y-data-comparison"


def test_profile_all_tabs_no_data_shows_info_and_returns():
    df = pd.DataFrame({"a": [1]})
    ctrl, dlg, _, _, _, _, async_ops = make_controller(
        df=df, tabs_count=3, data_all=[], dialog_choice=ProfileChoice.ALL
    )

    ctrl.profile_report()

    assert len(async_ops.calls) == 0


def test_on_export_done_success_with_elapsed_sets_status_and_opens_url():
    ctrl, _, _, _, status_msgs, open_url_called, _ = make_controller()

    jr = JobResult(ok=True, elapsed=1.2, path="C:/tmp/report.html", cancelled=False, error=None)
    ctrl._on_export_done(jr, ExportKind.PROFILE, "C:/tmp/report.html")

    assert status_msgs
    assert open_url_called["ok"] is True


def test_on_export_done_without_elapsed_sets_status():
    ctrl, _, _, _, status_msgs, _, _ = make_controller()

    jr = JobResult(ok=True, elapsed=None, path="C:/tmp/file.csv", cancelled=False, error=None)
    ctrl._on_export_done(jr, ExportKind.CSV, "C:/tmp/file.csv")

    assert status_msgs


def test_on_export_done_cancelled_shows_info_and_status():
    ctrl, dlg, _, _, status_msgs, _, _ = make_controller()

    jr = JobResult(ok=False, elapsed=None, path="C:/tmp/file.csv", cancelled=True, error=None)
    ctrl._on_export_done(jr, ExportKind.CSV, "C:/tmp/file.csv")

    assert status_msgs
    assert any(call[0] == "info" for call in dlg.calls)


def test_on_export_done_failure_warns_and_status():
    ctrl, dlg, _, _, status_msgs, _, _ = make_controller()

    jr = JobResult(ok=False, elapsed=None, path="C:/tmp/file.csv", cancelled=False, error="Något fel")
    ctrl._on_export_done(jr, ExportKind.CSV, "C:/tmp/file.csv")

    assert status_msgs
    assert any(call[0] == "warn" for call in dlg.calls)


def test_on_export_done_accepts_legacy_dict_payload():
    ctrl, _, _, _, status_msgs, _, _ = make_controller()

    ctrl._on_export_done({"ok": True, "elapsed": 2.0}, ExportKind.CSV, "C:/tmp/file.csv")

    assert status_msgs


def test_on_export_error_shows_critical_and_status():
    ctrl, dlg, _, _, status_msgs, _, _ = make_controller()

    ctrl._on_export_error("Boom", ExportKind.CSV)

    assert status_msgs
    assert any(call[0] == "critical" for call in dlg.calls)
