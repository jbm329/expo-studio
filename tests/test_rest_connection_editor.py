from __future__ import annotations

from PyQt6.QtWidgets import QListWidgetItem

from expo_jbm329.app.settings.rest_connection_editor import RestConnectionEditor
from expo_jbm329.gui.dialogs.service.null_dialog_service import NullDialogService


def make_editor() -> RestConnectionEditor:
    return RestConnectionEditor(dialogs=NullDialogService())


def test_on_auth_changed_enables_basic_fields_only():
    editor = make_editor()

    editor.auth_combo.setCurrentIndex(editor.auth_combo.findData("basic"))
    editor.on_auth_changed()

    assert editor.username_edit.isEnabled() is True
    assert editor.password_edit.isEnabled() is True
    assert editor.token_edit.isEnabled() is False
    assert editor.api_key_name_edit.isEnabled() is False


def test_on_auth_changed_enables_api_key_fields_only():
    editor = make_editor()

    editor.auth_combo.setCurrentIndex(editor.auth_combo.findData("api_key"))
    editor.on_auth_changed()

    assert editor.api_key_name_edit.isEnabled() is True
    assert editor.api_key_value_edit.isEnabled() is True
    assert editor.api_key_location_combo.isEnabled() is True
    assert editor.token_edit.isEnabled() is False
    assert editor.username_edit.isEnabled() is False


def test_gather_form_serializes_basic_auth():
    editor = make_editor()
    editor.url_edit.setText("https://example.com")
    editor.auth_combo.setCurrentIndex(editor.auth_combo.findData("basic"))
    editor.username_edit.setText("alice")
    editor.password_edit.setText("secret")

    cfg = editor._gather_form()

    assert cfg["auth"] == {
        "type": "basic",
        "username": "alice",
        "password": "secret",
    }


def test_gather_form_serializes_api_key_auth():
    editor = make_editor()
    editor.url_edit.setText("https://example.com")
    editor.auth_combo.setCurrentIndex(editor.auth_combo.findData("api_key"))
    editor.api_key_name_edit.setText("X-API-Key")
    editor.api_key_value_edit.setText("secret")
    editor.api_key_location_combo.setCurrentIndex(editor.api_key_location_combo.findData("query"))

    cfg = editor._gather_form()

    assert cfg["auth"] == {
        "type": "api_key",
        "api_key_name": "X-API-Key",
        "api_key_value": "secret",
        "api_key_location": "query",
    }


def test_gather_form_rejects_invalid_headers_json():
    editor = make_editor()
    editor.url_edit.setText("https://example.com")
    editor.headers_edit.setText("not json")

    try:
        editor._gather_form()
    except ValueError as exc:
        assert "Headers" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_save_changes_persists_valid_api_key_auth(monkeypatch):
    editor = make_editor()
    editor.data = {"Example": {}}
    editor.list_widget.addItem(QListWidgetItem("Example"))
    editor.list_widget.setCurrentRow(0)
    editor.url_edit.setText("https://example.com")
    editor.auth_combo.setCurrentIndex(editor.auth_combo.findData("api_key"))
    editor.api_key_name_edit.setText("X-API-Key")
    editor.api_key_value_edit.setText("secret")
    editor.api_key_location_combo.setCurrentIndex(editor.api_key_location_combo.findData("header"))

    written: dict[str, dict] = {}

    def fake_write_rest_connections(value: dict[str, dict]) -> None:
        written.update(value)

    monkeypatch.setattr(
        "expo_jbm329.app.settings.rest_connection_editor.write_rest_connections",
        fake_write_rest_connections,
    )

    editor.save_changes()

    assert written["Example"]["auth"] == {
        "type": "api_key",
        "api_key_name": "X-API-Key",
        "api_key_value": "secret",
        "api_key_location": "header",
    }
