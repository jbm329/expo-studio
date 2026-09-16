"""Models for REST data source services."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

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
            raise ValueError(f"Unsupported pagination type: {self.type}")

        if not self.page_param:
            raise ValueError("Page-number pagination requires page parameter name")

        if self.start_page < 1:
            raise ValueError("Page-number pagination start page must be >= 1")

        if self.page_size is not None and self.page_size < 1:
            raise ValueError("Page-number pagination page size must be >= 1")

        if self.page_size is not None and not self.page_size_param:
            raise ValueError("Page-number pagination page size requires parameter name")

        if self.max_pages is not None and self.max_pages < 1:
            raise ValueError("Page-number pagination max pages must be >= 1")


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
                raise ValueError("Bearer auth requires token")
            return

        if self.type == "basic":
            if not self.username or not self.password:
                raise ValueError("Basic auth requires username and password")
            return

        if self.type == "api_key":
            if not self.api_key_name:
                raise ValueError("API key auth requires parameter name")
            if not self.api_key_value:
                raise ValueError("API key auth requires value")
            if self.api_key_location not in ("header", "query"):
                raise ValueError("API key auth requires location 'header' or 'query'")
            return

        if self.type == "oauth2":
            if not self.token_url:
                raise ValueError("OAuth2 auth requires token URL")
            if not self.client_id:
                raise ValueError("OAuth2 auth requires client ID")
            if not self.client_secret:
                raise ValueError("OAuth2 auth requires client secret")

            grant_type = self.grant_type or "client_credentials"
            if grant_type == "client_credentials":
                return
            if grant_type == "refresh_token":
                if not self.refresh_token:
                    raise ValueError("OAuth2 refresh-token auth requires refresh token")
                return
            raise ValueError(f"Unsupported OAuth2 grant type: {grant_type}")

        raise ValueError(f"Unsupported auth type: {self.type}")



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

    def validate(self) -> None:
        """Validate request configuration.

        Raises:
            ValueError: If configuration is invalid.
        """
        if not self.name:
            raise ValueError("REST request name must not be empty")

        if not self.url:
            raise ValueError("REST request URL must not be empty")

        if self.method not in ("GET", "POST"):
            raise ValueError(f"Unsupported HTTP method: {self.method}")

        if self.method == "POST" and self.json_body is None:
            raise ValueError("POST requests require a JSON body")

        if self.response_path is not None and not isinstance(self.response_path, str):
            raise ValueError("REST response path must be a string or None")

        if self.auth is not None:
            self.auth.validate()

        if self.pagination is not None:
            self.pagination.validate()
