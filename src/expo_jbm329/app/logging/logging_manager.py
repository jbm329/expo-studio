"""Logging infrastructure for the Expo application.

This module provides centralized logging configuration and management,
including file and console handlers, custom filters, and logger instances
for different application components.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from expo_jbm329.app.settings.config_store import read_log_config
from expo_jbm329.utils.path_manager import get_log_path

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
        "db_logger",
        "jobs_logger",
        "service_logger",
        "system_logger",
        "ui_logger",
    )

    APP_PREFIXES = ("applogger",)

    def __init__(self) -> None:
        """Initializes the LoggingManager with pre-configured logger instances."""
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
        and initializes the logger instances. This method should be called once
        during application startup.
        """
        cfg = read_log_config() or {}
        root = logging.getLogger()

        # Root level
        root.setLevel(self._to_level(cfg.get("logger_level", "INFO")))

        # Remove old handlers
        for h in list(root.handlers):
            root.removeHandler(h)

        handlers_cfg = cfg.get("handlers", {}) or {}

        # Wildcard filter
        third_party_level = self._to_level(cfg.get("third_party_log_level", "WARNING"))
        tp_filter = ThirdPartyMinLevelFilter(third_party_level, self.APP_PREFIXES)

        # File handler
        if "file" in handlers_cfg:
            try:
                h = self._create_file_handler(cfg)
                h.addFilter(tp_filter)
                root.addHandler(h)
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

        # Stdout handler
        if "stdout" in handlers_cfg and not _is_frozen():
            try:
                h = self._create_stdout_handler(cfg)
                h.addFilter(tp_filter)
                root.addHandler(h)
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
                logging.getLogger("applogger").exception("Failed to init stdout handler")

        # Per-namespace overrides
        for lname, spec in (cfg.get("loggers", {}) or {}).items():
            if not isinstance(lname, str):
                continue
            lg = logging.getLogger(lname)
            lg.setLevel(self._to_level(spec.get("level", "INFO")))
            lg.propagate = bool(spec.get("propagate", True))

        self.system_logger.info("Logging initialized.")

    # =====================================================================
    # Handler builders
    # =====================================================================
    def _create_file_handler(self, cfg: dict) -> logging.Handler:
        """Creates a rotating file handler based on configuration.

        Args:
            cfg: The full configuration dict.

        Returns:
            A configured RotatingFileHandler instance.
        """
        params = self._subcfg(cfg, "handlers", "file")

        level = self._to_level(params.get("level", "INFO"))
        fmt = self._formatter(params.get("formatter", "default"))
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

    def _create_stdout_handler(self, cfg: dict) -> logging.Handler:
        """Creates a stdout stream handler based on configuration.

        Args:
            cfg: The full configuration dict.

        Returns:
            A configured StreamHandler instance.
        """
        params = self._subcfg(cfg, "handlers", "stdout")

        level = self._to_level(params.get("level", "WARNING"))
        fmt = self._formatter(params.get("formatter", "default"))

        h = logging.StreamHandler()
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
            return getattr(logging, str(v).upper())
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
            return int(v)
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
            return default

    @staticmethod
    def _subcfg(cfg: dict, *keys: str) -> dict:
        """Retrieves a sub-configuration from a nested dict.

        Args:
            cfg: The full configuration dict.
            *keys: The keys to traverse in the configuration dict.

        Returns:
            The sub-configuration dict at the specified keys, or an empty dict if not found.
        """
        cur = cfg
        for k in keys:
            if not isinstance(cur, dict):
                return {}
            cur = cur.get(k, {})
        return cur if isinstance(cur, dict) else {}
