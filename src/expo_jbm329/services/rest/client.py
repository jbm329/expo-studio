from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from expo_jbm329.services.rest.models import (
    RestAuthConfig,
    RestPaginationConfig,
    RestRequestConfig,
)


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

    _apply_auth(headers, params, config.auth)

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


def fetch_json_pages(
    config: RestRequestConfig,
    *,
    progress_cb: Callable[[int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
    timeout: float = 30.0,
) -> tuple[list[Any], float]:
    """Fetch one or more paged JSON payloads from a REST endpoint."""
    config.validate()

    pagination = config.pagination
    if pagination is None or pagination.type == "none":
        payload, elapsed = fetch_json(
            config,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
            timeout=timeout,
        )
        return [payload], elapsed

    return _fetch_page_number_payloads(
        config,
        pagination=pagination,
        progress_cb=progress_cb,
        cancel_cb=cancel_cb,
        timeout=timeout,
    )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _apply_auth(
    headers: dict[str, str],
    params: dict[str, str],
    auth: RestAuthConfig | None,
) -> None:
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

    if auth.type == "api_key":
        if not auth.api_key_name:
            raise RestClientError("API key auth requires parameter name")
        if not auth.api_key_value:
            raise RestClientError("API key auth requires value")
        if auth.api_key_location == "header":
            headers[auth.api_key_name] = auth.api_key_value
            return
        if auth.api_key_location == "query":
            params[auth.api_key_name] = auth.api_key_value
            return
        raise RestClientError("API key auth requires location 'header' or 'query'")

    raise RestClientError(f"Unsupported auth type: {auth.type}")


def _fetch_page_number_payloads(
    config: RestRequestConfig,
    *,
    pagination: RestPaginationConfig,
    progress_cb: Callable[[int], None] | None,
    cancel_cb: Callable[[], bool] | None,
    timeout: float,
) -> tuple[list[Any], float]:
    """Fetch paginated JSON payloads using page-number query parameters."""
    payloads: list[Any] = []
    total_elapsed = 0.0
    page = pagination.start_page
    page_limit = pagination.max_pages or 1_000_000

    while len(payloads) < page_limit:
        if cancel_cb and cancel_cb():
            raise RestClientError("Request cancelled")

        page_params = dict(config.query_params or {})
        page_params[pagination.page_param or "page"] = str(page)

        if pagination.page_size is not None and pagination.page_size_param is not None:
            page_params[pagination.page_size_param] = str(pagination.page_size)

        page_config = RestRequestConfig(
            name=config.name,
            url=config.url,
            json_body=config.json_body,
            method=config.method,
            headers=config.headers,
            query_params=page_params,
            response_path=config.response_path,
            auth=config.auth,
            pagination=None,
        )

        payload, elapsed = fetch_json(
            page_config,
            progress_cb=progress_cb,
            cancel_cb=cancel_cb,
            timeout=timeout,
        )
        total_elapsed += elapsed
        payloads.append(payload)

        if progress_cb and pagination.max_pages:
            progress = int((len(payloads) / pagination.max_pages) * 100)
            progress_cb(min(progress, 100))

        if not _should_continue_page_number_pagination(payload):
            break

        page += 1

    return payloads, total_elapsed


def _should_continue_page_number_pagination(payload: Any) -> bool:
    """Return whether a paged fetch should continue based on payload contents."""
    if isinstance(payload, list):
        return len(payload) > 0

    if isinstance(payload, dict):
        if not payload:
            return False

        for value in payload.values():
            if isinstance(value, list):
                return len(value) > 0

        return True

    return False
