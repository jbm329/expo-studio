"""Central settings service with publisher-subscriber support.

This module provides the SettingsService class, which manages application
settings, allows components to subscribe to changes, and handles reloading
from configuration stores.
"""
from __future__ import annotations

import contextlib
import copy
import logging
from collections.abc import Callable
from threading import RLock

from expo_jbm329.app.settings.config_store import load_settings

Subscriber = Callable[[dict], None]
Dispatcher = Callable[[Callable[[], None]], None]


class SettingsService:
    """Central settings hub with publisher-subscriber support.

    Responsibilities:
      - Holds current settings in memory.
      - Allows subscribers to get notified when settings change.
      - Supports reloading from config_store.load_settings().
      - Optional dispatcher to marshal notifications to UI thread.

    Attributes:
        _settings: Current settings dictionary.
        _subs: List of subscribed callables.
        _dispatcher: Optional callable to marshal notifications.
    """

    def __init__(
        self,
        *,
        initial_settings: dict | None = None,
        dispatcher: Dispatcher | None = None,
        loader: Callable[[], dict] = load_settings,
        logger: logging.Logger | None = None,
    ):
        """Initialize the SettingsService.

        Args:
            initial_settings: Optional initial settings dictionary.
            dispatcher: Optional callable to marshal notifications.
            loader: Callable to load settings from disk.
            logger: Optional logger instance.
        """
        self._lock = RLock()
        self._loader = loader
        self._dispatcher = dispatcher
        self._subs: list[Subscriber] = []
        self._settings: dict = initial_settings if initial_settings is not None else self._safe_load()
        self._logger = logger or logging.getLogger("applogger.service")
        self._logger.debug("SettingsService initialized.")

    # -----------------------------
    # Public API
    # -----------------------------
    def get(self) -> dict:
        """Return a deep copy of current settings."""
        with self._lock:
            return copy.deepcopy(self._settings)

    def subscribe(self, callback: Subscriber, *, immediate: bool = False) -> None:
        """Register a subscriber.

        If immediate=True, the subscriber is invoked once with the current
        settings (via dispatcher if provided).
        """
        if not callable(callback):
            msg = "SettingsService.subscribe requires a callable"
            raise TypeError(msg)

        with self._lock:
            if callback not in self._subs:
                self._subs.append(callback)

            if immediate:
                self._notify_one(callback, copy.deepcopy(self._settings))

    def unsubscribe(self, callback: Subscriber) -> None:
        """Remove a previously registered subscriber."""
        with self._lock, contextlib.suppress(ValueError):
            self._subs.remove(callback)

    def reload(self) -> dict:
        """Reload settings from disk and notify subscribers.

        Returns the new settings dict.
        """
        new_s = self._safe_load()
        with self._lock:
            self._settings = new_s
            snapshot = copy.deepcopy(self._settings)

        self._logger.info("Settings reloaded.")
        self._notify_all(snapshot)
        return snapshot

    def set_and_notify(self, new_settings: dict) -> None:
        """Force-set settings and notify subscribers.

        Typically you don't need this because SettingsEditor writes to disk and
        you can call reload().
        """
        if not isinstance(new_settings, dict):
            msg = "new_settings must be a dict"
            raise TypeError(msg)

        with self._lock:
            self._settings = copy.deepcopy(new_settings)
            snapshot = copy.deepcopy(self._settings)

        self._logger.info("Settings updated (set_and_notify).")
        self._notify_all(snapshot)

    # -----------------------------
    # Internals
    # -----------------------------
    def _safe_load(self) -> dict:
        try:
            s = self._loader()
            if not isinstance(s, dict):
                msg = "load_settings returned non-dict"
                raise ValueError(msg)
            return s
        except Exception as e:
            self._logger.exception("SettingsService: failed to load settings; falling back to empty dict. Error: %s", e)
            return {}

    def _notify_all(self, s: dict) -> None:
        subs_snapshot: list[Subscriber]
        with self._lock:
            subs_snapshot = list(self._subs)

        for cb in subs_snapshot:
            self._notify_one(cb, s)

    def _notify_one(self, cb: Subscriber, s: dict) -> None:
        def _invoke():
            try:
                cb(copy.deepcopy(s))
            except Exception:
                self._logger.exception("SettingsService subscriber raised.")

        if self._dispatcher is not None:
            # Marshal to UI thread (or provided dispatcher)
            try:
                self._dispatcher(_invoke)
            except Exception:
                self._logger.exception("SettingsService dispatcher failed; invoking directly.")
                _invoke()
        else:
            _invoke()
