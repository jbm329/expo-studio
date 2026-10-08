from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QWidget

from expo_jbm329.gui.dialogs.service.dialog_service import ProfileChoice
from expo_jbm329.services.file_writer import FileWriter
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


def test_export_context_anchors_overlay_without_mutating_main_window(monkeypatch):
    controller, _, dialogs, _, _, _, async_ops = make_controller(df=pd.DataFrame({"active": [99]}))
    original_parent = controller._parent
    original_target = controller._operation_target
    parent, target = QWidget(), QWidget()
    save = Mock(wraps=dialogs.get_save_filename)
    monkeypatch.setattr(dialogs, "get_save_filename", save)
    dialogs.enqueue_save_response("overview.csv", "CSV files (*.csv)")
    controller.export_csv(df=pd.DataFrame({"metadata": [1]}), parent_widget=parent, operation_target=target)
    assert async_ops.calls[0]["target"] is target
    assert save.call_args.kwargs["parent"] is parent
    assert controller._parent is original_parent
    assert controller._operation_target is original_target


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
@pytest.mark.parametrize("context", ["omitted", "none", "parent", "target", "both"])
def test_export_routes_resolved_dataframe_to_deferred_writer(
    monkeypatch, method, writer, suffix, scope, indeterminate, cancelable, directory_key, source, context
):
    active = pd.DataFrame({"active": [1, 2]})
    supplied = pd.DataFrame({"text": pd.Series(["a", None], dtype="string"), "number": [2.5, 3.5]})
    supplied.index = pd.Index(["row-a", "row-b"], name="row")
    expected = supplied if source.startswith("explicit") else active
    before = expected.copy(deep=True)
    ctrl, _, file_dialogs, file_jobs, _, _, async_ops = make_controller(
        df=None if source == "explicit_without_active" else active
    )
    default_parent, default_target = ctrl._parent, ctrl._operation_target
    parent, target = QWidget(), QWidget()
    context_kwargs = {
        "omitted": {},
        "none": {"parent_widget": None, "operation_target": None},
        "parent": {"parent_widget": parent},
        "target": {"operation_target": target},
        "both": {"parent_widget": parent, "operation_target": target},
    }[context]
    save = Mock(wraps=file_dialogs.get_save_filename)
    monkeypatch.setattr(file_dialogs, "get_save_filename", save)
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
        export(**context_kwargs)
    else:
        export(df=supplied if source.startswith("explicit") else None, **context_kwargs)

    assert lookups == ([] if source.startswith("explicit") else [True])
    assert len(async_ops.calls) == 1
    assert writer_calls == []
    call = async_ops.calls[0]
    assert call["scope"] == scope
    assert call["indeterminate"] is indeterminate
    assert call["cancelable"] is cancelable
    assert call["runner"] == "thread"
    assert call["target"] is (target if context in ("target", "both") else default_target)
    assert save.call_args.kwargs["parent"] is (parent if context in ("parent", "both") else default_parent)
    assert ctrl._parent is default_parent
    assert ctrl._operation_target is default_target
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
@pytest.mark.parametrize("override", [False, True])
def test_empty_explicit_dataframe_notifies_without_active_fallback(monkeypatch, method, frame, override):
    ctrl, dialogs, file_dialogs, _, _, _, async_ops = make_controller(df=pd.DataFrame({"active": [1]}))
    parent = QWidget() if override else ctrl._parent
    notify = Mock(wraps=dialogs.info)
    monkeypatch.setattr(dialogs, "info", notify)

    def unexpected_lookup(self):
        pytest.fail("Empty supplied data must not fall back to the active dataset")

    monkeypatch.setattr(ExportController, "_get_active_df", unexpected_lookup)
    monkeypatch.setattr(file_dialogs, "get_save_filename", lambda **kwargs: pytest.fail("Must not open a save dialog"))

    getattr(ctrl, method)(df=frame, parent_widget=parent if override else None)

    assert async_ops.calls == []
    assert len(dialogs.calls) == 1
    assert dialogs.calls[0][0] == "info"
    assert notify.call_args.kwargs["parent"] is parent


@pytest.mark.parametrize("method", ["export_csv", "export_excel", "export_data"])
@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("override", [False, True])
def test_save_cancellation_never_schedules_work_or_updates_directory(monkeypatch, method, explicit, override):
    frame = pd.DataFrame({"a": [1]})
    ctrl, dialogs, file_dialogs, _, status, _, async_ops = make_controller(df=frame)
    file_dialogs.enqueue_save_response("", "")
    parent = QWidget() if override else ctrl._parent
    save = Mock(wraps=file_dialogs.get_save_filename)
    monkeypatch.setattr(file_dialogs, "get_save_filename", save)
    monkeypatch.setattr(ctrl._dialog_state, "set_dir", lambda *args: pytest.fail("Cancel must not change directories"))

    getattr(ctrl, method)(
        **({"df": frame} if explicit else {}),
        parent_widget=parent if override else None,
        operation_target=QWidget() if override else None,
    )

    assert async_ops.calls == []
    assert dialogs.calls == []
    assert status == []
    assert save.call_args.kwargs["parent"] is parent


@pytest.mark.parametrize("method", ["export_csv", "export_excel", "export_data"])
@pytest.mark.parametrize("override", [False, True])
def test_missing_active_dataframe_notifies_for_every_format(monkeypatch, method, override):
    ctrl, dialogs, _, _, _, _, async_ops = make_controller()
    parent = QWidget() if override else ctrl._parent
    notify = Mock(wraps=dialogs.info)
    monkeypatch.setattr(dialogs, "info", notify)

    getattr(ctrl, method)(parent_widget=parent if override else None)

    assert async_ops.calls == []
    assert len(dialogs.calls) == 1
    assert dialogs.calls[0][0] == "info"
    assert notify.call_args.kwargs["parent"] is parent


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


@pytest.mark.parametrize("active", [None, pd.DataFrame({"active": [9]})])
@pytest.mark.parametrize("override", [False, True])
def test_named_excel_captures_order_and_routes_deferred_work(monkeypatch, active, override):
    ctrl, dialogs, file_dialogs, file_jobs, _, _, async_ops = make_controller(df=active)
    parent = QWidget() if override else ctrl._parent
    target = QWidget() if override else ctrl._operation_target
    first = pd.DataFrame({"a": pd.Series(["x", None], dtype="string")})
    second = pd.DataFrame(columns=["header only"])
    sheets = {" Exact ": first, "Empty": second}
    monkeypatch.setattr(ctrl._data_io, "validate_excel_sheets", FileWriter().validate_excel_sheets, raising=False)
    monkeypatch.setattr(async_ops, "run_target_overlay_operation", lambda **kwargs: async_ops.calls.append(kwargs))

    def unexpected(*args, **kwargs):
        pytest.fail("Named workbook must bypass active lookup and single-frame export")

    monkeypatch.setattr(ExportController, "_get_active_df", unexpected)
    monkeypatch.setattr(ctrl._data_io, "export_df_excel", unexpected)
    calls = []
    result = JobResult(ok=True, elapsed=None, path=r"C:\chosen\named.xlsx")

    def save(actual, path, **kwargs):
        calls.append((actual, path, kwargs))
        return result

    monkeypatch.setattr(ctrl._data_io, "export_dfs_excel", save, raising=False)

    def choose(**kwargs):
        assert kwargs["parent"] is parent
        sheets.clear()
        sheets["Replacement"] = pd.DataFrame({"b": [8]})
        return r"C:\chosen\named", "Excel files (*.xlsx)"

    monkeypatch.setattr(file_dialogs, "get_save_filename", choose)
    monkeypatch.setattr(file_jobs, "coerce_save_suffix", lambda *args, **kwargs: r"C:\chosen\named.xlsx")
    directories = []
    monkeypatch.setattr(ctrl._dialog_state, "set_dir", lambda key, path: directories.append((key, path)))

    ctrl.export_excel(
        df=None,
        sheets=sheets,
        parent_widget=parent if override else None,
        operation_target=target if override else None,
    )

    assert len(async_ops.calls) == 1
    assert calls == []
    assert dialogs.calls == []
    call = async_ops.calls[0]
    assert call["scope"] == "export:excel"
    assert call["target"] is target
    assert call["cancelable"] is True
    assert call["indeterminate"] is False
    assert directories == [("dialogs/export_excel_dir", Path(r"C:\chosen\named.xlsx").parent)]

    def progress(value):
        pass

    def cancel():
        return False

    assert call["work"](progress_cb=progress, cancel_cb=cancel, job_id="named-job", job_scope="export:excel") is result
    actual, path, kwargs = calls[0]
    assert list(actual) == [" Exact ", "Empty"]
    assert actual[" Exact "] is first
    assert actual["Empty"] is second
    assert path == r"C:\chosen\named.xlsx"
    assert kwargs == {
        "progress_cb": progress,
        "cancel_cb": cancel,
        "job_id": "named-job",
        "job_scope": "export:excel",
        "corr_id": call["corr_id"],
    }


@pytest.mark.parametrize(
    "sheets, conflict",
    [
        ({}, False),
        ({"Bad:name": pd.DataFrame({"a": [1]})}, False),
        ({"One": pd.DataFrame()}, False),
        ({"One": object()}, False),
        ({"One": pd.DataFrame({"a": [1]}), "ONE": pd.DataFrame({"a": [2]})}, False),
        ({"One": pd.DataFrame({"a": [1]})}, True),
    ],
)
@pytest.mark.parametrize("override", [False, True])
def test_invalid_named_excel_notifies_before_save(monkeypatch, sheets, conflict, override):
    ctrl, dialogs, file_dialogs, _, _, _, async_ops = make_controller(df=pd.DataFrame({"active": [1]}))
    parent = QWidget() if override else ctrl._parent
    notify = Mock(wraps=dialogs.warn)
    monkeypatch.setattr(dialogs, "warn", notify)
    monkeypatch.setattr(ctrl._data_io, "validate_excel_sheets", FileWriter().validate_excel_sheets, raising=False)

    def unexpected(*args, **kwargs):
        pytest.fail("Invalid named request must not open save dialog or resolve active data")

    monkeypatch.setattr(ExportController, "_get_active_df", unexpected)
    monkeypatch.setattr(file_dialogs, "get_save_filename", unexpected)
    ctrl.export_excel(
        df=pd.DataFrame({"a": [1]}) if conflict else None,
        sheets=sheets,
        parent_widget=parent if override else None,
    )
    assert async_ops.calls == []
    assert len(dialogs.calls) == 1
    assert dialogs.calls[0][0] == "warn"
    assert notify.call_args.kwargs["parent"] is parent


def test_named_excel_save_cancel_does_not_schedule(monkeypatch):
    ctrl, dialogs, file_dialogs, _, _, _, async_ops = make_controller()
    monkeypatch.setattr(ctrl._data_io, "validate_excel_sheets", FileWriter().validate_excel_sheets, raising=False)
    file_dialogs.enqueue_save_response("", "")
    monkeypatch.setattr(ctrl._dialog_state, "set_dir", lambda *args: pytest.fail("Cancelled save changed directory"))
    ctrl.export_excel(sheets={"Header": pd.DataFrame(columns=["a"])})
    assert async_ops.calls == []
    assert dialogs.calls == []


def test_excel_sheets_argument_is_keyword_only():
    ctrl, _, _, _, _, _, _ = make_controller()
    with pytest.raises(TypeError):
        ctrl.export_excel(None, {"One": pd.DataFrame({"a": [1]})})


@pytest.mark.parametrize("method,writer,suffix,scope,indeterminate,cancelable,directory_key", _DATA_EXPORTS)
@pytest.mark.parametrize("first_uses_default", [False, True])
@pytest.mark.parametrize("outcome", ["cancelled", "failure", "error", "unknown"])
def test_deferred_exports_keep_distinct_contexts_when_completing_in_reverse_order(
    monkeypatch, method, writer, suffix, scope, indeterminate, cancelable, directory_key, first_uses_default, outcome
):
    ctrl, dialogs, file_dialogs, _, status, _, async_ops = make_controller(df=pd.DataFrame({"active": [99]}))
    default_parent, default_target = ctrl._parent, ctrl._operation_target
    first_parent = default_parent if first_uses_default else QWidget()
    first_target = default_target if first_uses_default else QWidget()
    second_parent, second_target = QWidget(), QWidget()
    frames = [pd.DataFrame({"first": [1]}), pd.DataFrame({"second": [2]})]
    monkeypatch.setattr(async_ops, "run_target_overlay_operation", lambda **kwargs: async_ops.calls.append(kwargs))
    save = Mock(wraps=file_dialogs.get_save_filename)
    monkeypatch.setattr(file_dialogs, "get_save_filename", save)
    notifications = []
    for name in ("info", "warn", "critical"):
        monkeypatch.setattr(dialogs, name, lambda _name=name, **kwargs: notifications.append((_name, kwargs)))
    write = Mock(return_value=JobResult(ok=True, elapsed=None))
    monkeypatch.setattr(ctrl._data_io, writer, write)
    contexts = [(first_parent, first_target), (second_parent, second_target)]
    export = getattr(ctrl, method)
    for i, (parent, target) in enumerate(contexts):
        file_dialogs.enqueue_save_response(str(Path(r"C:\exports") / f"job-{i}{suffix}"), "chosen-filter")
        if i == 0 and first_uses_default:
            export(df=frames[i])
        else:
            export(df=frames[i], parent_widget=parent, operation_target=target)

    assert len(async_ops.calls) == 2
    assert [call.kwargs["parent"] for call in save.call_args_list] == [first_parent, second_parent]
    assert [call["target"] for call in async_ops.calls] == [first_target, second_target]
    assert ctrl._parent is default_parent
    assert ctrl._operation_target is default_target
    assert write.call_count == 0

    # Even default ownership must be captured, not read when the job finishes.
    ctrl._parent, ctrl._operation_target = QWidget(), QWidget()
    for i in (1, 0):
        call = async_ops.calls[i]
        call["work"](job_id=f"job-{i}", job_scope=scope)
        assert write.call_args.args[0] is frames[i]
        if outcome == "error":
            call["on_error"](f"error-{i}")
        else:
            call["on_result"](
                object()
                if outcome == "unknown"
                else JobResult(ok=False, elapsed=None, cancelled=outcome == "cancelled", error=f"error-{i}")
            )
        assert notifications[-1][1]["parent"] is contexts[i][0]
        assert (
            notifications[-1][0]
            == {"cancelled": "info", "failure": "warn", "error": "critical", "unknown": "warn"}[outcome]
        )
    assert len(notifications) == 2
    assert len(status) == 2


@pytest.mark.parametrize("method,writer,suffix,scope,indeterminate,cancelable,directory_key", _DATA_EXPORTS)
@pytest.mark.parametrize("override", [False, True])
def test_export_captures_context_before_save_dialog_and_completion(
    monkeypatch, method, writer, suffix, scope, indeterminate, cancelable, directory_key, override
):
    ctrl, dialogs, file_dialogs, _, _, _, async_ops = make_controller(df=pd.DataFrame({"a": [1]}))
    parent = QWidget() if override else ctrl._parent
    target = QWidget() if override else ctrl._operation_target
    monkeypatch.setattr(async_ops, "run_target_overlay_operation", lambda **kwargs: async_ops.calls.append(kwargs))
    notify = Mock(wraps=dialogs.warn)
    monkeypatch.setattr(dialogs, "warn", notify)
    replacement_parent, replacement_target = QWidget(), QWidget()

    def choose(*, parent, req):
        assert parent is expected_parent
        ctrl._parent = replacement_parent
        ctrl._operation_target = replacement_target
        return str(Path(r"C:\exports") / f"captured{suffix}"), "chosen-filter"

    expected_parent = parent
    monkeypatch.setattr(file_dialogs, "get_save_filename", choose)
    getattr(ctrl, method)(parent_widget=parent if override else None, operation_target=target if override else None)
    call = async_ops.calls[0]
    assert call["target"] is target
    call["on_result"](JobResult(ok=False, elapsed=None, error="Failed"))
    assert notify.call_args.kwargs["parent"] is parent


@pytest.mark.parametrize("method", ["export_csv", "export_excel", "export_data"])
@pytest.mark.parametrize("context_argument", ["parent_widget", "operation_target"])
def test_ui_context_arguments_are_keyword_only(method, context_argument):
    ctrl, _, _, _, _, _, _ = make_controller()
    with pytest.raises(TypeError):
        getattr(ctrl, method)(QWidget(), **{context_argument: QWidget()})
