from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QWidget

from expo_jbm329.gui.dialogs.service.null_dialog_service import NullDialogService
from expo_jbm329.services.data_profile.profile_cache import ColumnProfileCache
from expo_jbm329.workbench.controllers.result_tabs.result_tab_manager import ResultTabManager
from tests.stubs import DummyAsyncOps, DummyDialogState, DummyJobManager


class StubModel:
    def __init__(self, df, parent=None, **kwargs):
        self._df = df
        self.parent_view = parent

    def dataFrame(self):
        return self._df

    def setDataFrame(self, new_df, **kwargs):
        self._df = new_df
        if self.parent_view is not None:
            self.parent_view._df = new_df


class StubHeader:
    def __init__(self):
        self.customContextMenuRequested = SimpleNamespace(connect=lambda cb: None)
        self._font = QFont()

    def setContextMenuPolicy(self, p): pass
    def logicalIndexAt(self, pos): return 0
    def setStretchLastSection(self, *a): pass
    def setSectionResizeMode(self, *a): pass
    def mapToGlobal(self, p): return p
    def setHorizontalScrollBarPolicy(self, p): pass
    def setVerticalScrollBarPolicy(self, p): pass
    def setModel(self, m): pass
    def setSectionsClickable(self, b): pass
    def setSectionsMovable(self, b): pass
    def setHighlightSections(self, b): pass
    def selectionModel(self): return SimpleNamespace(selectedColumns=lambda: [])
    def setSortIndicator(self, i, o): pass
    def setSortIndicatorShown(self, b): pass
    def viewport(self): return SimpleNamespace(installEventFilter=lambda f: None)
    def installEventFilter(self, f): pass
    def setDefaultAlignment(self, a): pass
    def setDefaultSectionSize(self, s): pass
    def font(self): return self._font
    def sectionSize(self, i): return 100
    def resizeSection(self, i, size): pass


class StubView:
    SelectionBehavior = SimpleNamespace(SelectColumns=1)
    SelectionMode = SimpleNamespace(ExtendedSelection=1)
    EditTrigger = SimpleNamespace(NoEditTriggers=0)

    def __init__(self, parent=None):
        self._model = None
        self._df = None
        self._header = StubHeader()
        self.customContextMenuRequested = SimpleNamespace(connect=lambda cb: None)
        self.verticalHeader = lambda: SimpleNamespace(
            setVisible=lambda v: None,
            setDefaultAlignment=lambda a: None,
            setSectionResizeMode=lambda *a: None,
            setDefaultSectionSize=lambda s: None,
        )
        self.selectionModel = lambda: SimpleNamespace(selectedColumns=lambda: [])

    def horizontalHeader(self):
        return self._header

    def setModel(self, m):
        self._model = m
        if hasattr(m, "dataFrame"):
            self._df = m.dataFrame()
            if hasattr(m, "setDataFrame"):
                m.parent_view = self

    def model(self):
        return self._model

    def setDataFrame(self, df):
        self._df = df
        if self._model is not None:
            self._model._df = df

    def setSortingEnabled(self, b): pass
    def sortByColumn(self, column, order): pass
    def setSelectionBehavior(self, b): pass
    def setSelectionMode(self, m): pass
    def setEditTriggers(self, t): pass
    def setAlternatingRowColors(self, b): pass
    def setContextMenuPolicy(self, p): pass
    def setWordWrap(self, b): pass
    def setItemDelegate(self, d): pass
    def viewport(self): return SimpleNamespace(installEventFilter=lambda f: None)
    def installEventFilter(self, f): pass
    def setHorizontalHeader(self, h): self._header = h
    def setShowGrid(self, b): pass


class StubTabs:
    def __init__(self):
        self._widgets = []
        self._texts = {}
        self._data = {}
        self._current = -1

    def tabBar(self):
        return self

    def addTab(self, widget, title):
        idx = len(self._widgets)
        self._widgets.append(widget)
        self._texts[idx] = title
        self._data[idx] = f"tab-{idx}"
        if self._current < 0:
            self._current = 0
        return idx

    def setTabText(self, index, text):
        self._texts[index] = text

    def tabText(self, index):
        return self._texts.get(index, "")

    def setTabData(self, index, value):
        self._data[index] = value

    def tabData(self, index):
        return self._data.get(index)

    def tabAt(self, pos):
        return 0 if self._widgets else -1

    def mapToGlobal(self, p):
        return p

    def blockSignals(self, value):
        pass

    def count(self):
        return len(self._widgets)

    def currentIndex(self):
        return self._current

    def setCurrentIndex(self, idx):
        self._current = idx

    def widget(self, index):
        if 0 <= index < len(self._widgets):
            return self._widgets[index]
        return None

    def removeTab(self, index):
        if 0 <= index < len(self._widgets):
            self._widgets.pop(index)
            keys = sorted(self._texts)
            self._texts = {i: self._texts[k] for i, k in enumerate([k for k in keys if k != index])}
            keys = sorted(self._data)
            self._data = {i: self._data[k] for i, k in enumerate([k for k in keys if k != index])}


class StubParent(QWidget):
    pass


@pytest.fixture
def result_tabs_env(monkeypatch):
    import expo_jbm329.workbench.controllers.result_tabs.result_tab_manager as rtm_mod

    monkeypatch.setattr(rtm_mod, "QTableView", StubView)
    monkeypatch.setattr(rtm_mod, "DataFrameModel", StubModel)
    monkeypatch.setattr(rtm_mod, "QApplication", SimpleNamespace(instance=lambda: None))
    monkeypatch.setattr(rtm_mod, "QThread", SimpleNamespace(currentThread=lambda: "main"))
    monkeypatch.setattr(rtm_mod, "ui_invoke", lambda fn, *a, **k: fn(*a, **k))

    return SimpleNamespace(
        StubView=StubView,
        StubTabs=StubTabs,
        StubHeader=StubHeader,
        StubModel=StubModel,
        StubParent=StubParent,
    )


def make_manager(env, df=None):
    if df is None:
        df = pd.DataFrame({"a": [1, 2, 3]})

    parent = env.StubParent()
    tabs = env.StubTabs()
    cache = ColumnProfileCache()
    status_msgs: list[tuple[str, int | None]] = []
    dialogs = NullDialogService()
    async_ops = DummyAsyncOps()

    def set_status(msg: str, timeout: int | None) -> None:
        status_msgs.append((msg, timeout))

    mgr = ResultTabManager(
        parent_widget=parent,
        tabs=tabs,
        busy_overlay=SimpleNamespace(),
        async_ops=async_ops,
        col_profile_cache=cache,
        set_status=set_status,
        dialogs=dialogs,
    )
    return mgr, parent, tabs, cache, status_msgs, dialogs, async_ops
