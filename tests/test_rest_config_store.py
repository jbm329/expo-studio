from __future__ import annotations

from expo_jbm329.app.settings.config_store import _normalize_rest_entry


def test_normalize_rest_entry_normalizes_method_and_basic_auth():
    normalized = _normalize_rest_entry({
        "url": " https://example.com ",
        "method": "post",
        "auth": {
            "type": "basic",
            "username": "alice",
            "password": "secret",
        },
    })

    assert normalized["url"] == "https://example.com"
    assert normalized["method"] == "POST"
    assert normalized["auth"] == {
        "type": "basic",
        "username": "alice",
        "password": "secret",
    }


def test_normalize_rest_entry_normalizes_api_key_auth():
    normalized = _normalize_rest_entry({
        "url": "https://example.com",
        "auth": {
            "type": "api_key",
            "api_key_name": "X-API-Key",
            "api_key_value": "secret",
            "api_key_location": "HEADER",
        },
    })

    assert normalized["method"] == "GET"
    assert normalized["auth"] == {
        "type": "api_key",
        "api_key_name": "X-API-Key",
        "api_key_value": "secret",
        "api_key_location": "header",
    }


def test_normalize_rest_entry_normalizes_page_number_pagination():
    normalized = _normalize_rest_entry({
        "url": "https://example.com",
        "pagination": {
            "type": "page_number",
            "page_param": " page ",
            "start_page": "2",
            "page_size_param": " limit ",
            "page_size": "100",
            "max_pages": "5",
        },
    })

    assert normalized["pagination"] == {
        "type": "page_number",
        "page_param": "page",
        "start_page": 2,
        "page_size_param": "limit",
        "page_size": 100,
        "max_pages": 5,
    }
