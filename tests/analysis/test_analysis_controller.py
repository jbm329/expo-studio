from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QWidget

from expo_jbm329.utils.dataset_ref import DatasetRef
from expo_jbm329.workbench.controllers.analysis.analysis_controller import AnalysisController

_CONTROLLER_MODULE = "expo_jbm329.workbench.controllers.analysis.analysis_controller"


class DummyResults:
    def __init__(self, datasets=None, active_tab_id=None):
        self._datasets = datasets or []
        self._active_tab_id = active_tab_id

    def list_ready_datasets(self):
        return self._datasets

    def active_tab_id(self):
        return self._active_tab_id


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
        self.placeholder_calls: list[str] = []
        self.exec_called = False

    def show_placeholder(self, text):
        self.placeholder_calls.append(text)

    def exec(self):
        self.exec_called = True
        return QDialog.DialogCode.Accepted


def test_open_dialog_does_nothing_when_there_are_no_datasets(monkeypatch):
    created = []
    monkeypatch.setattr(f"{_CONTROLLER_MODULE}.AnalysisDialog", lambda **kwargs: created.append(kwargs))

    ctrl = AnalysisController(results=DummyResults(datasets=[]))
    ctrl.open_dialog(QWidget())

    assert created == []


def test_open_dialog_builds_dialog_with_datasets_and_active_tab(monkeypatch):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=10, column_count=3)
    dialogs: list[DummyAnalysisDialog] = []

    def _factory(**kwargs):
        dlg = DummyAnalysisDialog(**kwargs)
        dialogs.append(dlg)
        return dlg

    monkeypatch.setattr(f"{_CONTROLLER_MODULE}.AnalysisDialog", _factory)

    ctrl = AnalysisController(results=DummyResults(datasets=[dataset], active_tab_id="t1"))
    ctrl.open_dialog(QWidget())

    assert len(dialogs) == 1
    dlg = dialogs[0]
    assert dlg.kwargs["datasets"] == [dataset]
    assert dlg.kwargs["active_tab_id"] == "t1"
    assert dlg.exec_called


def test_category_changed_shows_not_implemented_placeholder(monkeypatch):
    dataset = DatasetRef(tab_id="t1", title="Sheet1", row_count=10, column_count=3)
    dialogs: list[DummyAnalysisDialog] = []

    def _factory(**kwargs):
        dlg = DummyAnalysisDialog(**kwargs)
        dialogs.append(dlg)
        return dlg

    monkeypatch.setattr(f"{_CONTROLLER_MODULE}.AnalysisDialog", _factory)

    ctrl = AnalysisController(results=DummyResults(datasets=[dataset], active_tab_id="t1"))
    ctrl.open_dialog(QWidget())

    dlg = dialogs[0]
    dlg.category_changed.emit("overview")

    assert dlg.placeholder_calls == [ctrl._tr(ctrl.TR_NOT_IMPLEMENTED)]  # noqa: SLF001
