from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import duckdb
import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QTranslator
from PyQt6.QtWidgets import QListWidgetItem

from expo_jbm329.app.settings import connection_editor
from expo_jbm329.app.settings.config_store import read_connections, write_connections
from expo_jbm329.app.settings.connection_editor import ConnectionEditor
from expo_jbm329.db import base
from expo_jbm329.db.core.models import SqlError, SqlResult
from expo_jbm329.gui.dialogs.service.null_dialog_service import NullDialogService
from expo_jbm329.gui.dialogs.workflows.file.file_dialog_service import FileDialogService, OpenFileRequest
from expo_jbm329.i18n.language import Language
from expo_jbm329.services.schema_cache import SchemaCacheEntry, SchemaCacheManager
from expo_jbm329.workbench.controllers.connection_controller import ConnectionController
from expo_jbm329.workbench.workbench_services import WorkbenchServices


def make_editor() -> ConnectionEditor:
    editor = ConnectionEditor(dialogs=NullDialogService())
    editor.show()
    return editor


def test_postgres_selection_sets_defaults():
    editor = make_editor()

    protocols = [editor.protocol_combo.itemText(i) for i in range(editor.protocol_combo.count())]
    assert "psycopg" in protocols
    assert "psycopg2" not in protocols

    ix = editor.db_type_combo.findData("postgresql")
    assert ix >= 0
    editor.db_type_combo.setCurrentIndex(ix)

    assert editor.protocol_combo.currentText() == "psycopg"
    assert editor.port_edit.text() == "5432"


def test_protocol_psycopg_field_states():
    editor = make_editor()

    ix = editor.protocol_combo.findText("psycopg")
    assert ix >= 0
    editor.protocol_combo.setCurrentIndex(ix)

    assert editor.server_edit.isEnabled() is True
    assert editor.port_edit.isEnabled() is True
    assert editor.db_edit.isEnabled() is True
    assert editor.user_edit.isEnabled() is True
    assert editor.password_edit.isEnabled() is True
    assert editor.extra_edit.isEnabled() is True

    assert editor.sqlite_browse_btn.isEnabled() is False
    assert editor.driver_edit.isEnabled() is False
    assert editor.system_drivers.isEnabled() is False
    assert editor.btn_add_driver.isEnabled() is False
    assert editor.trusted_checkbox.isEnabled() is False


def test_gather_form_and_load_postgres_connection():
    editor = make_editor()

    db_ix = editor.db_type_combo.findData("postgresql")
    editor.db_type_combo.setCurrentIndex(db_ix)

    editor.server_edit.setText("pg.example.com")
    editor.port_edit.setText("5432")
    editor.db_edit.setText("mydb")
    editor.user_edit.setText("pguser")
    editor.password_edit.setText("secret")
    editor.extra_edit.setText('{"sslmode": "require"}')

    form_data = editor._gather_current_form()
    assert form_data["db_type"] == "postgresql"
    assert form_data["protocol"] == "psycopg"
    assert form_data["server"] == "pg.example.com"
    assert form_data["port"] == 5432
    assert form_data["database"] == "mydb"
    assert form_data["user"] == "pguser"
    assert form_data["password"] == "secret"
    assert form_data["extra"] == {"sslmode": "require"}


def test_selection_changed_populates_postgres_fields():
    editor = make_editor()
    editor.data = {
        "pg_conn": {
            "name": "pg_conn",
            "db_type": "postgresql",
            "protocol": "psycopg",
            "server": "localhost",
            "port": 5432,
            "database": "production",
            "user": "admin",
            "password": "pass",
            "extra": {"connect_timeout": 10},
        }
    }
    item = QListWidgetItem("pg_conn")
    editor.list_widget.addItem(item)
    editor.list_widget.setCurrentItem(item)

    assert editor.db_type_combo.currentData() == "postgresql"
    assert editor.protocol_combo.currentText() == "psycopg"
    assert editor.server_edit.text() == "localhost"
    assert editor.port_edit.text() == "5432"
    assert editor.db_edit.text() == "production"
    assert editor.user_edit.text() == "admin"
    assert editor.password_edit.text() == "pass"


def test_db_type_switching_updates_default_ports():
    editor = make_editor()

    # Switch to PostgreSQL -> 5432
    pg_ix = editor.db_type_combo.findData("postgresql")
    editor.db_type_combo.setCurrentIndex(pg_ix)
    assert editor.port_edit.text() == "5432"

    # Switch to MySQL -> 3306
    mysql_ix = editor.db_type_combo.findData("mysql")
    editor.db_type_combo.setCurrentIndex(mysql_ix)
    assert editor.port_edit.text() == "3306"

    # Switch to Oracle -> 1521
    oracle_ix = editor.db_type_combo.findData("oracle")
    editor.db_type_combo.setCurrentIndex(oracle_ix)
    assert editor.port_edit.text() == "1521"

    # Switch to SQL Server -> 1433
    mssql_ix = editor.db_type_combo.findData("mssql")
    editor.db_type_combo.setCurrentIndex(mssql_ix)
    assert editor.port_edit.text() == "1433"


def test_sqlite_and_other_clears_port():
    editor = make_editor()

    pg_ix = editor.db_type_combo.findData("postgresql")
    editor.db_type_combo.setCurrentIndex(pg_ix)
    assert editor.port_edit.text() == "5432"

    # SQLite clears port
    sqlite_ix = editor.db_type_combo.findData("sqlite")
    editor.db_type_combo.setCurrentIndex(sqlite_ix)
    assert editor.port_edit.text() == ""

    # Oracle sets 1521
    oracle_ix = editor.db_type_combo.findData("oracle")
    editor.db_type_combo.setCurrentIndex(oracle_ix)
    assert editor.port_edit.text() == "1521"

    # Other clears port
    other_ix = editor.db_type_combo.findData("other")
    editor.db_type_combo.setCurrentIndex(other_ix)
    assert editor.port_edit.text() == ""


def test_saved_connection_custom_port_preserved():
    editor = make_editor()
    editor.data = {
        "custom_pg": {
            "name": "custom_pg",
            "db_type": "postgresql",
            "protocol": "psycopg",
            "server": "localhost",
            "port": 5433,
            "database": "custom_db",
            "user": "admin",
            "password": "pass",
        },
        "custom_mssql": {
            "name": "custom_mssql",
            "db_type": "mssql",
            "protocol": "odbc",
            "server": "localhost",
            "port": 14333,
            "database": "custom_db",
            "user": "sa",
            "password": "pass",
        },
    }

    item1 = QListWidgetItem("custom_pg")
    item2 = QListWidgetItem("custom_mssql")
    editor.list_widget.addItem(item1)
    editor.list_widget.addItem(item2)

    editor.list_widget.setCurrentItem(item1)
    assert editor.db_type_combo.currentData() == "postgresql"
    assert editor.port_edit.text() == "5433"

    editor.list_widget.setCurrentItem(item2)
    assert editor.db_type_combo.currentData() == "mssql"
    assert editor.port_edit.text() == "14333"


def test_delete_connection_formats_confirmation(widget_language: str) -> None:
    dialogs = MagicMock(spec=NullDialogService)
    dialogs.prompt_yes_no.return_value = False
    editor = ConnectionEditor(dialogs=dialogs)
    name = "Database {name} %1"
    editor.list_widget.addItem(name)
    editor.list_widget.setCurrentRow(editor.list_widget.count() - 1)

    editor.delete_connection()

    expected = (
        f"Vill du radera anslutningen '{name}'?"
        if widget_language == "sv"
        else f"Do you want to delete the connection '{name}'?"
    )
    dialogs.prompt_yes_no.assert_called_once_with(
        parent=editor, title=editor.tr("Delete"), text=expected, informative=None, default_yes=False
    )
    assert editor.list_widget.currentItem().text() == name


@pytest.mark.parametrize("with_hint", [False, True])
def test_connection_failure_formats_error(
    monkeypatch: pytest.MonkeyPatch, widget_language: str, with_hint: bool
) -> None:
    dialogs = MagicMock(spec=NullDialogService)
    editor = ConnectionEditor(dialogs=dialogs)
    editor.list_widget.addItem("Test connection")
    editor.list_widget.setCurrentRow(editor.list_widget.count() - 1)
    error = "Database error {error} %1 %2"
    hint = "Hint {name} %1" if with_hint else None
    monkeypatch.setattr(connection_editor, "write_connections", MagicMock())
    execute = MagicMock(return_value=SqlResult(ok=False, error=SqlError("connection", None, error, hint)))
    monkeypatch.setattr(connection_editor, "execute_sql_safe", execute)

    editor.test_connection()

    message = f"{error}\n\n{hint}" if with_hint else error
    prefix = "Kunde inte ansluta." if widget_language == "sv" else "Could not connect."
    dialogs.critical.assert_called_once_with(
        parent=editor, title=editor.tr("Connection error"), text=f"{prefix}\n\n{message}"
    )
    execute.assert_called_once()


@pytest.fixture
def duckdb_path(tmp_path: Path) -> Path:
    path = tmp_path / "first.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute("CREATE TABLE first_table (id INTEGER); INSERT INTO first_table VALUES (1)")
    return path


@pytest.fixture
def database_file_dialogs():
    return MagicMock(spec=FileDialogService)


@pytest.fixture
def duckdb_editor(duckdb_path: Path, database_file_dialogs):
    write_connections({
        "Duck file": {"db_type": "duckdb", "protocol": "duckdb", "database": str(duckdb_path)},
        "SQLite file": {"db_type": "sqlite", "protocol": "sqlite", "database": ":memory:"},
    })
    dialogs = MagicMock(spec=NullDialogService)
    editor = ConnectionEditor(dialogs=dialogs, file_dialogs=database_file_dialogs)
    editor.show()
    editor.list_widget.setCurrentRow(0)
    try:
        yield editor, dialogs
    finally:
        editor.close()
        editor.deleteLater()
        QCoreApplication.sendPostedEvents(editor, QEvent.Type.DeferredDelete)
        base.close_connection("Duck file")
        base.close_connection("SQLite file")


def test_duckdb_defaults_and_reloaded_field_states(duckdb_editor) -> None:
    editor, _ = duckdb_editor
    assert editor.db_type_combo.currentData() == "duckdb"
    assert editor.protocol_combo.currentText() == "duckdb"
    assert editor.port_edit.text() == ""
    for field in (
        editor.protocol_combo,
        editor.server_edit,
        editor.port_edit,
        editor.user_edit,
        editor.password_edit,
        editor.trusted_checkbox,
        editor.driver_edit,
        editor.system_drivers,
        editor.btn_add_driver,
        editor.dsn_edit,
        editor.extra_edit,
    ):
        assert not field.isEnabled()
    assert editor.db_edit.isEnabled()
    assert editor.sqlite_browse_btn.isEnabled()
    # The reload's trusted-connection handler must not re-enable credentials.
    editor.on_trusted_changed()
    assert not editor.user_edit.isEnabled()
    assert not editor.password_edit.isEnabled()


def test_switching_to_duckdb_clears_stale_options_and_leaving_restores_controls(duckdb_editor) -> None:
    editor, _ = duckdb_editor
    editor.db_type_combo.setCurrentIndex(editor.db_type_combo.findData("postgresql"))
    editor.extra_edit.setText('{"sslmode": "require"}')
    assert editor.protocol_combo.isEnabled()
    assert editor.extra_edit.isEnabled()
    editor.db_type_combo.setCurrentIndex(editor.db_type_combo.findData("duckdb"))
    assert editor.extra_edit.text() == ""
    assert editor.protocol_combo.currentText() == "duckdb"
    assert not editor.protocol_combo.isEnabled()
    editor.db_type_combo.setCurrentIndex(editor.db_type_combo.findData("sqlite"))
    assert editor.protocol_combo.currentText() == "sqlite"
    assert editor.protocol_combo.isEnabled()
    assert editor.sqlite_browse_btn.isEnabled()
    editor.db_type_combo.setCurrentIndex(editor.db_type_combo.findData("postgresql"))
    assert editor.protocol_combo.currentText() == "psycopg"
    assert editor.port_edit.text() == "5432"
    assert editor.user_edit.isEnabled()
    assert editor.dsn_edit.isEnabled()


@pytest.mark.parametrize("engine", ["duckdb", "sqlite"])
@pytest.mark.parametrize("cancelled", [False, True])
def test_database_browse_uses_engine_filter_and_preserves_path_on_cancel(
    duckdb_editor, database_file_dialogs, widget_language: str, engine: str, cancelled: bool
) -> None:
    editor, _ = duckdb_editor
    editor.db_type_combo.setCurrentIndex(editor.db_type_combo.findData(engine))
    previous = editor.db_edit.text()
    chosen = r"C:\selected\database.db"
    database_file_dialogs.get_open_filename.return_value = ("" if cancelled else chosen, "")
    editor.sqlite_browse_btn.click()
    assert editor.db_edit.text() == (previous if cancelled else chosen)
    title = editor.tr("Select DuckDB database file") if engine == "duckdb" else editor.tr("Select SQLite database file")
    file_filter = (
        editor.tr("DuckDB files (*.duckdb *.ddb *.db);;All files (*.*)")
        if engine == "duckdb"
        else editor.tr("SQLite files (*.db *.sqlite *.sqlite3);;All files (*.*)")
    )
    database_file_dialogs.get_open_filename.assert_called_once_with(
        editor, OpenFileRequest(title=title, initial_path="", filter_str=file_filter)
    )


def test_save_duckdb_roundtrip_drops_irrelevant_fields(duckdb_editor, duckdb_path: Path) -> None:
    editor, dialogs = duckdb_editor
    editor.server_edit.setText("stale-host")
    editor.password_edit.setText("stale-password")
    changed = MagicMock()
    editor.connections_changed.connect(changed)
    editor.save_changes()
    stored = read_connections()["Duck file"]
    assert stored == {
        "db_type": "duckdb",
        "protocol": "duckdb",
        "database": str(duckdb_path),
        "extra": {},
        "trusted_connection": "no",
    }
    changed.assert_called_once_with()
    dialogs.info.assert_called_once()
    reloaded = ConnectionEditor(dialogs=NullDialogService())
    reloaded.show()
    try:
        assert reloaded.db_type_combo.currentData() == "duckdb"
        assert reloaded.db_edit.text() == str(duckdb_path)
        assert not reloaded.user_edit.isEnabled()
        assert not reloaded.extra_edit.isEnabled()
    finally:
        reloaded.close()
        reloaded.deleteLater()
        QCoreApplication.sendPostedEvents(reloaded, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("action", ["save_changes", "test_connection"])
@pytest.mark.parametrize(
    "invalid",
    ["empty", "memory", "remote", "missing", "directory", "json", "list", "null", "override", "protocol", "engine"],
)
def test_invalid_duckdb_settings_do_not_persist_execute_or_invalidate(
    duckdb_editor, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str, invalid: str
) -> None:
    editor, dialogs = duckdb_editor
    initial = read_connections()
    invalidate = MagicMock()
    editor._invalidate_connection = invalidate
    execute = MagicMock()
    monkeypatch.setattr(connection_editor, "execute_sql_safe", execute)
    paths = {
        "empty": "",
        "memory": ":memory:",
        "remote": "md:remote",
        "missing": str(tmp_path / "missing.duckdb"),
        "directory": str(tmp_path),
    }
    if invalid in paths:
        editor.db_edit.setText(paths[invalid])
    elif invalid in ("json", "list", "null", "override"):
        editor.extra_edit.setText(
            {"json": "{", "list": "[]", "null": "null", "override": '{"read_only": false}'}[invalid]
        )
    elif invalid == "protocol":
        editor.protocol_combo.setCurrentText("sqlite")
    else:
        editor.db_type_combo.setCurrentIndex(editor.db_type_combo.findData("sqlite"))
        editor.protocol_combo.setCurrentText("duckdb")
    getattr(editor, action)()
    dialogs.warn.assert_called_once()
    assert read_connections() == initial
    assert editor.data == initial
    execute.assert_not_called()
    invalidate.assert_not_called()
    assert not (tmp_path / "missing.duckdb").exists()


def test_duckdb_test_uses_edited_file_and_preserves_save_semantics(
    duckdb_editor, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    editor, dialogs = duckdb_editor
    assert base.execute_sql_safe("Duck file", "SELECT * FROM first_table").ok
    old_service, _ = base._get_service_with_config("Duck file")
    next_path = tmp_path / "second.duckdb"
    with duckdb.connect(str(next_path)) as connection:
        connection.execute("CREATE TABLE second_table (value INTEGER); INSERT INTO second_table VALUES (2)")

    execute = MagicMock(wraps=base.execute_sql_safe)
    monkeypatch.setattr(connection_editor, "execute_sql_safe", execute)
    editor.db_edit.setText(str(next_path))
    changed = MagicMock()
    editor.connections_changed.connect(changed)
    editor.test_connection()

    dialogs.info.assert_called_once_with(editor, editor.tr("OK"), editor.tr("Connection succeeded!"))
    dialogs.critical.assert_not_called()
    execute.assert_called_once()
    assert execute.call_args.kwargs["sql_text"] == "SELECT 1"
    assert read_connections()["Duck file"]["database"] == str(next_path)
    new_service, cfg = base._get_service_with_config("Duck file")
    assert new_service is not old_service
    assert cfg.database == str(next_path)
    assert old_service.driver._engines == {}
    assert base.execute_sql_safe("Duck file", "SELECT * FROM second_table").data.iloc[0, 0] == 2
    changed.assert_called_once_with()


def test_duckdb_connection_failure_is_reported_and_test_still_saves_form(duckdb_editor, tmp_path: Path) -> None:
    editor, dialogs = duckdb_editor
    corrupt = tmp_path / "corrupt.duckdb"
    corrupt.write_bytes(b"not a database")
    editor.db_edit.setText(str(corrupt))
    editor.test_connection()
    dialogs.critical.assert_called_once()
    dialogs.info.assert_not_called()
    assert read_connections()["Duck file"]["database"] == str(corrupt)
    assert corrupt.read_bytes() == b"not a database"


@pytest.mark.parametrize("old_engine", ["duckdb", "sqlite"])
@pytest.mark.parametrize("action", ["save_changes", "test_connection", "delete_connection"])
def test_edits_involving_duckdb_invalidate_through_injected_owner(duckdb_editor, old_engine: str, action: str) -> None:
    editor, dialogs = duckdb_editor
    if old_engine == "sqlite":
        editor.data["Duck file"]["db_type"] = "sqlite"
    else:
        editor.db_type_combo.setCurrentIndex(editor.db_type_combo.findData("sqlite"))
    # Deletion uses the persisted engine rather than an unsaved type selection.
    should_invalidate = action != "delete_connection" or old_engine == "duckdb"
    callback = MagicMock()
    editor._invalidate_connection = callback
    dialogs.prompt_yes_no.return_value = True
    getattr(editor, action)()
    if should_invalidate:
        callback.assert_called_once_with("Duck file")
    else:
        callback.assert_not_called()


def test_delete_duckdb_closes_cached_backend(duckdb_editor) -> None:
    editor, dialogs = duckdb_editor
    base.execute_sql_safe("Duck file", "SELECT 1")
    service, _ = base._get_service_with_config("Duck file")
    dialogs.prompt_yes_no.return_value = True
    editor.delete_connection()
    assert "Duck file" not in read_connections()
    assert "Duck file" not in base._services
    assert service.driver._engines == {}


def test_sqlite_edit_and_test_retain_existing_invalidation_behavior(duckdb_editor) -> None:
    editor, _ = duckdb_editor
    editor.list_widget.setCurrentRow(1)
    callback = MagicMock()
    editor._invalidate_connection = callback
    editor.save_changes()
    editor.test_connection()
    callback.assert_not_called()


@pytest.mark.parametrize("language", list(Language))
def test_duckdb_dialog_strings_have_compiled_translations(language: Language) -> None:
    translator = QTranslator()
    path = Path(__file__).parents[1] / "src" / "expo_jbm329" / "i18n" / "locales" / f"app_{language.value}.qm"
    assert translator.load(str(path))
    for source in (
        "DuckDB (file-based)",
        "Select DuckDB database file",
        "DuckDB files (*.duckdb *.ddb *.db);;All files (*.*)",
    ):
        translated = translator.translate("ConnectionEditor", source)
        if language == Language.ENGLISH:
            assert not translated
        else:
            assert translated
            assert "*.duckdb *.ddb *.db" in translated if "*.duckdb" in source else translated != source


def test_duckdb_edit_invalidates_backend_schema_and_stale_prefetch_via_workbench(
    duckdb_editor, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    editor, dialogs = duckdb_editor
    cache = SchemaCacheManager()
    cache._cache["Duck file"] = SchemaCacheEntry(
        tables=[{"schema": "main", "name": "first_table"}],
        columns={("main", "first_table"): [{"COLUMN_NAME": "id"}]},
    )
    token = cache._make_token("Duck file")
    base.execute_sql_safe("Duck file", "SELECT 1")
    controller = ConnectionController(
        get_connection_names=lambda: read_connections().keys(),
        clear_schema_cache=cache.clear_for,
        close_db_connection=base.close_connection,
    )
    controller.bind_schema_loader(lambda name, refresh: None)
    controller.connect("Duck file")
    workbench = WorkbenchServices.__new__(WorkbenchServices)
    workbench.connections = controller
    workbench.editor_panel = MagicMock()
    editor._invalidate_connection = workbench.invalidate_connection_configuration
    second = tmp_path / "next.duckdb"
    with duckdb.connect(str(second)) as connection:
        connection.execute("CREATE TABLE second_table (next_id INTEGER)")
    editor.db_edit.setText(str(second))
    editor.test_connection()
    dialogs.info.assert_called_once()
    assert controller.active_connection is None
    assert cache.get_cache_for("Duck file") is None
    workbench.editor_panel.invalidate_connection_metadata.assert_called_once_with("Duck file")
    cfg = base._get_service_with_config("Duck file")[1]
    assert cfg.database == str(second)
    cache._cache["Duck file"] = SchemaCacheEntry(tables=base.list_tables("Duck file"))
    cache._on_bulk_done("Duck file", token, {("main", "first_table"): [{"COLUMN_NAME": "stale"}]})
    assert cache.get_cache_for("Duck file").columns == {}
    assert cache.get_cache_for("Duck file").tables == [{"schema": "main", "name": "second_table"}]


def test_create_new_duckdb_connection_through_dialog(duckdb_path: Path) -> None:
    write_connections({})
    dialogs = MagicMock(spec=NullDialogService)
    dialogs.prompt_text.return_value = ("New DuckDB", True)
    editor = ConnectionEditor(dialogs=dialogs)
    editor.show()
    try:
        assert not editor.db_type_combo.isEnabled()
        editor.btn_add.click()
        assert editor.list_widget.currentItem().text() == "New DuckDB"
        editor.db_type_combo.setCurrentIndex(editor.db_type_combo.findData("duckdb"))
        editor.db_edit.setText(str(duckdb_path))
        assert not editor.protocol_combo.isEnabled()
        editor.btn_save.click()
        assert read_connections()["New DuckDB"]["db_type"] == "duckdb"
        editor.btn_test.click()
        dialogs.critical.assert_not_called()
        dialogs.warn.assert_not_called()
        assert dialogs.info.call_count == 2
        assert base.execute_sql_safe("New DuckDB", "SELECT * FROM first_table").rows == 1
    finally:
        base.close_connection("New DuckDB")
        editor.close()
        editor.deleteLater()
        QCoreApplication.sendPostedEvents(editor, QEvent.Type.DeferredDelete)


def test_application_dialog_injects_workbench_invalidation_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from expo_jbm329.app import expo_studio

    workbench = MagicMock(spec=WorkbenchServices)
    workbench.icon_service = MagicMock()
    workbench.schema = MagicMock()
    controller = MagicMock(spec=ConnectionController)
    controller.get_connection_names.return_value = ["Duck file"]
    dialogs = NullDialogService()
    file_dialogs = MagicMock(spec=FileDialogService)
    host = SimpleNamespace(
        _require_workbench_services=lambda: workbench,
        _require_dialogs=lambda: dialogs,
        _require_file_dialogs=lambda: file_dialogs,
        connection_controller=controller,
    )
    dialog = MagicMock()
    factory = MagicMock(return_value=dialog)
    monkeypatch.setattr(expo_studio, "ConnectionEditor", factory)
    expo_studio.ExpoStudio._open_connection_dialog(host)
    assert factory.call_args.kwargs["dialogs"] is dialogs
    assert factory.call_args.kwargs["file_dialogs"] is file_dialogs
    assert factory.call_args.kwargs["invalidate_connection"] == workbench.invalidate_connection_configuration
    dialog.exec.assert_called_once_with()
    refresh = dialog.connections_changed.connect.call_args.args[0]
    refresh()
    workbench.schema.refresh_connections.assert_called_once_with(["Duck file"])
