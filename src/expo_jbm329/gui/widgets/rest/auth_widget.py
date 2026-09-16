"""Authentication configuration widget for REST connections."""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QFormLayout, QLineEdit, QWidget


class RestAuthWidget(QWidget):
    """Compact editor for REST authentication settings."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.auth_combo = QComboBox()
        self.auth_combo.addItem("None", userData="none")
        self.auth_combo.addItem("Bearer", userData="bearer")
        self.auth_combo.addItem("Basic", userData="basic")
        self.auth_combo.addItem("API key", userData="api_key")
        self.auth_combo.addItem("OAuth2", userData="oauth2")

        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_name_edit = QLineEdit()
        self.api_key_value_edit = QLineEdit()
        self.api_key_value_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_location_combo = QComboBox()
        self.api_key_location_combo.addItem("Header", userData="header")
        self.api_key_location_combo.addItem("Query parameter", userData="query")

        self.grant_type_combo = QComboBox()
        self.grant_type_combo.addItem("Client credentials", userData="client_credentials")
        self.grant_type_combo.addItem("Refresh token", userData="refresh_token")

        self.token_url_edit = QLineEdit()
        self.token_url_edit.setPlaceholderText("https://example.com/oauth/token")
        self.client_id_edit = QLineEdit()
        self.client_secret_edit = QLineEdit()
        self.client_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.scope_edit = QLineEdit()
        self.scope_edit.setPlaceholderText("read write")
        self.refresh_token_edit = QLineEdit()
        self.refresh_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.refresh_token_edit.setPlaceholderText("paste refresh token")

        self.form_layout = QFormLayout(self)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.addRow("Type:", self.auth_combo)
        self.form_layout.addRow("Bearer token", self.token_edit)
        self.form_layout.addRow("Basic username", self.username_edit)
        self.form_layout.addRow("Basic password", self.password_edit)
        self.form_layout.addRow("API key name", self.api_key_name_edit)
        self.form_layout.addRow("API key value", self.api_key_value_edit)
        self.form_layout.addRow("API key location", self.api_key_location_combo)
        self.form_layout.addRow("OAuth2 token URL", self.token_url_edit)
        self.form_layout.addRow("OAuth2 client ID", self.client_id_edit)
        self.form_layout.addRow("OAuth2 client secret", self.client_secret_edit)
        self.form_layout.addRow("OAuth2 grant type", self.grant_type_combo)
        self.form_layout.addRow("OAuth2 scope", self.scope_edit)
        self.form_layout.addRow("OAuth2 refresh token", self.refresh_token_edit)

        self.apply_visibility()

    def apply_visibility(self) -> None:
        """Show only fields relevant to the selected auth type."""
        auth = self.auth_combo.currentData()
        is_bearer = auth == "bearer"
        is_basic = auth == "basic"
        is_api_key = auth == "api_key"
        is_oauth2 = auth == "oauth2"

        self._set_state(self.token_edit, is_bearer)
        self._set_state(self.username_edit, is_basic)
        self._set_state(self.password_edit, is_basic)
        self._set_state(self.api_key_name_edit, is_api_key)
        self._set_state(self.api_key_value_edit, is_api_key)
        self._set_state(self.api_key_location_combo, is_api_key)
        self._set_state(self.token_url_edit, is_oauth2)
        self._set_state(self.client_id_edit, is_oauth2)
        self._set_state(self.client_secret_edit, is_oauth2)
        self._set_state(self.grant_type_combo, is_oauth2)
        self._set_state(self.scope_edit, is_oauth2)
        self._set_state(self.refresh_token_edit, is_oauth2)
        self._set_oauth_grant_visibility()

    def _set_oauth_grant_visibility(self) -> None:
        """Hide refresh-token field unless the selected grant requires it."""
        is_refresh = self.grant_type_combo.currentData() == "refresh_token"
        is_oauth2 = self.auth_combo.currentData() == "oauth2"
        self.refresh_token_edit.setEnabled(is_refresh and is_oauth2)
        self._set_field_visible(self.refresh_token_edit, is_oauth2 and is_refresh)

    def _set_state(self, widget: QWidget, visible: bool) -> None:
        widget.setEnabled(visible)
        self._set_field_visible(widget, visible)

    def _set_field_visible(self, widget: QWidget, visible: bool) -> None:
        widget.setVisible(visible)
        label = self.form_layout.labelForField(widget)
        if label is not None:
            label.setVisible(visible)
