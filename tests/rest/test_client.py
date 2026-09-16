from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from expo_jbm329.services.rest.client import RestClientError, fetch_json
from expo_jbm329.services.rest.models import RestAuthConfig, RestRequestConfig


def test_fetch_json_rejects_bad_auth():
    cfg = RestRequestConfig(
        name="Example",
        url="https://example.com",
        method="GET",
        auth=RestAuthConfig(type="basic", username="", password=""),
        json_body=None,
    )

    with pytest.raises(ValueError, match="Basic auth requires username and password"):
        fetch_json(cfg)


def test_fetch_json_parses_response(monkeypatch):
    cfg = RestRequestConfig(name="Example", url="https://example.com", json_body=None)
    response = MagicMock(status_code=200, json=lambda: {"ok": True}, text="")
    client = MagicMock()
    client.get.return_value = response
    cm = MagicMock()
    cm.__enter__.return_value = client
    cm.__exit__.return_value = False
    monkeypatch.setattr(httpx, "Client", lambda timeout=None: cm)

    payload, elapsed = fetch_json(cfg)

    assert payload == {"ok": True}
    assert elapsed >= 0


def test_fetch_json_supports_api_key_header_auth(monkeypatch):
    cfg = RestRequestConfig(
        name="Example",
        url="https://example.com",
        json_body=None,
        auth=RestAuthConfig(
            type="api_key",
            api_key_name="X-API-Key",
            api_key_value="secret",
            api_key_location="header",
        ),
    )
    response = MagicMock(status_code=200, json=lambda: {"ok": True}, text="")
    client = MagicMock()
    client.get.return_value = response
    cm = MagicMock()
    cm.__enter__.return_value = client
    cm.__exit__.return_value = False
    monkeypatch.setattr(httpx, "Client", lambda timeout=None: cm)

    fetch_json(cfg)

    assert client.get.call_args.kwargs["headers"]["X-API-Key"] == "secret"


def test_fetch_json_supports_api_key_query_auth(monkeypatch):
    cfg = RestRequestConfig(
        name="Example",
        url="https://example.com",
        json_body=None,
        auth=RestAuthConfig(
            type="api_key",
            api_key_name="api_key",
            api_key_value="secret",
            api_key_location="query",
        ),
    )
    response = MagicMock(status_code=200, json=lambda: {"ok": True}, text="")
    client = MagicMock()
    client.get.return_value = response
    cm = MagicMock()
    cm.__enter__.return_value = client
    cm.__exit__.return_value = False
    monkeypatch.setattr(httpx, "Client", lambda timeout=None: cm)

    fetch_json(cfg)

    assert client.get.call_args.kwargs["params"]["api_key"] == "secret"
