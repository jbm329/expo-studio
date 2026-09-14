from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from expo_jbm329.gui.dialogs.service.null_dialog_service import NullDialogService
from expo_jbm329.workbench.controllers.schema_controller import SchemaController
from tests.stubs import DummyAsyncOps, DummyIconService, DummyJobManager, DummyStatusLogger
from tests.qt_stubs import StubTree, StubTreeItem


class StubSchemaEntry:
    def __init__(self):
        self.db_name = "TestDB"
        self.tables = [{"schema": "dbo", "name": "Tbl"}]
        self.views = [{"schema": "dbo", "name": "View1"}]
        self.columns = {}
        self.loaded_at = "now"


class StubSchemaMgr:
    def __init__(self):
        self.entry = StubSchemaEntry()
        self.progress_cb = None
        self.job_runner = None

    def load_schema(self, conn, force_refresh=False, corr_id=None):
        return self.entry

    def prefetch_columns_async(self, conn, corr_id=None):
        return None

    def get_cache_for(self, conn):
        return self.entry

    def set_job_runner(self, fn):
        self.job_runner = fn


@pytest.fixture(autouse=True)
def patch_qtreewidgetitem(monkeypatch):
    import expo_jbm329.workbench.controllers.schema_controller as sc

    monkeypatch.setattr(sc, "QTreeWidgetItem", StubTreeItem)
    monkeypatch.setattr(sc, "build_select_star", lambda conn, schema, name, top_n: f"STAR {schema}.{name} {top_n}")
    monkeypatch.setattr(
        sc,
        "build_select_columns_auto",
        lambda conn, schema, name, top_n, with_schema: f"COLS {schema}.{name} {top_n} {with_schema}",
    )
    monkeypatch.setattr(sc, "list_columns", lambda conn, s, t: [])


def make_ctrl():
    parent = QWidget()
    tree = StubTree()
    schema_mgr = StubSchemaMgr()
    status_rec = DummyStatusLogger()
    inserted_sql: list[str] = []
    autocomplete_data: list[dict] = []

    ctrl = SchemaController(
        parent_widget=parent,
        tree_widget=tree,
        schema_mgr=schema_mgr,
        async_ops=DummyAsyncOps(),
        job_mgr=DummyJobManager(),
        create_tab_for_connection=lambda name: SimpleNamespace(name=name),
        insert_sql_into_tab=lambda tab, sql: inserted_sql.append(sql),
        set_status=status_rec.set_status,
        icon_service=DummyIconService(),
        get_current_connection=lambda: "Conn1",
        connect_connection=lambda name: None,
        disconnect_connection=lambda name: None,
        restore_baseline_status=lambda: status_rec.set_status("RESTORE", None),
        dialogs=NullDialogService(),
    )
    ctrl._set_autocomplete_schema = lambda data: autocomplete_data.append(data)
    return ctrl, tree, schema_mgr, inserted_sql, status_rec, autocomplete_data


def test_load_schema_success():
    ctrl, tree, schema_mgr, inserted, status_rec, auto = make_ctrl()
    ctrl.refresh_connections(["Conn1"])
    ctrl.load_schema_tree("Conn1")

    assert tree.top
    assert auto == []
    assert any("Finished loading schema" in msg for msg, _ in status_rec.messages)


def test_load_schema_failure(monkeypatch):
    ctrl, tree, schema_mgr, inserted, status_rec, auto = make_ctrl()
    monkeypatch.setattr(schema_mgr, "load_schema", lambda conn, force_refresh=False, corr_id=None: (_ for _ in ()).throw(Exception("fail!")))

    with pytest.raises(Exception):
        ctrl.load_schema_tree("Conn1")


def test_item_expanded_loads_columns_from_cache():
    ctrl, tree, schema_mgr, inserted, status_rec, auto = make_ctrl()
    schema_mgr.entry.columns = {
        ("dbo", "Tbl"): [
            {"COLUMN_NAME": "A", "DATA_TYPE": "int", "IS_NULLABLE": "YES"},
            {"COLUMN_NAME": "B", "DATA_TYPE": "text", "IS_NULLABLE": "NO"},
        ]
    }
    ctrl.refresh_connections(["Conn1"])
    ctrl.load_schema_tree("Conn1")
    tbl_item = tree.top[0].child(0).child(0)

    ctrl._on_item_expanded(tbl_item)

    assert tbl_item.childCount() == 2
    assert [tbl_item.child(i).data(0, Qt.ItemDataRole.UserRole)["column"] for i in range(2)] == ["A", "B"]


def test_double_click_table_inserts_select():
    ctrl, tree, schema_mgr, inserted, status_rec, auto = make_ctrl()
    ctrl.refresh_connections(["Conn1"])
    ctrl.load_schema_tree("Conn1")
    tbl_item = tree.top[0].child(0).child(0)

    ctrl._on_item_double_clicked(tbl_item)

    assert inserted


def test_reload_settings():
    ctrl, tree, schema_mgr, inserted, status_rec, auto = make_ctrl()
    ctrl.reload_settings({"workbench": {"gen_top_n": 500}})

    assert ctrl._gen_top_n == 500
