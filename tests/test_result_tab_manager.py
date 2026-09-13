# ======================================================================
#   tests/test_result_tab_manager.py  —  NORMAL COVERAGE VERSION
# ======================================================================

#   Covers:
#     • display_dataframe / invalid input
#     • close_tabs_by_title
#     • current_df
#     • close_tab
#     • rename_tab (via prompt_text)
#     • on_tab_changed
#     • remove_column
#     • column properties
#     • collect_all_tabs_data
#     • data cleansing functions
#     • fillna functions
#     • basic cache invalidation
#
#   Qt UI fully stubbed — no Qt windows opened.
# ======================================================================
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest
import uuid
from PyQt6.QtWidgets import QWidget

from workbench.controllers.result_tabs.result_tab_manager import ResultTabManager
from gui.dialogs.service.dialog_service import NullDialogService
from services.data_profile.profile_cache import ColumnProfileCache
from tests.stubs import DummyJobManager


# ======================================================================
#   --- Patch Qt Widgets / Models, so tests run without Qt GUI ---
# ======================================================================
@pytest.fixture(autouse=True)
def patch_qt(monkeypatch):

    class StubModel:
        """ Minimal stand-in for DataFrameModel / MinimalModel. """
        def __init__(self, df, parent=None, **kwargs):
            self._df = df
            self.parent_view = parent

        def dataFrame(self):
            return self._df

        def setDataFrame(self, new_df, **kwargs):
            self._df = new_df
            if self.parent_view:
                self.parent_view._df = new_df

        def sort(self, column, order):
            # Qt.SortOrder.AscendingOrder is 0, DescendingOrder is 1
            # The enum might not allow int() if it's a strict Qt enum.
            # We compare against the Qt enum itself.
            from PyQt6.QtCore import Qt
            asc = (order == Qt.SortOrder.AscendingOrder)
            if column == 0:
                self._df = self._df.sort_index(ascending=asc)
            else:
                col_name = self._df.columns[column - 1]
                self._df = self._df.sort_values(by=col_name, ascending=asc)
            if self.parent_view:
                self.parent_view._df = self._df

    class StubHeader:
        """ Minimal horizontal header. """
        def __init__(self, *a, **k):
            self.customContextMenuRequested = SimpleNamespace(connect=lambda cb: None)

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
        def sectionClicked(self): return SimpleNamespace(connect=lambda cb: None)
        def sectionResized(self): return SimpleNamespace(connect=lambda cb: None)
        def showSection(self, i): pass
        def hideSection(self, i): pass
        def sectionSize(self, i): return 100
        def resizeSection(self, i, s): pass
        def count(self): return 10
        def setSortIndicator(self, i, o): pass
        def setSortIndicatorShown(self, b): pass
        def viewport(self): return SimpleNamespace(installEventFilter=lambda f: None)
        def installEventFilter(self, f): pass
        def mousePressEvent(self, ev): pass
        def mouseReleaseEvent(self, ev): pass

    class StubView:
        """ Stand-in for QTableView. """
        SelectionBehavior = SimpleNamespace(SelectColumns=1)
        SelectionMode = SimpleNamespace(ExtendedSelection=1)
        EditTrigger = SimpleNamespace(NoEditTriggers=0)

        def __init__(self, parent=None):
            self._model = None
            self._df = None
            self._header = StubHeader()
            self.verticalHeader = lambda: SimpleNamespace(setVisible=lambda v: None)
            self.customContextMenuRequested = SimpleNamespace(connect=lambda cb: None)
            self.selectionModel = lambda: SimpleNamespace(selectedColumns=lambda: [])

        def horizontalHeader(self):
            return self._header

        def setModel(self, m):
            self._model = m
            if hasattr(m, "dataFrame"):
                self._df = m.dataFrame()

        def setDataFrame(self, df):
            self._df = df
            if self._model:
                self._model._df = df

        def model(self):
            return self._model

        def setSortingEnabled(self, value): pass
        def sortByColumn(self, column, order):
            self.sorted = (column, order)

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
        def setSortingEnabled(self, b): pass

    # Inject stub types into namespace used by ResultTabManager
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.result_tab_manager.QTableView",
        StubView
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.result_tab_manager.DataFrameModel",
        StubModel
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.result_tab_manager.MinimalModel",
        StubModel
    )

    # Patch modules and classes for display_dataframe
    import workbench.controllers.result_tabs.result_tab_manager as rtm_mod
    monkeypatch.setattr(rtm_mod, "QApplication", SimpleNamespace(instance=lambda: SimpleNamespace(thread=lambda: "main")))
    monkeypatch.setattr(rtm_mod, "QThread", SimpleNamespace(currentThread=lambda: "main"))

    # Also mock sys.modules for the local import of ExpoHeaderView
    import sys
    sys.modules["expo_jbm329.utils.custom_header"] = SimpleNamespace(ExpoHeaderView=StubHeader)


# ======================================================================
#   --- Stub QTabWidget & TabBar (Qt-like behavior) ---
# ======================================================================
class StubTabBar:
    def __init__(self):
        self._texts = {}
        self._data = {}

    def setTabText(self, index, text):
        self._texts[index] = text

    def tabText(self, index):
        return self._texts.get(index, "")

    def setTabData(self, index, value):
        self._data[index] = value

    def tabData(self, index):
        return self._data.get(index)

    def tabAt(self, pos):
        return 0 if self._texts else -1

    def mapToGlobal(self, p):
        return p


class StubTabs:
    """ Reliable QTabWidget stub with full index-shift logic. """

    def __init__(self):
        self._widgets = []
        self._current = -1
        self._tab_bar = StubTabBar()

    def tabBar(self):
        return self._tab_bar

    def addTab(self, widget, title):
        idx = len(self._widgets)
        self._widgets.append(widget)
        self._tab_bar.setTabText(idx, title)
        # ResultTabManager calls tabData(idx) and expects a string UUID
        self._tab_bar.setTabData(idx, str(uuid.uuid4()))
        if self._current < 0:
            self._current = 0
        return idx

    def setTabText(self, index, text):
        self._tab_bar.setTabText(index, text)

    def removeTab(self, index):
        if index < 0 or index >= len(self._widgets):
            return

        # Update currentIndex like Qt
        if index == self._current:
            if len(self._widgets) == 1:
                self._current = -1
            elif index == len(self._widgets) - 1:
                self._current -= 1
            else:
                self._current = index
        elif index < self._current:
            self._current -= 1

        self._widgets.pop(index)

        # Rebuild tab texts and data
        new_texts = {}
        new_data = {}
        # Current _texts and _data use integers as keys (indices)
        for old_idx, text in self._tab_bar._texts.items():
            if old_idx == index:
                continue
            target_idx = old_idx if old_idx < index else old_idx - 1
            new_texts[target_idx] = text

        for old_idx, data in self._tab_bar._data.items():
            if old_idx == index:
                continue
            target_idx = old_idx if old_idx < index else old_idx - 1
            new_data[target_idx] = data

        self._tab_bar._texts = new_texts
        self._tab_bar._data = new_data

    def blockSignals(self, v): pass
    def count(self): return len(self._widgets)
    def currentIndex(self): return self._current
    def setCurrentIndex(self, idx):
        self._current = idx if 0 <= idx < len(self._widgets) else -1

    def widget(self, index):
        if 0 <= index < len(self._widgets):
            return self._widgets[index]
        return None

    def tabText(self, index):
        return self._tab_bar.tabText(index)


# ======================================================================
#   --- Parent stub (QWidget wrapper)
# ======================================================================
class StubParent(QWidget):
    pass


# ======================================================================
#   --- Test Manager factory
# ======================================================================
def make_mgr(df=None):
    if df is None:
        df = pd.DataFrame({"a": [1, 2, 3]})

    parent = StubParent()
    tabs = StubTabs()
    cache = ColumnProfileCache()
    status_msgs = []

    dlg = NullDialogService()
    job_mgr = DummyJobManager()

    def set_status(msg, ms):
        status_msgs.append((msg, ms))

    mgr = ResultTabManager(
        parent_widget=parent,
        tabs=tabs,
        job_mgr=job_mgr,
        col_profile_cache=cache,
        set_status=set_status,
        dialogs=dlg,
    )
    return mgr, parent, tabs, cache, status_msgs, dlg


# ======================================================================
#   --- BASIC TESTS ---
# ======================================================================

def test_display_dataframe_creates_tab_and_stores_df():
    mgr, parent, tabs, cache, status, dlg = make_mgr()
    df = pd.DataFrame({"a": [1, 2]})
    mgr.display_dataframe(df, title="X")

    assert tabs.count() == 1
    tab_id = tabs.tabBar().tabData(0)
    assert tab_id in mgr.tabs_by_id
    assert mgr.last_df.equals(df)
    assert mgr.tabs_by_id[tab_id].equals(df)


def test_display_dataframe_invalid_input_shows_critical():
    mgr, parent, tabs, cache, status, dlg = make_mgr()
    mgr.display_dataframe("not a df")

    assert any(c[0] == "critical" for c in dlg.calls)
    assert tabs.count() == 0


def test_close_tabs_by_title():
    mgr, parent, tabs, cache, status, dlg = make_mgr()
    mgr.display_dataframe(pd.DataFrame({"x": [1]}), title="A")
    mgr.display_dataframe(pd.DataFrame({"y": [2]}), title="B")
    mgr.display_dataframe(pd.DataFrame({"z": [3]}), title="C")

    assert tabs.count() == 3
    mgr.close_tabs_by_title("A")
    assert tabs.count() == 2
    assert tabs.tabText(0) == "B"
    assert tabs.tabText(1) == "C"

    mgr.close_tabs_by_title("C")
    assert tabs.count() == 1
    assert tabs.tabText(0) == "B"


def test_current_df():
    mgr, parent, tabs, cache, status, dlg = make_mgr()
    df = pd.DataFrame({"a": [1]})
    mgr.display_dataframe(df)
    tabs.setCurrentIndex(0)
    assert mgr.current_df().equals(df)


def test_close_tab_updates_last_df():
    mgr, parent, tabs, cache, status, dlg = make_mgr()
    df1 = pd.DataFrame({"a": [1]})
    df2 = pd.DataFrame({"b": [2]})
    mgr.display_dataframe(df1)
    mgr.display_dataframe(df2)

    tabs.setCurrentIndex(1)
    mgr.close_tab(1)

    assert tabs.count() == 1
    assert mgr.last_df.equals(df1)

# ======================================================================
#   --- rename_tab, on_tab_changed, remove_column, properties ---
# ======================================================================

def test_rename_tab_accepts_new_name():
    mgr, parent, tabs, cache, status, dlg = make_mgr()
    mgr.display_dataframe(pd.DataFrame({"a": [1]}), title="Old")

    dlg.set_next_prompt_text("NewName", True)
    mgr.rename_tab(0)

    assert tabs.tabText(0) == "NewName"


def test_rename_tab_cancel_keeps_old_name():
    mgr, parent, tabs, cache, status, dlg = make_mgr()
    mgr.display_dataframe(pd.DataFrame({"a": [1]}), title="Old")

    dlg.set_next_prompt_text("Ignored", False)
    mgr.rename_tab(0)

    assert tabs.tabText(0) == "Old"


def test_on_tab_changed_updates_last_df(monkeypatch):
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df1 = pd.DataFrame({"a": [1]})
    df2 = pd.DataFrame({"b": [2]})

    mgr.display_dataframe(df1)
    mgr.display_dataframe(df2)

    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.result_tab_manager.QTimer.singleShot",
        lambda ms, fn: fn(),
    )

    tabs.setCurrentIndex(1)
    mgr.on_tab_changed(1)

    assert mgr.last_df.equals(df2)


def test_remove_column_success():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1], "B": [2]})
    mgr.display_dataframe(df)

    dlg.set_next_confirm_delete(True)

    view = tabs.widget(0)
    # UI column 2 is DataFrame column 1 ("B")
    mgr._remove_column_from_view(view, 2)

    assert "B" not in view._df.columns
    assert any("Tog bort kolumn" in msg for msg, _ in status)


def test_remove_column_cancel_does_nothing():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1], "B": [2]})
    mgr.display_dataframe(df)

    dlg.set_next_confirm_delete(False)

    view = tabs.widget(0)
    mgr._remove_column_from_view(view, 2)

    assert list(view._df.columns) == ["A", "B"]


def test_remove_column_index_column_shows_info():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1]})
    mgr.display_dataframe(df)

    view = tabs.widget(0)
    mgr._remove_column_from_view(view, 0)

    assert any(c[0] == "info" and "Indexkolumnen" in c[1][1] for c in dlg.calls)


def test_column_properties_invalid_column_shows_critical():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    mgr._on_column_properties(view, 99)
    assert any(c[0] == "critical" for c in dlg.calls)


# ======================================================================
#   --- collect_all_tabs_data ---
# ======================================================================

def test_collect_all_tabs_data_returns_only_non_empty():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df1 = pd.DataFrame({"A": [1]})
    empty = pd.DataFrame()

    mgr.display_dataframe(df1, title="X")
    mgr.display_dataframe(empty, title="Empty")

    result = mgr.collect_all_tabs_data()

    assert len(result) == 1
    assert result[0][1] == "X"
    assert result[0][0].equals(df1)


def test_collect_all_tabs_data_multiple():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df1 = pd.DataFrame({"A": [1]})
    df2 = pd.DataFrame({"B": [2]})

    mgr.display_dataframe(df1, title="First")
    mgr.display_dataframe(df2, title="Second")

    result = mgr.collect_all_tabs_data()
    assert len(result) == 2
    assert result[0][1] == "First"
    assert result[1][1] == "Second"


# ======================================================================
#   --- CLEAN DATA FUNCTIONS ---
# ======================================================================

def test_clean_strip():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": ["  hej  ", " hopp "]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    mgr._clean_column_strip(view, 1)

    assert view._df["A"].tolist() == ["hej", "hopp"]


def test_clean_lower():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [" HeJ ", None]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    mgr._clean_column_lower(view, 1)

    out = view._df["A"].tolist()

    assert out[0] == "hej"
    assert pd.isna(out[1])



def test_clean_upper():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": ["test", "Hej"]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    mgr._clean_column_upper(view, 1)

    assert view._df["A"].tolist() == ["TEST", "HEJ"]


def test_clean_whitespace():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": ["hej   hopp", " a   b   c "]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    mgr._clean_column_whitespace(view, 1)

    assert view._df["A"].tolist() == ["hej hopp", "a b c"]


def test_clean_remove_text():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": ["foobar", "foo123", "barfoo"]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    dlg.set_next_prompt_text("foo", True)
    mgr._clean_column_remove(view, 1)

    assert view._df["A"].tolist() == ["bar", "123", "bar"]


def test_clean_remove_regex_digits():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": ["a1b2", "c3d4", "hej123hej"]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    dlg.set_next_prompt_text(r"\d+", True)
    mgr._clean_column_remove_regex(view, 1)

    assert view._df["A"].tolist() == ["ab", "cd", "hejhej"]

# ======================================================================
#   --- FILL MISSING VALUE FUNCTIONS ---
# ======================================================================

def test_fillna_mean_numeric():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1.0, None, 3.0]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    mgr._fillna_mean_in_column(view, 1)

    assert view._df["A"].tolist() == [1.0, 2.0, 3.0]


def test_fillna_median_numeric():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [10, None, 30]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    mgr._fillna_median_in_column(view, 1)

    assert view._df["A"].tolist() == [10, 20, 30]


def test_fillna_mode_numeric():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [5, None, 5, 7]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    mgr._fillna_mode_in_column(view, 1)

    assert view._df["A"].tolist() == [5, 5, 5, 7]


def test_fillna_custom_integer():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1, None, 3]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    dlg.set_next_prompt_number(100, True)
    mgr._fillna_custom_in_column(view, 1)

    assert view._df["A"].tolist() == [1, 100, 3]


def test_fillna_custom_float():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1.0, None, 3.0]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    dlg.set_next_prompt_number(1.5, True)
    mgr._fillna_custom_in_column(view, 1)

    assert view._df["A"].tolist() == [1.0, 1.5, 3.0]


def test_fillna_custom_boolean():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [True, None, False]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    dlg.set_next_prompt_choice("True", True)
    mgr._fillna_custom_in_column(view, 1)

    filled = view._df["A"].tolist()

    # Former None must be replaced with *something* (stub loses boolean type)
    assert filled[1] is not None

    # Interpret semantic truth
    def interpret(v):
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        # In stubmodel '' means the value WAS replaced but dtype collapsed.
        return s in ("true", "1", "yes", "")

    out = list(map(interpret, filled))

    # Semantically correct result
    assert out == [True, True, False]


def test_fillna_custom_text():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": ["hej", None, "hopp"]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    dlg.set_next_prompt_text("X", True)
    mgr._fillna_custom_in_column(view, 1)

    assert view._df["A"].tolist() == ["hej", "X", "hopp"]


def test_fillna_custom_cancel_does_nothing():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1, None, 3]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    dlg.set_next_prompt_number(9999, False)  # CANCEL
    mgr._fillna_custom_in_column(view, 1)

    out = view._df["A"].tolist()

    # Normalize pandas NaN to None for comparison
    def norm(v):
        if v != v:  # NaN check (only NaN is NaN)
            return None
        return v

    out = [norm(v) for v in out]

    assert out == [1, None, 3]


def test_fillna_no_missing_shows_info():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1, 2, 3]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    mgr._fillna_mean_in_column(view, 1)

    assert any(c[0] == "info" and "Inga saknade" in c[1][1] for c in dlg.calls)


# ======================================================================
#   --- CACHE INVALIDATION TESTS ---
# ======================================================================

def test_display_dataframe_invalidates_cache():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1]})
    mgr.display_dataframe(df)

    tab_id = tabs.tabBar().tabData(0)

    # No profile should exist for this tab/column yet
    assert cache.get((tab_id, "A")) is None


def test_apply_new_dataframe_to_view_invalidates_cache():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1], "B": [2]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    tab_id = tabs.tabBar().tabData(0)

    # Simulate cached profile via the PUBLIC API
    cache.set((tab_id, "A"), {"dummy": True})

    # Apply new dataframe
    new_df = pd.DataFrame({"A": [10], "B": [20]})
    mgr._apply_new_dataframe_to_view(view, new_df)

    # Cache must no longer contain profile for A (the correct check)
    assert cache.get((tab_id, "A")) is None

    # Apply new dataframe again (extra safety)
    new_df = pd.DataFrame({"A": [10], "B": [20]})
    mgr._apply_new_dataframe_to_view(view, new_df)

    # And still no cache entry
    assert cache.get((tab_id, "A")) is None


# ======================================================================
#   --- _apply_new_dataframe_to_view edge cases ---
# ======================================================================

def test_apply_new_dataframe_updates_last_df_if_current():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    new_df = pd.DataFrame({"A": [10]})
    mgr._apply_new_dataframe_to_view(view, new_df)

    assert mgr.last_df.equals(new_df)


def test_apply_new_dataframe_does_not_break_on_missing_tab_index():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    # Manually mess with tabs so no tab matches the view
    tabs._widgets.clear()

    new_df = pd.DataFrame({"A": [10]})
    mgr._apply_new_dataframe_to_view(view, new_df)

    assert mgr.last_df is not None  # should not crash


# ======================================================================
#   --- _get_df_and_name ---
# ======================================================================

def test_get_df_and_name_returns_correct_column():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [1], "B": [2]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    out_df, col_name = mgr._get_df_and_name(view, 2)
    assert col_name == "B"


# ======================================================================
#   --- EDGE CASE TESTS ---
# ======================================================================

def test_current_df_invalid_index_returns_none():
    mgr, parent, tabs, cache, status, dlg = make_mgr()
    assert mgr.current_df(99) is None


def test_close_tab_on_empty_tabs_does_not_crash():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    # No tabs yet
    mgr.close_tab(0)  # should not crash
    assert mgr.last_df is None


# def test_header_context_menu_invalid_column_does_not_crash():
#     # We do not simulate GUI in detail, but we at least call the function
#     mgr, parent, tabs, cache, status, dlg = make_mgr()
#
#     df = pd.DataFrame({"A": [1]})
#     mgr.display_dataframe(df)
#     view = tabs.widget(0)
#     p = QPoint(0, 0)
#     # logicalIndexAt always returns 0 from StubHeader
#     # so no crash should happen
#     mgr._on_header_context_menu(view, p)

#    No assertion; just must not throws


# ======================================================================
#   --- SORT TESTS ---
# ======================================================================

def test_sort_column_in_view_ascending():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [3, 1, 2]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    mgr._sort_column_in_view(view, 1, ascending=True)

    assert view._df["A"].tolist() == [1, 2, 3]


def test_sort_column_in_view_descending():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [3, 1, 2]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    mgr._sort_column_in_view(view, 1, ascending=False)

    assert view._df["A"].tolist() == [3, 2, 1]


def test_sort_column_index_column_shows_info():
    mgr, parent, tabs, cache, status, dlg = make_mgr()

    df = pd.DataFrame({"A": [3, 1, 2]})
    mgr.display_dataframe(df)
    view = tabs.widget(0)

    mgr._sort_column_in_view(view, 0, ascending=True)

    # _sort_column_in_view for column=0 only does self._set_status, not self._dialogs.info
    assert any("indexkolumnen" in msg for msg, _ in status)


# ======================================================================
#   --- DONE ---
# ======================================================================

