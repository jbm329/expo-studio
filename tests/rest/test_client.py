from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from expo_jbm329.services.rest.client import RestClientError, fetch_json
from expo_jbm329.services.rest.models import RestAuthConfig, RestRequestConfig, RestRetryConfig


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


def test_fetch_json_retries_on_rate_limit_response(monkeypatch):
    sleep_calls: list[float] = []
    cfg = RestRequestConfig(
        name="Example",
        url="https://example.com",
        json_body=None,
        retry=RestRetryConfig(max_retries=2, initial_delay=0.0, max_delay=0.0, retry_status_codes=(429,)),
    )

    first = MagicMock(status_code=429, text="rate limited", headers={"Retry-After": "0"})
    second = MagicMock(status_code=200, json=lambda: {"ok": True}, text="")
    client = MagicMock()
    client.get.side_effect = [first, second]
    cm = MagicMock()
    cm.__enter__.return_value = client
    cm.__exit__.return_value = False
    monkeypatch.setattr(httpx, "Client", lambda timeout=None: cm)
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    payload, elapsed = fetch_json(cfg)

    assert payload == {"ok": True}
    assert elapsed >= 0
    assert client.get.call_count == 2
    assert sleep_calls == [0.0]
