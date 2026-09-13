# tests/test_export_controller.py
from __future__ import annotations

import pandas as pd
import pytest

from expo_jbm329.workbench.controllers.export_controller import ExportController
from gui.dialogs.service.dialog_service import ProfileChoice
from expo_jbm329.services.job_result import JobResult
from tests.stubs import DummyResults, DummyFileJobs, DummyDataIO, make_dialog_services

# Gemensam fabrik (bygger controller med injicerade tjänster)
def make_controller(
        *,
        df: pd.DataFrame | None = None,
        tabs_count: int = 1,
        data_all: list[tuple[pd.DataFrame, str]] | None = None,
        dialog_choice: ProfileChoice = ProfileChoice.ACTIVE,
):
    parent = object()  # behövs inte vara QWidget i tester
    results = DummyResults(df=df, tabs_count=tabs_count, data_all=data_all)
    status_msgs: list[tuple[str, int | None]] = []

    def set_status(t, ms):
        return status_msgs.append((t, ms))

    file_jobs = DummyFileJobs()

    def fmt_time(s):
        return f"{s:.1f}s"

    def fmt_path(p):
        return str(p)

    def get_tab_title():
        return "MinTabb"

    open_url_called = {"ok": False}

    def open_url(uri):
        return open_url_called.update(ok=True) or True

    data_io = DummyDataIO()

    dlg, fdlg = make_dialog_services(profile_choice=dialog_choice)

    ctrl = ExportController(
        parent_widget=parent,
        results=results,
        set_status=set_status,
        file_jobs=file_jobs,
        fmt_time=fmt_time,
        fmt_path=fmt_path,
        get_tab_title=get_tab_title,
        open_url=open_url,
        data_io=data_io,
        dialogs=dlg,
        file_dialogs=fdlg,
    )
    # returnera även hjälpobjekt vi vill inspektrera i tester
    return ctrl, dlg, fdlg, file_jobs, status_msgs, open_url_called


# ----------------------------
# TESTER: export_csv
# ----------------------------
def test_export_csv_no_df_shows_info_and_returns():
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller(df=None)

    ctrl.export_csv()

    # Ingen jobb-körning
    assert file_jobs.run_calls == 0
    # Info-dialog förväntas
    assert any(call[0] == "info" and call[1] == ("Inget dataset", "Det finns inget dataset att exportera.")
               for call in dlg.calls)


def test_export_csv_user_cancels_does_not_run():
    df = pd.DataFrame({"a": [1]})
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller(df=df)

    # Användaren avbryter (fdlg returnerar tom path)
    fdlg.enqueue_save_response("", "")

    ctrl.export_csv()

    assert file_jobs.run_calls == 0
    # Verifiera att en SaveFileRequest för CSV gjordes
    assert fdlg.calls[0].title == "Exportera CSV"


def test_export_csv_runs_with_scope_and_suffix():
    df = pd.DataFrame({"a": [1]})
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller(df=df)

    # Användaren väljer fil
    fdlg.enqueue_save_response("C:/tmp/data.csv", "CSV-filer (*.csv)")

    ctrl.export_csv()

    assert file_jobs.run_calls == 1
    lr = file_jobs.last_run
    assert lr["scope"] == "export:csv"
    assert lr["started_msg"] == "Exporterar CSV…"
    # job_args: (df, path)
    assert lr["job_args"][1] == "C:/tmp/data.csv"


# ----------------------------
# TESTER: export_excel
# ----------------------------
def test_export_excel_no_df_shows_info_and_returns():
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller(df=None)
    ctrl.export_excel()
    assert file_jobs.run_calls == 0
    assert any(c[0] == "info" and c[1][0] == "Inget dataset" for c in dlg.calls)


def test_export_excel_runs_with_scope_and_suffix():
    df = pd.DataFrame({"a": [1]})
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller(df=df)
    fdlg.enqueue_save_response("C:/tmp/data.xlsx", "Excel-filer (*.xlsx)")
    ctrl.export_excel()

    assert file_jobs.run_calls == 1
    lr = file_jobs.last_run
    assert lr["scope"] == "export:excel"
    assert lr["job_args"][1] == "C:/tmp/data.xlsx"


# ----------------------------
# TESTER: export_data (pickle/feather/parquet/df)
# ----------------------------
@pytest.mark.parametrize(
    "chosen_path, expected_scope, expected_suffix",
    [
        ("C:/tmp/data.df", "export:df", ".df"),
        ("C:/tmp/data.feather", "export:feather", ".feather"),
        ("C:/tmp/data.ft", "export:ft", ".ft"),
        ("C:/tmp/data.parquet", "export:parquet", ".parquet"),
    ],
)
def test_export_data_runs_with_correct_scope_and_suffix(chosen_path, expected_scope, expected_suffix):
    df = pd.DataFrame({"a": [1]})
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller(df=df)
    fdlg.enqueue_save_response(chosen_path, "Alla dataformat (*.df *.feather *.ft *.parquet)")

    ctrl.export_data()

    assert file_jobs.run_calls == 1
    lr = file_jobs.last_run
    assert lr["scope"] == expected_scope
    assert lr["job_args"][1] == chosen_path
    # suffix bestäms av path i controllern
    # (vi asserterar via scope ovan, suffix används bara internt i started_msg i run-helpern)


def test_export_data_no_df_shows_info_and_returns():
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller(df=None)
    ctrl.export_data()
    assert file_jobs.run_calls == 0
    assert any(c[0] == "info" and "Det finns inget dataset att exportera." in c[1][1] for c in dlg.calls)


# ----------------------------
# TESTER: profile_report
# ----------------------------
def test_profile_report_single_tab_runs_profile_single():
    df = pd.DataFrame({"a": [1]})
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller(df=df, tabs_count=1)

    # Användaren väljer html-fil för single
    fdlg.enqueue_save_response("C:/tmp/report.html", "HTML-filer (*.html)")

    ctrl.profile_report()

    assert file_jobs.run_calls == 1
    lr = file_jobs.last_run
    assert lr["scope"] == "processdata:y-data-single"
    # job_args: (df, path, title)
    assert lr["job_args"][1] == "C:/tmp/report.html"
    assert lr["job_args"][2] == "MinTabb"


def test_profile_report_multi_tabs_cancel_does_not_run():
    df = pd.DataFrame({"a": [1]})
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller(
        df=df, tabs_count=3, dialog_choice=ProfileChoice.CANCEL
    )
    ctrl.profile_report()
    assert file_jobs.run_calls == 0
    # verify that confirm dialog called
    assert any(c[0] == "confirm_profile_scope" for c in dlg.calls)


def test_profile_report_multi_tabs_active_runs_single():
    df = pd.DataFrame({"a": [1]})
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller(
        df=df, tabs_count=3, dialog_choice=ProfileChoice.ACTIVE
    )
    fdlg.enqueue_save_response("C:/tmp/single.html", "HTML-filer (*.html)")

    ctrl.profile_report()

    assert file_jobs.run_calls == 1
    assert file_jobs.last_run["scope"] == "processdata:y-data-single"


def test_profile_report_multi_tabs_all_runs_comparison():
    df = pd.DataFrame({"a": [1]})
    # ge collect_all_tabs_data något att jobba med
    data_all = [(pd.DataFrame({"x": [1]}), "A"), (pd.DataFrame({"y": [2]}), "B")]
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller(
        df=df, tabs_count=3, data_all=data_all, dialog_choice=ProfileChoice.ALL
    )
    fdlg.enqueue_save_response("C:/tmp/compare.html", "HTML-filer (*.html)")

    ctrl.profile_report()

    assert file_jobs.run_calls == 1
    assert file_jobs.last_run["scope"] == "processdata:y-data-comparison"
    assert file_jobs.last_run["job_args"][1] == "C:/tmp/compare.html"


def test_profile_all_tabs_no_data_shows_info_and_returns():
    df = pd.DataFrame({"a": [1]})
    # tabs_count spelar ingen roll här, vi kallar _profile_all_tabs indirekt via ALL-valet, men utan data
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller(
        df=df, tabs_count=3, data_all=[], dialog_choice=ProfileChoice.ALL
    )
    ctrl.profile_report()
    assert file_jobs.run_calls == 0
    assert any(c[0] == "info" and "Kunde inte hitta några dataset att profilera." in c[1][1] for c in dlg.calls)


# ----------------------------
# TESTER: callbacks _on_export_done / _on_export_error
# ----------------------------
def test_on_export_done_success_with_elapsed_sets_status_and_opens_url():
    # Vi behöver öppna URL i "Dataprofil"-fallet
    ctrl, dlg, fdlg, file_jobs, status_msgs, open_url_called = make_controller()

    jr = JobResult(ok=True, elapsed=1.2, path="C:/tmp/report.html", cancelled=False, error=None)
    # ska inte kasta exception då open_url returnerar True i fabrik
    ctrl._on_export_done(jr, "Dataprofil", "C:/tmp/report.html")

    # set_status ska ha markerat "klar" med tid
    assert any("klar (1.2s)" in msg for msg, _ in status_msgs)
    assert open_url_called["ok"] is True


def test_on_export_done_success_without_elapsed_sets_status():
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller()

    jr = JobResult(ok=True, elapsed=None, path="C:/tmp/file.csv", cancelled=False, error=None)
    ctrl._on_export_done(jr, "Data(.csv) export", "C:/tmp/file.csv")

    assert any("klar:" in msg for msg, _ in status_msgs)


def test_on_export_done_cancelled_shows_info_and_status():
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller()

    jr = JobResult(ok=False, elapsed=None, path="C:/tmp/file.csv", cancelled=True, error=None)
    ctrl._on_export_done(jr, "Data(.csv) export", "C:/tmp/file.csv")

    assert any("avbröts." in msg for msg, _ in status_msgs)
    assert any(c[0] == "info" and c[1][0] == "Data(.csv) export" for c in dlg.calls)


def test_on_export_done_failure_warns_and_status():
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller()

    jr = JobResult(ok=False, elapsed=None, path="C:/tmp/file.csv", cancelled=False, error="Något fel")
    ctrl._on_export_done(jr, "Data(.csv) export", "C:/tmp/file.csv")

    assert any("misslyckades." in msg for msg, _ in status_msgs)
    assert any(c[0] == "warn" and c[1][0] == "Data(.csv) export" for c in dlg.calls)


def test_on_export_done_accepts_legacy_dict_payload():
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller()
    payload = {"ok": True, "elapsed": 2.0}

    # ska tolkas som ok-resultat
    ctrl._on_export_done(payload, "Data(.csv) export", "C:/tmp/file.csv")

    assert any("klar (" in msg for msg, _ in status_msgs)


def test_on_export_error_shows_critical_and_status():
    ctrl, dlg, fdlg, file_jobs, status_msgs, _ = make_controller()

    ctrl._on_export_error("Boom", "Data(.csv) export")

    assert any("misslyckades." in msg for msg, _ in status_msgs)
    assert any(c[0] == "critical" and c[1][0] == "Data(.csv) export" for c in dlg.calls)
