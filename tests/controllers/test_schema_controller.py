from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import duckdb
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QTreeWidgetItem, QWidget

from expo_jbm329.db import base
from expo_jbm329.db.dialects.duckdb import DuckDbDialect
from expo_jbm329.db.dialects.mssql import MssqlDialect
from expo_jbm329.db.dialects.mysql import MySqlDialect
from expo_jbm329.db.dialects.postgres import PostgresDialect
from expo_jbm329.db.dialects.sqlite import SqliteDialect
from expo_jbm329.utils.format_utils import fmt_int
from expo_jbm329.workbench.controllers.schema_controller import SchemaController
from tests.qt_stubs import StubTree


class StubIconService:
    def __init__(self):
        self.calls = []

    def get(self, icon_id):
        self.calls.append(icon_id)
        return QIcon()


class StubSchemaEntry:
    def __init__(self):
        self.db_name = "TestDB"
        self.tables = [{"schema": "dbo", "name": "Tbl"}]
        self.views = [{"schema": "dbo", "name": "View1"}]
        self.columns = {("dbo", "Tbl"): [{"COLUMN_NAME": "A", "DATA_TYPE": "int", "IS_NULLABLE": "YES"}]}


class StubSchemaMgr:
    def __init__(self):
        self.entry = StubSchemaEntry()
        self.progress_cb = None
        self.runner = None

    def load_schema(self, conn, force_refresh=False, corr_id=None):
        return self.entry

    def prefetch_columns_async(self, conn, corr_id=None):
        return None

    def get_cache_for(self, conn):
        return self.entry

    def set_job_runner(self, fn):
        self.runner = fn


class DummyAsyncOps:
    def run_operation(self, **kwargs):
        return SimpleNamespace()


class DummyJobMgr:
    def cancel_scope(self, scope):
        return None


def make_ctrl(resolve_dialect=None):
    tree = StubTree()
    schema_mgr = StubSchemaMgr()
    status_msgs: list[tuple[str, int | None]] = []
    inserted_sql: list[str] = []
    dialogs = SimpleNamespace(critical=MagicMock())
    connect_connection = MagicMock()
    disconnect_connection = MagicMock()
    restore_baseline_status = MagicMock()

    ctrl = SchemaController(
        parent_widget=QWidget(),
        tree_widget=tree,
        schema_mgr=schema_mgr,
        async_ops=DummyAsyncOps(),
        job_mgr=DummyJobMgr(),
        create_tab_for_connection=lambda name: SimpleNamespace(name=name),
        insert_sql_into_tab=lambda tab, sql: inserted_sql.append(sql),
        set_status=lambda msg, timeout: status_msgs.append((msg, timeout)),
        icon_service=StubIconService(),
        get_current_connection=lambda: "Conn1",
        connect_connection=connect_connection,
        disconnect_connection=disconnect_connection,
        restore_baseline_status=restore_baseline_status,
        dialogs=dialogs,
        resolve_dialect=resolve_dialect or (lambda _conn: MssqlDialect()),
    )
    return ctrl, tree, schema_mgr, inserted_sql, status_msgs, dialogs, connect_connection, disconnect_connection


def test_schema_error_and_progress_use_explicit_formatting_context(monkeypatch):
    from expo_jbm329.utils.i18n_utils import translate_fmt
    from expo_jbm329.workbench.controllers import schema_controller

    ctrl, _, _, _, status, dialogs, _, _ = make_ctrl()
    formatter = MagicMock(wraps=translate_fmt)
    monkeypatch.setattr(schema_controller, "translate_fmt", formatter)
    monkeypatch.setattr(SchemaController, "_reset_connection_state", lambda _self, _connection: None)

    ctrl._handle_schema_error(ValueError("failure {literal} %1"), "Conn1", "Failed")
    assert dialogs.critical.call_args.kwargs["text"] == "Could not load schema. \n\nfailure {literal} %1"
    ctrl._on_schema_progress_ui(2, 5)
    assert status[-1] == ("Preloading schema… 2/5", 1500)
    assert [call.args[0] for call in formatter.call_args_list] == ["SchemaController", "SchemaController"]
    assert not hasattr(SchemaController, "_tr_fmt")


def test_refresh_connections_builds_tree():
    ctrl, tree, *_ = make_ctrl()

    ctrl.refresh_connections(["Conn1"])

    assert tree.topLevelItemCount() == 1
    item = tree.topLevelItem(0)
    assert item.text(0) == "Conn1"


def test_load_schema_tree_builds_schema_nodes():
    ctrl, tree, schema_mgr, inserted_sql, status_msgs, dialogs, *_ = make_ctrl()

    ctrl.refresh_connections(["Conn1"])
    ctrl.load_schema_tree("Conn1")

    root = tree.topLevelItem(0)
    db_item = root.child(0)
    assert db_item.text(0) == "TestDB"
    assert db_item.childCount() == 2
    assert status_msgs[-1][0] == "Finished loading schema"


def test_item_expanded_uses_cache():
    ctrl, tree, schema_mgr, inserted_sql, status_msgs, dialogs, *_ = make_ctrl()

    ctrl.refresh_connections(["Conn1"])
    ctrl.load_schema_tree("Conn1")
    tbl_item = tree.topLevelItem(0).child(0).child(0).child(0)

    ctrl._on_item_expanded(tbl_item)

    assert tbl_item.childCount() == 1
    child = tbl_item.child(0)
    assert child.data(0, Qt.ItemDataRole.UserRole)["type"] == "column"


def test_double_click_table_inserts_select(monkeypatch):
    # No connection config -> service init fails -> dialect-aware ANSI fallback.
    monkeypatch.setattr("expo_jbm329.db.base.read_connections", dict)
    ctrl, tree, schema_mgr, inserted_sql, *_ = make_ctrl()

    ctrl.refresh_connections(["Conn1"])
    ctrl.load_schema_tree("Conn1")
    tbl_item = tree.topLevelItem(0).child(0).child(0).child(0)

    ctrl._on_item_double_clicked(tbl_item)

    assert inserted_sql
    assert inserted_sql[0] == 'SELECT * FROM "dbo"."Tbl"'


def test_insert_select_columns_uses_single_indent_for_projected_columns(monkeypatch):
    ctrl, tree, schema_mgr, inserted_sql, *_ = make_ctrl()
    ctrl.refresh_connections(["Conn1"])
    ctrl.load_schema_tree("Conn1")
    tbl_item = tree.topLevelItem(0).child(0).child(0).child(0)

    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.schema_controller.build_select_columns_auto",
        lambda *args, **kwargs: "SELECT\n    [A],\n    [B]\nFROM [dbo].[Tbl];",
    )

    ctrl._insert_select_columns(
        tbl_item,
        {"schema": "dbo", "name": "Tbl", "type": "table"},
        with_schema=False,
    )

    assert inserted_sql == ["SELECT\n    [A],\n    [B]\nFROM [dbo].[Tbl];"]


def test_reload_settings_updates_top_n():
    ctrl, *_ = make_ctrl()

    ctrl.reload_settings({"workbench": {"gen_top_n": 500}})

    assert ctrl._gen_top_n == 500


def _loaded_table_item(ctrl, tree):
    ctrl.refresh_connections(["Conn1"])
    ctrl.load_schema_tree("Conn1")
    return tree.topLevelItem(0).child(0).child(0).child(0)


def test_init_registers_drag_text_provider():
    ctrl, tree, *_ = make_ctrl()

    assert tree.drag_text_provider == ctrl.build_drag_text


@pytest.mark.parametrize(
    ("dialect", "expected_table", "expected_column"),
    [
        (MssqlDialect(), "[dbo].[Tbl]", "[dbo].[Tbl].[A]"),
        (MySqlDialect(), "`dbo`.`Tbl`", "`dbo`.`Tbl`.`A`"),
        (PostgresDialect(), '"dbo"."Tbl"', '"dbo"."Tbl"."A"'),
        (SqliteDialect(), '"dbo"."Tbl"', '"dbo"."Tbl"."A"'),
        (DuckDbDialect(), '"dbo"."Tbl"', '"dbo"."Tbl"."A"'),
    ],
)
def test_build_drag_text_uses_connection_dialect(dialect, expected_table, expected_column):
    resolved = []

    def resolve(conn):
        resolved.append(conn)
        return dialect

    ctrl, tree, *_ = make_ctrl(resolve_dialect=resolve)
    tbl_item = _loaded_table_item(ctrl, tree)
    ctrl._on_item_expanded(tbl_item)
    col_item = tbl_item.child(0)

    assert ctrl.build_drag_text([tbl_item]) == expected_table
    assert ctrl.build_drag_text([col_item]) == expected_column
    assert set(resolved) == {"Conn1"}


def test_build_drag_text_groups_items_per_connection():
    dialects = {"Conn1": MssqlDialect(), "Conn2": MySqlDialect()}
    ctrl, tree, *_ = make_ctrl(resolve_dialect=dialects.__getitem__)
    ctrl.refresh_connections(["Conn1", "Conn2"])
    ctrl.load_schema_tree("Conn1")
    ctrl.load_schema_tree("Conn2")
    item1 = tree.topLevelItem(0).child(0).child(0).child(0)
    item2 = tree.topLevelItem(1).child(0).child(0).child(0)

    assert ctrl.build_drag_text([item1, item2]) == "[dbo].[Tbl]\n`dbo`.`Tbl`"


def test_build_drag_text_without_connection_uses_ansi():
    ctrl, *_ = make_ctrl()
    orphan = QTreeWidgetItem(["dbo.T"])
    orphan.setData(0, Qt.ItemDataRole.UserRole, {"type": "table", "schema": "dbo", "name": "T"})

    assert ctrl.build_drag_text([orphan]) == '"dbo"."T"'


@pytest.mark.parametrize(
    ("dialect", "top_n", "expected"),
    [
        (MssqlDialect(), 500, ("SELECT * TOP 500", "SELECT TOP 500", "SELECT TOP 500 (schema)")),
        (MySqlDialect(), 500, ("SELECT * LIMIT 500", "SELECT LIMIT 500", "SELECT LIMIT 500 (schema)")),
        (
            PostgresDialect(),
            2000,
            (
                f"SELECT * LIMIT {fmt_int(2000)}",
                f"SELECT LIMIT {fmt_int(2000)}",
                f"SELECT LIMIT {fmt_int(2000)} (schema)",
            ),
        ),
        (PostgresDialect(), 1000, ("SELECT * LIMIT 1000", "SELECT LIMIT 1000", "SELECT LIMIT 1000 (schema)")),
        (PostgresDialect(), 500, ("SELECT * LIMIT 500", "SELECT LIMIT 500", "SELECT LIMIT 500 (schema)")),
        (SqliteDialect(), 0, ("SELECT *", "SELECT", "SELECT (schema)")),
        (DuckDbDialect(), 500, ("SELECT * LIMIT 500", "SELECT LIMIT 500", "SELECT LIMIT 500 (schema)")),
    ],
)
def test_select_menu_labels_are_dialect_aware(dialect, top_n, expected):
    ctrl, *_ = make_ctrl()
    ctrl.reload_settings({"workbench": {"gen_top_n": top_n}})

    assert ctrl._select_menu_labels(dialect) == expected


@pytest.mark.parametrize("dialect", [PostgresDialect(), DuckDbDialect()])
def test_ansi_table_double_click_and_context_menu_queries(monkeypatch, dialect):
    ctrl, tree, schema_mgr, inserted_sql, *_ = make_ctrl(resolve_dialect=lambda _conn: dialect)
    ctrl.refresh_connections(["Conn1"])
    ctrl.load_schema_tree("Conn1")
    tbl_item = tree.topLevelItem(0).child(0).child(0).child(0)

    meta = {"schema": "public", "name": "users", "type": "table"}
    tbl_item.setData(0, Qt.ItemDataRole.UserRole, meta)

    # Mock build_select_columns_auto to simulate DB metadata returned for PostgreSQL
    def _mock_build_select(conn, schema, name, top_n=None, with_schema=False, corr_id=None):
        cols = ['"public"."users"."id"', '"public"."users"."name"'] if with_schema else ['"id"', '"name"']
        indent = "    "
        proj = f",\n{indent}".join(cols)
        limit_str = f" LIMIT {top_n}" if top_n else ""
        return f'SELECT\n{indent}{proj}\nFROM "{schema}"."{name}"{limit_str};'

    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.schema_controller.build_select_columns_auto",
        _mock_build_select,
    )
    monkeypatch.setattr(
        "expo_jbm329.workbench.controllers.schema_controller.build_select_star",
        lambda conn, schema, name, top_n=None: (
            f'SELECT *\nFROM "{schema}"."{name}"' + (f" LIMIT {top_n}" if top_n else "") + ";"
        ),
    )

    # 1. Double-click table node (triggers SELECT columns without schema)
    ctrl._on_item_double_clicked(tbl_item)
    assert inserted_sql[-1] == 'SELECT\n    "id",\n    "name"\nFROM "public"."users" LIMIT 1000;'

    # 2. Context menu: SELECT * LIMIT 1,000
    ctrl._insert_select_star(tbl_item, meta)
    assert inserted_sql[-1] == 'SELECT *\nFROM "public"."users" LIMIT 1000;'

    # 3. Context menu: SELECT LIMIT 1,000 (columns without schema)
    ctrl._insert_select_columns(tbl_item, meta, with_schema=False)
    assert inserted_sql[-1] == 'SELECT\n    "id",\n    "name"\nFROM "public"."users" LIMIT 1000;'

    # 4. Context menu: SELECT LIMIT 1,000 (schema) (columns with schema)
    ctrl._insert_select_columns(tbl_item, meta, with_schema=True)
    assert inserted_sql[-1] == (
        'SELECT\n    "public"."users"."id",\n    "public"."users"."name"\nFROM "public"."users" LIMIT 1000;'
    )


def test_duckdb_drag_text_escapes_quoted_schema_table_and_column():
    ctrl, tree, *_ = make_ctrl(resolve_dialect=lambda _conn: DuckDbDialect())
    table = _loaded_table_item(ctrl, tree)
    table.setData(0, Qt.ItemDataRole.UserRole, {"type": "table", "schema": 'a"b', "name": "it's"})
    column = QTreeWidgetItem(table, ['c"d'])
    column.setData(0, Qt.ItemDataRole.UserRole, {"type": "column", "schema": 'a"b', "table": "it's", "column": 'c"d'})
    assert ctrl.build_drag_text([table]) == '"a""b"."it\'s"'
    assert ctrl.build_drag_text([column]) == '"a""b"."it\'s"."c""d"'


def test_duckdb_schema_actions_generate_executable_queries(tmp_path, monkeypatch):
    path = tmp_path / "schema-actions.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute("""
            CREATE SCHEMA "s""q";
            CREATE TABLE "s""q"."o'x" ("c""q" INTEGER);
            INSERT INTO "s""q"."o'x" VALUES (7), (7), (7);
        """)
    monkeypatch.setattr(base, "read_connections", lambda: {"Conn1": {"db_type": "duckdb", "database": str(path)}})
    try:
        ctrl, tree, manager, inserted_sql, *_ = make_ctrl(resolve_dialect=lambda _conn: DuckDbDialect())
        ctrl.reload_settings({"workbench": {"gen_top_n": 2}})
        manager.entry.tables = base.list_tables("Conn1")
        manager.entry.views = []
        manager.entry.columns = base.list_all_columns_map("Conn1")
        table = _loaded_table_item(ctrl, tree)
        meta = table.data(0, Qt.ItemDataRole.UserRole)
        ctrl._on_item_double_clicked(table)
        ctrl._insert_select_star(table, meta)
        ctrl._insert_select_columns(table, meta, with_schema=True)
        ctrl._on_item_expanded(table)
        ctrl._on_item_double_clicked(table.child(0))

        assert len(inserted_sql) == 4
        for sql in inserted_sql:
            assert '"s""q"."o\'x"' in sql
            result = base.execute_sql_safe("Conn1", sql)
            assert result.ok
            assert list(result.data.columns) == ['c"q']
            assert result.data.iloc[:, 0].tolist() == ([7] if "DISTINCT" in sql else [7, 7])
        assert all("LIMIT 2" in sql for sql in inserted_sql[:3])
    finally:
        base.close_connection("Conn1")
