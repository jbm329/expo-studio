"""REST Connection Editor dialog for managing REST API connections."""

from __future__ import annotations

import contextlib
import json
from typing import Literal

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QTextCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.app.settings.config_store import (
    read_rest_connections,
    write_rest_connections,
)
from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.services.rest.client import fetch_json
from expo_jbm329.services.rest.models import RestAuthConfig, RestRequestConfig
from expo_jbm329.services.rest.normalizer import normalize_json_to_df
from expo_jbm329.utils.format_utils import fmt_shape
from expo_jbm329.workbench.icon.icon_service import IconService


class RestConnectionEditor(QDialog):
    """Dialog for creating and editing REST API connections."""

    connections_changed = pyqtSignal()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def __init__(
        self,
        parent: QWidget | None = None,
        preset_name: str | None = None,
        dialogs: DialogService | None = None,
        icon_service: IconService | None = None,
    ):
        """Initializes the RestConnectionEditor dialog."""
        super().__init__(parent)
        self._preset_name = preset_name
        self._dialogs = dialogs if dialogs else QtDialogService()
        self._icon_service = icon_service

        self.setWindowTitle(self.tr("REST API connections"))
        self.setFixedSize(700, 525)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # Icon via IconService
        self._update_icon()
        if self._icon_service:
            self._icon_service.icons_updated.connect(self._update_icon)

        # Loaded in showEvent
        self.data: dict[str, dict] = {}

        # ==============================================================
        # Left: connection list
        # ==============================================================
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self.on_selection_changed)

        # ==============================================================
        # Right: form fields
        # ==============================================================
        self.url_edit = QLineEdit()

        self.method_combo = QComboBox()
        self.method_combo.addItem("GET", userData="GET")
        self.method_combo.addItem("POST", userData="POST")
        self.method_combo.currentIndexChanged.connect(self.on_method_changed)

        self.body_edit = QPlainTextEdit()
        self.body_edit.setPlaceholderText(
            '{\n  "query": [],\n  "response": { "format": "JSON" }\n}'
        )
        self.body_edit.setMinimumHeight(120)

        self.response_path_edit = QLineEdit()
        self.response_path_edit.setPlaceholderText("e.g. hourly, data.items, 1, results.0.values")

        self.auth_combo = QComboBox()
        self.auth_combo.addItem(self.tr("None"), userData="none")
        self.auth_combo.addItem(self.tr("Bearer token"), userData="bearer")
        self.auth_combo.currentIndexChanged.connect(self.on_auth_changed)

        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.headers_edit = QLineEdit()
        self.headers_edit.setPlaceholderText('{"Accept": "application/json"}')

        self.params_edit = QPlainTextEdit()
        self.params_edit.setPlaceholderText('{"limit": 100}')

        # --- Re-evaluate Save/Test availability ---
        self.url_edit.textChanged.connect(self._update_action_buttons)
        self.method_combo.currentIndexChanged.connect(self._update_action_buttons)
        self.body_edit.textChanged.connect(self._update_action_buttons)
        self.params_edit.textChanged.connect(self._update_action_buttons)

        # ==============================================================
        # Layout (form)
        # ==============================================================
        form = QFormLayout()
        form.addRow(self.tr("URL:"), self.url_edit)
        form.addRow(self.tr("Method:"), self.method_combo)
        form.addRow(self.tr("JSON body:"), self.body_edit)
        form.addRow(self.tr("Response path:"), self.response_path_edit)
        form.addRow(self.tr("Authentication:"), self.auth_combo)
        form.addRow(self.tr("Bearer token:"), self.token_edit)
        form.addRow(self.tr("Headers (JSON):"), self.headers_edit)
        form.addRow(self.tr("Query params (JSON):"), self.params_edit)

        self.body_edit.setVisible(False)  # default: GET

        # ==============================================================
        # Buttons
        # ==============================================================
        self.btn_add = QPushButton(self.tr("Add"))
        self.btn_test = QPushButton(self.tr("Test"))
        self.btn_delete = QPushButton(self.tr("Delete"))
        self.btn_save = QPushButton(self.tr("Save"))
        self.btn_close = QPushButton(self.tr("Close"))

        self.btn_add.clicked.connect(self.add_connection)
        self.btn_test.clicked.connect(self.test_connection)
        self.btn_delete.clicked.connect(self.delete_connection)
        self.btn_save.clicked.connect(self.save_changes)
        self.btn_close.clicked.connect(self.close)

        self._update_action_buttons()

        btns = QHBoxLayout()
        for b in (self.btn_add, self.btn_test, self.btn_delete, self.btn_save, self.btn_close):
            btns.addWidget(b)

        # ==============================================================
        # Main layout
        # ==============================================================
        left = QVBoxLayout()
        left.addWidget(QLabel(self.tr("Connections:")))
        left.addWidget(self.list_widget)

        right = QVBoxLayout()
        right.addLayout(form)
        right.addLayout(btns)

        main = QHBoxLayout()
        main.addLayout(left, 1)
        main.addLayout(right, 2)

        self.setLayout(main)

        self.on_auth_changed()

    # ----------------------------------------------------------------------
    # Update icon
    # ----------------------------------------------------------------------
    def _update_icon(self):
        """Updates the window icon using the IconService or a fallback path."""
        if self._icon_service:
            icon = self._icon_service.get("rest")
        else:
            icon = QIcon(":/icons/dark/themes/dark/rest.png")  # fallback
        self.setWindowIcon(icon)

    # ------------------------------------------------------------------
    # showEvent
    # ------------------------------------------------------------------
    def showEvent(self, event):
        """Loads connection data and populates list."""
        super().showEvent(event)

        self.data = read_rest_connections()

        self.list_widget.clear()
        self.list_widget.addItems(self.data.keys())

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

        if self._preset_name:
            self._select_connection(self._preset_name)

    # ==================================================================
    # Handlers
    # ==================================================================
    def on_method_changed(self) -> None:
        """Handles the change in HTTP method selection."""
        method = self.method_combo.currentData()
        is_post = method == "POST"
        self.body_edit.setVisible(is_post)
        if not is_post:
            self.body_edit.clear()

    def on_auth_changed(self):
        """Handles the change in authentication type selection."""
        auth = self.auth_combo.currentData()
        self.token_edit.setEnabled(auth == "bearer")

    def on_selection_changed(self, current):
        """Loads the selected connection's data into the form fields."""
        if not current:
            self._clear_form_fields()
            self._set_fields_enabled(False)
            return

        name = current.text()
        cfg = self.data.get(name, {})

        url_val = cfg.get("url")

        if isinstance(url_val, str):
            self.url_edit.setText(url_val)
            self.url_edit.setCursorPosition(0)
            self.url_edit.setToolTip(url_val)
        else:
            self.url_edit.clear()
            self.url_edit.setToolTip("")

        method = cfg.get("method", "GET")
        ix = self.method_combo.findData(method)
        if ix >= 0:
            self.method_combo.setCurrentIndex(ix)

        self.on_method_changed()

        body = cfg.get("json_body")
        if isinstance(body, dict):
            self.body_edit.setPlainText(json.dumps(body, indent=2))
        else:
            self.body_edit.clear()

        rp = cfg.get("response_path") or ""

        if isinstance(rp, str):
            self.response_path_edit.setText(rp)
        else:
            self.response_path_edit.clear()
            self.response_path_edit.setToolTip("")

        headers = cfg.get("headers") or {}
        self.headers_edit.setText(
            json.dumps(headers) if headers else ""
        )

        params = cfg.get("query_params") or {}

        text = json.dumps(params, indent=2) if params else ""
        self.params_edit.setPlainText(text)
        self.params_edit.moveCursor(QTextCursor.MoveOperation.Start)

        auth = cfg.get("auth", {}).get("type", "none")
        ix = self.auth_combo.findData(auth)
        if ix >= 0:
            self.auth_combo.setCurrentIndex(ix)

        token = cfg.get("auth", {}).get("token", "")
        self.token_edit.setText(token)

        self._set_fields_enabled(True)
        self._update_action_buttons()
    
    # ==================================================================
    # Helpers
    # ==================================================================
    def _gather_form(self) -> dict:

        raw_method = self.method_combo.currentData()
        method: Literal["GET", "POST"] = "POST" if raw_method == "POST" else "GET"

        cfg: dict = {
            "url": self.url_edit.text().strip(),
            "method": method,
            "response_path": self.response_path_edit.text().strip(),
            "headers": {},
            "query_params": {},
            "auth": {"type": self.auth_combo.currentData()},
        }

        if cfg["method"] == "POST":
            body_txt = self.body_edit.toPlainText().strip()
            if body_txt:
                with contextlib.suppress(Exception):
                    cfg["json_body"] = json.loads(body_txt)
            else:
                cfg["json_body"] = None

        if cfg["auth"]["type"] == "bearer":
            cfg["auth"]["token"] = self.token_edit.text().strip()

        headers_txt = self.headers_edit.text().strip()
        if headers_txt:
            with contextlib.suppress(Exception):
                cfg["headers"] = json.loads(headers_txt)

        params_txt = self.params_edit.toPlainText().strip()
        if params_txt:
            with contextlib.suppress(Exception):
                cfg["query_params"] = json.loads(params_txt)

        return cfg

    def _clear_form_fields(self) -> None:
        self.url_edit.clear()
        self.response_path_edit.clear()
        self.headers_edit.clear()
        self.params_edit.clear()
        self.token_edit.clear()
        self.auth_combo.setCurrentIndex(self.auth_combo.findData("none"))
        self._update_action_buttons()

    def _set_fields_enabled(self, enabled: bool) -> None:
        """Enable or disable all input fields in the REST connection form.

        Args:
            enabled: Whether to enable (True) or disable (False) the fields.
        """
        for w in (
            self.url_edit,
            self.method_combo,
            self.body_edit,
            self.response_path_edit,
            self.auth_combo,
            self.token_edit,
            self.headers_edit,
            self.params_edit,
        ):
            w.setEnabled(enabled)

    def _is_form_executable(self) -> bool:
        """Return True if the current form state allows Save/Test."""
        url_ok = bool(self.url_edit.text().strip())
        if not url_ok:
            return False

        path = self.response_path_edit.text().strip()
        if not self._is_valid_response_path_syntax(path):
            return False

        method = self.method_combo.currentData()
        if method == "POST":
            body_txt = self.body_edit.toPlainText().strip()
            if not body_txt:
                return False

            # Optional: validate JSON syntax
            try:
                json.loads(body_txt)
            except Exception:
                return False

        return True

    def _update_action_buttons(self) -> None:
        enabled = self._is_form_executable()
        self.btn_save.setEnabled(enabled)
        self.btn_test.setEnabled(enabled)

        if not enabled and self.method_combo.currentData() == "POST":
            self.btn_test.setToolTip(self.tr("POST requests require a valid JSON body"))
        else:
            self.btn_test.setToolTip("")

        path = self.response_path_edit.text().strip()
        if path and not self._is_valid_response_path_syntax(path):
            self.response_path_edit.setToolTip(
                self.tr(
                    "Invalid response path.\n"
                    "Use dot-separated keys or numeric indices.\n"
                    "Examples:\n"
                    "  hourly\n"
                    "  data.items\n"
                    "  1\n"
                    "  results.0.values"
                )
            )
        else:
            self.response_path_edit.setToolTip("")

        params_txt = self.params_edit.toPlainText().strip()
        if params_txt:
            try:
                json.loads(params_txt)
            except Exception:
                self.params_edit.setToolTip(self.tr("Invalid JSON"))
                return
        else:
            self.params_edit.setToolTip("")

    def _is_valid_response_path_syntax(self, path: str) -> bool:
        """Check basic syntax of response_path."""
        if not path:
            return True  # empty is allowed

        parts = path.split(".")
        for part in parts:
            if not part:
                return False
            if part.isdigit():
                continue
            # simple key check: letters, numbers, underscore
            if not part.replace("_", "").isalnum():
                return False

        return True

    def _select_connection(self, name: str) -> None:
        """Select a connection by name in the list widget."""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.text() == name:
                self.list_widget.setCurrentRow(i)
                return

    # ==================================================================
    # Manage connections
    # ==================================================================

    def add_connection(self) -> None:
        """Add a new REST connection by prompting for a name."""
        name, ok = self._dialogs.prompt_text(
            parent=self,
            title=self.tr("New REST connection"),
            label=self.tr("Name:"),
            default=None,
        )
        if not ok or not name or not name.strip():
            return

        name = name.strip()
        if name in self.data:
            self._dialogs.warn(
                parent=self,
                title=self.tr("Failure"),
                text=self.tr("A REST connection with that name already exists."),
            )
            return

        # Create empty config (NOT filled with "{}")
        self.data[name] = {
            "url": "",
            "headers": {},
            "query_params": {},
            "response_path": "",
            "auth": {"type": "none"},
        }

        self.list_widget.addItem(name)
        self.list_widget.setCurrentRow(self.list_widget.count() - 1)

        self._clear_form_fields()
        self._set_fields_enabled(True)

        self.connections_changed.emit()

    def test_connection(self) -> None:
        """Test the REST API using the current form values without saving."""
        try:
            cfg_raw = self._gather_form()

            if not cfg_raw.get("url"):
                self._dialogs.warn(
                    parent=self,
                    title=self.tr("Missing URL"),
                    text=self.tr("URL must be specified before testing."),
                )
                return

            auth_raw = cfg_raw.get("auth", {}) or {}
            auth = RestAuthConfig(
                type=auth_raw.get("type", "none"),
                token=auth_raw.get("token"),
            )

            raw_method = cfg_raw.get("method")

            if raw_method == "POST":
                method: Literal["GET", "POST"] = "POST"
            else:
                method: Literal["GET", "POST"] = "GET"

            config = RestRequestConfig(
                name=self.tr("Test request"),
                url=cfg_raw.get("url", ""),
                method=method,
                headers=cfg_raw.get("headers", {}),
                query_params=cfg_raw.get("query_params", {}),
                json_body=cfg_raw.get("json_body"),
                response_path=cfg_raw.get("response_path") or None,
                auth=auth,
            )

            # --- Perform test ---
            payload, _elapsed = fetch_json(config)
            try:
                df = normalize_json_to_df(
                    payload,
                    response_path=config.response_path,
                )
            except Exception as exc:
                self._dialogs.critical(
                    parent=self,
                    title=self.tr("Invalid response path"),
                    text=self.tr(
                        "The response path could not be applied to the API response.\n\n{error}"
                    ).format(error=str(exc)),
                )
                return

            rows, cols = fmt_shape(df)

            text = self.tr(
                "API test successful.\n\nReturned {rows} rows and {cols} columns.\n\nTime: {sec:.2f}s"
            ).format(rows=rows, cols=cols, sec=_elapsed)

            self._dialogs.info(
                parent=self,
                title=self.tr("Test successful"),
                text=text
            )

        except Exception as exc:
            self._dialogs.critical(
                parent=self,
                title=self.tr("Test failed"),
                text=str(exc),
            )

    def delete_connection(self):
        """Deletes the currently selected connection after confirmation."""
        item = self.list_widget.currentItem()
        if not item:
            return

        name = item.text()
        confirm = self._dialogs.prompt_yes_no(
            parent=self,
            title=self.tr("Delete"),
            text=self.tr("Do you want to delete '{name}'?").format(name=name),
            default_yes=False,
        )
        if not confirm:
            return

        self.data.pop(name, None)
        self.list_widget.takeItem(self.list_widget.row(item))
        write_rest_connections(self.data)
        self.connections_changed.emit()

    def save_changes(self):
        """Saves the current form values to the selected connection entry."""
        item = self.list_widget.currentItem()
        if not item:
            return

        name = item.text()
        self.data[name] = self._gather_form()

        write_rest_connections(self.data)

        self._dialogs.info(
            parent=self,
            title=self.tr("Saved"),
            text=self.tr("REST connection saved successfully."),
        )
        self.connections_changed.emit()
