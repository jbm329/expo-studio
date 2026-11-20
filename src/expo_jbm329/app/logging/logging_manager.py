"""Logging infrastructure for the Expo application.

This module provides centralized logging configuration and management,
including file and console handlers, custom filters, and logger instances
for different application components.
"""

from __future__ import annotations

import logging
import os
import sys
from io import TextIOWrapper
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING, override

from expo_jbm329.app.logging.console_stream import open_parent_console
from expo_jbm329.app.settings.config_store import DEFAULT_LOG_STDOUT_HANDLER_CONFIG, read_log_config
from expo_jbm329.app.settings.json_types import JsonObject, int_value, object_or_empty, string_value
from expo_jbm329.utils.path_manager import get_log_path

if TYPE_CHECKING:
    from typing import TextIO

    _TextStreamHandler = logging.StreamHandler[TextIO]
else:
    _TextStreamHandler = logging.StreamHandler

BUILTIN_FORMATTERS = {
    "default": {
        "format": "%(levelname)s %(asctime)s: %(message)s",
        "datefmt": "%Y-%m-%d %H:%M:%S",
    },
    "verbose": {
        "format": ("%(levelname)s %(asctime)s %(filename)s line %(lineno)d function %(funcName)s:\n >%(message)s"),
        "datefmt": "%Y-%m-%d %H:%M:%S%z",
    },
}


def _is_frozen() -> bool:
    """Checks if the application is running from a frozen executable.

    Returns:
        True if the application is frozen (e.g., PyInstaller), False otherwise.
    """
    return bool(getattr(sys, "frozen", False))


class ThirdPartyMinLevelFilter(logging.Filter):
    """A logging filter that enforces minimum levels for non-app loggers.

    This filter allows all loggers with names starting with specified app prefixes
    to pass through, while enforcing a minimum log level for all other loggers.
    """

    def __init__(self, min_level: int, app_prefixes: tuple[str, ...]) -> None:
        """Initializes the filter.

        Args:
            min_level: The minimum log level for non-app loggers.
            app_prefixes: Tuple of logger name prefixes that are exempt from the min level.
        """
        super().__init__()
        self.min_level = min_level
        self.app_prefixes = app_prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        """Filters log records based on logger name and level.

        Args:
            record: The log record to filter.

        Returns:
            True if the record should be logged, False otherwise.
        """
        name = record.name or ""
        for p in self.app_prefixes:
            if name == p or name.startswith(p + "."):
                return True
        return record.levelno >= self.min_level


class _OwnedStreamHandler(_TextStreamHandler):
    """Close the text stream opened specifically for Windows log output."""

    @override
    def emit(self, record: logging.LogRecord) -> None:
        """Ignore a record already dispatched to this handler before reload."""
        if not self.stream.closed:
            super().emit(record)

    @override
    def close(self) -> None:
        """Close the owned stream while holding the handler lock."""
        self.acquire()
        try:
            self.stream.close()
        finally:
            self.release()
            super().close()


class LoggingManager:
    """Manages logging configuration and provides logger instances.

    This class handles the setup of logging infrastructure based on configuration,
    including handlers, filters, and log levels. It provides pre-configured logger
    instances for different application components.

    Attributes:
        APP_PREFIXES: Tuple of logger name prefixes considered app loggers.
        ui_logger: Logger for UI-related messages.
        service_logger: Logger for service layer messages.
        jobs_logger: Logger for job-related messages.
        db_logger: Logger for database-related messages.
        system_logger: Logger for system-level messages.
    """

    __slots__ = (
        "_console_log",
        "_owned_handlers",
        "db_logger",
        "jobs_logger",
        "service_logger",
        "system_logger",
        "ui_logger",
    )

    APP_PREFIXES = ("applogger",)

    def __init__(self, *, console_log: bool = False) -> None:
        """Initializes the LoggingManager with pre-configured logger instances."""
        self._console_log = console_log
        self._owned_handlers: list[logging.Handler] = []
        self.ui_logger: logging.Logger = logging.getLogger("applogger.ui")
        self.service_logger: logging.Logger = logging.getLogger("applogger.service")
        self.jobs_logger: logging.Logger = logging.getLogger("applogger.jobs")
        self.db_logger: logging.Logger = logging.getLogger("applogger.db")
        self.system_logger: logging.Logger = logging.getLogger("applogger")

    # =====================================================================
    # Bootstrap
    # =====================================================================
    def setup(self) -> None:
        """Sets up the logging infrastructure based on configuration.

        Reads the logging configuration, configures handlers, filters, and log levels,
        and initializes the logger instances. Call at startup and when applying
        new logging settings.
        """
        cfg = read_log_config()
        root = logging.getLogger()

        # Root level
        root.setLevel(self._to_level(cfg.get("logger_level", "INFO")))

        # Remove old handlers
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in self._owned_handlers:
            h.close()
        self._owned_handlers.clear()

        handlers_cfg = object_or_empty(cfg.get("handlers"))
        frozen = _is_frozen()
        frozen_console_platform = frozen and sys.platform in {"win32", "linux"}
        fallback = logging.NullHandler()
        if frozen_console_platform:
            # Prevent logging.lastResort from writing to stderr without a configured sink.
            root.addHandler(fallback)

        # Wildcard filter
        third_party_level = self._to_level(cfg.get("third_party_log_level", "WARNING"))
        tp_filter = ThirdPartyMinLevelFilter(third_party_level, self.APP_PREFIXES)

        # File handler
        if "file" in handlers_cfg:
            try:
                h = self._create_file_handler(cfg)
                h.addFilter(tp_filter)
                root.addHandler(h)
                self._owned_handlers.append(h)
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
                logging.getLogger("applogger").exception("Failed to init file handler")

        # The legacy configuration key is "stdout", but records go to stderr.
        if (frozen_console_platform and self._console_log) or (not frozen and "stdout" in handlers_cfg):
            try:
                console_handler = self._create_console_handler(cfg, attach=frozen and sys.platform == "win32")
            except (OSError, ValueError):
                self.system_logger.exception("LoggingManager: failed to initialize console output")
            else:
                if console_handler is not None:
                    console_handler.addFilter(tp_filter)
                    root.addHandler(console_handler)
                    self._owned_handlers.append(console_handler)

        if self._owned_handlers and frozen_console_platform:
            root.removeHandler(fallback)

        # Per-namespace overrides
        for lname, spec_value in object_or_empty(cfg.get("loggers")).items():
            spec = object_or_empty(spec_value)
            lg = logging.getLogger(lname)
            lg.setLevel(self._to_level(spec.get("level", "INFO")))
            lg.propagate = bool(spec.get("propagate", True))

        self.system_logger.info("Logging initialized.")

    # =====================================================================
    # Handler builders
    # =====================================================================
    def _create_file_handler(self, cfg: JsonObject) -> logging.Handler:
        """Creates a rotating file handler based on configuration.

        Args:
            cfg: The full configuration dict.

        Returns:
            A configured RotatingFileHandler instance.
        """
        params = self._subcfg(cfg, "handlers", "file")

        level = self._to_level(params.get("level", "INFO"))
        fmt = self._formatter(string_value(params.get("formatter"), "default"))
        max_bytes = self._to_int(params.get("maxBytes"), 5_000_000)
        backup = self._to_int(params.get("backupCount"), 3)

        h = RotatingFileHandler(
            get_log_path(),
            maxBytes=max_bytes,
            backupCount=backup,
            encoding="utf-8",
        )
        h.setLevel(level)
        h.setFormatter(fmt)
        return h

    def _create_console_handler(self, cfg: JsonObject, *, attach: bool) -> logging.Handler | None:
        params = DEFAULT_LOG_STDOUT_HANDLER_CONFIG | self._subcfg(cfg, "handlers", "stdout")
        level = self._to_level(params["level"])
        fmt = self._formatter(string_value(params["formatter"], "default"))

        stream = sys.stderr
        h: logging.StreamHandler[TextIO]
        if stream is None:
            if not attach:
                return None
            stream = open_parent_console()
            if stream is None:
                return None
            h = _OwnedStreamHandler(stream)
        elif stream.closed or not stream.writable():
            return None
        elif attach and isinstance(stream, TextIOWrapper) and not stream.isatty():
            # Windows redirects can default to an ANSI code page. Leave stderr
            # and its descriptor alone while writing the log records as UTF-8.
            h = _OwnedStreamHandler(
                os.fdopen(stream.fileno(), "w", encoding="utf-8", errors="backslashreplace", closefd=False)
            )
        else:
            h = logging.StreamHandler(stream)
        h.setLevel(level)
        h.setFormatter(fmt)
        return h

    # =====================================================================
    # Helpers
    # =====================================================================
    def _formatter(self, name: str) -> logging.Formatter:
        """Returns a logging formatter based on the given name.

        Args:
            name: The name of the formatter (e.g., "default", "verbose").

        Returns:
            A logging.Formatter instance.
        """
        tpl = BUILTIN_FORMATTERS.get(name) or BUILTIN_FORMATTERS["default"]
        return logging.Formatter(tpl["format"], tpl["datefmt"])

    @staticmethod
    def _to_level(v: object) -> int:
        """Converts a value to a logging level integer.

        Args:
            v: The value to convert (int or str).

        Returns:
            The corresponding logging level integer, or INFO if invalid.
        """
        if isinstance(v, int):
            return v
        try:
            level: object = getattr(logging, str(v).upper())
            return level if isinstance(level, int) else logging.INFO
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
            return logging.INFO

    @staticmethod
    def _to_int(v: object, default: int) -> int:
        """Converts a value to an integer.

        Args:
            v: The value to convert.
            default: The default value if conversion fails.

        Returns:
            The converted integer value, or default if conversion fails.
        """
        try:
            return int_value(v, default)
        except TypeError:
            return default

    @staticmethod
    def _subcfg(cfg: JsonObject, *keys: str) -> JsonObject:
        """Retrieves a sub-configuration from a nested dict.

        Args:
            cfg: The full configuration dict.
            *keys: The keys to traverse in the configuration dict.

        Returns:
            The sub-configuration dict at the specified keys, or an empty dict if not found.
        """
        cur: object = cfg
        for k in keys:
            if not isinstance(cur, dict):
                return {}
            cur = cur.get(k, {})
        return object_or_empty(cur)
