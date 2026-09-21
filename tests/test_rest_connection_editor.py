from __future__ import annotations

from PyQt6.QtWidgets import QListWidgetItem

from expo_jbm329.app.settings.rest_connection_editor import RestConnectionEditor
from expo_jbm329.gui.dialogs.service.null_dialog_service import NullDialogService


def make_editor() -> RestConnectionEditor:
    editor = RestConnectionEditor(dialogs=NullDialogService())
    editor.show()
    return editor


def test_on_auth_changed_enables_basic_fields_only():
    editor = make_editor()

    editor.auth_combo.setCurrentIndex(editor.auth_combo.findData("basic"))
    editor.on_auth_changed()

    assert editor.username_edit.isEnabled() is True
    assert editor.password_edit.isEnabled() is True
    assert editor.auth_section.body.isVisible() is True
    assert editor.token_edit.isEnabled() is False
    assert editor.auth_widget.form_layout.labelForField(editor.token_edit).isVisible() is False
    assert editor.api_key_name_edit.isEnabled() is False


def test_on_auth_changed_enables_api_key_fields_only():
    editor = make_editor()

    editor.auth_combo.setCurrentIndex(editor.auth_combo.findData("api_key"))
    editor.on_auth_changed()

    assert editor.api_key_name_edit.isEnabled() is True
    assert editor.api_key_value_edit.isEnabled() is True
    assert editor.api_key_location_combo.isEnabled() is True
    assert editor.auth_section.body.isVisible() is True
    assert editor.token_edit.isEnabled() is False
    assert editor.username_edit.isEnabled() is False
    assert editor.auth_widget.form_layout.labelForField(editor.username_edit).isVisible() is False


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
        raise AssertionError("Expected ValueError")  # noqa: TRY003


def test_save_changes_persists_valid_api_key_auth(monkeypatch):
    editor = make_editor()
    editor.data = {
        "Example": {
            "url": "",
            "headers": {},
            "query_params": {},
            "response_path": "",
            "auth": {"type": "none"},
            "pagination": {"type": "none"},
        }
    }
    editor.list_widget.addItem(QListWidgetItem("Example"))
    editor.on_selection_changed(editor.list_widget.item(0))
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

    assert editor.data["Example"]["auth"]["type"] == "api_key"
    assert written["Example"]["auth"] == {
        "type": "api_key",
        "api_key_name": "X-API-Key",
        "api_key_value": "secret",
        "api_key_location": "header",
    }


def test_on_pagination_changed_enables_page_number_fields_only():
    editor = make_editor()

    editor.pagination_combo.setCurrentIndex(editor.pagination_combo.findData("page_number"))
    editor.on_pagination_changed()

    assert editor.page_param_edit.isEnabled() is True
    assert editor.start_page_edit.isEnabled() is True
    assert editor.page_size_param_edit.isEnabled() is True
    assert editor.page_size_edit.isEnabled() is True
    assert editor.max_pages_edit.isEnabled() is True
    assert editor.pagination_section.body.isVisible() is True


def test_on_auth_changed_hides_auth_section_when_none_selected():
    editor = make_editor()

    editor.auth_combo.setCurrentIndex(editor.auth_combo.findData("none"))
    editor.on_auth_changed()

    assert editor.auth_section.body.isVisible() is False
    assert editor.auth_section.toggle.isChecked() is False


def test_on_pagination_changed_hides_pagination_section_when_none_selected():
    editor = make_editor()

    editor.pagination_combo.setCurrentIndex(editor.pagination_combo.findData("none"))
    editor.on_pagination_changed()

    assert editor.pagination_section.body.isVisible() is False
    assert editor.pagination_section.toggle.isChecked() is False


def test_gather_form_serializes_page_number_pagination():
    editor = make_editor()
    editor.url_edit.setText("https://example.com")
    editor.pagination_combo.setCurrentIndex(editor.pagination_combo.findData("page_number"))
    editor.page_param_edit.setText("page")
    editor.start_page_edit.setText("2")
    editor.page_size_param_edit.setText("limit")
    editor.page_size_edit.setText("50")
    editor.max_pages_edit.setText("10")

    cfg = editor._gather_form()

    assert cfg["pagination"] == {
        "type": "page_number",
        "page_param": "page",
        "start_page": 2,
        "page_size_param": "limit",
        "page_size": 50,
        "max_pages": 10,
    }


def test_save_changes_persists_valid_page_number_pagination(monkeypatch):
    editor = make_editor()
    editor.data = {
        "Example": {
            "url": "",
            "headers": {},
            "query_params": {},
            "response_path": "",
            "auth": {"type": "none"},
            "pagination": {"type": "none"},
        }
    }
    editor.list_widget.addItem(QListWidgetItem("Example"))
    editor.on_selection_changed(editor.list_widget.item(0))
    editor.list_widget.setCurrentRow(0)
    editor.url_edit.setText("https://example.com")
    editor.pagination_combo.setCurrentIndex(editor.pagination_combo.findData("page_number"))
    editor.page_param_edit.setText("page")
    editor.start_page_edit.setText("2")
    editor.page_size_param_edit.setText("limit")
    editor.page_size_edit.setText("50")
    editor.max_pages_edit.setText("10")

    written: dict[str, dict] = {}

    def fake_write_rest_connections(value: dict[str, dict]) -> None:
        written.update(value)

    monkeypatch.setattr(
        "expo_jbm329.app.settings.rest_connection_editor.write_rest_connections",
        fake_write_rest_connections,
    )

    editor.save_changes()

    assert written["Example"]["pagination"] == {
        "type": "page_number",
        "page_param": "page",
        "start_page": 2,
        "page_size_param": "limit",
        "page_size": 50,
        "max_pages": 10,
    }


def test_open_scb_browser_applies_generated_query(monkeypatch):
    editor = make_editor()

    class FakeDialog:
        def __init__(self, parent=None, dialogs=None):
            self.parent = parent
            self.dialogs = dialogs

        def exec(self):
            return 1

        def get_result(self):
            return {
                "url": "https://statistikdatabasen.scb.se/api/v2/tables/TAB6471/data",
                "query_params": {
                    "lang": "sv",
                    "outputFormat": "json-stat2",
                    "valueCodes[Region]": "01,03",
                },
            }

    monkeypatch.setattr(
        "expo_jbm329.app.settings.rest_connection_editor.ScbBrowserDialog",
        FakeDialog,
    )

    editor.open_scb_browser()

    assert editor.url_edit.text() == "https://statistikdatabasen.scb.se/api/v2/tables/TAB6471/data"
    assert '"lang": "sv"' in editor.params_edit.toPlainText()
    assert '"valueCodes[Region]": "01,03"' in editor.params_edit.toPlainText()
