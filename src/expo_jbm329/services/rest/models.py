"""Models for REST data source services."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class RestAuthConfig:
    """Authentication configuration for REST requests."""

    type: str  # e.g. "none", "bearer", "basic"
    token: str | None = None
    username: str | None = None
    password: str | None = None


@dataclass(frozen=True)
class RestRequestConfig:
    """Configuration for a REST API request."""

    name: str
    url: str
    json_body: Mapping[str, object] | None
    method: Literal["GET", "POST"] = "GET"

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
