"""REST Connection Editor dialog for managing REST API connections."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal, override

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from expo_jbm329.app.settings.config_store import (
    read_rest_connections,
    write_rest_connections,
)
from expo_jbm329.gui.dialogs.rest.scb_browser_dialog import ScbBrowserDialog
from expo_jbm329.gui.dialogs.service.qt_dialog_service import QtDialogService
from expo_jbm329.gui.widgets.rest.auth_widget import RestAuthWidget
from expo_jbm329.gui.widgets.rest.pagination_widget import RestPaginationWidget
from expo_jbm329.services.rest.client import fetch_json
from expo_jbm329.services.rest.models import (
    RestAuthConfig,
    RestPaginationConfig,
    RestRequestConfig,
)
from expo_jbm329.services.rest.normalizer import normalize_json_to_df
from expo_jbm329.services.rest.schema import build_response_preview
from expo_jbm329.utils.format_utils import fmt_shape

if TYPE_CHECKING:
    from expo_jbm329.gui.dialogs.service.dialog_service import DialogService
    from expo_jbm329.workbench.icon.icon_service import IconService


class _SectionPanel(QWidget):
    """Small collapsible panel used to group editor fields."""

    def __init__(
        self,
        title: str,
        *,
        checked: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.toggle = QCheckBox(title)
        self.toggle.setChecked(checked)
        self.body = QWidget()
        self.body_layout = QFormLayout()
        self.body_layout.setContentsMargins(16, 0, 0, 0)
        self.body.setLayout(self.body_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)
        self.setLayout(layout)

        self.toggle.toggled.connect(self.body.setVisible)
        self.body.setVisible(checked)


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
        self._dialogs = dialogs or QtDialogService()
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

        self.btn_scb_browser = QPushButton(self.tr("SCB query builder…"))
        self.btn_scb_browser.clicked.connect(self.open_scb_browser)

        self.url_edit = QLineEdit()

        self.method_combo = QComboBox()
        self.method_combo.addItem("GET", userData="GET")
        self.method_combo.addItem("POST", userData="POST")
        self.method_combo.currentIndexChanged.connect(self.on_method_changed)

        self.body_edit = QPlainTextEdit()
        self.body_edit.setPlaceholderText('{\n  "query": [],\n  "response": { "format": "JSON" }\n}')
        self.body_edit.setMinimumHeight(120)

        self.response_path_edit = QLineEdit()
        self.response_path_edit.setPlaceholderText("e.g. hourly, data.items, 1, results.0.values")

        self.auth_widget = RestAuthWidget(self)
        self.auth_combo = self.auth_widget.auth_combo
        self.auth_combo.currentIndexChanged.connect(self.on_auth_changed)
        self.token_edit = self.auth_widget.token_edit
        self.username_edit = self.auth_widget.username_edit
        self.password_edit = self.auth_widget.password_edit
        self.api_key_name_edit = self.auth_widget.api_key_name_edit
        self.api_key_value_edit = self.auth_widget.api_key_value_edit
        self.api_key_location_combo = self.auth_widget.api_key_location_combo
        self.grant_type_combo = self.auth_widget.grant_type_combo
        self.grant_type_combo.currentIndexChanged.connect(self.on_oauth2_grant_changed)
        self.token_url_edit = self.auth_widget.token_url_edit
        self.client_id_edit = self.auth_widget.client_id_edit
        self.client_secret_edit = self.auth_widget.client_secret_edit
        self.scope_edit = self.auth_widget.scope_edit
        self.refresh_token_edit = self.auth_widget.refresh_token_edit

        self.pagination_widget = RestPaginationWidget(self)
        self.pagination_combo = self.pagination_widget.pagination_combo
        self.pagination_combo.currentIndexChanged.connect(self.on_pagination_changed)
        self.page_param_edit = self.pagination_widget.page_param_edit
        self.start_page_edit = self.pagination_widget.start_page_edit
        self.page_size_param_edit = self.pagination_widget.page_size_param_edit
        self.page_size_edit = self.pagination_widget.page_size_edit
        self.max_pages_edit = self.pagination_widget.max_pages_edit

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
        wizard_panel = _SectionPanel(self.tr("Wizards"), checked=True)
        wizard_btns = QHBoxLayout()
        wizard_btns.addWidget(self.btn_scb_browser)
        wizard_panel.body_layout.addRow(wizard_btns)
        general_panel = _SectionPanel(self.tr("General"), checked=True)
        general_panel.body_layout.addRow(self.tr("URL:"), self.url_edit)
        general_panel.body_layout.addRow(self.tr("Method:"), self.method_combo)
        general_panel.body_layout.addRow(self.tr("Response path:"), self.response_path_edit)

        request_panel = _SectionPanel(self.tr("Request"), checked=True)
        request_panel.body_layout.addRow(self.tr("JSON body:"), self.body_edit)
        request_panel.body_layout.addRow(self.tr("Headers (JSON):"), self.headers_edit)
        request_panel.body_layout.addRow(self.tr("Query params (JSON):"), self.params_edit)

        self.auth_section = _SectionPanel(self.tr("Authentication"), checked=False)
        self.auth_section.body_layout.addRow(self.auth_widget)

        self.pagination_section = _SectionPanel(self.tr("Pagination"), checked=False)
        self.pagination_section.body_layout.addRow(self.pagination_widget)
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

        form_container = QWidget()
        form_layout = QVBoxLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.addWidget(wizard_panel)
        form_layout.addWidget(general_panel)
        form_layout.addWidget(request_panel)
        form_layout.addWidget(self.auth_section)
        form_layout.addWidget(self.pagination_section)
        form_layout.addStretch(1)
        form_container.setLayout(form_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_container)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        right = QVBoxLayout()
        right.addWidget(scroll)
        right.addLayout(btns)

        main = QHBoxLayout()
        main.addLayout(left, 1)
        main.addLayout(right, 2)

        self.setLayout(main)

        self.on_auth_changed()
        self.on_oauth2_grant_changed()
        self.on_pagination_changed()

    # ----------------------------------------------------------------------
    # Update icon
    # ----------------------------------------------------------------------
    def _update_icon(self):
        """Updates the window icon using the IconService or a fallback path."""
        icon = self._icon_service.get("rest") if self._icon_service else QIcon(":/icons/dark/themes/dark/rest.png")
        self.setWindowIcon(icon)

    # ------------------------------------------------------------------
    # showEvent
    # ------------------------------------------------------------------
    @override
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
        self.auth_section.toggle.setChecked(auth != "none")
        self.auth_section.body.setVisible(auth != "none")
        self.auth_widget.apply_visibility()
        self.on_oauth2_grant_changed()

    def on_oauth2_grant_changed(self):
        """Handles the change in OAuth2 grant type selection."""
        self.auth_widget.set_oauth_grant_visibility()

    def on_pagination_changed(self):
        """Handles the change in pagination mode selection."""
        is_page_number = self.pagination_combo.currentData() == "page_number"
        self.pagination_section.toggle.setChecked(is_page_number)
        self.pagination_section.body.setVisible(is_page_number)
        self.pagination_widget.apply_visibility()

    def _apply_helper_result(self, result: dict[str, Any] | None) -> None:
        """Apply an SCB helper result to the generic REST form."""
        if not result:
            return

        self.url_edit.setText(result["url"])
        self.method_combo.setCurrentIndex(self.method_combo.findData("GET"))
        self.params_edit.setPlainText(json.dumps(result["query_params"], indent=2))
        self.params_edit.moveCursor(QTextCursor.MoveOperation.Start)

    def open_scb_browser(self) -> None:
        """Open the SCB browser and apply a selected query to the form."""
        dialog = ScbBrowserDialog(self, dialogs=self._dialogs)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_helper_result(dialog.get_result())

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
        self.headers_edit.setText(json.dumps(headers) if headers else "")

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
        self.token_url_edit.setText(str(cfg.get("auth", {}).get("token_url", "")))
        self.client_id_edit.setText(str(cfg.get("auth", {}).get("client_id", "")))
        self.client_secret_edit.setText(str(cfg.get("auth", {}).get("client_secret", "")))
        self.scope_edit.setText(str(cfg.get("auth", {}).get("scope", "")))
        self.refresh_token_edit.setText(str(cfg.get("auth", {}).get("refresh_token", "")))

        grant_type = cfg.get("auth", {}).get("grant_type", "client_credentials")
        grant_ix = self.grant_type_combo.findData(grant_type)
        if grant_ix >= 0:
            self.grant_type_combo.setCurrentIndex(grant_ix)

        api_key_location = cfg.get("auth", {}).get("api_key_location", "header")
        api_key_ix = self.api_key_location_combo.findData(api_key_location)
        if api_key_ix >= 0:
            self.api_key_location_combo.setCurrentIndex(api_key_ix)

        pagination = cfg.get("pagination") or {"type": "none"}
        pagination_type = pagination.get("type", "none")
        pagination_ix = self.pagination_combo.findData(pagination_type)
        if pagination_ix >= 0:
            self.pagination_combo.setCurrentIndex(pagination_ix)

        self.page_param_edit.setText(str(pagination.get("page_param", "")))
        self.start_page_edit.setText(str(pagination.get("start_page", "1")))
        self.page_size_param_edit.setText(str(pagination.get("page_size_param", "")))
        self.page_size_edit.setText(str(pagination.get("page_size", "")))
        self.max_pages_edit.setText(str(pagination.get("max_pages", "")))

        self._set_fields_enabled(True)
        self.on_pagination_changed()
        self._update_action_buttons()

    # ==================================================================
    # Helpers
    # ==================================================================
    def _gather_form(self) -> dict:
        """Collect and validate the form into a persisted config shape."""
        raw_method = self.method_combo.currentData()
        method: Literal["GET", "POST"] = "POST" if raw_method == "POST" else "GET"
        auth_type = self.auth_combo.currentData()
        pagination_type = self.pagination_combo.currentData()

        cfg: dict[str, Any] = {
            "url": self.url_edit.text().strip(),
            "method": method,
            "response_path": self.response_path_edit.text().strip(),
            "headers": {},
            "query_params": {},
            "auth": {"type": auth_type},
            "pagination": {"type": "none"},
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
        elif auth_type == "oauth2":
            cfg["auth"]["token_url"] = self.token_url_edit.text().strip()
            cfg["auth"]["client_id"] = self.client_id_edit.text().strip()
            cfg["auth"]["client_secret"] = self.client_secret_edit.text().strip()
            cfg["auth"]["grant_type"] = self.grant_type_combo.currentData()
            cfg["auth"]["scope"] = self.scope_edit.text().strip()
            cfg["auth"]["refresh_token"] = self.refresh_token_edit.text().strip()

        if pagination_type == "page_number":
            page_param = self.page_param_edit.text().strip()
            if not page_param:
                raise ValueError(self.tr("Page-number pagination requires a page parameter name"))
            cfg["pagination"] = {
                "type": "page_number",
                "page_param": page_param,
                "start_page": self._parse_positive_int(
                    self.start_page_edit.text(),
                    field_name=self.tr("Start page"),
                    default=1,
                ),
            }
            page_size_param = self.page_size_param_edit.text().strip()
            if page_size_param:
                cfg["pagination"]["page_size_param"] = page_size_param
            page_size = self._parse_optional_positive_int(
                self.page_size_edit.text(),
                field_name=self.tr("Page size"),
            )
            if page_size is not None:
                cfg["pagination"]["page_size"] = page_size
            max_pages = self._parse_optional_positive_int(
                self.max_pages_edit.text(),
                field_name=self.tr("Max pages"),
            )
            if max_pages is not None:
                cfg["pagination"]["max_pages"] = max_pages

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
        pagination_raw = cfg_raw.get("pagination") or {"type": "none"}

        auth = RestAuthConfig(
            type=auth_raw.get("type", "none"),
            token=auth_raw.get("token"),
            username=auth_raw.get("username"),
            password=auth_raw.get("password"),
            api_key_name=auth_raw.get("api_key_name"),
            api_key_value=auth_raw.get("api_key_value"),
            api_key_location=auth_raw.get("api_key_location"),
            grant_type=auth_raw.get("grant_type"),
            token_url=auth_raw.get("token_url"),
            client_id=auth_raw.get("client_id"),
            client_secret=auth_raw.get("client_secret"),
            scope=auth_raw.get("scope"),
            refresh_token=auth_raw.get("refresh_token"),
            access_token=auth_raw.get("access_token"),
        )

        pagination = None
        if pagination_raw.get("type") == "page_number":
            pagination = RestPaginationConfig(
                type="page_number",
                page_param=pagination_raw.get("page_param"),
                start_page=int(pagination_raw.get("start_page", 1)),
                page_size_param=pagination_raw.get("page_size_param"),
                page_size=pagination_raw.get("page_size"),
                max_pages=pagination_raw.get("max_pages"),
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
            pagination=pagination,
        )
        config.validate()
        return config

    def _parse_json_object(self, text: str, *, field_name: str) -> dict[str, object]:
        """Parse a JSON object field from the editor."""
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(self.tr("{field} must contain valid JSON.").format(field=field_name)) from exc

        if not isinstance(value, dict):
            raise ValueError(self.tr("{field} must be a JSON object.").format(field=field_name))

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
        self.token_url_edit.clear()
        self.client_id_edit.clear()
        self.client_secret_edit.clear()
        self.scope_edit.clear()
        self.refresh_token_edit.clear()
        self.grant_type_combo.setCurrentIndex(self.grant_type_combo.findData("client_credentials"))
        self.page_param_edit.clear()
        self.start_page_edit.clear()
        self.page_size_param_edit.clear()
        self.page_size_edit.clear()
        self.max_pages_edit.clear()
        self.auth_combo.setCurrentIndex(self.auth_combo.findData("none"))
        self.api_key_location_combo.setCurrentIndex(self.api_key_location_combo.findData("header"))
        self.grant_type_combo.setCurrentIndex(self.grant_type_combo.findData("client_credentials"))
        self.pagination_combo.setCurrentIndex(self.pagination_combo.findData("none"))
        self.on_oauth2_grant_changed()
        self.on_pagination_changed()
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
            self.token_url_edit,
            self.client_id_edit,
            self.client_secret_edit,
            self.grant_type_combo,
            self.scope_edit,
            self.refresh_token_edit,
            self.pagination_combo,
            self.page_param_edit,
            self.start_page_edit,
            self.page_size_param_edit,
            self.page_size_edit,
            self.max_pages_edit,
            self.headers_edit,
            self.params_edit,
        ):
            w.setEnabled(enabled)

    def _set_auth_row_state(self, widget: QWidget, visible: bool) -> None:
        """Show or hide an authentication detail row."""
        widget.setEnabled(visible)
        self._set_row_visible(widget, visible)

    def _set_pagination_row_state(self, widget: QWidget, visible: bool) -> None:
        """Show or hide a pagination detail row."""
        widget.setEnabled(visible)
        self._set_row_visible(widget, visible)

    def _set_row_visible(self, widget: QWidget, visible: bool) -> None:
        """Show or hide a row managed by one of the section form layouts."""
        widget.setVisible(visible)
        label = self.auth_section.body_layout.labelForField(widget)
        if label is None and hasattr(self.auth_widget, "form_layout"):
            label = self.auth_widget.form_layout.labelForField(widget)
        if label is None:
            label = self.pagination_section.body_layout.labelForField(widget)
        if label is None and hasattr(self.pagination_widget, "form_layout"):
            label = self.pagination_widget.form_layout.labelForField(widget)
        if label is not None:
            label.setVisible(visible)

    def _parse_positive_int(self, raw_value: str, *, field_name: str, default: int) -> int:
        """Parse a positive integer field from the form."""
        trimmed = raw_value.strip()
        if not trimmed:
            return default
        try:
            value = int(trimmed)
        except ValueError as exc:
            raise ValueError(self.tr("{field} must be an integer").format(field=field_name)) from exc
        if value < 1:
            raise ValueError(self.tr("{field} must be >= 1").format(field=field_name))
        return value

    def _parse_optional_positive_int(self, raw_value: str, *, field_name: str) -> int | None:
        """Parse an optional positive integer field from the form."""
        trimmed = raw_value.strip()
        if not trimmed:
            return None
        try:
            value = int(trimmed)
        except ValueError as exc:
            raise ValueError(self.tr("{field} must be an integer").format(field=field_name)) from exc
        if value < 1:
            raise ValueError(self.tr("{field} must be >= 1").format(field=field_name))
        return value

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

        if self.pagination_combo.currentData() == "page_number":
            page_param = self.page_param_edit.text().strip()
            if not page_param:
                return False
            try:
                self._parse_positive_int(self.start_page_edit.text(), field_name=self.tr("Start page"), default=1)
                self._parse_optional_positive_int(self.page_size_edit.text(), field_name=self.tr("Page size"))
                self._parse_optional_positive_int(self.max_pages_edit.text(), field_name=self.tr("Max pages"))
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

        if self.pagination_combo.currentData() == "page_number":
            if not self.page_param_edit.text().strip():
                self.page_param_edit.setToolTip(self.tr("Page-number pagination requires a page parameter name"))
                return
            self.page_param_edit.setToolTip("")
            try:
                self._parse_positive_int(self.start_page_edit.text(), field_name=self.tr("Start page"), default=1)
                self._parse_optional_positive_int(self.page_size_edit.text(), field_name=self.tr("Page size"))
                self._parse_optional_positive_int(self.max_pages_edit.text(), field_name=self.tr("Max pages"))
            except ValueError as exc:
                self.page_size_edit.setToolTip(str(exc))
                return
            self.page_size_edit.setToolTip("")

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
            "pagination": {"type": "none"},
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
                preview = build_response_preview(
                    payload,
                    response_path=config.response_path,
                    limit=5,
                )
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
            ) as exc:
                self._dialogs.critical(
                    parent=self,
                    title=self.tr("Invalid response path"),
                    text=self.tr("The response path could not be applied to the API response.\n\n{error}").format(
                        error=str(exc)
                    ),
                )
                return

            rows, cols = fmt_shape(df)
            column_summary = ", ".join(preview["columns"]) if preview["columns"] else self.tr("none")
            sample_data = preview["sample"][:1]
            sample_text = ""
            if sample_data:
                sample_text = "\n\nSample row: " + str(sample_data[0])

            text = self.tr(
                "API test successful.\n\nReturned {rows} rows and {cols} columns.\n"
                "Columns: {columns}.\nTime: {sec:.2f}s{sample}"
            ).format(
                rows=rows,
                cols=cols,
                columns=column_summary,
                sec=_elapsed,
                sample=sample_text,
            )

            self._dialogs.info(parent=self, title=self.tr("Test successful"), text=text)

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
        ) as exc:
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
            "pagination": {"type": "none"},
        }

        if config.json_body is not None:
            payload["json_body"] = dict(config.json_body)

        if config.pagination is not None and config.pagination.type == "page_number":
            payload["pagination"] = {
                "type": "page_number",
                "page_param": config.pagination.page_param or "",
                "start_page": config.pagination.start_page,
            }
            if config.pagination.page_size_param:
                payload["pagination"]["page_size_param"] = config.pagination.page_size_param
            if config.pagination.page_size is not None:
                payload["pagination"]["page_size"] = config.pagination.page_size
            if config.pagination.max_pages is not None:
                payload["pagination"]["max_pages"] = config.pagination.max_pages

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
        elif config.auth.type == "oauth2":
            payload["auth"]["token_url"] = config.auth.token_url or ""
            payload["auth"]["client_id"] = config.auth.client_id or ""
            payload["auth"]["client_secret"] = config.auth.client_secret or ""
            payload["auth"]["grant_type"] = config.auth.grant_type or "client_credentials"
            payload["auth"]["scope"] = config.auth.scope or ""
            payload["auth"]["refresh_token"] = config.auth.refresh_token or ""

        return payload
