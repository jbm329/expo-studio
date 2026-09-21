"""REST connection registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from expo_jbm329.services.rest.models import (
    RestApiKeyLocation,
    RestAuthConfig,
    RestAuthType,
    RestOAuth2GrantType,
    RestRequestConfig,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class RestConnectionEntry:
    """Runtime metadata + request configuration for a REST connection."""

    name: str
    request: RestRequestConfig
    source: Literal["user", "sample"]
    read_only: bool = False
    folder: str | None = None


class RestConnectionRegistry:
    """Runtime registry for REST API connections.

    Aggregates REST connections from:
      - persistent user-defined configurations
      - built-in, read-only sample connections

    This registry is in-memory only and does not handle persistence.
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        self._entries: dict[str, RestConnectionEntry] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(
        self,
        *,
        name: str,
        request: RestRequestConfig,
        source: Literal["user", "sample"],
        read_only: bool = False,
        folder: str | None = None,
    ) -> None:
        """Register a new REST connection."""
        request.validate()

        self._entries[name] = RestConnectionEntry(
            name=name,
            request=request,
            source=source,
            read_only=read_only,
            folder=folder,
        )

    def unregister_user_connections(self) -> None:
        """Remove all user-defined (non-sample) connections from the registry."""
        self._entries = {name: entry for name, entry in self._entries.items() if entry.source != "user"}

    # ------------------------------------------------------------------
    # Bulk loaders
    # ------------------------------------------------------------------
    def reload_user_connections(self, raw: dict[str, dict[str, object]]) -> None:
        """Replace all user connections from a fresh config store read.

        Samples are preserved. Intended to be called after a write to the
        config store so the registry reflects the new state without a full
        restart.
        """
        self.unregister_user_connections()
        self.load_user_connections(raw)

    def load_user_connections(self, raw: dict[str, dict[str, object]]) -> None:
        """Load persistent REST connections from config_store."""
        for name, cfg in raw.items():
            url = cfg.get("url")
            if not isinstance(url, str) or not url.strip():
                continue

            # Invalid or missing HTTP method defaults to GET (safe fallback)
            method = self._normalize_method(cfg.get("method"))

            response_path = cfg.get("response_path")
            if not isinstance(response_path, str) or response_path.strip() in ("", "None"):
                response_path = None

            auth_raw = cfg.get("auth")
            if not isinstance(auth_raw, dict):
                auth_raw = {"type": "none"}

            json_body_raw = cfg.get("json_body")
            json_body = cast("dict[str, object] | None", json_body_raw if isinstance(json_body_raw, dict) else None)
            headers_raw = cfg.get("headers", {})
            headers = {str(k): str(v) for k, v in headers_raw.items()} if isinstance(headers_raw, dict) else {}
            query_params_raw = cfg.get("query_params", {})
            query_params = (
                {str(k): str(v) for k, v in query_params_raw.items()} if isinstance(query_params_raw, dict) else {}
            )

            req = RestRequestConfig(
                name=name,
                url=url,
                method=method,
                json_body=json_body,
                headers=headers,
                query_params=query_params,
                response_path=response_path,
                auth=RestAuthConfig(
                    type=self._normalize_auth_type(auth_raw.get("type")),
                    token=self._optional_str(auth_raw.get("token")),
                    username=self._optional_str(auth_raw.get("username")),
                    password=self._optional_str(auth_raw.get("password")),
                    api_key_name=self._optional_str(auth_raw.get("api_key_name")),
                    api_key_value=self._optional_str(auth_raw.get("api_key_value")),
                    api_key_location=self._normalize_api_key_location(auth_raw.get("api_key_location")),
                    grant_type=self._normalize_oauth2_grant_type(auth_raw.get("grant_type")),
                    token_url=self._optional_str(auth_raw.get("token_url")),
                    client_id=self._optional_str(auth_raw.get("client_id")),
                    client_secret=self._optional_str(auth_raw.get("client_secret")),
                    scope=self._optional_str(auth_raw.get("scope")),
                    refresh_token=self._optional_str(auth_raw.get("refresh_token")),
                    access_token=self._optional_str(auth_raw.get("access_token")),
                ),
            )
            self.register(
                name=name,
                request=req,
                source="user",
                read_only=False,
                folder=None,
            )

    def load_samples(self, samples: Iterable[RestRequestConfig]) -> None:
        """Load built-in read-only sample connections."""
        for req in samples:
            self.register(
                name=req.name,
                request=req,
                source="sample",
                read_only=True,
                folder="samples",
            )

    # ------------------------------------------------------------------
    # Query API (used by UI)
    # ------------------------------------------------------------------
    def list_all(self) -> list[RestConnectionEntry]:
        """Retrieve all registered connections."""
        return list(self._entries.values())

    def get(self, name: str) -> RestConnectionEntry | None:
        """Retrieve a connection by name."""
        return self._entries.get(name)

    def exists(self, name: str) -> bool:
        """Check if a connection exists."""
        return name in self._entries

    # ------------------------------------------------------------------
    # Capability checks
    # ------------------------------------------------------------------
    def can_edit(self, name: str) -> bool:
        """Check if a connection can be edited."""
        e = self._entries.get(name)
        return bool(e and not e.read_only)

    def can_delete(self, name: str) -> bool:
        """Check if a connection can be deleted."""
        e = self._entries.get(name)
        return bool(e and not e.read_only)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _optional_str(value: object) -> str | None:
        """Return a stripped string value or None."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_auth_type(value: object) -> RestAuthType:
        """Normalize persisted auth type values."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            match normalized:
                case "none":
                    return "none"
                case "bearer":
                    return "bearer"
                case "basic":
                    return "basic"
                case "api_key":
                    return "api_key"
                case "oauth2":
                    return "oauth2"
                case _:
                    pass
        return "none"

    @staticmethod
    def _normalize_api_key_location(value: object) -> RestApiKeyLocation | None:
        """Normalize persisted API-key location values."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            match normalized:
                case "header":
                    return "header"
                case "query":
                    return "query"
                case _:
                    pass
        return None

    @staticmethod
    def _normalize_oauth2_grant_type(value: object) -> RestOAuth2GrantType | None:
        """Normalize persisted OAuth2 grant type values."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            match normalized:
                case "client_credentials":
                    return "client_credentials"
                case "refresh_token":
                    return "refresh_token"
                case _:
                    pass
        return None

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_method(val: object) -> Literal["GET", "POST"]:
        """Normalize HTTP method value.

        Defaults to GET if value is missing or invalid.
        """
        if isinstance(val, str):
            v = val.strip().upper()
            match v:
                case "GET":
                    return "GET"
                case "POST":
                    return "POST"
                case _:
                    pass
        return "GET"


# ----------------------------------------------------------------------
# Singleton instance
# ----------------------------------------------------------------------
rest_registry = RestConnectionRegistry()
