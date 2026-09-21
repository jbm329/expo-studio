"""Models for REST data source services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

RestAuthType = Literal["none", "bearer", "basic", "api_key", "oauth2"]
RestHttpMethod = Literal["GET", "POST"]
RestApiKeyLocation = Literal["header", "query"]
RestOAuth2GrantType = Literal["client_credentials", "refresh_token"]
RestPaginationType = Literal["none", "page_number"]


@dataclass(frozen=True)
class RestPaginationConfig:
    """Pagination configuration for REST requests."""

    type: RestPaginationType = "none"
    page_param: str | None = None
    start_page: int = 1
    page_size_param: str | None = None
    page_size: int | None = None
    max_pages: int | None = None

    def validate(self) -> None:
        """Validate pagination configuration.

        Raises:
            ValueError: If the pagination configuration is invalid.
        """
        if self.type == "none":
            return

        if self.type != "page_number":
            msg = f"Unsupported pagination type: {self.type}"
            raise ValueError(msg)

        if not self.page_param:
            msg = "Page-number pagination requires page parameter name"
            raise ValueError(msg)

        if self.start_page < 1:
            msg = "Page-number pagination start page must be >= 1"
            raise ValueError(msg)

        if self.page_size is not None and self.page_size < 1:
            msg = "Page-number pagination page size must be >= 1"
            raise ValueError(msg)

        if self.page_size is not None and not self.page_size_param:
            msg = "Page-number pagination page size requires parameter name"
            raise ValueError(msg)

        if self.max_pages is not None and self.max_pages < 1:
            msg = "Page-number pagination max pages must be >= 1"
            raise ValueError(msg)


@dataclass(frozen=True)
class RestRetryConfig:
    """Retry policy for REST transport failures and rate-limited responses."""

    max_retries: int = 3
    initial_delay: float = 0.5
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    retry_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)
    respect_retry_after: bool = True

    def validate(self) -> None:
        """Validate retry configuration."""
        if self.max_retries < 0:
            msg = "Retry policy max retries must be >= 0"
            raise ValueError(msg)
        if self.initial_delay < 0:
            msg = "Retry policy initial delay must be >= 0"
            raise ValueError(msg)
        if self.max_delay < 0:
            msg = "Retry policy max delay must be >= 0"
            raise ValueError(msg)
        if self.backoff_factor < 1:
            msg = "Retry policy backoff factor must be >= 1"
            raise ValueError(msg)
        if not self.retry_status_codes:
            msg = "Retry policy must include at least one retryable status code"
            raise ValueError(msg)


@dataclass(frozen=True)
class RestAuthConfig:
    """Authentication configuration for REST requests."""

    type: RestAuthType
    token: str | None = None
    username: str | None = None
    password: str | None = None
    api_key_name: str | None = None
    api_key_value: str | None = None
    api_key_location: RestApiKeyLocation | None = None
    grant_type: RestOAuth2GrantType | None = None
    token_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scope: str | None = None
    refresh_token: str | None = None
    access_token: str | None = None

    def validate(self) -> None:
        """Validate authentication configuration.

        Raises:
            ValueError: If the authentication configuration is invalid.
        """
        if self.type == "none":
            return

        if self.type == "bearer":
            if not self.token:
                msg = "Bearer auth requires token"
                raise ValueError(msg)
            return

        if self.type == "basic":
            if not self.username or not self.password:
                msg = "Basic auth requires username and password"
                raise ValueError(msg)
            return

        if self.type == "api_key":
            if not self.api_key_name:
                msg = "API key auth requires parameter name"
                raise ValueError(msg)
            if not self.api_key_value:
                msg = "API key auth requires value"
                raise ValueError(msg)
            if self.api_key_location not in ("header", "query"):
                msg = "API key auth requires location 'header' or 'query'"
                raise ValueError(msg)
            return

        if self.type == "oauth2":
            if not self.token_url:
                msg = "OAuth2 auth requires token URL"
                raise ValueError(msg)
            if not self.client_id:
                msg = "OAuth2 auth requires client ID"
                raise ValueError(msg)
            if not self.client_secret:
                msg = "OAuth2 auth requires client secret"
                raise ValueError(msg)

            grant_type = self.grant_type or "client_credentials"
            if grant_type == "client_credentials":
                return
            if grant_type == "refresh_token":
                if not self.refresh_token:
                    msg = "OAuth2 refresh-token auth requires refresh token"
                    raise ValueError(msg)
                return
            msg_0 = f"Unsupported OAuth2 grant type: {grant_type}"
            raise ValueError(msg_0)

        msg_0 = f"Unsupported auth type: {self.type}"
        raise ValueError(msg_0)


@dataclass(frozen=True)
class RestRequestConfig:
    """Configuration for a REST API request."""

    name: str
    url: str
    json_body: Mapping[str, object] | None
    method: RestHttpMethod = "GET"

    headers: Mapping[str, str] = field(default_factory=dict)
    query_params: Mapping[str, str] = field(default_factory=dict)

    response_path: str | None = None
    auth: RestAuthConfig | None = None
    pagination: RestPaginationConfig | None = None
    retry: RestRetryConfig | None = None

    def validate(self) -> None:
        """Validate request configuration.

        Raises:
            ValueError: If configuration is invalid.
        """
        if not self.name:
            msg = "REST request name must not be empty"
            raise ValueError(msg)

        if not self.url:
            msg = "REST request URL must not be empty"
            raise ValueError(msg)

        if self.method not in ("GET", "POST"):
            msg_0 = f"Unsupported HTTP method: {self.method}"
            raise ValueError(msg_0)

        if self.method == "POST" and self.json_body is None:
            msg = "POST requests require a JSON body"
            raise ValueError(msg)

        if self.auth is not None:
            self.auth.validate()

        if self.pagination is not None:
            self.pagination.validate()

        if self.retry is not None:
            self.retry.validate()
