"""Models for REST data source services."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

RestAuthType = Literal["none", "bearer", "basic", "api_key"]
RestHttpMethod = Literal["GET", "POST"]
RestApiKeyLocation = Literal["header", "query"]


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
