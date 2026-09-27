from __future__ import annotations

import pandas as pd
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QWidget

from expo_jbm329.gui.dialogs.analysis.chi_square_view import ChiSquareView
from expo_jbm329.gui.dialogs.analysis.correlation_config import CorrelationConfigWidget
from expo_jbm329.gui.dialogs.analysis.correlation_view import CorrelationView
from expo_jbm329.gui.dialogs.analysis.group_comparison_view import GroupComparisonView
from expo_jbm329.gui.dialogs.analysis.hypothesis_tests_config import HypothesisTestsConfigWidget
from expo_jbm329.gui.dialogs.analysis.overview_view import OverviewView
from expo_jbm329.gui.dialogs.analysis.regression_config import RegressionConfigWidget
from expo_jbm329.gui.dialogs.analysis.regression_view import RegressionView
from expo_jbm329.gui.dialogs.analysis.statistics_config import StatisticsConfigWidget
from expo_jbm329.gui.dialogs.analysis.statistics_view import StatisticsView
from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.correlation import CorrelationMethod
from expo_jbm329.services.analysis.regression import RegressionError
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
        self.config_widgets: list[QWidget | None] = []
        self.exec_called = False
        self._panel = QWidget()
        self._selected_category: AnalysisCategory | None = None
        self._selected_dataset_tab_id: str | None = None
        self._current_content: QWidget | None = None

    def show_placeholder(self, text):
        self.placeholder_calls.append(text)
        self._current_content = None

    def set_content_widget(self, widget):
        self.content_widgets.append(widget)
        self._current_content = widget

    def content_widget(self):
        return self._current_content

    def set_config_widget(self, widget):
        self.config_widgets.append(widget)

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
    yield dialogs

    # Matplotlib canvases (StatisticsView) schedule a deferred draw_idle();
    # flush it here, while `dialogs` still keeps every created widget alive,
    # so the queued paint never fires later against an already-garbage-
    # collected canvas in an unrelated test.
    QApplication.processEvents()


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
    dlg._selected_category = AnalysisCategory.OUTLIERS
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.OUTLIERS.value)

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


def test_statistics_category_also_builds_a_column_picker_config_widget(dialog_factory):
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
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
    _simulate_success(async_ops.last_call)

    assert len(dlg.config_widgets) == 2  # proactive None, then the real config widget
    config = dlg.config_widgets[-1]
    assert isinstance(config, StatisticsConfigWidget)
    assert config.selected_column() == "a"


def test_changing_the_statistics_config_column_updates_the_content_view_directly(dialog_factory):
    """Switching columns is a pure GUI-thread operation - it must not
    dispatch a new background job (all columns' data is already computed).
    """
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
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
    _simulate_success(async_ops.last_call)

    jobs_before = len(async_ops.calls)
    config = dlg.config_widgets[-1]
    config._column_combo.setCurrentIndex(1)  # noqa: SLF001

    assert len(async_ops.calls) == jobs_before  # no new background job
    assert config.selected_column() == "b"


def test_switching_to_a_category_hides_a_stale_config_widget_while_loading(dialog_factory):
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=3, column_count=1)
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
    _simulate_success(async_ops.last_call)
    assert dlg.config_widgets[-1] is not None

    # Switch to Overview: the stale Statistics config widget must be hidden
    # immediately, even before Overview's own job completes.
    dlg._selected_category = AnalysisCategory.OVERVIEW
    dlg.category_changed.emit(AnalysisCategory.OVERVIEW.value)

    assert dlg.config_widgets[-1] is None


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
    dlg._selected_category = AnalysisCategory.OUTLIERS
    dlg.category_changed.emit(AnalysisCategory.OUTLIERS.value)
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


# ----------------------------------------------------------------------
# Hypothesis Tests / Group Comparison: config-driven recompute
# ----------------------------------------------------------------------


def _hypothesis_tests_df() -> pd.DataFrame:
    # 24 rows with fully distinct "value"/"other" values (> MAX_GROUPS) so
    # only "grp" and "color" are eligible categorical columns - Group
    # Comparison defaults to ("value", "grp") with two numeric choices to
    # switch between, and chi-square defaults to ("grp", "color").
    return pd.DataFrame({
        "value": [float(i) for i in range(24)],
        "other": [float(i) * 10 for i in range(24)],
        "grp": ["A", "B"] * 12,
        "color": ["r", "g", "b"] * 8,
    })


def _gc_numeric_combo(config: HypothesisTestsConfigWidget) -> QComboBox:
    gc_config = config._group_comparison_config  # noqa: SLF001
    assert gc_config is not None
    return gc_config._numeric_combo  # noqa: SLF001


def _open_hypothesis_tests(async_ops: DummyAsyncOps, dialog_factory, df: pd.DataFrame | None = None):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=24, column_count=4)
    ctrl = AnalysisController(
        results=DummyResults(
            datasets=[dataset],
            active_tab_id="t1",
            dfs={"t1": _hypothesis_tests_df() if df is None else df},
        ),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.HYPOTHESIS_TESTS
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.HYPOTHESIS_TESTS.value)
    _simulate_success(async_ops.last_call)
    return ctrl, dlg


def test_hypothesis_tests_category_runs_as_a_background_job_with_a_busy_overlay(dialog_factory):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=4, column_count=3)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": _hypothesis_tests_df()}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.HYPOTHESIS_TESTS
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.HYPOTHESIS_TESTS.value)

    assert len(async_ops.calls) == 1
    call = async_ops.last_call
    assert call["target"] is dlg.content_panel()
    assert call["scope"] == "analysis:hypothesis_tests"
    assert dlg.content_widgets == []

    _simulate_success(call)

    assert len(dlg.content_widgets) == 1
    assert isinstance(dlg.content_widgets[0], GroupComparisonView)


def test_hypothesis_tests_category_also_builds_a_column_picker_config_widget(dialog_factory):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=4, column_count=3)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": _hypothesis_tests_df()}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.HYPOTHESIS_TESTS
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.HYPOTHESIS_TESTS.value)
    _simulate_success(async_ops.last_call)

    assert len(dlg.config_widgets) == 2  # proactive None, then the real config widget
    config = dlg.config_widgets[-1]
    assert isinstance(config, HypothesisTestsConfigWidget)
    assert config.current_configuration() == (HypothesisTest.GROUP_COMPARISON, ("value", "grp"))
    assert config.chi_square_selection() == ("grp", "color")


def test_hypothesis_tests_with_no_eligible_columns_still_shows_the_test_selector(dialog_factory):
    df = pd.DataFrame({"a": ["x", "y", "z"]})
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=3, column_count=1)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": df}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.HYPOTHESIS_TESTS
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.HYPOTHESIS_TESTS.value)
    _simulate_success(async_ops.last_call)

    assert isinstance(dlg.content_widgets[-1], GroupComparisonView)
    config = dlg.config_widgets[-1]
    assert isinstance(config, HypothesisTestsConfigWidget)
    assert config.group_comparison_selection() is None
    assert config.chi_square_selection() is None


def test_changing_the_hypothesis_tests_config_selection_dispatches_a_new_background_job(dialog_factory):
    """Unlike Statistics' pure GUI-thread column switch, changing either
    dropdown here must trigger a new background job - the selected columns
    determine *what* gets computed, not just what gets redrawn."""
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=4, column_count=3)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": _hypothesis_tests_df()}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.HYPOTHESIS_TESTS
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.HYPOTHESIS_TESTS.value)
    _simulate_success(async_ops.last_call)

    jobs_before = len(async_ops.calls)
    config_widgets_before = len(dlg.config_widgets)
    config = dlg.config_widgets[-1]
    _gc_numeric_combo(config).setCurrentIndex(1)  # noqa: SLF001 - "value" -> "other"

    assert len(async_ops.calls) == jobs_before + 1
    new_call = async_ops.last_call
    assert new_call["scope"] == "analysis:hypothesis_tests:group_comparison:other:grp"
    assert new_call["target"] is dlg.content_panel()

    _simulate_success(new_call)

    assert isinstance(dlg.content_widgets[-1], GroupComparisonView)
    # The configuration widget itself must not be replaced by the recompute.
    assert len(dlg.config_widgets) == config_widgets_before


def test_stale_hypothesis_tests_recompute_is_discarded_when_selection_changes_again(dialog_factory):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=4, column_count=3)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": _hypothesis_tests_df()}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.HYPOTHESIS_TESTS
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.HYPOTHESIS_TESTS.value)
    _simulate_success(async_ops.last_call)

    config = dlg.config_widgets[-1]
    _gc_numeric_combo(config).setCurrentIndex(1)  # noqa: SLF001 - "value" -> "other"
    first_recompute_call = async_ops.last_call

    _gc_numeric_combo(config).setCurrentIndex(0)  # noqa: SLF001 - "other" -> "value" again
    second_recompute_call = async_ops.last_call

    content_widgets_before = len(dlg.content_widgets)
    _simulate_success(first_recompute_call)
    assert len(dlg.content_widgets) == content_widgets_before  # stale result dropped

    _simulate_success(second_recompute_call)
    assert len(dlg.content_widgets) == content_widgets_before + 1


def test_stale_hypothesis_tests_recompute_is_discarded_when_category_changes(dialog_factory):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=4, column_count=3)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": _hypothesis_tests_df()}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.HYPOTHESIS_TESTS
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.HYPOTHESIS_TESTS.value)
    _simulate_success(async_ops.last_call)

    config = dlg.config_widgets[-1]
    _gc_numeric_combo(config).setCurrentIndex(1)  # noqa: SLF001
    recompute_call = async_ops.last_call

    # User navigates to Overview before the recompute completes.
    dlg._selected_category = AnalysisCategory.OVERVIEW
    dlg.category_changed.emit(AnalysisCategory.OVERVIEW.value)
    _simulate_success(async_ops.last_call)  # Overview's own job

    content_widgets_before = len(dlg.content_widgets)
    _simulate_success(recompute_call)
    assert len(dlg.content_widgets) == content_widgets_before  # stale, dropped


def test_hypothesis_tests_recompute_shows_error_placeholder_without_touching_config(dialog_factory):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=4, column_count=3)
    async_ops = DummyAsyncOps()
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1", dfs={"t1": _hypothesis_tests_df()}),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.HYPOTHESIS_TESTS
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.HYPOTHESIS_TESTS.value)
    _simulate_success(async_ops.last_call)

    config_widgets_before = len(dlg.config_widgets)
    config = dlg.config_widgets[-1]
    _gc_numeric_combo(config).setCurrentIndex(1)  # noqa: SLF001

    async_ops.last_call["on_error"]("boom")

    assert dlg.placeholder_calls[-1] == ctrl._tr(ctrl.TR_ANALYSIS_ERROR)  # noqa: SLF001
    assert len(dlg.config_widgets) == config_widgets_before  # config untouched


# ----------------------------------------------------------------------
# Hypothesis Tests: switching between tests
# ----------------------------------------------------------------------


def _select_test(config: HypothesisTestsConfigWidget, test: HypothesisTest) -> None:
    combo = config._test_combo  # noqa: SLF001
    combo.setCurrentIndex(combo.findData(test.value))


def test_switching_to_chi_square_dispatches_a_chi_square_background_job(dialog_factory):
    async_ops = DummyAsyncOps()
    _ctrl, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    config = dlg.config_widgets[-1]
    jobs_before = len(async_ops.calls)
    config_widgets_before = len(dlg.config_widgets)

    _select_test(config, HypothesisTest.CHI_SQUARE)

    assert len(async_ops.calls) == jobs_before + 1
    call = async_ops.last_call
    assert call["scope"] == "analysis:hypothesis_tests:chi_square:grp:color"
    assert call["target"] is dlg.content_panel()

    _simulate_success(call)

    assert isinstance(dlg.content_widgets[-1], ChiSquareView)
    assert len(dlg.config_widgets) == config_widgets_before


def test_switching_back_to_group_comparison_keeps_its_previous_selection(dialog_factory):
    async_ops = DummyAsyncOps()
    _ctrl, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    config = dlg.config_widgets[-1]
    _gc_numeric_combo(config).setCurrentIndex(1)  # "value" -> "other"
    _simulate_success(async_ops.last_call)

    _select_test(config, HypothesisTest.CHI_SQUARE)
    _simulate_success(async_ops.last_call)
    _select_test(config, HypothesisTest.GROUP_COMPARISON)

    assert async_ops.last_call["scope"] == "analysis:hypothesis_tests:group_comparison:other:grp"
    _simulate_success(async_ops.last_call)
    assert isinstance(dlg.content_widgets[-1], GroupComparisonView)


def test_changing_the_chi_square_column_dispatches_a_new_background_job(dialog_factory):
    async_ops = DummyAsyncOps()
    _ctrl, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    config = dlg.config_widgets[-1]
    _select_test(config, HypothesisTest.CHI_SQUARE)
    _simulate_success(async_ops.last_call)

    chi_config = config._chi_square_config  # noqa: SLF001
    assert chi_config is not None
    chi_config._row_combo.setCurrentIndex(chi_config._row_combo.findText("color"))  # noqa: SLF001

    assert async_ops.last_call["scope"] == "analysis:hypothesis_tests:chi_square:color:grp"
    _simulate_success(async_ops.last_call)
    assert isinstance(dlg.content_widgets[-1], ChiSquareView)


def test_stale_group_comparison_result_is_discarded_after_switching_test(dialog_factory):
    async_ops = DummyAsyncOps()
    _ctrl, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    config = dlg.config_widgets[-1]

    _gc_numeric_combo(config).setCurrentIndex(1)
    group_comparison_call = async_ops.last_call
    _select_test(config, HypothesisTest.CHI_SQUARE)
    chi_square_call = async_ops.last_call

    content_widgets_before = len(dlg.content_widgets)
    _simulate_success(group_comparison_call)
    assert len(dlg.content_widgets) == content_widgets_before  # stale, dropped

    _simulate_success(chi_square_call)
    assert isinstance(dlg.content_widgets[-1], ChiSquareView)


def test_switching_to_an_unavailable_test_computes_its_defaults_and_shows_the_error(dialog_factory):
    # Only "grp" is categorical: Group Comparison works, chi-square has no column pair.
    df = pd.DataFrame({"value": [float(i) for i in range(24)], "grp": ["A", "B"] * 12})
    async_ops = DummyAsyncOps()
    _ctrl, dlg = _open_hypothesis_tests(async_ops, dialog_factory, df)
    config = dlg.config_widgets[-1]

    _select_test(config, HypothesisTest.CHI_SQUARE)

    assert async_ops.last_call["scope"] == "analysis:hypothesis_tests:chi_square"
    _simulate_success(async_ops.last_call)
    assert isinstance(dlg.content_widgets[-1], ChiSquareView)


# ----------------------------------------------------------------------
# Correlation Explorer
# ----------------------------------------------------------------------


def _correlation_df() -> pd.DataFrame:
    return pd.DataFrame({
        "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "b": [2.0, 4.1, 5.9, 8.2, 9.8, 12.1],
        "c": [5.0, 3.0, 4.0, 1.0, 2.0, 0.5],
        "text": ["x", "y", "z", "x", "y", "z"],
    })


def _open_correlation(async_ops: DummyAsyncOps, dialog_factory, df: pd.DataFrame | None = None):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=6, column_count=4)
    ctrl = AnalysisController(
        results=DummyResults(
            datasets=[dataset],
            active_tab_id="t1",
            dfs={"t1": _correlation_df() if df is None else df},
        ),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.CORRELATION
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.CORRELATION.value)
    return ctrl, dlg


def _correlation_config(dlg: DummyAnalysisDialog) -> CorrelationConfigWidget:
    config = dlg.config_widgets[-1]
    assert isinstance(config, CorrelationConfigWidget)
    return config


def _correlation_view(dlg: DummyAnalysisDialog) -> CorrelationView:
    view = dlg.content_widget()
    assert isinstance(view, CorrelationView)
    return view


def test_correlation_runs_as_a_cancelable_background_job_with_progress(dialog_factory):
    async_ops = DummyAsyncOps()
    _open_correlation(async_ops, dialog_factory)

    call = async_ops.last_call
    assert call["scope"] == "analysis:correlation"
    assert call["cancelable"] is True
    assert call["indeterminate"] is False
    assert call["timeout_ms"] == 600_000


def test_non_correlation_jobs_keep_an_indeterminate_non_cancelable_overlay(dialog_factory):
    async_ops = DummyAsyncOps()
    _open_hypothesis_tests(async_ops, dialog_factory)

    call = async_ops.last_call
    assert call["cancelable"] is False
    assert call["indeterminate"] is True
    assert call["timeout_ms"] == 60_000


def test_correlation_job_reports_progress_through_the_injected_callback(dialog_factory):
    async_ops = DummyAsyncOps()
    _open_correlation(async_ops, dialog_factory)
    progress: list[int] = []

    result = async_ops.last_call["work"](progress_cb=progress.append, cancel_cb=lambda: False)

    assert result is not None
    assert progress[-1] == 100


def test_correlation_shows_view_and_config_with_the_strongest_pair(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)

    view = _correlation_view(dlg)
    config = _correlation_config(dlg)
    detail = view.pair_detail()
    assert detail is not None
    assert (detail.pair.x_column, detail.pair.y_column) == ("a", "b")
    assert config.current_pair() == ("a", "b")
    assert config.matrix_configuration() == (CorrelationMethod.PEARSON, ("a", "b", "c"))


def test_correlation_without_enough_numeric_columns_shows_error_without_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory, pd.DataFrame({"a": [1.0, 2.0, 3.0]}))
    _simulate_success(async_ops.last_call)

    view = _correlation_view(dlg)
    assert view.table() is None
    assert dlg.config_widgets[-1] is None


def test_cancelled_correlation_shows_the_cancelled_placeholder(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_correlation(async_ops, dialog_factory)
    call = async_ops.last_call

    call["on_result"](call["work"](cancel_cb=lambda: True))

    assert dlg.placeholder_calls == [ctrl._tr(ctrl.TR_ANALYSIS_CANCELLED)]  # noqa: SLF001
    assert dlg.config_widgets[-1] is None


def test_cancel_during_the_matrix_computation_returns_none(dialog_factory):
    async_ops = DummyAsyncOps()
    _open_correlation(async_ops, dialog_factory)
    polls: list[None] = []

    def _cancel_after_first_poll() -> bool:
        polls.append(None)
        return len(polls) > 1

    assert async_ops.last_call["work"](cancel_cb=_cancel_after_first_poll) is None


def test_method_change_recomputes_the_matrix_as_a_cancelable_job(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _correlation_config(dlg)
    first_view = _correlation_view(dlg)
    configs_before = len(dlg.config_widgets)

    config._method_combo.setCurrentIndex(config._method_combo.findData(CorrelationMethod.SPEARMAN))  # noqa: SLF001

    call = async_ops.last_call
    assert call["scope"] == "analysis:correlation:matrix:spearman"
    assert call["target"] is dlg.content_panel()
    assert call["cancelable"] is True
    assert call["indeterminate"] is False

    _simulate_success(call)

    view = _correlation_view(dlg)
    assert view is not first_view
    assert view.method() is CorrelationMethod.SPEARMAN
    detail = view.pair_detail()
    assert detail is not None
    assert detail.method is CorrelationMethod.SPEARMAN
    assert len(dlg.config_widgets) == configs_before  # config is kept


def test_apply_recomputes_the_matrix_with_the_checked_columns(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _correlation_config(dlg)

    item = config._column_list.item(2)  # noqa: SLF001 - "c"
    item.setCheckState(item.checkState().Unchecked)
    config._apply_button.click()  # noqa: SLF001
    _simulate_success(async_ops.last_call)

    view = _correlation_view(dlg)
    table = view.table()
    assert table is not None
    assert table.rowCount() == 1


def test_cancelled_matrix_recompute_shows_placeholder_and_keeps_config(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _correlation_config(dlg)

    config._apply_button.click()  # noqa: SLF001
    call = async_ops.last_call
    call["on_result"](call["work"](cancel_cb=lambda: True))

    assert dlg.placeholder_calls[-1] == ctrl._tr(ctrl.TR_ANALYSIS_CANCELLED)  # noqa: SLF001
    assert dlg.config_widgets[-1] is config


def test_stale_matrix_recompute_is_discarded_when_the_method_changes_again(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _correlation_config(dlg)
    combo = config._method_combo  # noqa: SLF001

    combo.setCurrentIndex(combo.findData(CorrelationMethod.SPEARMAN))
    first = async_ops.last_call
    combo.setCurrentIndex(combo.findData(CorrelationMethod.KENDALL))
    second = async_ops.last_call

    contents_before = len(dlg.content_widgets)
    _simulate_success(first)
    assert len(dlg.content_widgets) == contents_before

    _simulate_success(second)
    assert _correlation_view(dlg).method() is CorrelationMethod.KENDALL


def test_pair_change_recomputes_only_the_pair_detail_over_the_pair_panel(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _correlation_config(dlg)
    view = _correlation_view(dlg)
    contents_before = len(dlg.content_widgets)

    config.set_pair("c", "a")

    call = async_ops.last_call
    assert call["scope"] == "analysis:correlation:pair:pearson:c:a"
    assert call["target"] is view.pair_panel()
    assert call["cancelable"] is False

    _simulate_success(call)

    assert len(dlg.content_widgets) == contents_before  # view updated in place
    detail = view.pair_detail()
    assert detail is not None
    assert (detail.pair.x_column, detail.pair.y_column) == ("c", "a")


def test_clicking_a_table_row_selects_the_pair_and_recomputes_it(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _correlation_config(dlg)
    view = _correlation_view(dlg)
    table = view.table()
    assert table is not None

    table.cellClicked.emit(2, 0)

    last_pair = view._result.pairs[2]  # noqa: SLF001
    assert config.current_pair() == (last_pair.x_column, last_pair.y_column)
    assert async_ops.last_call["scope"].startswith("analysis:correlation:pair:")


def test_stale_pair_recompute_is_discarded_when_the_pair_changes_again(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _correlation_config(dlg)
    view = _correlation_view(dlg)
    initial_detail = view.pair_detail()

    config.set_pair("c", "a")
    first = async_ops.last_call
    config.set_pair("b", "c")
    second = async_ops.last_call

    _simulate_success(first)
    assert view.pair_detail() is initial_detail

    _simulate_success(second)
    detail = view.pair_detail()
    assert detail is not None
    assert (detail.pair.x_column, detail.pair.y_column) == ("b", "c")


def test_pair_change_while_the_matrix_is_computing_is_caught_up_afterwards(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _correlation_config(dlg)

    config._apply_button.click()  # noqa: SLF001
    matrix_call = async_ops.last_call
    dlg.show_placeholder("computing")  # no view is displayed while the matrix job runs
    jobs_before = len(async_ops.calls)

    config.set_pair("c", "a")
    assert len(async_ops.calls) == jobs_before  # nothing to update yet

    _simulate_success(matrix_call)

    pair_call = async_ops.last_call
    assert pair_call["scope"] == "analysis:correlation:pair:pearson:c:a"
    _simulate_success(pair_call)
    detail = _correlation_view(dlg).pair_detail()
    assert detail is not None
    assert (detail.pair.x_column, detail.pair.y_column) == ("c", "a")


def test_pair_recompute_uses_the_displayed_matrix_method(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _correlation_config(dlg)

    # Method changed, but its matrix job hasn't finished: the view is still Pearson.
    config._method_combo.setCurrentIndex(config._method_combo.findData(CorrelationMethod.KENDALL))  # noqa: SLF001
    config.set_pair("c", "a")

    assert async_ops.last_call["scope"] == "analysis:correlation:pair:pearson:c:a"


def test_recompute_shows_error_placeholder_when_the_dataset_cannot_be_reloaded(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _correlation_config(dlg)
    ctrl._results._dfs.clear()  # noqa: SLF001 - the dataset disappeared
    jobs_before = len(async_ops.calls)

    config._apply_button.click()  # noqa: SLF001

    assert len(async_ops.calls) == jobs_before
    assert dlg.placeholder_calls[-1] == ctrl._tr(ctrl.TR_ANALYSIS_ERROR)  # noqa: SLF001


def test_recompute_without_a_selected_dataset_does_nothing(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _correlation_config(dlg)
    dlg._selected_dataset_tab_id = None
    jobs_before = len(async_ops.calls)

    config._apply_button.click()  # noqa: SLF001

    assert len(async_ops.calls) == jobs_before


def test_failed_recompute_shows_error_placeholder_unless_stale(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _correlation_config(dlg)
    combo = config._method_combo  # noqa: SLF001

    combo.setCurrentIndex(combo.findData(CorrelationMethod.SPEARMAN))
    first = async_ops.last_call
    combo.setCurrentIndex(combo.findData(CorrelationMethod.KENDALL))
    second = async_ops.last_call

    first["on_error"]("boom")
    assert dlg.placeholder_calls == []

    second["on_error"]("boom")
    assert dlg.placeholder_calls == [ctrl._tr(ctrl.TR_ANALYSIS_ERROR)]  # noqa: SLF001


# ----------------------------------------------------------------------
# Linear Regression
# ----------------------------------------------------------------------


def _regression_df() -> pd.DataFrame:
    return pd.DataFrame({
        "y": [1.0, 2.5, 2.0, 4.5, 5.0, 6.5, 6.0, 8.5],
        "x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        "z": [2.0, 1.0, 4.0, 3.0, 6.0, 5.0, 8.0, 7.0],
        "g": ["a", "b", "a", "b", "a", "b", "a", "a"],
    })


def _open_regression(async_ops: DummyAsyncOps, dialog_factory, df: pd.DataFrame | None = None):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=8, column_count=4)
    ctrl = AnalysisController(
        results=DummyResults(
            datasets=[dataset],
            active_tab_id="t1",
            dfs={"t1": _regression_df() if df is None else df},
        ),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.REGRESSION
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.REGRESSION.value)
    return ctrl, dlg


def _regression_config(dlg: DummyAnalysisDialog) -> RegressionConfigWidget:
    config = dlg.config_widgets[-1]
    assert isinstance(config, RegressionConfigWidget)
    return config


def _regression_view(dlg: DummyAnalysisDialog) -> RegressionView:
    view = dlg.content_widgets[-1]
    assert isinstance(view, RegressionView)
    return view


def _check_predictors(config: RegressionConfigWidget, *columns: str) -> None:
    predictor_list = config._predictor_list  # noqa: SLF001
    for index in range(predictor_list.count()):
        item = predictor_list.item(index)
        assert item is not None
        if item.flags() & Qt.ItemFlag.ItemIsUserCheckable and item.flags() & Qt.ItemFlag.ItemIsEnabled:
            wanted = item.data(Qt.ItemDataRole.UserRole) in columns
            item.setCheckState(Qt.CheckState.Checked if wanted else Qt.CheckState.Unchecked)


def test_regression_initially_prompts_for_predictors_with_a_standard_overlay(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_regression(async_ops, dialog_factory)

    call = async_ops.last_call
    assert call["scope"] == "analysis:regression"
    assert call["cancelable"] is False
    _simulate_success(call)

    view = _regression_view(dlg)
    assert view.result().error is RegressionError.NO_PREDICTORS_SELECTED
    assert view.result().target == "y"
    config = _regression_config(dlg)
    assert config.model_configuration() == ("y", ())


def test_regression_without_numeric_columns_has_no_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_regression(async_ops, dialog_factory, df=pd.DataFrame({"g": ["a", "b", "a"]}))
    _simulate_success(async_ops.last_call)

    assert _regression_view(dlg).result().error is RegressionError.NO_NUMERIC_COLUMN
    assert dlg.config_widgets[-1] is None


def test_applying_predictors_refits_the_model_in_a_background_job(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_regression(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _regression_config(dlg)

    _check_predictors(config, "x", "g")
    config._apply_button.click()  # noqa: SLF001

    call = async_ops.last_call
    assert call["scope"] == "analysis:regression:y:x:g"
    assert call["cancelable"] is False
    _simulate_success(call)

    view = _regression_view(dlg)
    assert view.result().error is None
    assert view.result().predictors == ("x", "g")
    assert dlg.config_widgets[-1] is config  # the config is never rebuilt


def test_changing_the_target_refits_without_it_as_a_predictor(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_regression(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _regression_config(dlg)
    _check_predictors(config, "x", "z")
    config._apply_button.click()  # noqa: SLF001
    _simulate_success(async_ops.last_call)

    combo = config._target_combo  # noqa: SLF001
    combo.setCurrentIndex(combo.findText("x"))

    call = async_ops.last_call
    assert call["scope"] == "analysis:regression:x:z"
    _simulate_success(call)
    assert _regression_view(dlg).result().target == "x"
    assert _regression_view(dlg).result().predictors == ("z",)


def test_stale_regression_result_is_discarded(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_regression(async_ops, dialog_factory)
    _simulate_success(async_ops.last_call)
    config = _regression_config(dlg)

    _check_predictors(config, "x")
    config._apply_button.click()  # noqa: SLF001
    first = async_ops.last_call
    _check_predictors(config, "z")
    config._apply_button.click()  # noqa: SLF001
    second = async_ops.last_call
    views_before = len(dlg.content_widgets)

    _simulate_success(first)
    assert len(dlg.content_widgets) == views_before

    _simulate_success(second)
    assert _regression_view(dlg).result().predictors == ("z",)
