
"""REST client implementation."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx

from expo_jbm329.services.rest.models import (
    RestAuthConfig,
    RestPaginationConfig,
    RestRequestConfig,
    RestRetryConfig,
)

if TYPE_CHECKING:
    from collections.abc import Callable


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

    retry_cfg = config.retry or RestRetryConfig()

    if cancel_cb and cancel_cb():
        msg = "Request cancelled before start"
        raise RestClientError(msg)

    for attempt in range(retry_cfg.max_retries + 1):
        headers = dict(config.headers or {})
        params = dict(config.query_params or {})

        _apply_auth(headers, params, config.auth, timeout=timeout)
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
            if attempt < retry_cfg.max_retries:
                _sleep_for_retry(attempt, retry_cfg, None, cancel_cb=cancel_cb)
                continue
            msg_0 = f"Request failed: {exc}"
            raise RestClientError(msg_0) from exc

        if cancel_cb and cancel_cb():
            msg = "Request cancelled"
            raise RestClientError(msg)

        if response.status_code in retry_cfg.retry_status_codes and attempt < retry_cfg.max_retries:
            _sleep_for_retry(attempt, retry_cfg, response, cancel_cb=cancel_cb)
            continue

        if response.status_code != 200:
            body = response.text[:500] if response.text else ""
            msg_0 = f"HTTP {response.status_code}: {body}"
            raise RestClientError(msg_0)

        try:
            payload = response.json()
        except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
            msg = "Response is not valid JSON"
            raise RestClientError(msg) from exc

        elapsed = time.perf_counter() - t0
        return payload, elapsed

    msg = "Request failed after retries"
    raise RestClientError(msg)


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

def _sleep_for_retry(
    attempt: int,
    retry_cfg: RestRetryConfig,
    response: httpx.Response | None,
    *,
    cancel_cb: Callable[[], bool] | None = None,
) -> None:
    """Sleep using the configured retry delay and optional Retry-After header."""
    if cancel_cb and cancel_cb():
        msg = "Request cancelled"
        raise RestClientError(msg)

    if retry_cfg.respect_retry_after and response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = 0.0
            time.sleep(delay)
            return

    delay = min(retry_cfg.initial_delay * (retry_cfg.backoff_factor ** attempt), retry_cfg.max_delay)
    time.sleep(delay)


def _fetch_oauth2_access_token(auth: RestAuthConfig, *, timeout: float) -> str:
    """Acquire an OAuth2 access token using the configured grant flow."""
    if not auth.token_url:
        msg = "OAuth2 auth requires token URL"
        raise RestClientError(msg)
    if not auth.client_id:
        msg = "OAuth2 auth requires client ID"
        raise RestClientError(msg)
    if not auth.client_secret:
        msg = "OAuth2 auth requires client secret"
        raise RestClientError(msg)

    grant_type = auth.grant_type or "client_credentials"
    payload: dict[str, str] = {"grant_type": grant_type}
    if grant_type == "refresh_token":
        if not auth.refresh_token:
            msg = "OAuth2 refresh-token auth requires refresh token"
            raise RestClientError(msg)
        payload["refresh_token"] = auth.refresh_token
    if auth.scope:
        payload["scope"] = auth.scope

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
            response = client.post(
                auth.token_url,
                data=payload,
                headers={"Accept": "application/json"},
                auth=(auth.client_id, auth.client_secret),
            )
    except httpx.RequestError as exc:
        msg_0 = f"OAuth2 token request failed: {exc}"
        raise RestClientError(msg_0) from exc

    if response.status_code != 200:
        body = response.text[:500] if response.text else ""
        msg_0 = f"OAuth2 token request failed: HTTP {response.status_code}: {body}"
        raise RestClientError(msg_0)

    try:
        token_payload = response.json()
    except (AttributeError, ConnectionError, FileNotFoundError, IndexError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
        msg = "OAuth2 token response is not valid JSON"
        raise RestClientError(msg) from exc

    access_token = token_payload.get("access_token")
    if not access_token:
        msg = "OAuth2 token response missing access_token"
        raise RestClientError(msg)

    return str(access_token)


def _apply_auth(
    headers: dict[str, str],
    params: dict[str, str],
    auth: RestAuthConfig | None,
    *,
    timeout: float = 30.0,
) -> None:
    """Apply authentication configuration to request headers."""
    if not auth or auth.type == "none":
        return

    if auth.type == "bearer":
        if not auth.token:
            msg = "Bearer auth requires token"
            raise RestClientError(msg)
        headers["Authorization"] = f"Bearer {auth.token}"
        return

    if auth.type == "basic":
        if not auth.username or not auth.password:
            msg = "Basic auth requires username and password"
            raise RestClientError(msg)
        import base64
        raw = f"{auth.username}:{auth.password}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        return

    if auth.type == "api_key":
        if not auth.api_key_name:
            msg = "API key auth requires parameter name"
            raise RestClientError(msg)
        if not auth.api_key_value:
            msg = "API key auth requires value"
            raise RestClientError(msg)
        if auth.api_key_location == "header":
            headers[auth.api_key_name] = auth.api_key_value
            return
        if auth.api_key_location == "query":
            params[auth.api_key_name] = auth.api_key_value
            return
        msg = "API key auth requires location 'header' or 'query'"
        raise RestClientError(msg)

    if auth.type == "oauth2":
        if not auth.token_url:
            msg = "OAuth2 auth requires token URL"
            raise RestClientError(msg)
        if not auth.client_id:
            msg = "OAuth2 auth requires client ID"
            raise RestClientError(msg)
        if not auth.client_secret:
            msg = "OAuth2 auth requires client secret"
            raise RestClientError(msg)
        access_token = auth.access_token or _fetch_oauth2_access_token(auth, timeout=timeout)
        headers["Authorization"] = f"Bearer {access_token}"
        return

    msg_0 = f"Unsupported auth type: {auth.type}"
    raise RestClientError(msg_0)

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
            msg = "Request cancelled"
            raise RestClientError(msg)

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
            retry=config.retry,
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
