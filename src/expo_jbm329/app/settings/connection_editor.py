"""Connection Editor dialog for managing database connections.

This module provides the ConnectionEditor class, which is a unified,
protocol-aware connection workbench for Expo. It supports various database
types (SQL Server, PostgreSQL, MySQL, Oracle, SQLite) and protocols
(ODBC, pymysql, mysqlconnector, sqlite).
"""

from __future__ import annotations

import contextlib
import json
import uuid
from typing import TYPE_CHECKING, override

import pyodbc
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.app.settings.config_store import read_connections, write_connections
from expo_jbm329.db.base import execute_sql_safe
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.utils.i18n_utils import tr

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.icon.icon_service import IconService

# =============================================================================
# Constants
# =============================================================================
_DEFAULT_PORTS = {
    "mssql": 1433,
    "postgresql": 5432,
    "mysql": 3306,
    "oracle": 1521,
}

_DEFAULT_PROTOCOL = {
    "mssql": "odbc",
    "postgresql": "psycopg2",  # framtida stöd
    "mysql": "pymysql",
    "mariadb": "pymysql",
    "sqlite": "sqlite",
    "oracle": "odbc",
    "other": "odbc",
}


# =============================================================================
# Helper functions
# =============================================================================


def _default_port_for(db_type: str) -> int | None:
    """Returns the default port number for a given database type.

    Args:
        db_type: The database type (e.g., 'mssql', 'postgresql', 'mysql', 'oracle').

    Returns:
        The default port number if known; otherwise, None.
    """
    return _DEFAULT_PORTS.get(db_type)


def _infer_db_type_from_driver_text(driver_text: str) -> str:
    """Infer engine from ODBC driver name (fallback heuristic).

    Args:
        driver_text: The ODBC driver name.

    Returns:
        The inferred database type string.
    """
    t = (driver_text or "").lower()
    if "sql server" in t or "mssql" in t:
        return "mssql"
    if "postgres" in t:
        return "postgresql"
    if "mysql" in t or "mariadb" in t:
        return "mysql"
    if "oracle" in t:
        return "oracle"
    if "sqlite" in t:
        return "sqlite"
    return "other"


# =============================================================================
# Dialog Class
# =============================================================================


class ConnectionEditor(QDialog):
    """Enterprise-level connection workbench.

    Provides a unified interface for managing database connections for various protocols.
    The UI text is Swedish, while comments and docstrings are in English.

    Attributes:
        connections_changed (pyqtSignal): Signal emitted when connections are added,
            deleted, or updated.
    """

    connections_changed = pyqtSignal()

    # ----------------------------------------------------------------------
    # Initialization
    # ----------------------------------------------------------------------

    def __init__(
        self,
        parent: QWidget | None = None,
        dialogs: DialogService | None = None,
        icon_service: IconService | None = None,
    ):
        """Initializes the ConnectionEditor dialog.

        Args:
            parent: The parent widget.
            dialogs: Service for showing dialog boxes. Defaults to QtDialogService if None.
            icon_service: Service for retrieving icons.
        """
        super().__init__(parent)

        self._dialogs = dialogs or QtDialogService()
        self._icon_service = icon_service

        # --- Dialog setup ---
        self.setWindowTitle(self.tr("Database connections"))
        self.setFixedSize(600, 440)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # Icon via IconService
        self._update_icon()
        if self._icon_service:
            self._icon_service.icons_updated.connect(self._update_icon)

        # Data loaded later in showEvent
        self.data: dict[str, dict] = {}

        # ==================================================================
        # Left list: connection names
        # ==================================================================
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self.on_selection_changed)

        # ==================================================================
        # Right panel: widgets
        # ==================================================================

        # DB type
        self.db_type_combo = QComboBox()
        self.db_type_combo.addItem(self.tr("SQL Server"), userData="mssql")
        self.db_type_combo.addItem(self.tr("PostgreSQL"), userData="postgresql")
        self.db_type_combo.addItem(self.tr("MySQL / MariaDB"), userData="mysql")
        self.db_type_combo.addItem(self.tr("Oracle"), userData="oracle")
        self.db_type_combo.addItem(self.tr("SQLite (file-based)"), userData="sqlite")
        self.db_type_combo.addItem(self.tr("Other"), userData="other")

        self.db_type_combo.currentIndexChanged.connect(self.on_db_type_changed)

        # Protocol
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["odbc", "pymysql", "mysqlconnector", "sqlite"])
        self.protocol_combo.currentIndexChanged.connect(self.on_protocol_changed)

        # ODBC drivers
        self.system_drivers = QComboBox()
        try:
            for d in pyodbc.drivers():
                self.system_drivers.addItem(d)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self.system_drivers.addItem(self.tr("(No ODBC-drivers found)"))

        self.driver_edit = QLineEdit()
        self.driver_edit.setReadOnly(True)

        self.btn_add_driver = QPushButton(self.tr("Use selected driver"))
        self.btn_add_driver.clicked.connect(self.on_add_driver)

        # Common fields
        self.server_edit = QLineEdit()
        self.port_edit = QLineEdit()
        self.db_edit = QLineEdit()
        self.user_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        # SQLite browse
        self.sqlite_browse_btn = QPushButton(self.tr("Browse…"))
        self.sqlite_browse_btn.clicked.connect(self.on_sqlite_browse)

        # Trusted Connection
        self.trusted_checkbox = QCheckBox(self.tr("Trusted Connection"))
        self.trusted_checkbox.stateChanged.connect(self.on_trusted_changed)

        # Extra JSON
        self.extra_edit = QLineEdit()
        self.extra_edit.setPlaceholderText('{"ssl": "require"}')

        # Optional DSN
        self.dsn_edit = QLineEdit()

        # ==================================================================
        # Layout (right side)
        # ==================================================================
        form = QFormLayout()
        form.addRow(self.tr("Database:"), self.db_type_combo)
        form.addRow(self.tr("Protocol:"), self.protocol_combo)

        form.addRow(self.tr("System ODBC:"), self.system_drivers)
        form.addRow("", self.btn_add_driver)
        form.addRow(self.tr("ODBC driver:"), self.driver_edit)

        form.addRow(self.tr("Server:"), self.server_edit)
        form.addRow(self.tr("Port:"), self.port_edit)
        form.addRow(self.tr("Database / File:"), self.db_edit)
        form.addRow("", self.sqlite_browse_btn)

        form.addRow(self.tr("User:"), self.user_edit)
        form.addRow(self.tr("Password:"), self.password_edit)
        form.addRow(self.tr("Trusted Connection:"), self.trusted_checkbox)

        form.addRow(self.tr("DSN (optional):"), self.dsn_edit)
        form.addRow(self.tr("Extra (JSON):"), self.extra_edit)

        # Buttons
        self.btn_add = QPushButton(self.tr("Add"))
        self.btn_test = QPushButton(self.tr("Test connection"))
        self.btn_delete = QPushButton(self.tr("Delete"))
        self.btn_save = QPushButton(self.tr("Save"))
        self.btn_exit = QPushButton(self.tr("Close"))

        self.btn_add.clicked.connect(self.add_connection)
        self.btn_test.clicked.connect(self.test_connection)
        self.btn_delete.clicked.connect(self.delete_connection)
        self.btn_save.clicked.connect(self.save_changes)
        self.btn_exit.clicked.connect(self.close)

        btns = QHBoxLayout()
        for b in (self.btn_add, self.btn_test, self.btn_delete, self.btn_save, self.btn_exit):
            btns.addWidget(b)

        # ==================================================================
        # Main layout
        # ==================================================================
        left = QVBoxLayout()
        left.addWidget(QLabel(self.tr("Connections:")))
        left.addWidget(self.list_widget)

        right = QVBoxLayout()
        right.addLayout(form)
        right.addLayout(btns)

        main_layout = QHBoxLayout()
        main_layout.addLayout(left, 1)
        main_layout.addLayout(right, 2)

        self.setLayout(main_layout)

    # ----------------------------------------------------------------------
    # Update icon
    # ----------------------------------------------------------------------
    def _update_icon(self):
        """Updates the window icon using the IconService or a fallback path."""
        if self._icon_service:
            icon = self._icon_service.get("connection")
        else:
            icon = QIcon(":/icons/dark/themes/dark/connection.png")  # fallback
        self.setWindowIcon(icon)

    # ----------------------------------------------------------------------
    # showEvent - only positioning + loading data
    # ----------------------------------------------------------------------
    @override
    def showEvent(self, event):
        """Load connection data and populate list.

        Centers the dialog on its parent and reads existing connections from storage.

        Args:
            event: The QShowEvent.
        """
        super().showEvent(event)

        # Center window on parent
        if self.parent():
            pg = self.parent().geometry()
            dg = self.geometry()
            self.move(pg.x() + (pg.width() - dg.width()) // 2, pg.y() + (pg.height() - dg.height()) // 2)

        # Load connections
        self.data = read_connections()

        self.list_widget.clear()
        self.list_widget.addItems(self.data.keys())

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        else:
            self._set_fields_enabled(False)

    # =============================================================================
    # Field enable/disable logic
    # =============================================================================

    def _set_fields_enabled(self, enabled: bool):
        """Enables or disables all input fields in the connection form.

        Args:
            enabled: Whether to enable (True) or disable (False) the fields.
        """
        for w in (
            self.db_type_combo,
            self.protocol_combo,
            self.system_drivers,
            self.driver_edit,
            self.btn_add_driver,
            self.server_edit,
            self.port_edit,
            self.db_edit,
            self.sqlite_browse_btn,
            self.user_edit,
            self.password_edit,
            self.trusted_checkbox,
            self.dsn_edit,
            self.extra_edit,
        ):
            w.setEnabled(enabled)

    def on_protocol_changed(self):
        """Updates the enabled state of UI fields based on the selected protocol."""
        protocol = self.protocol_combo.currentText()

        # First enable everything (baseline)
        self._set_fields_enabled(True)

        if protocol == "odbc":
            self.sqlite_browse_btn.setEnabled(False)

        elif protocol in ("pymysql", "mysqlconnector"):
            # Disable ODBC-specific
            self.driver_edit.setEnabled(False)
            self.system_drivers.setEnabled(False)
            self.btn_add_driver.setEnabled(False)
            self.trusted_checkbox.setEnabled(False)
            self.sqlite_browse_btn.setEnabled(False)

        elif protocol == "sqlite":
            # Only DB/file is relevant
            self.server_edit.setEnabled(False)
            self.port_edit.setEnabled(False)
            self.user_edit.setEnabled(False)
            self.password_edit.setEnabled(False)
            self.trusted_checkbox.setEnabled(False)
            self.system_drivers.setEnabled(False)
            self.btn_add_driver.setEnabled(False)
            self.driver_edit.setEnabled(False)
            self.sqlite_browse_btn.setEnabled(True)

        else:
            # Other protocols
            self.system_drivers.setEnabled(False)
            self.driver_edit.setEnabled(False)
            self.btn_add_driver.setEnabled(False)
            self.trusted_checkbox.setEnabled(False)
            self.sqlite_browse_btn.setEnabled(False)

    def on_db_type_changed(self):
        """Updates default protocol and port when the database type changes."""
        db_type = self.db_type_combo.currentData()

        # Default protocol
        default_proto = _DEFAULT_PROTOCOL.get(db_type, "odbc")
        ix = self.protocol_combo.findText(default_proto)
        if ix >= 0:
            self.protocol_combo.setCurrentIndex(ix)

        # Default port
        dport = _default_port_for(db_type)
        if dport is not None and not self.port_edit.text().strip():
            self.port_edit.setText(str(dport))
        elif db_type == "sqlite":
            self.port_edit.clear()

        self.on_protocol_changed()

    # =============================================================================
    # Handlers
    # =============================================================================

    def on_add_driver(self):
        """Applies the selected system ODBC driver to the driver edit field."""
        self.driver_edit.setText(self.system_drivers.currentText())

        inferred = _infer_db_type_from_driver_text(self.driver_edit.text())
        for i in range(self.db_type_combo.count()):
            if self.db_type_combo.itemData(i) == inferred:
                self.db_type_combo.setCurrentIndex(i)
                break

    def on_trusted_changed(self):
        """Enables or disables credential fields if Trusted Connection is toggled."""
        if self.trusted_checkbox.isChecked():
            self.user_edit.clear()
            self.password_edit.clear()
            self.user_edit.setEnabled(False)
            self.password_edit.setEnabled(False)
        else:
            self.user_edit.setEnabled(True)
            self.password_edit.setEnabled(True)

    def on_sqlite_browse(self):
        """Opens a file dialog to select an SQLite database file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Select SQLite database file"),
            "",
            self.tr("SQLite files (*.db *.sqlite *.sqlite3);;All files (*.*)"),
        )

        if path:
            self.db_edit.setText(path)

    def on_selection_changed(self, current):
        """Loads the selected connection's data into the form fields.

        Args:
            current: The currently selected QListWidgetItem.
        """
        if current is None:
            self.clear_fields()
            return

        name = current.text()
        conn = self.data.get(name, {})

        db_type = conn.get("db_type", "mssql")
        if isinstance(db_type, dict):
            # Fallback if db_type is somehow a dict (should not happen with normalized data)
            db_type = "mssql"
        proto = conn.get("protocol", _DEFAULT_PROTOCOL.get(str(db_type), "odbc"))

        # DB type
        for i in range(self.db_type_combo.count()):
            if self.db_type_combo.itemData(i) == db_type:
                self.db_type_combo.setCurrentIndex(i)
                break

        # Protocol
        ix = self.protocol_combo.findText(proto)
        if ix >= 0:
            self.protocol_combo.setCurrentIndex(ix)

        # Common fields
        self.server_edit.setText(conn.get("server", ""))
        self.db_edit.setText(conn.get("database", ""))

        port = conn.get("port")
        self.port_edit.setText(str(port) if port is not None else "")

        self.user_edit.setText(conn.get("user", ""))
        self.password_edit.setText(conn.get("password", ""))

        # ODBC
        self.driver_edit.setText(conn.get("driver", ""))
        tc = str(conn.get("trusted_connection", "")).lower()
        self.trusted_checkbox.setChecked(tc == "yes")

        # DSN
        self.dsn_edit.setText(conn.get("dsn", ""))

        # Extra JSON
        extra = conn.get("extra", {})
        try:
            self.extra_edit.setText(json.dumps(extra))
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self.extra_edit.setText("{}")

        self.on_protocol_changed()
        self.on_trusted_changed()

    def clear_fields(self):
        """Clears all input fields in the connection form."""
        for w in (
            self.driver_edit,
            self.server_edit,
            self.port_edit,
            self.db_edit,
            self.user_edit,
            self.password_edit,
            self.dsn_edit,
            self.extra_edit,
        ):
            w.clear()

        self.trusted_checkbox.setChecked(False)
        self.db_type_combo.setCurrentIndex(0)
        self.protocol_combo.setCurrentIndex(0)

    # =============================================================================
    # CRUD
    # =============================================================================

    def _gather_current_form(self) -> dict:
        """Extracts current connection information from the form fields.

        Returns:
            A dictionary containing the connection parameters.
        """
        d = {
            "db_type": self.db_type_combo.currentData(),
            "protocol": self.protocol_combo.currentText(),
            "driver": self.driver_edit.text().strip(),
            "server": self.server_edit.text().strip(),
            "database": self.db_edit.text().strip(),
            "user": self.user_edit.text().strip(),
            "password": self.password_edit.text(),
            "trusted_connection": "yes" if self.trusted_checkbox.isChecked() else "no",
            "dsn": self.dsn_edit.text().strip(),
        }

        # port
        port_txt = self.port_edit.text().strip()
        if port_txt:
            with contextlib.suppress(Exception):
                d["port"] = int(port_txt)

        # extra JSON
        extra_txt = self.extra_edit.text().strip()
        if extra_txt:
            with contextlib.suppress(Exception):
                d["extra"] = json.loads(extra_txt)

        return d

    def add_connection(self):
        """Prompts for a name and adds a new connection entry with default values."""
        name, ok = self._dialogs.prompt_text(
            parent=self,
            title=self.tr("New connection"),
            label=self.tr("Name:"),
            default=None,
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        if name in self.data:
            self._dialogs.warn(
                parent=self, title=self.tr("Failure"), text=self.tr("There is already a connection with that name.")
            )
            return

        self.data[name] = {
            "db_type": "mssql",
            "protocol": "odbc",
            "driver": "",
            "server": "",
            "database": "",
            "port": 1433,
            "user": "",
            "password": "",
            "trusted_connection": "no",
            "extra": {},
        }

        write_connections(self.data)
        self.connections_changed.emit()

        self.list_widget.addItem(name)
        self.list_widget.setCurrentRow(self.list_widget.count() - 1)
        self._set_fields_enabled(True)

    def delete_connection(self):
        """Deletes the currently selected connection after confirmation."""
        item = self.list_widget.currentItem()
        if not item:
            return

        name = item.text()
        confirm = self._dialogs.prompt_yes_no(
            parent=self,
            title=self.tr("Delete"),
            text=self.tr("Do you want to delete the connection '%1'?").replace("%1", name),
            informative=None,
            default_yes=False,
        )

        if not confirm:
            return

        self.data.pop(name, None)
        write_connections(self.data)
        self.connections_changed.emit()

        self.list_widget.takeItem(self.list_widget.row(item))

        if self.list_widget.count() == 0:
            self._set_fields_enabled(False)

    def save_changes(self):
        """Saves the current form values to the selected connection entry."""
        item = self.list_widget.currentItem()
        if not item:
            return

        name = item.text()
        self.data[name] = self._gather_current_form()

        write_connections(self.data)
        self._dialogs.info(parent=self, title=self.tr("Saved"), text=self.tr("Changes saved successfully."))
        self.connections_changed.emit()

    # =============================================================================
    # Connection Testing
    # =============================================================================

    def test_connection(self):
        """Tests the current connection configuration using execute_sql_safe."""
        item = self.list_widget.currentItem()
        if not item:
            self._dialogs.warn(parent=self, title=self.tr("Failure"), text=self.tr("No connection selected."))
            return

        name = item.text()

        corr_id = uuid.uuid4().hex

        self.data[name] = self._gather_current_form()
        write_connections(self.data)

        engine = self.data[name].get("db_type")
        test_sql = "SELECT 1 FROM DUAL" if engine == "oracle" else "SELECT 1"
        res = execute_sql_safe(
            connection_name=name,
            sql_text=test_sql,
            top_n=None,
            job_id=None,
            corr_id=corr_id,
        )

        if res.ok:
            self._dialogs.info(self, self.tr("OK"), self.tr("Connection succeeded!"))
        else:
            err = res.error
            msg = tr("DbErrors", err.message) if err else self.tr("Unknown error.")
            if err and getattr(err, "hint", None):
                hint = tr("DbErrors", err.hint)
                msg = f"{msg}\n\n{hint}"

            self._dialogs.critical(
                parent=self,
                title=self.tr("Connection error"),
                text=self.tr("Could not connect.\n\n%1").replace("%1", msg),
            )
