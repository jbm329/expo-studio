from __future__ import annotations

import dataclasses

import pandas as pd
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QLabel, QTableWidget, QWidget

from expo_jbm329.gui.dialogs.analysis.chi_square_view import ChiSquareView
from expo_jbm329.gui.dialogs.analysis.clustering_config import ClusteringConfigWidget
from expo_jbm329.gui.dialogs.analysis.clustering_view import ClusteringView
from expo_jbm329.gui.dialogs.analysis.correlation_config import CorrelationConfigWidget
from expo_jbm329.gui.dialogs.analysis.correlation_view import CorrelationView
from expo_jbm329.gui.dialogs.analysis.group_comparison_view import GroupComparisonView
from expo_jbm329.gui.dialogs.analysis.hypothesis_tests_config import HypothesisTestsConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_config import OutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_config import MultivariateOutliersConfigWidget
from expo_jbm329.gui.dialogs.analysis.outliers_multivariate_view import MultivariateOutliersView
from expo_jbm329.gui.dialogs.analysis.outliers_view import OutliersView
from expo_jbm329.gui.dialogs.analysis.overview_view import OverviewView
from expo_jbm329.gui.dialogs.analysis.pca_config import PCAConfigWidget
from expo_jbm329.gui.dialogs.analysis.pca_view import PCAView
from expo_jbm329.gui.dialogs.analysis.regression_config import RegressionConfigWidget
from expo_jbm329.gui.dialogs.analysis.regression_view import RegressionView
from expo_jbm329.gui.dialogs.analysis.statistics_config import StatisticsConfigWidget
from expo_jbm329.gui.dialogs.analysis.statistics_view import StatisticsView
from expo_jbm329.gui.dialogs.analysis.timeseries_config import TimeSeriesConfigWidget
from expo_jbm329.gui.dialogs.analysis.timeseries_view import TimeSeriesView
from expo_jbm329.services.analysis.categories import AnalysisCategory, HypothesisTest
from expo_jbm329.services.analysis.clustering import ClusteringMethod
from expo_jbm329.services.analysis.correlation import CorrelationMethod
from expo_jbm329.services.analysis.multivariate_outliers import MultivariateOutlierError, MultivariateOutlierMethod
from expo_jbm329.services.analysis.outliers import OutlierMethod
from expo_jbm329.services.analysis.pca import PCAError
from expo_jbm329.services.analysis.regression import RegressionError
from expo_jbm329.services.analysis.timeseries import DecompositionModel
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
        self._current_config: QWidget | None = None

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
        self._current_config = widget

    def config_widget(self):
        return self._current_config

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


def _assert_apply_prompt(ctrl: AnalysisController, dlg: DummyAnalysisDialog) -> None:
    content = dlg.content_widget()
    assert isinstance(content, QLabel)
    assert content.text() == ctrl._tr(ctrl.TR_APPLY_PROMPT)  # noqa: SLF001


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


def test_deferred_initial_refresh_is_skipped_after_category_interaction(monkeypatch):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=3, column_count=1)
    dialogs: list[DummyAnalysisDialog] = []
    calls: list[object] = []

    class InteractingDialog(DummyAnalysisDialog):
        def exec(self):
            self.exec_called = True
            self._selected_category = AnalysisCategory.STATISTICS
            self._selected_dataset_tab_id = "t1"
            self.category_changed.emit(AnalysisCategory.STATISTICS.value)
            return QDialog.DialogCode.Accepted

    def _factory(**kwargs):
        dialog = InteractingDialog(**kwargs)
        dialogs.append(dialog)
        return dialog

    monkeypatch.setattr(f"{_CONTROLLER_MODULE}.AnalysisDialog", _factory)
    monkeypatch.setattr(AnalysisController, "_refresh_content", lambda self, dialog: calls.append(dialog))
    ctrl = AnalysisController(
        results=DummyResults(datasets=[dataset], active_tab_id="t1"),
        async_ops=DummyAsyncOps(),
    )

    _open_and_flush(ctrl, QWidget())

    assert calls == [dialogs[0]]


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
    ctrl._category_handlers.pop(AnalysisCategory.TIME_SERIES)  # noqa: SLF001
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.TIME_SERIES
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.TIME_SERIES.value)

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


def test_statistics_category_shows_categorical_summaries_without_numeric_config(dialog_factory):
    df = pd.DataFrame({"sex": ["F", "M", "F", None]})
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=4, column_count=1)
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

    content = dlg.content_widgets[-1]
    assert isinstance(content, StatisticsView)
    assert content.findChild(QTableWidget) is not None
    assert dlg.config_widgets[-1] is None


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
    content = dlg.content_widgets[-1]
    assert isinstance(content, StatisticsView)
    config._column_combo.setCurrentIndex(1)  # noqa: SLF001
    config._summary_method_combo.setCurrentIndex(1)  # noqa: SLF001

    assert len(async_ops.calls) == jobs_before  # no new background job
    assert config.selected_column() == "b"
    numeric_table = next(table for table in content.findChildren(QTableWidget) if table.columnCount() == 16)
    assert numeric_table.item(1, 15).text().startswith("5")


def test_clicking_a_statistics_table_row_updates_the_config_without_a_new_job(dialog_factory):
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
    content = dlg.content_widgets[-1]
    config = dlg.config_widgets[-1]
    assert isinstance(content, StatisticsView)
    assert isinstance(config, StatisticsConfigWidget)
    table = next(table for table in content.findChildren(QTableWidget) if table.columnCount() == 16)

    table.cellClicked.emit(1, 0)

    assert len(async_ops.calls) == jobs_before
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
    ctrl._category_handlers.pop(AnalysisCategory.TIME_SERIES)  # noqa: SLF001
    dlg._selected_category = AnalysisCategory.TIME_SERIES
    dlg.category_changed.emit(AnalysisCategory.TIME_SERIES.value)
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
# Hypothesis Tests: Apply-first recompute
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
    return ctrl, dlg


def _hypothesis_tests_config(dlg: DummyAnalysisDialog) -> HypothesisTestsConfigWidget:
    config = dlg.config_widgets[-1]
    assert isinstance(config, HypothesisTestsConfigWidget)
    return config


def _apply_hypothesis_test(async_ops: DummyAsyncOps, dlg: DummyAnalysisDialog) -> dict:
    """Click Apply and return the test job's call, without completing it."""
    _hypothesis_tests_config(dlg)._apply_button.click()  # noqa: SLF001
    return async_ops.last_call


def _select_test(config: HypothesisTestsConfigWidget, test: HypothesisTest) -> None:
    combo = config._test_combo  # noqa: SLF001
    combo.setCurrentIndex(combo.findData(test.value))


def test_hypothesis_tests_initialize_without_a_job_and_prompt_for_apply(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_hypothesis_tests(async_ops, dialog_factory)

    assert async_ops.calls == []
    _assert_apply_prompt(ctrl, dlg)
    config = _hypothesis_tests_config(dlg)
    assert config.current_configuration() == (HypothesisTest.GROUP_COMPARISON, ("value", "grp"))
    assert config.chi_square_selection() == ("grp", "color")
    assert config.applied_configuration() is None


def test_hypothesis_tests_with_no_eligible_columns_show_the_error_and_the_test_selector(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_hypothesis_tests(async_ops, dialog_factory, pd.DataFrame({"a": ["x", "y", "z"]}))

    assert async_ops.calls == []
    assert isinstance(dlg.content_widget(), GroupComparisonView)
    config = _hypothesis_tests_config(dlg)
    assert config.group_comparison_selection() is None
    assert config.chi_square_selection() is None
    assert not config._apply_button.isEnabled()  # noqa: SLF001


def test_hypothesis_test_column_changes_start_no_job_until_applied(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_hypothesis_tests(async_ops, dialog_factory)

    _gc_numeric_combo(_hypothesis_tests_config(dlg)).setCurrentIndex(1)  # "value" -> "other"

    assert async_ops.calls == []


def test_applying_a_hypothesis_test_runs_a_background_job_and_keeps_the_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    config = _hypothesis_tests_config(dlg)
    config_widgets_before = len(dlg.config_widgets)
    _gc_numeric_combo(config).setCurrentIndex(1)  # "value" -> "other"

    call = _apply_hypothesis_test(async_ops, dlg)

    assert len(async_ops.calls) == 1
    assert call["scope"] == "analysis:hypothesis_tests:group_comparison:other:grp"
    assert call["target"] is dlg.content_panel()
    assert call["cancelable"] is False
    assert call["indeterminate"] is True
    assert call["timeout_ms"] == 60_000

    _simulate_success(call)

    assert isinstance(dlg.content_widget(), GroupComparisonView)
    assert len(dlg.config_widgets) == config_widgets_before


def test_column_change_after_apply_keeps_the_result_until_applied_again(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    _simulate_success(_apply_hypothesis_test(async_ops, dlg))
    view = dlg.content_widget()
    jobs_before = len(async_ops.calls)

    _gc_numeric_combo(_hypothesis_tests_config(dlg)).setCurrentIndex(1)

    assert len(async_ops.calls) == jobs_before
    assert dlg.content_widget() is view


def test_stale_hypothesis_test_result_is_discarded_when_applied_again(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    config = _hypothesis_tests_config(dlg)

    _gc_numeric_combo(config).setCurrentIndex(1)  # "value" -> "other"
    first = _apply_hypothesis_test(async_ops, dlg)
    _gc_numeric_combo(config).setCurrentIndex(0)  # "other" -> "value" again
    second = _apply_hypothesis_test(async_ops, dlg)

    content_widgets_before = len(dlg.content_widgets)
    _simulate_success(first)
    assert len(dlg.content_widgets) == content_widgets_before  # stale result dropped

    _simulate_success(second)
    assert len(dlg.content_widgets) == content_widgets_before + 1


def test_stale_hypothesis_test_result_is_discarded_when_category_changes(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    call = _apply_hypothesis_test(async_ops, dlg)

    # User navigates to Overview before the test completes.
    dlg._selected_category = AnalysisCategory.OVERVIEW
    dlg.category_changed.emit(AnalysisCategory.OVERVIEW.value)
    _simulate_success(async_ops.last_call)  # Overview's own job

    content_widgets_before = len(dlg.content_widgets)
    _simulate_success(call)
    assert len(dlg.content_widgets) == content_widgets_before  # stale, dropped


def test_hypothesis_test_error_shows_the_error_placeholder_without_touching_config(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    config_widgets_before = len(dlg.config_widgets)

    _apply_hypothesis_test(async_ops, dlg)["on_error"]("boom")

    assert dlg.placeholder_calls[-1] == ctrl._tr(ctrl.TR_ANALYSIS_ERROR)  # noqa: SLF001
    assert len(dlg.config_widgets) == config_widgets_before  # config untouched


# ----------------------------------------------------------------------
# Hypothesis Tests: switching between tests
# ----------------------------------------------------------------------


def test_switching_test_replaces_the_result_with_the_prompt_without_a_job(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    _simulate_success(_apply_hypothesis_test(async_ops, dlg))
    config_widgets_before = len(dlg.config_widgets)
    jobs_before = len(async_ops.calls)

    _select_test(_hypothesis_tests_config(dlg), HypothesisTest.CHI_SQUARE)

    assert len(async_ops.calls) == jobs_before
    _assert_apply_prompt(ctrl, dlg)
    assert len(dlg.config_widgets) == config_widgets_before


def test_applying_chi_square_runs_a_chi_square_background_job(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    _select_test(_hypothesis_tests_config(dlg), HypothesisTest.CHI_SQUARE)

    call = _apply_hypothesis_test(async_ops, dlg)

    assert call["scope"] == "analysis:hypothesis_tests:chi_square:grp:color"
    _simulate_success(call)
    assert isinstance(dlg.content_widget(), ChiSquareView)


def test_switching_back_to_group_comparison_keeps_its_pending_selection(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    config = _hypothesis_tests_config(dlg)
    _gc_numeric_combo(config).setCurrentIndex(1)  # "value" -> "other"

    _select_test(config, HypothesisTest.CHI_SQUARE)
    _select_test(config, HypothesisTest.GROUP_COMPARISON)

    _assert_apply_prompt(ctrl, dlg)
    assert _apply_hypothesis_test(async_ops, dlg)["scope"] == "analysis:hypothesis_tests:group_comparison:other:grp"


def test_changing_the_chi_square_column_is_applied_with_the_new_pair(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    config = _hypothesis_tests_config(dlg)
    _select_test(config, HypothesisTest.CHI_SQUARE)

    chi_config = config._chi_square_config  # noqa: SLF001
    assert chi_config is not None
    chi_config._row_combo.setCurrentIndex(chi_config._row_combo.findText("color"))  # noqa: SLF001

    assert async_ops.calls == []
    call = _apply_hypothesis_test(async_ops, dlg)
    assert call["scope"] == "analysis:hypothesis_tests:chi_square:color:grp"
    _simulate_success(call)
    assert isinstance(dlg.content_widget(), ChiSquareView)


def test_stale_group_comparison_result_is_discarded_after_switching_test(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_hypothesis_tests(async_ops, dialog_factory)
    group_comparison_call = _apply_hypothesis_test(async_ops, dlg)

    _select_test(_hypothesis_tests_config(dlg), HypothesisTest.CHI_SQUARE)
    content_widgets_before = len(dlg.content_widgets)
    _simulate_success(group_comparison_call)

    assert len(dlg.content_widgets) == content_widgets_before  # stale, dropped
    _assert_apply_prompt(ctrl, dlg)


def test_switching_to_an_unavailable_test_shows_its_error_and_disables_apply(dialog_factory):
    # Only "grp" is categorical: Group Comparison works, chi-square has no column pair.
    df = pd.DataFrame({"value": [float(i) for i in range(24)], "grp": ["A", "B"] * 12})
    async_ops = DummyAsyncOps()
    _, dlg = _open_hypothesis_tests(async_ops, dialog_factory, df)
    config = _hypothesis_tests_config(dlg)

    _select_test(config, HypothesisTest.CHI_SQUARE)

    assert async_ops.calls == []
    assert isinstance(dlg.content_widget(), ChiSquareView)
    assert not config._apply_button.isEnabled()  # noqa: SLF001


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


def _apply_correlation(async_ops: DummyAsyncOps, dlg: DummyAnalysisDialog) -> dict:
    """Click Apply and return the matrix job's call, without completing it."""
    _correlation_config(dlg)._apply_button.click()  # noqa: SLF001
    return async_ops.last_call


def _open_applied_correlation(async_ops: DummyAsyncOps, dialog_factory):
    ctrl, dlg = _open_correlation(async_ops, dialog_factory)
    _simulate_success(_apply_correlation(async_ops, dlg))
    return ctrl, dlg


def test_correlation_initializes_without_a_job_and_prompts_for_apply(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_correlation(async_ops, dialog_factory)

    assert async_ops.calls == []
    _assert_apply_prompt(ctrl, dlg)
    config = _correlation_config(dlg)
    assert config.matrix_configuration() == (CorrelationMethod.PEARSON, ("a", "b", "c"))
    assert config.checked_columns() == ("a", "b", "c")
    assert config.is_pair_selection_enabled() is False


def test_pair_change_before_the_first_apply_starts_no_job(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)

    _correlation_config(dlg).set_pair("c", "a")

    assert async_ops.calls == []


def test_method_change_without_apply_starts_no_job(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_applied_correlation(async_ops, dialog_factory)
    config = _correlation_config(dlg)
    jobs_before = len(async_ops.calls)

    config._method_combo.setCurrentIndex(config._method_combo.findData(CorrelationMethod.SPEARMAN))  # noqa: SLF001

    assert len(async_ops.calls) == jobs_before
    assert config.matrix_configuration() == (CorrelationMethod.PEARSON, ("a", "b", "c"))
    assert _correlation_view(dlg).method() is CorrelationMethod.PEARSON


def test_correlation_apply_runs_as_a_cancelable_background_job_with_progress(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)

    call = _apply_correlation(async_ops, dlg)

    assert call["scope"] == "analysis:correlation:matrix:pearson"
    assert call["target"] is dlg.content_panel()
    assert call["cancelable"] is True
    assert call["indeterminate"] is False
    assert call["timeout_ms"] == 600_000


def test_correlation_job_reports_progress_through_the_injected_callback(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    call = _apply_correlation(async_ops, dlg)
    progress: list[int] = []

    result = call["work"](progress_cb=progress.append, cancel_cb=lambda: False)

    assert result is not None
    assert progress[-1] == 100


def test_first_apply_details_the_strongest_pair_and_enables_pair_selection(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    config = _correlation_config(dlg)
    config.set_pair("c", "a")  # disabled pickers only hold a placeholder pair

    _simulate_success(_apply_correlation(async_ops, dlg))

    detail = _correlation_view(dlg).pair_detail()
    assert detail is not None
    assert (detail.pair.x_column, detail.pair.y_column) == ("a", "b")
    assert config.current_pair() == ("a", "b")
    assert config.is_pair_selection_enabled() is True
    assert async_ops.last_call["scope"] == "analysis:correlation:matrix:pearson"  # no extra pair job


def test_correlation_without_enough_numeric_columns_shows_error_without_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory, pd.DataFrame({"a": [1.0, 2.0, 3.0]}))

    assert async_ops.calls == []
    view = _correlation_view(dlg)
    assert view.table() is None
    assert dlg.config_widgets[-1] is None


def test_cancel_during_the_matrix_computation_returns_none(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    call = _apply_correlation(async_ops, dlg)
    polls: list[None] = []

    def _cancel_after_first_poll() -> bool:
        polls.append(None)
        return len(polls) > 1

    assert call["work"](cancel_cb=_cancel_after_first_poll) is None


def test_applied_method_change_recomputes_the_matrix_and_keeps_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_applied_correlation(async_ops, dialog_factory)
    config = _correlation_config(dlg)
    first_view = _correlation_view(dlg)
    configs_before = len(dlg.config_widgets)

    config._method_combo.setCurrentIndex(config._method_combo.findData(CorrelationMethod.SPEARMAN))  # noqa: SLF001
    call = _apply_correlation(async_ops, dlg)

    assert call["scope"] == "analysis:correlation:matrix:spearman"
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
    _, dlg = _open_applied_correlation(async_ops, dialog_factory)
    config = _correlation_config(dlg)

    item = config._column_list.item(2)  # noqa: SLF001 - "c"
    item.setCheckState(item.checkState().Unchecked)
    _simulate_success(_apply_correlation(async_ops, dlg))

    view = _correlation_view(dlg)
    table = view.table()
    assert table is not None
    assert table.rowCount() == 1


def test_cancelled_matrix_recompute_shows_placeholder_and_keeps_config(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_correlation(async_ops, dialog_factory)
    config = _correlation_config(dlg)

    call = _apply_correlation(async_ops, dlg)
    call["on_result"](call["work"](cancel_cb=lambda: True))

    assert dlg.placeholder_calls[-1] == ctrl._tr(ctrl.TR_ANALYSIS_CANCELLED)  # noqa: SLF001
    assert dlg.config_widgets[-1] is config
    assert config.is_pair_selection_enabled() is False


def test_stale_matrix_recompute_is_discarded_when_applied_again(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_applied_correlation(async_ops, dialog_factory)
    config = _correlation_config(dlg)
    combo = config._method_combo  # noqa: SLF001

    combo.setCurrentIndex(combo.findData(CorrelationMethod.SPEARMAN))
    first = _apply_correlation(async_ops, dlg)
    combo.setCurrentIndex(combo.findData(CorrelationMethod.KENDALL))
    second = _apply_correlation(async_ops, dlg)

    contents_before = len(dlg.content_widgets)
    _simulate_success(first)
    assert len(dlg.content_widgets) == contents_before

    _simulate_success(second)
    assert _correlation_view(dlg).method() is CorrelationMethod.KENDALL


def test_pair_change_recomputes_only_the_pair_detail_over_the_pair_panel(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_applied_correlation(async_ops, dialog_factory)
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
    _, dlg = _open_applied_correlation(async_ops, dialog_factory)
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
    _, dlg = _open_applied_correlation(async_ops, dialog_factory)
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
    _, dlg = _open_applied_correlation(async_ops, dialog_factory)
    config = _correlation_config(dlg)

    matrix_call = _apply_correlation(async_ops, dlg)
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
    _, dlg = _open_applied_correlation(async_ops, dialog_factory)
    config = _correlation_config(dlg)

    # Kendall is applied, but its matrix job hasn't finished: the view is still Pearson.
    config._method_combo.setCurrentIndex(config._method_combo.findData(CorrelationMethod.KENDALL))  # noqa: SLF001
    _apply_correlation(async_ops, dlg)
    config.set_pair("c", "a")

    assert async_ops.last_call["scope"] == "analysis:correlation:pair:pearson:c:a"


def test_recompute_shows_error_placeholder_when_the_dataset_cannot_be_reloaded(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_correlation(async_ops, dialog_factory)
    ctrl._results._dfs.clear()  # noqa: SLF001 - the dataset disappeared

    _correlation_config(dlg)._apply_button.click()  # noqa: SLF001

    assert async_ops.calls == []
    assert dlg.placeholder_calls[-1] == ctrl._tr(ctrl.TR_ANALYSIS_ERROR)  # noqa: SLF001


def test_recompute_without_a_selected_dataset_does_nothing(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_correlation(async_ops, dialog_factory)
    dlg._selected_dataset_tab_id = None

    _correlation_config(dlg)._apply_button.click()  # noqa: SLF001

    assert async_ops.calls == []


def test_failed_recompute_shows_error_placeholder_unless_stale(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_correlation(async_ops, dialog_factory)
    config = _correlation_config(dlg)
    combo = config._method_combo  # noqa: SLF001

    combo.setCurrentIndex(combo.findData(CorrelationMethod.SPEARMAN))
    first = _apply_correlation(async_ops, dlg)
    combo.setCurrentIndex(combo.findData(CorrelationMethod.KENDALL))
    second = _apply_correlation(async_ops, dlg)

    first["on_error"]("boom")
    assert dlg.placeholder_calls == []

    second["on_error"]("boom")
    assert dlg.placeholder_calls == [ctrl._tr(ctrl.TR_ANALYSIS_ERROR)]  # noqa: SLF001


def test_non_correlation_jobs_keep_an_indeterminate_non_cancelable_overlay(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_hypothesis_tests(async_ops, dialog_factory)

    call = _apply_hypothesis_test(async_ops, dlg)
    assert call["cancelable"] is False
    assert call["indeterminate"] is True
    assert call["timeout_ms"] == 60_000


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
    async_ops.calls.clear()
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


def test_regression_initializes_without_a_background_job_or_busy_overlay(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_regression(async_ops, dialog_factory)

    assert async_ops.calls == []
    view = _regression_view(dlg)
    assert view.result().error is RegressionError.NO_PREDICTORS_SELECTED
    assert view.result().target == "y"
    config = _regression_config(dlg)
    assert config.model_configuration() == ("y", ())


def test_regression_without_numeric_columns_has_no_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_regression(async_ops, dialog_factory, df=pd.DataFrame({"g": ["a", "b", "a"]}))

    assert async_ops.calls == []
    assert _regression_view(dlg).result().error is RegressionError.NO_NUMERIC_COLUMN
    assert dlg.config_widgets[-1] is None


def test_failing_initializer_shows_error_placeholder_without_a_job(dialog_factory, monkeypatch):
    def _raise(_df: pd.DataFrame) -> object:
        raise ValueError

    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_regression(async_ops, dialog_factory)
    handler = ctrl._category_handlers[AnalysisCategory.REGRESSION]  # noqa: SLF001
    monkeypatch.setitem(
        ctrl._category_handlers,  # noqa: SLF001
        AnalysisCategory.REGRESSION,
        dataclasses.replace(handler, initialize=_raise),
    )

    dlg.category_changed.emit(AnalysisCategory.REGRESSION.value)

    assert async_ops.calls == []
    assert dlg.placeholder_calls[-1] == ctrl._tr(ctrl.TR_ANALYSIS_ERROR)  # noqa: SLF001
    assert dlg.config_widgets[-1] is None


def test_applying_predictors_refits_the_model_in_a_background_job(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_regression(async_ops, dialog_factory)
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


# ----------------------------------------------------------------------
# Outlier Explorer
# ----------------------------------------------------------------------


def _outliers_df() -> pd.DataFrame:
    return pd.DataFrame({
        "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 100.0],
        "b": [float(i) for i in range(10)],
        "text": list("abcdefghij"),
    })


def _open_outliers(async_ops: DummyAsyncOps, dialog_factory, df: pd.DataFrame | None = None):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=10, column_count=3)
    ctrl = AnalysisController(
        results=DummyResults(
            datasets=[dataset],
            active_tab_id="t1",
            dfs={"t1": _outliers_df() if df is None else df},
        ),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.OUTLIERS
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.OUTLIERS.value)
    return ctrl, dlg


def _outliers_config(dlg: DummyAnalysisDialog) -> OutliersConfigWidget:
    config = dlg.config_widgets[-1]
    assert isinstance(config, OutliersConfigWidget)
    return config


def _outliers_view(dlg: DummyAnalysisDialog) -> OutliersView:
    view = dlg.content_widget()
    assert isinstance(view, OutliersView)
    return view


def _multivariate_outliers_config(dlg: DummyAnalysisDialog) -> MultivariateOutliersConfigWidget:
    config = dlg.config_widget()
    assert isinstance(config, MultivariateOutliersConfigWidget)
    return config


def _multivariate_outliers_view(dlg: DummyAnalysisDialog) -> MultivariateOutliersView:
    view = dlg.content_widget()
    assert isinstance(view, MultivariateOutliersView)
    return view


def _detail_column(view: OutliersView) -> str:
    detail = view.column_detail()
    assert detail is not None
    return detail.summary.column


def _select_outlier_method(config: OutliersConfigWidget, method: OutlierMethod) -> None:
    combo = config._method_combo  # noqa: SLF001
    combo.setCurrentIndex(combo.findData(method))


def _apply_outliers(async_ops: DummyAsyncOps, dlg: DummyAnalysisDialog) -> dict:
    """Click the univariate Apply and return the summary job's call, without completing it."""
    _outliers_config(dlg)._apply_button.click()  # noqa: SLF001
    return async_ops.last_call


def _open_applied_outliers(async_ops: DummyAsyncOps, dialog_factory):
    ctrl, dlg = _open_outliers(async_ops, dialog_factory)
    _simulate_success(_apply_outliers(async_ops, dlg))
    return ctrl, dlg


def _switch_to_multivariate(dlg: DummyAnalysisDialog) -> MultivariateOutliersConfigWidget:
    _outliers_config(dlg)._mode_combo.setCurrentIndex(1)  # noqa: SLF001
    return _multivariate_outliers_config(dlg)


def test_outliers_initialize_without_a_job_and_prompt_for_apply(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_outliers(async_ops, dialog_factory)

    assert async_ops.calls == []
    _assert_apply_prompt(ctrl, dlg)
    config = _outliers_config(dlg)
    assert config.summary_configuration() == (OutlierMethod.IQR, 1.5)
    assert config.is_column_selection_enabled() is False


def test_outlier_column_change_before_the_first_apply_starts_no_job(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_outliers(async_ops, dialog_factory)

    _outliers_config(dlg).set_column("b")

    assert async_ops.calls == []


def test_outlier_apply_runs_as_a_background_job_with_a_standard_overlay(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_outliers(async_ops, dialog_factory)

    call = _apply_outliers(async_ops, dlg)

    assert call["scope"] == "analysis:outliers:summary:iqr:1.5"
    assert call["target"] is dlg.content_panel()
    assert call["cancelable"] is False
    assert call["indeterminate"] is True


def test_first_outlier_apply_details_the_top_ranked_column_and_enables_column_selection(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_outliers(async_ops, dialog_factory)
    config = _outliers_config(dlg)
    config.set_column("b")  # the disabled picker only holds a placeholder column

    _simulate_success(_apply_outliers(async_ops, dlg))

    assert _detail_column(_outliers_view(dlg)) == "a"
    assert config.current_column() == "a"
    assert config.is_column_selection_enabled() is True
    assert async_ops.last_call["scope"] == "analysis:outliers:summary:iqr:1.5"  # no extra column job


def test_outliers_without_numeric_columns_show_error_without_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_outliers(async_ops, dialog_factory, pd.DataFrame({"t": ["x", "y", "z"]}))

    assert async_ops.calls == []
    view = _outliers_view(dlg)
    assert view.table() is None
    assert view.column_detail() is None
    assert dlg.config_widgets[-1] is None


def test_outlier_method_and_threshold_changes_start_no_job_until_applied(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_applied_outliers(async_ops, dialog_factory)
    config = _outliers_config(dlg)
    jobs_before = len(async_ops.calls)

    _select_outlier_method(config, OutlierMethod.Z_SCORE)
    config._threshold_spin.setValue(2.5)  # noqa: SLF001

    assert len(async_ops.calls) == jobs_before
    assert config.summary_configuration() == (OutlierMethod.IQR, 1.5)
    assert _outliers_view(dlg).configuration() == (OutlierMethod.IQR, 1.5)


def test_switching_outliers_to_multivariate_prompts_without_fitting(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_applied_outliers(async_ops, dialog_factory)
    jobs_before = len(async_ops.calls)

    multivariate_config = _switch_to_multivariate(dlg)

    assert len(async_ops.calls) == jobs_before
    _assert_apply_prompt(ctrl, dlg)
    assert multivariate_config.analysis_configuration() == (
        ("a", "b"),
        MultivariateOutlierMethod.ISOLATION_FOREST,
        True,
        0.05,
        20,
    )


def test_switching_to_multivariate_with_too_few_numeric_columns_explains_why(dialog_factory):
    async_ops = DummyAsyncOps()
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "text": ["x", "y", "z"]})
    _, dlg = _open_outliers(async_ops, dialog_factory, df)

    multivariate_config = _switch_to_multivariate(dlg)

    assert async_ops.calls == []
    view = _multivariate_outliers_view(dlg)
    assert view._result.error is MultivariateOutlierError.NOT_ENOUGH_NUMERIC_COLUMNS  # noqa: SLF001
    assert dlg.config_widget() is multivariate_config


def test_switching_to_multivariate_shows_error_when_the_dataset_cannot_be_reloaded(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_outliers(async_ops, dialog_factory)
    ctrl._results._dfs.clear()  # noqa: SLF001 - the dataset disappeared

    _outliers_config(dlg)._mode_combo.setCurrentIndex(1)  # noqa: SLF001

    assert async_ops.calls == []
    assert dlg.placeholder_calls[-1] == ctrl._tr(ctrl.TR_ANALYSIS_ERROR)  # noqa: SLF001
    assert dlg.config_widget() is None


def test_first_multivariate_apply_fits_the_default_configuration(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_outliers(async_ops, dialog_factory)
    config = _switch_to_multivariate(dlg)

    config._apply_button.click()  # noqa: SLF001

    call = async_ops.last_call
    assert call["scope"] == "analysis:outliers:multivariate:isolation_forest:standardized:contamination:0.05:a:b"
    assert call["target"] is dlg.content_panel()
    assert call["cancelable"] is False
    _simulate_success(call)
    assert _multivariate_outliers_view(dlg).configuration() == config.analysis_configuration()


def test_applying_multivariate_configuration_refits_and_retains_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_outliers(async_ops, dialog_factory)
    config = _switch_to_multivariate(dlg)

    config._method_combo.setCurrentIndex(config._method_combo.findData(MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR))  # noqa: SLF001
    config._contamination_spin.setValue(10.0)  # noqa: SLF001
    config._neighbors_spin.setValue(3)  # noqa: SLF001
    config._apply_button.click()  # noqa: SLF001

    call = async_ops.last_call
    assert (
        call["scope"]
        == "analysis:outliers:multivariate:local_outlier_factor:standardized:contamination:0.1:neighbors:3:a:b"
    )
    _simulate_success(call)

    assert dlg.config_widget() is config
    assert _multivariate_outliers_view(dlg).configuration() == (
        ("a", "b"),
        MultivariateOutlierMethod.LOCAL_OUTLIER_FACTOR,
        True,
        0.1,
        3,
    )


def test_stale_multivariate_fit_is_discarded(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_outliers(async_ops, dialog_factory)
    config = _switch_to_multivariate(dlg)

    config._contamination_spin.setValue(10.0)  # noqa: SLF001
    config._apply_button.click()  # noqa: SLF001
    first = async_ops.last_call
    config._contamination_spin.setValue(20.0)  # noqa: SLF001
    config._apply_button.click()  # noqa: SLF001
    second = async_ops.last_call
    views_before = len(dlg.content_widgets)

    _simulate_success(first)
    assert len(dlg.content_widgets) == views_before

    _simulate_success(second)
    assert _multivariate_outliers_view(dlg).configuration()[3] == 0.2


def test_switching_multivariate_mode_back_restores_the_univariate_prompt(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_applied_outliers(async_ops, dialog_factory)
    config = _switch_to_multivariate(dlg)
    jobs_before = len(async_ops.calls)

    config._mode_combo.setCurrentIndex(0)  # noqa: SLF001

    assert len(async_ops.calls) == jobs_before
    _assert_apply_prompt(ctrl, dlg)
    assert isinstance(dlg.config_widget(), OutliersConfigWidget)


def test_applied_outlier_method_recomputes_the_summary_and_keeps_the_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_applied_outliers(async_ops, dialog_factory)
    config = _outliers_config(dlg)
    first_view = _outliers_view(dlg)
    configs_before = len(dlg.config_widgets)
    config.set_column("b")
    _simulate_success(async_ops.last_call)

    _select_outlier_method(config, OutlierMethod.Z_SCORE)
    call = _apply_outliers(async_ops, dlg)

    assert call["scope"] == "analysis:outliers:summary:z_score:3.0"
    _simulate_success(call)

    view = _outliers_view(dlg)
    assert view is not first_view
    assert view.configuration() == (OutlierMethod.Z_SCORE, 3.0)
    detail = view.column_detail()
    assert detail is not None
    assert detail.method is OutlierMethod.Z_SCORE
    assert detail.summary.column == "b"  # the selected column is kept
    assert len(dlg.config_widgets) == configs_before


def test_stale_outlier_summary_is_discarded_when_applied_again(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_applied_outliers(async_ops, dialog_factory)
    config = _outliers_config(dlg)
    spin = config._threshold_spin  # noqa: SLF001

    spin.setValue(2.0)
    first = _apply_outliers(async_ops, dlg)
    spin.setValue(3.0)
    second = _apply_outliers(async_ops, dlg)

    contents_before = len(dlg.content_widgets)
    _simulate_success(first)
    assert len(dlg.content_widgets) == contents_before

    _simulate_success(second)
    assert _outliers_view(dlg).configuration() == (OutlierMethod.IQR, 3.0)


def test_outlier_column_change_recomputes_only_the_detail_over_the_detail_panel(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_applied_outliers(async_ops, dialog_factory)
    config = _outliers_config(dlg)
    view = _outliers_view(dlg)
    contents_before = len(dlg.content_widgets)

    config.set_column("b")

    call = async_ops.last_call
    assert call["scope"] == "analysis:outliers:column:iqr:1.5:b"
    assert call["target"] is view.detail_panel()
    assert call["cancelable"] is False

    _simulate_success(call)

    assert len(dlg.content_widgets) == contents_before  # view updated in place
    assert _detail_column(view) == "b"


def test_clicking_an_outlier_summary_row_selects_the_column(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_applied_outliers(async_ops, dialog_factory)
    config = _outliers_config(dlg)
    table = _outliers_view(dlg).table()
    assert table is not None

    table.cellClicked.emit(1, 0)

    assert config.current_column() == "b"
    assert async_ops.last_call["scope"] == "analysis:outliers:column:iqr:1.5:b"


def test_stale_outlier_column_recompute_is_discarded_when_the_column_changes_again(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_applied_outliers(async_ops, dialog_factory)
    config = _outliers_config(dlg)
    view = _outliers_view(dlg)
    initial_detail = view.column_detail()

    config.set_column("b")
    first = async_ops.last_call
    config.set_column("a")
    second = async_ops.last_call

    _simulate_success(first)
    assert view.column_detail() is initial_detail

    _simulate_success(second)
    assert _detail_column(view) == "a"


def test_outlier_column_change_while_the_summary_is_computing_is_caught_up_afterwards(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_applied_outliers(async_ops, dialog_factory)
    config = _outliers_config(dlg)

    _select_outlier_method(config, OutlierMethod.MODIFIED_Z_SCORE)
    summary_call = _apply_outliers(async_ops, dlg)
    dlg.show_placeholder("computing")  # no view is displayed while the summary job runs
    jobs_before = len(async_ops.calls)

    config.set_column("b")
    assert len(async_ops.calls) == jobs_before  # nothing to update yet

    _simulate_success(summary_call)
    assert _detail_column(_outliers_view(dlg)) == "a"

    column_call = async_ops.last_call
    assert column_call["scope"] == "analysis:outliers:column:modified_z_score:3.5:b"
    _simulate_success(column_call)
    assert _detail_column(_outliers_view(dlg)) == "b"


def test_outlier_column_recompute_uses_the_displayed_summary_configuration(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_applied_outliers(async_ops, dialog_factory)
    config = _outliers_config(dlg)

    # Z-score is applied, but its summary job hasn't finished: the view still shows IQR.
    _select_outlier_method(config, OutlierMethod.Z_SCORE)
    _apply_outliers(async_ops, dlg)
    config.set_column("b")

    assert async_ops.last_call["scope"] == "analysis:outliers:column:iqr:1.5:b"


# ----------------------------------------------------------------------
# Principal Component Analysis
# ----------------------------------------------------------------------


def _pca_df() -> pd.DataFrame:
    return pd.DataFrame({
        "a": [1.0, 2.0, 3.0, 4.0, 5.0],
        "b": [2.0, 4.0, 7.0, 8.0, 11.0],
        "c": [9.0, 2.0, 5.0, 3.0, 7.0],
        "text": list("abcde"),
    })


def _open_pca(async_ops: DummyAsyncOps, dialog_factory, df: pd.DataFrame | None = None):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=5, column_count=4)
    ctrl = AnalysisController(
        results=DummyResults(
            datasets=[dataset],
            active_tab_id="t1",
            dfs={"t1": _pca_df() if df is None else df},
        ),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.PCA
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.PCA.value)
    return ctrl, dlg


def _pca_config(dlg: DummyAnalysisDialog) -> PCAConfigWidget:
    config = dlg.config_widgets[-1]
    assert isinstance(config, PCAConfigWidget)
    return config


def _pca_view(dlg: DummyAnalysisDialog) -> PCAView:
    view = dlg.content_widget()
    assert isinstance(view, PCAView)
    return view


def _set_pca_checked(config: PCAConfigWidget, column: str, checked: bool) -> None:
    items = config._column_list.findItems(column, Qt.MatchFlag.MatchExactly)  # noqa: SLF001
    assert len(items) == 1
    items[0].setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)


def test_pca_initializes_without_a_job_and_prompts_for_apply(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_pca(async_ops, dialog_factory)

    assert async_ops.calls == []
    _assert_apply_prompt(ctrl, dlg)
    config = _pca_config(dlg)
    assert config.analysis_configuration() == (("a", "b", "c"), True)
    assert config.checked_columns() == ("a", "b", "c")


def test_first_pca_apply_fits_the_default_configuration(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_pca(async_ops, dialog_factory)

    _pca_config(dlg)._apply_button.click()  # noqa: SLF001

    call = async_ops.last_call
    assert call["scope"] == "analysis:pca:fit:standardized:a:b:c"
    _simulate_success(call)
    assert _pca_view(dlg).configuration() == (("a", "b", "c"), True)


def test_pca_without_enough_numeric_columns_shows_error_without_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_pca(async_ops, dialog_factory, pd.DataFrame({"a": [1.0, 2.0], "text": ["x", "y"]}))

    assert async_ops.calls == []
    view = _pca_view(dlg)
    assert view.loadings_table() is None
    assert PCAError.NOT_ENOUGH_NUMERIC_COLUMNS.value in str(view._result.error)  # noqa: SLF001
    assert dlg.config_widgets[-1] is None


def test_apply_recomputes_pca_and_keeps_the_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_pca(async_ops, dialog_factory)
    config = _pca_config(dlg)
    prompt = dlg.content_widget()
    configs_before = len(dlg.config_widgets)

    _set_pca_checked(config, "c", False)
    config._standardize_checkbox.setChecked(False)  # noqa: SLF001
    config._apply_button.click()  # noqa: SLF001

    call = async_ops.last_call
    assert call["scope"] == "analysis:pca:fit:raw:a:b"
    assert call["target"] is dlg.content_panel()
    assert call["cancelable"] is False

    _simulate_success(call)

    view = _pca_view(dlg)
    assert view is not prompt
    assert view.configuration() == (("a", "b"), False)
    assert len(dlg.config_widgets) == configs_before


def test_stale_pca_recompute_is_discarded_when_apply_changes_again(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_pca(async_ops, dialog_factory)
    config = _pca_config(dlg)

    _set_pca_checked(config, "c", False)
    config._apply_button.click()  # noqa: SLF001
    first = async_ops.last_call

    config._standardize_checkbox.setChecked(False)  # noqa: SLF001
    config._apply_button.click()  # noqa: SLF001
    second = async_ops.last_call

    contents_before = len(dlg.content_widgets)
    _simulate_success(first)
    assert len(dlg.content_widgets) == contents_before

    _simulate_success(second)
    assert _pca_view(dlg).configuration() == (("a", "b"), False)


# ----------------------------------------------------------------------
# Clustering
# ----------------------------------------------------------------------


def _clustering_df() -> pd.DataFrame:
    return pd.DataFrame({
        "x": [0.0, 0.1, -0.1, 10.0, 10.1, 9.9],
        "y": [0.0, -0.1, 0.1, 10.0, 10.1, 9.9],
        "z": [1.0, 1.1, 0.9, 5.0, 5.1, 4.9],
        "text": list("abcdef"),
    })


def _open_clustering(async_ops: DummyAsyncOps, dialog_factory, df: pd.DataFrame | None = None):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=6, column_count=4)
    ctrl = AnalysisController(
        results=DummyResults(
            datasets=[dataset],
            active_tab_id="t1",
            dfs={"t1": _clustering_df() if df is None else df},
        ),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())

    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.CLUSTERING
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.CLUSTERING.value)
    return ctrl, dlg


def _clustering_config(dlg: DummyAnalysisDialog) -> ClusteringConfigWidget:
    config = dlg.config_widgets[-1]
    assert isinstance(config, ClusteringConfigWidget)
    return config


def _clustering_view(dlg: DummyAnalysisDialog) -> ClusteringView:
    view = dlg.content_widget()
    assert isinstance(view, ClusteringView)
    return view


def _set_clustering_checked(config: ClusteringConfigWidget, column: str, checked: bool) -> None:
    items = config._column_list.findItems(column, Qt.MatchFlag.MatchExactly)  # noqa: SLF001
    assert len(items) == 1
    items[0].setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)


def test_clustering_initializes_without_a_job_and_prompts_for_apply(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_clustering(async_ops, dialog_factory)

    assert async_ops.calls == []
    _assert_apply_prompt(ctrl, dlg)
    config = _clustering_config(dlg)
    assert config.analysis_configuration() == (("x", "y", "z"), ClusteringMethod.K_MEANS, True, 3, 0.5, 5)
    assert config.checked_columns() == ("x", "y", "z")


def test_first_clustering_apply_fits_the_default_configuration(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_clustering(async_ops, dialog_factory)

    _clustering_config(dlg)._apply_button.click()  # noqa: SLF001

    call = async_ops.last_call
    assert call["scope"] == "analysis:clustering:fit:k_means:standardized:clusters:3:x:y:z"
    _simulate_success(call)
    assert _clustering_view(dlg).configuration() == (("x", "y", "z"), ClusteringMethod.K_MEANS, True, 3, 0.5, 5)


def test_clustering_without_numeric_columns_shows_error_without_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_clustering(async_ops, dialog_factory, pd.DataFrame({"text": ["x", "y"]}))

    assert async_ops.calls == []
    assert _clustering_view(dlg).cluster_table() is None
    assert dlg.config_widgets[-1] is None


def test_clustering_apply_recomputes_dbscan_and_keeps_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_clustering(async_ops, dialog_factory)
    config = _clustering_config(dlg)
    prompt = dlg.content_widget()
    configs_before = len(dlg.config_widgets)

    _set_clustering_checked(config, "z", False)
    config._standardize_checkbox.setChecked(False)  # noqa: SLF001
    combo = config._method_combo  # noqa: SLF001
    combo.setCurrentIndex(combo.findData(ClusteringMethod.DBSCAN))
    config._epsilon_spin.setValue(0.75)  # noqa: SLF001
    config._min_samples_spin.setValue(2)  # noqa: SLF001
    config._apply_button.click()  # noqa: SLF001

    call = async_ops.last_call
    assert call["scope"] == "analysis:clustering:fit:dbscan:raw:eps:0.75:min_samples:2:x:y"
    assert call["target"] is dlg.content_panel()
    assert call["cancelable"] is False

    _simulate_success(call)

    view = _clustering_view(dlg)
    assert view is not prompt
    assert view.configuration() == (("x", "y"), ClusteringMethod.DBSCAN, False, 3, 0.75, 2)
    assert len(dlg.config_widgets) == configs_before


def test_stale_clustering_recompute_is_discarded_after_another_apply(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_clustering(async_ops, dialog_factory)
    config = _clustering_config(dlg)

    config._cluster_count_spin.setValue(2)  # noqa: SLF001
    config._apply_button.click()  # noqa: SLF001
    first = async_ops.last_call
    config._cluster_count_spin.setValue(4)  # noqa: SLF001
    config._apply_button.click()  # noqa: SLF001
    second = async_ops.last_call

    contents_before = len(dlg.content_widgets)
    _simulate_success(first)
    assert len(dlg.content_widgets) == contents_before

    _simulate_success(second)
    assert _clustering_view(dlg).configuration()[3] == 4


# ----------------------------------------------------------------------
# Time Series Explorer
# ----------------------------------------------------------------------


def _time_series_df() -> pd.DataFrame:
    return pd.DataFrame({
        "when": pd.date_range("2025-01-01", periods=21, freq="D"),
        "value": range(21),
        "other": range(100, 121),
    })


def _open_time_series(async_ops: DummyAsyncOps, dialog_factory, df: pd.DataFrame | None = None):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=21, column_count=3)
    ctrl = AnalysisController(
        results=DummyResults(
            datasets=[dataset],
            active_tab_id="t1",
            dfs={"t1": _time_series_df() if df is None else df},
        ),
        async_ops=async_ops,
    )
    _open_and_flush(ctrl, QWidget())
    dlg = dialog_factory[0]
    dlg._selected_category = AnalysisCategory.TIME_SERIES
    dlg._selected_dataset_tab_id = "t1"
    dlg.category_changed.emit(AnalysisCategory.TIME_SERIES.value)
    return ctrl, dlg


def _time_series_config(dlg: DummyAnalysisDialog) -> TimeSeriesConfigWidget:
    config = dlg.config_widgets[-1]
    assert isinstance(config, TimeSeriesConfigWidget)
    return config


def _time_series_view(dlg: DummyAnalysisDialog) -> TimeSeriesView:
    view = dlg.content_widget()
    assert isinstance(view, TimeSeriesView)
    return view


def test_time_series_initializes_without_a_job_and_prompts_for_apply(dialog_factory):
    async_ops = DummyAsyncOps()
    ctrl, dlg = _open_time_series(async_ops, dialog_factory)

    assert async_ops.calls == []
    _assert_apply_prompt(ctrl, dlg)
    config = _time_series_config(dlg)
    assert config.analysis_configuration() == ("when", "value", None, None, DecompositionModel.ADDITIVE)
    assert config.pending_configuration() == config.analysis_configuration()


def test_first_time_series_apply_analyzes_the_default_configuration(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_time_series(async_ops, dialog_factory)

    _time_series_config(dlg)._apply_button.click()  # noqa: SLF001

    call = async_ops.last_call
    assert call["scope"] == "analysis:time_series:fit:when:value:original:auto:additive"
    _simulate_success(call)
    assert _time_series_view(dlg).configuration() == ("when", "value", None, 7, DecompositionModel.ADDITIVE)


def test_time_series_without_datetime_has_no_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_time_series(async_ops, dialog_factory, pd.DataFrame({"value": [1.0, 2.0, 3.0]}))

    assert async_ops.calls == []
    assert isinstance(dlg.content_widget(), TimeSeriesView)
    assert dlg.config_widgets[-1] is None


def test_time_series_apply_recomputes_and_keeps_config(dialog_factory):
    async_ops = DummyAsyncOps()
    _, dlg = _open_time_series(async_ops, dialog_factory)
    config = _time_series_config(dlg)
    configs_before = len(dlg.config_widgets)

    config._value_combo.setCurrentIndex(config._value_combo.findText("other"))  # noqa: SLF001
    config._frequency_combo.setCurrentIndex(config._frequency_combo.findData("W"))  # noqa: SLF001
    config._auto_period.setChecked(False)  # noqa: SLF001
    config._period_spin.setValue(3)  # noqa: SLF001
    config._model_combo.setCurrentIndex(config._model_combo.findData(DecompositionModel.MULTIPLICATIVE))  # noqa: SLF001
    config._apply_button.click()  # noqa: SLF001

    call = async_ops.last_call
    assert call["scope"] == "analysis:time_series:fit:when:other:W:3:multiplicative"
    _simulate_success(call)
    assert _time_series_view(dlg).configuration() == ("when", "other", "W", 3, DecompositionModel.MULTIPLICATIVE)
    assert len(dlg.config_widgets) == configs_before
