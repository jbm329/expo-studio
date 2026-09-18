"""REST connection registry."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from expo_jbm329.services.rest.models import RestAuthConfig, RestRequestConfig


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
        self._entries = {
            name: entry for name, entry in self._entries.items() if entry.source != "user"
        }

    # ------------------------------------------------------------------
    # Bulk loaders
    # ------------------------------------------------------------------
    def reload_user_connections(self, raw: dict[str, dict]) -> None:
        """Replace all user connections from a fresh config store read.

        Samples are preserved. Intended to be called after a write to the
        config store so the registry reflects the new state without a full
        restart.
        """
        self.unregister_user_connections()
        self.load_user_connections(raw)

    def load_user_connections(self, raw: dict[str, dict]) -> None:
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

            req = RestRequestConfig(
                name=name,
                url=url,
                method=method,
                json_body=cfg.get("json_body"),
                headers=cfg.get("headers", {}),
                query_params=cfg.get("query_params", {}),
                response_path=response_path,
                auth=RestAuthConfig(**auth_raw),
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
    def _normalize_method(val: object) -> Literal["GET", "POST"]:
        """Normalize HTTP method value.

        Defaults to GET if value is missing or invalid.
        """
        if isinstance(val, str):
            v = val.strip().upper()
            if v in ("GET", "POST"):
                return v
        return "GET"


# ----------------------------------------------------------------------
# Singleton instance
# ----------------------------------------------------------------------
rest_registry = RestConnectionRegistry()
