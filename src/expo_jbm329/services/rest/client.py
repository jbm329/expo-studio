from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from expo_jbm329.services.rest.models import RestAuthConfig, RestRequestConfig


class RestClientError(RuntimeError):
    """Raised when a REST request fails."""

def fetch_json(
    config: RestRequestConfig,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
    timeout: float = 30.0,
) -> tuple[Any, float]:
    """Fetch JSON data from a REST endpoint.

    This function performs a synchronous HTTP GET request and returns
    the parsed JSON payload along with the elapsed time.

    Args:
        config: REST request configuration.
        progress_cb: Optional progress callback (0..100).
        cancel_cb: Optional cancellation callback.
        timeout: Request timeout in seconds.

    Returns:
        A tuple of (json_payload, elapsed_seconds).

    Raises:
        RestClientError: If the request fails or returns a non-200 status.
    """
    config.validate()

    if cancel_cb and cancel_cb():
        raise RestClientError("Request cancelled before start")

    headers = dict(config.headers or {})
    params = dict(config.query_params or {})

    _apply_auth(headers, config.auth)

    # Good default for APIs like SCB / World Bank
    headers.setdefault("Accept", "application/json")

    t0 = time.perf_counter()

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
            if config.method == "POST":
                response = client.post(
                    config.url,
                    headers=headers,
                    params=params,
                    json=config.json_body,
                )
            else:
                response = client.get(
                    config.url,
                    headers=headers,
                    params=params,
                )
    except httpx.RequestError as exc:
        raise RestClientError(f"Request failed: {exc}") from exc

    if cancel_cb and cancel_cb():
        raise RestClientError("Request cancelled")

    if response.status_code != 200:
        body = response.text[:500] if response.text else ""
        raise RestClientError(f"HTTP {response.status_code}: {body}")

    try:
        payload = response.json()
    except Exception as exc:
        raise RestClientError("Response is not valid JSON") from exc

    elapsed = time.perf_counter() - t0

    return payload, elapsed


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _apply_auth(headers: dict[str, str], auth: RestAuthConfig | None) -> None:
    """Apply authentication configuration to request headers."""
    if not auth or auth.type == "none":
        return

    if auth.type == "bearer":
        if not auth.token:
            raise RestClientError("Bearer auth requires token")
        headers["Authorization"] = f"Bearer {auth.token}"
        return

    if auth.type == "basic":
        if not auth.username or not auth.password:
            raise RestClientError("Basic auth requires username and password")
        import base64
        raw = f"{auth.username}:{auth.password}".encode("utf-8")
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        return

    raise RestClientError(f"Unsupported auth type: {auth.type}")

