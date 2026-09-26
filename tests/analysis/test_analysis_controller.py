from __future__ import annotations

import pandas as pd
import pytest
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from expo_jbm329.gui.dialogs.analysis.overview_view import OverviewView
from expo_jbm329.gui.dialogs.analysis.statistics_view import StatisticsView
from expo_jbm329.services.analysis.categories import AnalysisCategory
from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.workbench.controllers.analysis.analysis_controller import AnalysisController

_CONTROLLER_MODULE = "expo_jbm329.workbench.controllers.analysis.analysis_controller"


class DummyResults:
    def __init__(self, datasets=None, active_tab_id=None, dfs=None):
        self._datasets = datasets or []
        self._active_tab_id = active_tab_id
        self._dfs = dfs or {}

    def list_ready_datasets(self):
        return self._datasets

    def active_tab_id(self):
        return self._active_tab_id

    def get_df_by_tab_id(self, tab_id):
        return self._dfs[tab_id]


class DummyAsyncOps:
    """Records run_target_overlay_operation calls without executing anything.

    Tests simulate the background job explicitly via the captured kwargs
    (work/on_result/on_error/stale_check), mirroring how the real
    AsyncOperationController would eventually invoke them.
    """

    def __init__(self):
        self.calls: list[dict] = []

    def run_target_overlay_operation(self, **kwargs):
        self.calls.append(kwargs)
        return object()

    @property
    def last_call(self) -> dict:
        return self.calls[-1]


class DummySignal:
    def __init__(self):
        self._slot = None

    def connect(self, slot):
        self._slot = slot

    def emit(self, value):
        if self._slot is not None:
            self._slot(value)


class DummyAnalysisDialog:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.category_changed = DummySignal()
        self.dataset_changed = DummySignal()
        self.placeholder_calls: list[str] = []
        self.content_widgets: list[QWidget] = []
        self.exec_called = False
        self._panel = QWidget()
        self._selected_category: AnalysisCategory | None = None
        self._selected_dataset_tab_id: str | None = None

    def show_placeholder(self, text):
        self.placeholder_calls.append(text)

    def set_content_widget(self, widget):
        self.content_widgets.append(widget)

    def selected_category(self):
        return self._selected_category

    def selected_dataset_tab_id(self):
        return self._selected_dataset_tab_id

    def content_panel(self):
        return self._panel

    def exec(self):
        self.exec_called = True
        return QDialog.DialogCode.Accepted


@pytest.fixture
def dialog_factory(monkeypatch):
    dialogs: list[DummyAnalysisDialog] = []

    def _factory(**kwargs):
        dlg = DummyAnalysisDialog(**kwargs)
        dialogs.append(dlg)
        return dlg

    monkeypatch.setattr(f"{_CONTROLLER_MODULE}.AnalysisDialog", _factory)
    return dialogs


def _open_and_flush(ctrl: AnalysisController, parent: QWidget) -> None:
    """Open the dialog and let the deferred initial refresh (singleShot) run."""
    ctrl.open_dialog(parent)
    QApplication.processEvents()


def _simulate_success(call_kwargs: dict) -> None:
    """Simulate a background job completing successfully.

    Mirrors AsyncOperationController's own stale_check gating: a stale
    result must never reach on_result.
    """
    stale_check = call_kwargs.get("stale_check")
    if stale_check is not None and stale_check():
        return
    result = call_kwargs["work"](cancel_cb=lambda: False)
    call_kwargs["on_result"](result)


def test_open_dialog_does_nothing_when_there_are_no_datasets(dialog_factory):
    ctrl = AnalysisController(results=DummyResults(datasets=[]), async_ops=DummyAsyncOps())
    _open_and_flush(ctrl, QWidget())

    assert dialog_factory == []


def test_open_dialog_builds_dialog_with_datasets_and_active_tab(dialog_factory):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=10, column_count=3)

    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1"),
        async_ops=DummyAsyncOps(),
    )
    _open_and_flush(ctrl, QWidget())

    assert len(dialog_factory) == 1
    dlg = dialog_factory[0]
    assert dlg.kwargs["datasets"] == [dataset]
    assert dlg.kwargs["active_tab_id"] == "t1"
    assert dlg.exec_called


def test_open_dialog_schedules_exactly_one_deferred_initial_refresh(monkeypatch, dialog_factory):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=10, column_count=3)
    calls: list[object] = []
    monkeypatch.setattr(AnalysisController, "_refresh_content", lambda self, dialog: calls.append(dialog))

    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1"),
        async_ops=DummyAsyncOps(),
    )
    _open_and_flush(ctrl, QWidget())

    assert calls == [dialog_factory[0]]


def test_initial_refresh_shows_overview_content_when_overview_is_preselected(monkeypatch):
    """AnalysisDialog always pre-selects Overview and an active dataset at
    construction time; the deferred initial refresh must turn that default
    selection into real content without any further signal.
    """
    df = pd.DataFrame({"a": [1, 2, 3]})
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=3, column_count=1)
    dialogs: list[DummyAnalysisDialog] = []

    def _factory(**kwargs):
        dlg = DummyAnalysisDialog(**kwargs)
        dlg._selected_category = AnalysisCategory.OVERVIEW
        dlg._selected_dataset_tab_id = "t1"
        dialogs.append(dlg)
        return dlg

    monkeypatch.setattr(f"{_CONTROLLER_MODULE}.AnalysisDialog", _factory)

    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": df}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialogs[0]
    assert len(async_ops.calls) == 1
    _simulate_success(async_ops.last_call)

    assert len(dlg.content_widgets) == 1
    assert isinstance(dlg.content_widgets[0], OverviewView)


def test_category_without_a_registered_handler_shows_not_implemented_placeholder(dialog_factory):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=10, column_count=3)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1"),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.CORRELATION
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.CORRELATION.value)

    assert dlg.placeholder_calls == [ctrl._tr(ctrl.TR_NOT_IMPLEMENTED)]  # noqa: SLF001
    assert dlg.content_widgets == []
    assert async_ops.calls == []  # never dispatches a background job


def test_overview_category_runs_as_a_background_job_with_a_busy_overlay(dialog_factory):
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=3, column_count=2)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": df}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.OVERVIEW
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.OVERVIEW.value)

    assert len(async_ops.calls) == 1
    call = async_ops.last_call
    assert call["target"] is dlg.content_panel()
    assert call["runner"] == "pool"
    assert call["scope"] == "analysis:overview"
    # Nothing is shown until the job "completes" - the busy overlay is what
    # covers the result pane in the meantime.
    assert dlg.content_widgets == []

    _simulate_success(call)

    assert len(dlg.content_widgets) == 1
    assert isinstance(dlg.content_widgets[0], OverviewView)


def test_statistics_category_runs_as_a_background_job_with_a_busy_overlay(dialog_factory):
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": ["x", "y", "z"]})
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=3, column_count=2)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": df}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.STATISTICS
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.STATISTICS.value)

    assert len(async_ops.calls) == 1
    call = async_ops.last_call
    assert call["target"] is dlg.content_panel()
    assert call["runner"] == "pool"
    assert call["scope"] == "analysis:statistics"
    assert dlg.content_widgets == []

    _simulate_success(call)

    assert len(dlg.content_widgets) == 1
    assert isinstance(dlg.content_widgets[0], StatisticsView)
    assert dlg.placeholder_calls == []


def test_overview_result_is_discarded_when_the_dataset_changes_before_it_completes(dialog_factory):
    df1 = pd.DataFrame({"a": [1, 2, 3]})
    df2 = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
    datasets = [
        DatasetRef(tab_id="t1", title="Sheet1", row_count=3, column_count=1),
        DatasetRef(tab_id="t2", title="Sheet2", row_count=5, column_count=1),
    ]
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=datasets, active_tab_id="t1", dfs={"t1": df1, "t2": df2}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.OVERVIEW
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.OVERVIEW.value)
    first_call = async_ops.last_call

    # User switches dataset before the first job "completes".
    dlg._selected_dataset_tab_id = "t2"
    dlg.dataset_changed.emit("t2")
    second_call = async_ops.last_call

    # The stale (first) job finally completes: its result must be dropped.
    _simulate_success(first_call)
    assert dlg.content_widgets == []

    # The fresh (second) job completes normally.
    _simulate_success(second_call)
    assert len(dlg.content_widgets) == 1
    assert dlg.content_widgets[0]._result.row_count == 5  # noqa: SLF001


def test_overview_category_shows_error_placeholder_when_dataset_lookup_fails(dialog_factory):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=3, column_count=1)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.OVERVIEW
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.OVERVIEW.value)

    assert async_ops.calls == []  # dataset lookup fails before any job starts
    assert dlg.content_widgets == []
    assert dlg.placeholder_calls == [ctrl._tr(ctrl.TR_ANALYSIS_ERROR)]  # noqa: SLF001


def test_overview_category_shows_error_placeholder_when_the_job_itself_fails(dialog_factory):
    df = pd.DataFrame({"a": [1, 2, 3]})
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=3, column_count=1)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": df}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.OVERVIEW
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.OVERVIEW.value)

    async_ops.last_call["on_error"]("boom")

    assert dlg.content_widgets == []
    assert dlg.placeholder_calls == [ctrl._tr(ctrl.TR_ANALYSIS_ERROR)]  # noqa: SLF001


def test_job_error_is_ignored_once_stale(dialog_factory):
    df1 = pd.DataFrame({"a": [1, 2, 3]})
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=3, column_count=1)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": df1}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.OVERVIEW
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.OVERVIEW.value)
    call = async_ops.last_call

    # User navigates away to an unimplemented category before the job fails.
    dlg._selected_category = AnalysisCategory.CORRELATION
    dlg.category_changed.emit(AnalysisCategory.CORRELATION.value)
    assert dlg.placeholder_calls == [ctrl._tr(ctrl.TR_NOT_IMPLEMENTED)]  # noqa: SLF001

    call["on_error"]("boom")

    # The stale error must not clobber the (already correct) placeholder.
    assert dlg.placeholder_calls == [ctrl._tr(ctrl.TR_NOT_IMPLEMENTED)]  # noqa: SLF001


def test_cancelled_work_returns_none_and_is_ignored(dialog_factory):
    df = pd.DataFrame({"a": [1, 2, 3]})
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=3, column_count=1)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": df}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.OVERVIEW
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.OVERVIEW.value)
    call = async_ops.last_call

    result = call["work"](cancel_cb=lambda: True)
    assert result is None

    call["on_result"](result)
    assert dlg.content_widgets == []


def test_no_category_selected_does_not_touch_the_dialog(dialog_factory):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=3, column_count=1)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1"),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg.dataset_changed.emit("t1")

    assert dlg.placeholder_calls == []
    assert dlg.content_widgets == []
    assert async_ops.calls == []
