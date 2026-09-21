"""Connection controller for managing database connections in the Expo application.

This module provides the ConnectionController class, which handles connection
selection, schema loading, and related UI state management. It includes several
Protocol definitions for type-safe callback definitions.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


class ConnectionController:
    """Controller for managing database connections in the Expo application.

    This class handles connection selection, schema loading, and UI state
    management. It maintains the connection dropdown widget in the toolbar,
    responds to selection changes, and coordinates with other services to
    load schemas and update UI state.

    All dependencies are injected as callbacks, ensuring the controller
    remains decoupled from ExpoStudio implementation details.
    """

    __slots__ = (
        "__weakref__",
        "_active_connection",
        "_clear_schema_cache",
        "_close_db",
        "_get_connection_names",
        "_load_schema",
        "_logger",
        "_on_active_connection_changed",
        "_on_connection_list_changed",
    )
    """
    Note:
    This controller uses explicit two-phase wiring.

    Certain callbacks (schema loading, schema clearing) are bound
    after both ConnectionController and SchemaController are created.
    This is intentional and required to avoid circular construction
    dependencies in the Qt workbench.
    """

    def __init__(
        self,
        *,
        get_connection_names: Callable[[], Iterable[str]],
        clear_schema_cache: Callable[[str], None],
        close_db_connection: Callable[[str], None],
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the ConnectionController.

        Args:
            get_connection_names: Callback to retrieve available connection names.
            clear_schema_cache: Callback to clear the schema cache.
            close_db_connection: Callback to close database connections.
            logger: Optional logger instance.
        """
        self._get_connection_names = get_connection_names
        self._clear_schema_cache = clear_schema_cache
        self._close_db = close_db_connection
        self._logger = logger or logging.getLogger("applogger.ui")

        self._active_connection: str | None = None

        # Wired later (explicitly)
        self._load_schema: Callable[[str, bool], None] | None = None
        self._on_connection_list_changed: list[Callable[[], None]] = []
        self._on_active_connection_changed: list[Callable[[str | None, str | None], None]] = []

    # ==================================================================
    # Public connection API
    # ==================================================================

    @property
    def active_connection(self) -> str | None:
        """Return the active connection name, if any."""
        return self._active_connection

    def connect(self, name: str) -> None:
        """Connect to a database connection by name."""
        if not name:
            return
        if self._load_schema is None:
            msg = "ConnectionController not wired: load_schema is missing"
            raise RuntimeError(msg)

        if self._active_connection == name:
            self._logger.debug("ConnectionController: already connected (%s)", name)
            return

        self._logger.info("ConnectionController: connecting to %s", name)

        previous = self._active_connection
        self._active_connection = name

        try:
            self._load_schema(name, False)
        except (
            AttributeError,
            ConnectionError,
            FileNotFoundError,
            IndexError,
            KeyError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            self._logger.debug("ConnectionController: connection failed, reverting state for %s", name)
            self._active_connection = previous
            raise

        for cb in self._on_active_connection_changed:
            try:
                cb(previous, name)
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._logger.exception("ConnectionController: callback failed")

    def disconnect(self, name: str | None = None) -> None:
        """Disconnect a specific database connection."""
        if name is None:
            name = self._active_connection

        if not name:
            return

        self._logger.info("ConnectionController: disconnecting from %s", name)

        # Clear schema cache
        with contextlib.suppress(Exception):
            self._clear_schema_cache(name)
            self._close_db(name)

        # If the disconnected connection was active, clear active_connection
        if self._active_connection == name:
            previous = self._active_connection
            self._active_connection = None

            for cb in self._on_active_connection_changed:
                try:
                    cb(previous, None)
                except (
                    AttributeError,
                    ConnectionError,
                    FileNotFoundError,
                    IndexError,
                    KeyError,
                    LookupError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ):
                    self._logger.exception("ConnectionController: callback failed")

        else:
            # Non-active disconnect: do NOT emit active_connection_changed
            self._logger.debug(
                "ConnectionController: disconnected non-active connection %s (active=%s)",
                name,
                self._active_connection,
            )

    def get_connection_names(self) -> list[str]:
        """Return available connection names."""
        return list(self._get_connection_names())

    def on_connection_list_changed(self, callback: Callable[[], None]) -> None:
        """Register a callback to be invoked when connection state changes."""
        self._on_connection_list_changed.append(callback)

    def on_active_connection_changed(self, callback: Callable[[str | None, str | None], None]) -> None:
        """Register a callback invoked when the active connection changes.

        Callback receives (previous, current).
        """
        self._on_active_connection_changed.append(callback)

    def bind_schema_loader(self, loader: Callable[[str, bool], None]) -> None:
        """Bind schema loading callback."""
        self._load_schema = loader

    # ==================================================================
    # Internal helpers
    # ==================================================================
    def _emit(self, callbacks: list[Callable[[], None]]) -> None:
        for cb in callbacks:
            try:
                cb()
            except (
                AttributeError,
                ConnectionError,
                FileNotFoundError,
                IndexError,
                KeyError,
                LookupError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._logger.exception("ConnectionController callback failed")
