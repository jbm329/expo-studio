from __future__ import annotations

from PyQt6.QtWidgets import QListWidgetItem

from expo_jbm329.app.settings.connection_editor import ConnectionEditor
from expo_jbm329.gui.dialogs.service.null_dialog_service import NullDialogService


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
