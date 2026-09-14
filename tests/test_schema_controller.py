# tests/test_schema_controller.py
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from gui.dialogs.service.dialog_service import NullDialogService
from expo_jbm329.workbench.controllers.schema_controller import SchemaController
from tests.qt_stubs import StubTree, StubTreeItem
from tests.stubs import DummyIconService, DummyJobManager, DummyStatusLogger

# ---- Patchar: QTreeWidgetItem, SQL-builders, list_columns ----


@pytest.fixture(autouse=True)
def patch_qtreewidgetitem(monkeypatch):
    from expo_jbm329.workbench.controllers import schema_controller as sc
    monkeypatch.setattr(sc, "QTreeWidgetItem", StubTreeItem)

def stub_build_select_star(conn, schema, name, top_n):
    return f"SELECT_TOP_STAR {schema}.{name} (TOP {top_n})"

def stub_build_select_cols(conn, schema, name, top_n, with_schema):
    suf = "WITH_SCHEMA" if with_schema else "NO_SCHEMA"
    return f"SELECT_TOP_COLS_{suf} {schema}.{name} (TOP {top_n})"

@pytest.fixture(autouse=True)
def patch_sql_builders(monkeypatch):
    monkeypatch.setattr("expo_jbm329.workbench.controllers.schema_controller.build_select_star", stub_build_select_star)
    monkeypatch.setattr("expo_jbm329.workbench.controllers.schema_controller.build_select_columns_auto", stub_build_select_cols)

@pytest.fixture(autouse=True)
def patch_list_columns(monkeypatch):
    # Grundläge: inga kolumner → testa fallback/cachen per test
    monkeypatch.setattr("expo_jbm329.workbench.controllers.schema_controller.list_columns", lambda conn, s, t: [])

# ---- SchemaMgr-stub ----

class StubSchemaEntry:
    def __init__(self):
        self.db_name = "TestDB"
        self.tables = [{"schema": "dbo", "name": "Tbl"}]
        self.views  = [{"schema": "dbo", "name": "View1"}]
        self.columns = {}
        self.loaded_at = "now"

class StubSchemaMgr:
    def __init__(self):
        self.entry = StubSchemaEntry()
    def load_schema(self, conn, force_refresh=False): return self.entry
    def prefetch_columns_async(self, conn): pass
    def get_cache_for(self, conn): return self.entry

# ---- Fabrik ----

def make_ctrl():
    parent = QWidget()
    tree = StubTree()
    schema_mgr = StubSchemaMgr()
    job_mgr = DummyJobManager()

    inserted_sql, autocomplete_data = [], []
    status_rec = DummyStatusLogger()
    
    insert_sql = lambda sql: inserted_sql.append(sql)
    get_conn = lambda: "Conn1"
    set_auto = lambda d: autocomplete_data.append(d)
    restore  = lambda: status_rec.set_status("RESTORE", None)

    icon_svc = DummyIconService()
    dlg = NullDialogService()
    fmt_int = lambda x: f"{x:,}".replace(",", " ")

    ctrl = SchemaController(
        parent_widget=parent,
        tree_widget=tree,
        schema_mgr=schema_mgr,
        job_mgr=job_mgr,
        insert_sql=insert_sql,
        set_status=status_rec.set_status,
        icon_service=icon_svc,
        get_conn_name=get_conn,
        set_autocomplete_schema=set_auto,
        restore_baseline_status=restore,
        dialogs=dlg,
        fmt_int=fmt_int
    )
    return ctrl, tree, schema_mgr, inserted_sql, status_rec, autocomplete_data, dlg

# ---- Tester ----

def test_load_schema_success():
    ctrl, tree, schema_mgr, inserted, status_rec, auto, dlg = make_ctrl()
    ctrl.load_schema_tree("Conn1")
    assert tree.top, "Root item was not created"
    assert auto, "Autocomplete was not rebuilt"
    assert ("Schema klart", 4000) in status_rec.messages

def test_load_schema_failure(monkeypatch):
    ctrl, tree, schema_mgr, inserted, status_rec, auto, dlg = make_ctrl()
    monkeypatch.setattr(schema_mgr, "load_schema", lambda conn, force_refresh=False: (_ for _ in ()).throw(Exception("fail!")))
    ctrl.load_schema_tree("Conn1")
    assert any(c[0] == "critical" for c in dlg.calls)
    assert any("Misslyckades" in msg for msg, _ in status_rec.messages)

def test_item_expanded_loads_columns_from_cache():
    ctrl, tree, schema_mgr, inserted, status_rec, auto, dlg = make_ctrl()
    schema_mgr.entry.columns = {("dbo", "Tbl"): [
        {"COLUMN_NAME": "A", "DATA_TYPE": "int", "IS_NULLABLE": "YES"},
        {"COLUMN_NAME": "B", "DATA_TYPE": "text", "IS_NULLABLE": "NO"},
    ]}
    ctrl.load_schema_tree("Conn1")
    tbl_item = tree.top[0].child(0).child(0)
    ctrl._on_item_expanded(tbl_item)
    assert tbl_item.childCount() == 2
    assert [tbl_item.child(i).data(0, Qt.ItemDataRole.UserRole)["column"] for i in range(2)] == ["A", "B"]

def test_item_expanded_with_db_fallback(monkeypatch):
    ctrl, tree, schema_mgr, inserted, status_rec, auto, dlg = make_ctrl()
    monkeypatch.setattr("expo_jbm329.workbench.controllers.schema_controller.list_columns",
                        lambda conn, s, t: [{"COLUMN_NAME": "X", "DATA_TYPE": "int", "IS_NULLABLE": "YES"}])
    ctrl.load_schema_tree("Conn1")
    tbl_item = tree.top[0].child(0).child(0)
    ctrl._on_item_expanded(tbl_item)
    assert tbl_item.childCount() == 1
    assert tbl_item.child(0).data(0, Qt.ItemDataRole.UserRole)["column"] == "X"

def test_double_click_column_inserts_brackets():
    ctrl, tree, schema_mgr, inserted, status_rec, auto, dlg = make_ctrl()
    # Ge expanderingen kolumner
    schema_mgr.entry.columns = {("dbo", "Tbl"): [{"COLUMN_NAME": "A", "DATA_TYPE": "int", "IS_NULLABLE": "YES"}]}
    ctrl.load_schema_tree("Conn1")
    tbl_item = tree.top[0].child(0).child(0)
    ctrl._on_item_expanded(tbl_item)
    col_item = tbl_item.child(0)
    ctrl._on_item_double_clicked(col_item)
    assert inserted[-1] == "[A]"

def test_double_click_table_inserts_select():
    ctrl, tree, schema_mgr, inserted, status_rec, auto, dlg = make_ctrl()
    ctrl.load_schema_tree("Conn1")
    tbl_item = tree.top[0].child(0).child(0)
    ctrl._on_item_double_clicked(tbl_item)
    assert "SELECT_TOP_COLS_NO_SCHEMA" in inserted[-1]
    assert "(TOP 1000)" in inserted[-1]

def test_context_menu_star():
    ctrl, tree, schema_mgr, inserted, status_rec, auto, dlg = make_ctrl()
    ctrl.load_schema_tree("Conn1")
    # Vi hoppar över menyn i sig och verifierar select-funktionen direkt
    meta = tree.top[0].child(0).child(0).data(0, Qt.ItemDataRole.UserRole)
    ctrl._insert_select_star(meta)
    assert "SELECT_TOP_STAR" in inserted[-1]
    assert "(TOP 1000)" in inserted[-1]

def test_reload_settings():
    ctrl, tree, schema_mgr, inserted, status_rec, auto, dlg = make_ctrl()
    ctrl.reload_settings({"workbench": {"gen_top_n": 500}})
    assert ctrl._gen_top_n == 500

    # Verify it affects SQL generation
    ctrl.load_schema_tree("Conn1")
    tbl_item = tree.top[0].child(0).child(0)
    ctrl._on_item_double_clicked(tbl_item)
    assert "(TOP 500)" in inserted[-1]

def test_update_icons(monkeypatch):
    ctrl, tree, schema_mgr, inserted, status_rec, auto, dlg = make_ctrl()
    ctrl.load_schema_tree("Conn1")

    # We'll just verify it doesn't crash and calls get on icon_service
    icon_svc = ctrl._icon_service
    original_get = icon_svc.get
    called_names = []

    def mock_get(name):
        called_names.append(name)
        return original_get(name)

    monkeypatch.setattr(icon_svc, "get", mock_get)
    ctrl.update_icons()

    assert "database" in called_names
    assert "folder" in called_names
    assert "table" in called_names

def test_rebuild_autocomplete_empty_cache(monkeypatch):
    ctrl, tree, schema_mgr, inserted, status, auto, dlg = make_ctrl()
    monkeypatch.setattr(schema_mgr, "get_cache_for", lambda c: None)
    ctrl.rebuild_autocomplete("Conn1")
    assert auto[-1] == {}

def test_on_schema_progress(monkeypatch):
    ctrl, tree, schema_mgr, inserted, status_rec, auto, dlg = make_ctrl()
    called = []
    monkeypatch.setattr("expo_jbm329.workbench.controllers.schema_controller.ui_invoke",
                        lambda fn, *a: called.append(("invoke", fn.__name__, a)))
    ctrl.on_schema_progress(3, 10)
    assert called and called[0][1] == "_on_schema_progress_ui"
    assert called[0][2] == (3, 10)
