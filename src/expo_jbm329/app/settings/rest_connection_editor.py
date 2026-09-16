"""REST Connection Editor dialog for managing REST API connections."""

from __future__ import annotations

import json
from typing import Any, Literal

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
        self.auth_combo.addItem(self.tr("Basic"), userData="basic")
        self.auth_combo.addItem(self.tr("API key"), userData="api_key")
        self.auth_combo.currentIndexChanged.connect(self.on_auth_changed)

        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_name_edit = QLineEdit()
        self.api_key_value_edit = QLineEdit()
        self.api_key_value_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_location_combo = QComboBox()
        self.api_key_location_combo.addItem(self.tr("Header"), userData="header")
        self.api_key_location_combo.addItem(self.tr("Query parameter"), userData="query")

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
        is_bearer = auth == "bearer"
        is_basic = auth == "basic"
        is_api_key = auth == "api_key"

        self.token_edit.setEnabled(is_bearer)
        self.username_edit.setEnabled(is_basic)
        self.password_edit.setEnabled(is_basic)
        self.api_key_name_edit.setEnabled(is_api_key)
        self.api_key_value_edit.setEnabled(is_api_key)
        self.api_key_location_combo.setEnabled(is_api_key)

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
        self.username_edit.setText(cfg.get("auth", {}).get("username", ""))
        self.password_edit.setText(cfg.get("auth", {}).get("password", ""))
        self.api_key_name_edit.setText(cfg.get("auth", {}).get("api_key_name", ""))
        self.api_key_value_edit.setText(cfg.get("auth", {}).get("api_key_value", ""))

        api_key_location = cfg.get("auth", {}).get("api_key_location", "header")
        api_key_ix = self.api_key_location_combo.findData(api_key_location)
        if api_key_ix >= 0:
            self.api_key_location_combo.setCurrentIndex(api_key_ix)

        self._set_fields_enabled(True)
        self._update_action_buttons()
    
    # ==================================================================
    # Helpers
    # ==================================================================
    def _gather_form(self) -> dict:
        """Collect and validate the form into a persisted config shape."""
        raw_method = self.method_combo.currentData()
        method: Literal["GET", "POST"] = "POST" if raw_method == "POST" else "GET"
        auth_type = self.auth_combo.currentData()

        cfg: dict[str, Any] = {
            "url": self.url_edit.text().strip(),
            "method": method,
            "response_path": self.response_path_edit.text().strip(),
            "headers": {},
            "query_params": {},
            "auth": {"type": auth_type},
        }

        if cfg["method"] == "POST":
            body_txt = self.body_edit.toPlainText().strip()
            if body_txt:
                cfg["json_body"] = self._parse_json_object(
                    body_txt,
                    field_name=self.tr("JSON body"),
                )
            else:
                cfg["json_body"] = None

        if auth_type == "bearer":
            cfg["auth"]["token"] = self.token_edit.text().strip()
        elif auth_type == "basic":
            cfg["auth"]["username"] = self.username_edit.text().strip()
            cfg["auth"]["password"] = self.password_edit.text().strip()
        elif auth_type == "api_key":
            cfg["auth"]["api_key_name"] = self.api_key_name_edit.text().strip()
            cfg["auth"]["api_key_value"] = self.api_key_value_edit.text().strip()
            cfg["auth"]["api_key_location"] = self.api_key_location_combo.currentData()

        headers_txt = self.headers_edit.text().strip()
        if headers_txt:
            cfg["headers"] = self._parse_string_map(
                headers_txt,
                field_name=self.tr("Headers"),
            )

        params_txt = self.params_edit.toPlainText().strip()
        if params_txt:
            cfg["query_params"] = self._parse_string_map(
                params_txt,
                field_name=self.tr("Query params"),
            )

        return cfg

    def _build_request_config(self, *, name: str) -> RestRequestConfig:
        """Build and validate a REST request config from the current form."""
        cfg_raw = self._gather_form()
        auth_raw = cfg_raw.get("auth", {}) or {}

        auth = RestAuthConfig(
            type=auth_raw.get("type", "none"),
            token=auth_raw.get("token"),
            username=auth_raw.get("username"),
            password=auth_raw.get("password"),
            api_key_name=auth_raw.get("api_key_name"),
            api_key_value=auth_raw.get("api_key_value"),
            api_key_location=auth_raw.get("api_key_location"),
        )

        raw_method = cfg_raw.get("method")
        method: Literal["GET", "POST"] = "POST" if raw_method == "POST" else "GET"

        config = RestRequestConfig(
            name=name,
            url=cfg_raw.get("url", ""),
            method=method,
            headers=cfg_raw.get("headers", {}),
            query_params=cfg_raw.get("query_params", {}),
            json_body=cfg_raw.get("json_body"),
            response_path=cfg_raw.get("response_path") or None,
            auth=auth,
        )
        config.validate()
        return config

    def _parse_json_object(self, text: str, *, field_name: str) -> dict[str, object]:
        """Parse a JSON object field from the editor."""
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                self.tr("{field} must contain valid JSON.").format(field=field_name)
            ) from exc

        if not isinstance(value, dict):
            raise ValueError(
                self.tr("{field} must be a JSON object.").format(field=field_name)
            )

        return value

    def _parse_string_map(self, text: str, *, field_name: str) -> dict[str, str]:
        """Parse a JSON object and coerce keys and values to strings."""
        value = self._parse_json_object(text, field_name=field_name)
        return {str(key): str(item) for key, item in value.items()}

    def _clear_form_fields(self) -> None:
        self.url_edit.clear()
        self.response_path_edit.clear()
        self.headers_edit.clear()
        self.params_edit.clear()
        self.token_edit.clear()
        self.username_edit.clear()
        self.password_edit.clear()
        self.api_key_name_edit.clear()
        self.api_key_value_edit.clear()
        self.auth_combo.setCurrentIndex(self.auth_combo.findData("none"))
        self.api_key_location_combo.setCurrentIndex(self.api_key_location_combo.findData("header"))
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
            self.username_edit,
            self.password_edit,
            self.api_key_name_edit,
            self.api_key_value_edit,
            self.api_key_location_combo,
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

            try:
                self._parse_json_object(body_txt, field_name=self.tr("JSON body"))
            except ValueError:
                return False

        try:
            self._build_request_config(name=self.tr("Validation request"))
        except ValueError:
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

        for editor, field_name in (
            (self.headers_edit, self.tr("Headers")),
            (self.params_edit, self.tr("Query params")),
        ):
            raw_text = editor.text().strip() if isinstance(editor, QLineEdit) else editor.toPlainText().strip()
            if not raw_text:
                editor.setToolTip("")
                continue
            try:
                self._parse_string_map(raw_text, field_name=field_name)
            except ValueError as exc:
                editor.setToolTip(str(exc))
                return
            editor.setToolTip("")

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
            config = self._build_request_config(name=self.tr("Test request"))

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
        config = self._build_request_config(name=name)
        self.data[name] = self._serialize_request_config(config)

        write_rest_connections(self.data)

        self._dialogs.info(
            parent=self,
            title=self.tr("Saved"),
            text=self.tr("REST connection saved successfully."),
        )
        self.connections_changed.emit()

    def _serialize_request_config(self, config: RestRequestConfig) -> dict[str, Any]:
        """Serialize a request config to the persisted dialog structure."""
        payload: dict[str, Any] = {
            "url": config.url,
            "method": config.method,
            "response_path": config.response_path or "",
            "headers": dict(config.headers),
            "query_params": dict(config.query_params),
            "auth": {"type": config.auth.type if config.auth else "none"},
        }

        if config.json_body is not None:
            payload["json_body"] = dict(config.json_body)

        if config.auth is None:
            return payload

        if config.auth.type == "bearer" and config.auth.token:
            payload["auth"]["token"] = config.auth.token
        elif config.auth.type == "basic":
            payload["auth"]["username"] = config.auth.username or ""
            payload["auth"]["password"] = config.auth.password or ""
        elif config.auth.type == "api_key":
            payload["auth"]["api_key_name"] = config.auth.api_key_name or ""
            payload["auth"]["api_key_value"] = config.auth.api_key_value or ""
            payload["auth"]["api_key_location"] = config.auth.api_key_location or "header"

        return payload
