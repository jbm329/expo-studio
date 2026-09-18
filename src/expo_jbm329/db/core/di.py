"""Dependency injection container for database drivers and dialects.

This module provides a lightweight service registry for managing and
instantiating database-specific driver and dialect components. It allows
for decoupling the database core from specific implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from .interfaces import DialectProtocol, DriverProtocol


class ServiceRegistry:
    """Lightweight DI container for DB drivers and dialects.

    Attributes:
        _drivers (dict[str, Callable[[], DriverProtocol]]): Mapping of protocol keys
            to factory functions returning a DriverProtocol.
        _dialects (dict[str, Callable[[], DialectProtocol]]): Mapping of engine keys
            to factory functions returning a DialectProtocol.
    """

    def __init__(self) -> None:
        """Initialize the ServiceRegistry."""
        # Mapping of protocol key -> factory function returning a DriverProtocol
        self._drivers: dict[str, Callable[[], DriverProtocol]] = {}
        # Mapping of engine key -> factory function returning a DialectProtocol
        self._dialects: dict[str, Callable[[], DialectProtocol]] = {}

    def register_driver(self, protocol: str, factory: Callable[[], DriverProtocol]) -> None:
        """Register a driver factory by protocol key.

        Args:
            protocol (str): The protocol key, e.g., 'odbc', 'psycopg2', 'pymysql'.
            factory (Callable[[], DriverProtocol]): A factory function that returns
                a DriverProtocol instance.

        Raises:
            ValueError: If protocol is empty or factory is not callable.
        """
        if not protocol or not callable(factory):
            msg = "Invalid driver registration (protocol or factory)."
            raise ValueError(msg)
        self._drivers[protocol] = factory

    def register_dialect(self, engine: str, factory: Callable[[], DialectProtocol]) -> None:
        """Register a dialect factory by engine key.

        Args:
            engine (str): The engine key, e.g., 'mssql', 'postgresql', 'mysql'.
            factory (Callable[[], DialectProtocol]): A factory function that returns
                a DialectProtocol instance.

        Raises:
            ValueError: If engine is empty or factory is not callable.
        """
        if not engine or not callable(factory):
            msg = "Invalid dialect registration (engine or factory)."
            raise ValueError(msg)
        self._dialects[engine] = factory

    def create_driver(self, protocol: str) -> DriverProtocol:
        """Create a new driver instance for the given protocol key.

        Args:
            protocol (str): The protocol key to create a driver for.

        Returns:
            DriverProtocol: An instance of the registered driver.

        Raises:
            KeyError: If no driver is registered for the given protocol key.
        """
        try:
            factory = self._drivers[protocol]
        except KeyError as e:
            msg = f"No driver registered for protocol='{protocol}'."
            raise KeyError(msg) from e
        return factory()

    def create_dialect(self, engine: str) -> DialectProtocol:
        """Create a new dialect instance for the given engine key.

        Args:
            engine (str): The engine key to create a dialect for.

        Returns:
            DialectProtocol: An instance of the registered dialect.

        Raises:
            KeyError: If no dialect is registered for the given engine key.
        """
        try:
            factory = self._dialects[engine]
        except KeyError as e:
            msg = f"No dialect registered for engine='{engine}'."
            raise KeyError(msg) from e
        return factory()
