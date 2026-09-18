from __future__ import annotations

from expo_jbm329.services.rest.models import RestAuthConfig, RestRequestConfig
from expo_jbm329.services.rest.registry import RestConnectionRegistry


def test_registry_register_and_capabilities():
    registry = RestConnectionRegistry()
    req = RestRequestConfig(name="Example", url="https://example.com", json_body=None)

    registry.register(name="Example", request=req, source="sample", read_only=True, folder="samples")

    assert registry.exists("Example")
    assert registry.can_edit("Example") is False
    assert registry.can_delete("Example") is False
    assert registry.get("Example").request == req


def test_registry_load_and_reload_user_connections():
    registry = RestConnectionRegistry()
    raw = {
        "User": {
            "url": "https://example.com",
            "method": "post",
            "json_body": {},
            "headers": {},
            "query_params": {},
            "response_path": None,
            "auth": {"type": "none"},
        }
    }

    registry.load_user_connections(raw)
    assert registry.exists("User")
    assert registry.can_edit("User")

    registry.reload_user_connections({})
    assert registry.exists("User") is False


def test_registry_load_user_connections_supports_api_key_auth():
    registry = RestConnectionRegistry()
    raw = {
        "User": {
            "url": "https://example.com",
            "method": "GET",
            "headers": {},
            "query_params": {},
            "response_path": None,
            "auth": {
                "type": "api_key",
                "api_key_name": "X-API-Key",
                "api_key_value": "secret",
                "api_key_location": "header",
            },
        }
    }

    registry.load_user_connections(raw)
    entry = registry.get("User")

    assert entry is not None
    assert entry.request.auth == RestAuthConfig(
        type="api_key",
        api_key_name="X-API-Key",
        api_key_value="secret",
        api_key_location="header",
    )


def test_registry_skips_incomplete_user_connections_with_empty_url():
    registry = RestConnectionRegistry()

    registry.load_user_connections({
        "Draft": {
            "url": "",
            "method": "GET",
            "headers": {},
            "query_params": {},
            "response_path": None,
            "auth": {"type": "none"},
        }
    })

    assert registry.exists("Draft") is False
