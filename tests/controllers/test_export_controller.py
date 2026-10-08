from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from PyQt6.QtGui import QAction

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

    assert async_ops.calls == []
    assert any(call[0] == "info" for call in dlg.calls)


def test_export_csv_user_cancels_does_not_run():
    df = pd.DataFrame({"a": [1]})
    ctrl, _, fdlg, file_jobs, _, _, async_ops = make_controller(df=df)

    fdlg.enqueue_save_response("", "")

    ctrl.export_csv()

    assert async_ops.calls == []


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


_DATA_EXPORTS = [
    ("export_csv", "export_df_csv", ".csv", "export:csv", False, True, "dialogs/export_csv_dir"),
    ("export_excel", "export_df_excel", ".xlsx", "export:excel", False, True, "dialogs/export_excel_dir"),
    ("export_data", "export_df_datafile", ".parquet", "export:parquet", True, False, "dialogs/export_data_dir"),
]


@pytest.mark.parametrize("method,writer,suffix,scope,indeterminate,cancelable,directory_key", _DATA_EXPORTS)
@pytest.mark.parametrize("source", ["omitted", "none", "explicit", "explicit_without_active"])
def test_export_routes_resolved_dataframe_to_deferred_writer(
    monkeypatch, method, writer, suffix, scope, indeterminate, cancelable, directory_key, source
):
    active = pd.DataFrame({"active": [1, 2]})
    supplied = pd.DataFrame({"text": pd.Series(["a", None], dtype="string"), "number": [2.5, 3.5]})
    supplied.index = pd.Index(["row-a", "row-b"], name="row")
    expected = supplied if source.startswith("explicit") else active
    before = expected.copy(deep=True)
    ctrl, _, file_dialogs, file_jobs, _, _, async_ops = make_controller(
        df=None if source == "explicit_without_active" else active
    )
    monkeypatch.setattr(async_ops, "run_target_overlay_operation", lambda **kwargs: async_ops.calls.append(kwargs))
    lookups = []

    def active_lookup():
        if source.startswith("explicit"):
            pytest.fail("Explicit DataFrame export must not look up active data")
        lookups.append(True)
        return active

    monkeypatch.setattr(ExportController, "_get_active_df", lambda self: active_lookup())
    chosen_path = r"C:\tmp\selected"
    coerced_path = chosen_path + suffix
    coerces = []

    def coerce(path, selected_filter, fallback):
        coerces.append((path, selected_filter, fallback))
        return coerced_path

    monkeypatch.setattr(file_jobs, "coerce_save_suffix", coerce)
    directories = []
    monkeypatch.setattr(ctrl._dialog_state, "set_dir", lambda key, path: directories.append((key, path)))
    file_dialogs.enqueue_save_response(chosen_path, "chosen-filter")
    writer_calls = []
    result = JobResult(ok=True, elapsed=None, path=coerced_path)

    def write(df, path, **kwargs):
        writer_calls.append((df, path, kwargs))
        return result

    monkeypatch.setattr(ctrl._data_io, writer, write)
    export = getattr(ctrl, method)
    if source == "omitted":
        export()
    else:
        export(df=supplied if source.startswith("explicit") else None)

    assert lookups == ([] if source.startswith("explicit") else [True])
    assert len(async_ops.calls) == 1
    assert writer_calls == []
    call = async_ops.calls[0]
    assert call["scope"] == scope
    assert call["indeterminate"] is indeterminate
    assert call["cancelable"] is cancelable
    assert call["runner"] == "thread"
    assert call["target"] is ctrl._operation_target
    assert call["timeout_ms"] == 0
    assert coerces == [(chosen_path, "chosen-filter", ".df" if method == "export_data" else suffix)]
    assert directories == [(directory_key, Path(coerced_path).parent)]

    # A tab change before work begins must not redirect the already scheduled export.
    monkeypatch.setattr(ExportController, "_get_active_df", lambda self: pd.DataFrame({"other": [999]}))

    def progress(value):
        pass

    def cancel():
        return False

    assert call["work"](progress_cb=progress, cancel_cb=cancel, job_id="job-42", job_scope=scope) is result
    assert len(writer_calls) == 1
    actual, path, callbacks = writer_calls[0]
    assert actual is expected
    pd.testing.assert_frame_equal(actual, before)
    assert path == coerced_path
    assert callbacks == {
        "progress_cb": progress,
        "cancel_cb": cancel,
        "job_id": "job-42",
        "job_scope": scope,
        "corr_id": call["corr_id"],
    }
    assert call["corr_id"]


@pytest.mark.parametrize("method", ["export_csv", "export_excel", "export_data"])
@pytest.mark.parametrize("frame", [pd.DataFrame({"empty": []}), pd.DataFrame(index=[0, 1])])
def test_empty_explicit_dataframe_notifies_without_active_fallback(monkeypatch, method, frame):
    ctrl, dialogs, file_dialogs, _, _, _, async_ops = make_controller(df=pd.DataFrame({"active": [1]}))

    def unexpected_lookup(self):
        pytest.fail("Empty supplied data must not fall back to the active dataset")

    monkeypatch.setattr(ExportController, "_get_active_df", unexpected_lookup)
    monkeypatch.setattr(file_dialogs, "get_save_filename", lambda **kwargs: pytest.fail("Must not open a save dialog"))

    getattr(ctrl, method)(df=frame)

    assert async_ops.calls == []
    assert len(dialogs.calls) == 1
    assert dialogs.calls[0][0] == "info"


@pytest.mark.parametrize("method", ["export_csv", "export_excel", "export_data"])
@pytest.mark.parametrize("explicit", [False, True])
def test_save_cancellation_never_schedules_work_or_updates_directory(monkeypatch, method, explicit):
    frame = pd.DataFrame({"a": [1]})
    ctrl, dialogs, file_dialogs, _, status, _, async_ops = make_controller(df=frame)
    file_dialogs.enqueue_save_response("", "")
    monkeypatch.setattr(ctrl._dialog_state, "set_dir", lambda *args: pytest.fail("Cancel must not change directories"))

    getattr(ctrl, method)(**({"df": frame} if explicit else {}))

    assert async_ops.calls == []
    assert dialogs.calls == []
    assert status == []


@pytest.mark.parametrize("method", ["export_csv", "export_excel", "export_data"])
def test_missing_active_dataframe_notifies_for_every_format(method):
    ctrl, dialogs, _, _, _, _, async_ops = make_controller()

    getattr(ctrl, method)()

    assert async_ops.calls == []
    assert len(dialogs.calls) == 1
    assert dialogs.calls[0][0] == "info"


@pytest.mark.parametrize("method", ["export_csv", "export_excel", "export_data"])
def test_dataframe_argument_is_keyword_only(method):
    ctrl, _, _, _, _, _, async_ops = make_controller()

    with pytest.raises(TypeError):
        getattr(ctrl, method)(pd.DataFrame({"a": [1]}))

    assert async_ops.calls == []


@pytest.mark.parametrize("method", ["export_csv", "export_excel", "export_data"])
def test_export_remains_compatible_with_qaction_triggered_signal(method):
    ctrl, _, file_dialogs, _, _, _, async_ops = make_controller(df=pd.DataFrame({"a": [1]}))
    file_dialogs.enqueue_save_response("", "")
    action = QAction("Export")
    action.triggered.connect(getattr(ctrl, method))

    action.trigger()

    assert async_ops.calls == []


@pytest.mark.parametrize("payload", [object(), {"ok": False}, {"ok": False, "cancelled": True}])
def test_legacy_and_unknown_completion_payloads_surface_failure_or_cancellation(payload):
    ctrl, dialogs, _, _, status, opened, _ = make_controller()

    ctrl._on_export_done(payload, ExportKind.CSV, r"C:\tmp\file.csv")

    assert len(status) == 1
    assert len(dialogs.calls) == 1
    assert dialogs.calls[0][0] == ("info" if isinstance(payload, dict) and payload.get("cancelled") else "warn")
    assert not opened["ok"]


@pytest.mark.parametrize("outcome", ["success", "cancelled", "failure", "error"])
def test_scheduled_callbacks_keep_completion_and_error_behavior(monkeypatch, outcome):
    ctrl, dialogs, file_dialogs, _, status, opened, async_ops = make_controller(df=pd.DataFrame({"a": [1]}))
    monkeypatch.setattr(async_ops, "run_target_overlay_operation", lambda **kwargs: async_ops.calls.append(kwargs))
    file_dialogs.enqueue_save_response(r"C:\tmp\file.csv", "CSV files (*.csv)")
    ctrl.export_csv()
    call = async_ops.calls[0]
    if outcome == "error":
        call["on_error"]("Writer failed")
    else:
        call["on_result"](
            JobResult(
                ok=outcome == "success",
                elapsed=None,
                cancelled=outcome == "cancelled",
                error="Writer failed" if outcome == "failure" else None,
                path=r"C:\tmp\file.csv",
            )
        )

    assert len(status) == 1
    assert not opened["ok"]
    if outcome == "success":
        assert dialogs.calls == []
    else:
        assert len(dialogs.calls) == 1
        assert dialogs.calls[0][0] == {"cancelled": "info", "failure": "warn", "error": "critical"}[outcome]
